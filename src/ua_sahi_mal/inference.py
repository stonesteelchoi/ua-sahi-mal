from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List

import numpy as np
from PIL import Image
from sahi import AutoDetectionModel
from sahi.postprocess.combine import GreedyNMMPostprocess
from sahi.predict import get_prediction
from sahi.prediction import PredictionResult
from sahi.slicing import get_slice_bboxes

from ua_sahi_mal.coarse import combine_probability_entropy, run_dense_coarse_pass
from ua_sahi_mal.config import PredictConfig
from ua_sahi_mal.routing import TileSelection, build_candidates, build_low_routing_map, select_tiles
from ua_sahi_mal.upsampling import RoutingUpsampler, pad_image_to_multiple


@dataclass(frozen=True)
class SelectiveSahiResult:
    prediction_result: PredictionResult
    low_routing_map: np.ndarray
    routing_map: np.ndarray
    low_probability_map: np.ndarray | None
    low_entropy_map: np.ndarray | None
    selection: TileSelection
    upsampler_name: str
    coarse_mode: str
    durations: Dict[str, float]


def load_detection_model(config: PredictConfig, device: str):
    from ua_sahi_mal.offline import enforce_offline_network

    enforce_offline_network()
    return AutoDetectionModel.from_pretrained(
        model_type="ultralytics",
        model_path=config.model,
        confidence_threshold=config.confidence,
        device=device,
        image_size=config.image_size,
    )


def _prediction_score(prediction: object) -> float:
    score = getattr(prediction, "score", 0.0)
    return float(getattr(score, "value", score))


def run_selective_sahi(
    image: Image.Image,
    detection_model,
    upsampler: RoutingUpsampler,
    config: PredictConfig,
) -> SelectiveSahiResult:
    config.validate()
    durations: Dict[str, float] = {}
    image = image.convert("RGB")
    image_width, image_height = image.size

    padded = pad_image_to_multiple(image, config.route_scale)
    low_shape = (
        padded.padded_height // config.route_scale,
        padded.padded_width // config.route_scale,
    )
    low_probability_map: np.ndarray | None = None
    low_entropy_map: np.ndarray | None = None
    started = time.perf_counter()
    if config.coarse_mode == "dense":
        dense = run_dense_coarse_pass(
            image=image,
            detection_model=detection_model,
            confidence_threshold=config.route_confidence,
            output_shape=low_shape,
        )
        routing_prediction = dense.prediction_result
        routing_predictions = routing_prediction.object_prediction_list
        low_probability_map = dense.probability_map
        low_entropy_map = dense.entropy_map
        low_routing_map = combine_probability_entropy(
            low_probability_map,
            low_entropy_map,
            probability_weight=config.probability_weight,
            entropy_weight=config.entropy_weight,
        )
    else:
        routing_prediction = get_prediction(
            image=image,
            detection_model=detection_model,
            confidence_threshold=config.route_confidence,
            verbose=0,
        )
        routing_predictions = routing_prediction.object_prediction_list
        low_routing_map = build_low_routing_map(
            padded_image=padded.image,
            predictions=routing_predictions,
            route_scale=config.route_scale,
            box_weight=config.box_weight,
            texture_weight=config.texture_weight,
        )
    durations["full_image_prediction"] = time.perf_counter() - started

    started = time.perf_counter()
    upsampled_padded = upsampler.upsample(padded.image, low_routing_map)
    routing_map = padded.crop_map(upsampled_padded)
    durations["routing_map"] = time.perf_counter() - started

    started = time.perf_counter()
    tile_bboxes = get_slice_bboxes(
        image_height=image_height,
        image_width=image_width,
        slice_height=config.slice_height,
        slice_width=config.slice_width,
        overlap_height_ratio=config.overlap,
        overlap_width_ratio=config.overlap,
        auto_slice_resolution=False,
    )
    candidates = build_candidates(
        route_map=routing_map,
        tile_bboxes=tile_bboxes,
        predictions=routing_predictions,
        top_fraction=config.top_fraction,
        guard_threshold=config.guard_threshold,
    )
    selection = select_tiles(
        candidates=candidates,
        budget=config.budget,
        coverage_ratio=config.coverage_ratio,
        image_width=image_width,
        image_height=image_height,
    )
    durations["tile_selection"] = time.perf_counter() - started

    started = time.perf_counter()
    image_array = np.asarray(image)
    selected_candidates = list(selection.selected)
    sliced_predictions: List[object] = []
    full_shape = [image_height, image_width]

    for batch_start in range(0, len(selected_candidates), config.batch_size):
        batch_candidates = selected_candidates[batch_start : batch_start + config.batch_size]
        batch_images = []
        batch_shifts = []
        for candidate in batch_candidates:
            x1, y1, x2, y2 = candidate.bbox
            batch_images.append(np.ascontiguousarray(image_array[y1:y2, x1:x2]))
            batch_shifts.append([x1, y1])

        detection_model.perform_batch_inference(batch_images)
        detection_model.convert_original_predictions(
            shift_amount=batch_shifts,
            full_shape=[full_shape] * len(batch_images),
        )
        for image_predictions in detection_model.object_prediction_list_per_image:
            for prediction in image_predictions:
                sliced_predictions.append(prediction.get_shifted_object_prediction())

    durations["selected_tile_prediction"] = time.perf_counter() - started

    combined_predictions = list(sliced_predictions)
    if config.include_standard_prediction:
        combined_predictions.extend(
            prediction
            for prediction in routing_predictions
            if _prediction_score(prediction) >= config.confidence
        )

    started = time.perf_counter()
    postprocess = GreedyNMMPostprocess(
        match_threshold=config.postprocess_match_threshold,
        match_metric="IOS",
        class_agnostic=False,
    )
    if len(combined_predictions) > 1:
        combined_predictions = postprocess(combined_predictions)
    durations["postprocess"] = time.perf_counter() - started
    durations["total"] = sum(durations.values())

    result = PredictionResult(
        image=image,
        object_prediction_list=combined_predictions,
        durations_in_seconds=durations,
    )
    return SelectiveSahiResult(
        prediction_result=result,
        low_routing_map=low_routing_map,
        routing_map=routing_map,
        low_probability_map=low_probability_map,
        low_entropy_map=low_entropy_map,
        selection=selection,
        upsampler_name=upsampler.name,
        coarse_mode=config.coarse_mode,
        durations=durations,
    )
