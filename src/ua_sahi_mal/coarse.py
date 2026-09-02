"""Ultralytics YOLO coarse-pass routing maps.

This module captures the pre-NMS class logits from the same full-image forward
pass that SAHI uses for standard predictions. It is deliberately isolated from
the rest of the router because Ultralytics head outputs are version-specific.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

import cv2
import numpy as np


@dataclass(frozen=True)
class DenseCoarseResult:
    prediction_result: Any
    probability_map: np.ndarray
    entropy_map: np.ndarray
    fpn_shapes: tuple[tuple[int, int], ...]
    input_shape: tuple[int, int]


def _sigmoid(array: np.ndarray) -> np.ndarray:
    positive = array >= 0
    result = np.empty_like(array, dtype=np.float32)
    result[positive] = 1.0 / (1.0 + np.exp(-array[positive]))
    negative_exp = np.exp(array[~positive])
    result[~positive] = negative_exp / (1.0 + negative_exp)
    return result


def _binary_entropy(probability: np.ndarray) -> np.ndarray:
    clipped = np.clip(probability.astype(np.float32), 1e-7, 1 - 1e-7)
    entropy = -(clipped * np.log2(clipped) + (1 - clipped) * np.log2(1 - clipped))
    return np.clip(entropy, 0.0, 1.0).astype(np.float32)


def aggregate_fpn_logits(
    logits_by_level: Sequence[np.ndarray],
    *,
    output_shape: tuple[int, int],
) -> tuple[np.ndarray, np.ndarray]:
    """Aggregate ``[classes, height, width]`` logits into class-agnostic maps."""

    output_height, output_width = output_shape
    if output_height < 1 or output_width < 1:
        raise ValueError("output_shape must be positive")
    if not logits_by_level:
        raise ValueError("at least one FPN logit level is required")
    resized_probabilities: list[np.ndarray] = []
    for level_index, logits in enumerate(logits_by_level):
        array = np.asarray(logits, dtype=np.float32)
        if array.ndim != 3 or array.shape[0] < 1 or array.shape[1] < 1 or array.shape[2] < 1:
            raise ValueError(
                f"FPN logits[{level_index}] must have [classes, height, width] shape"
            )
        if not np.isfinite(array).all():
            raise ValueError(f"FPN logits[{level_index}] contains non-finite values")
        class_agnostic = _sigmoid(array).max(axis=0)
        resized = cv2.resize(
            class_agnostic,
            (output_width, output_height),
            interpolation=cv2.INTER_LINEAR,
        )
        resized_probabilities.append(resized.astype(np.float32))
    probability = np.maximum.reduce(resized_probabilities)
    probability = np.clip(probability, 0.0, 1.0).astype(np.float32)
    return probability, _binary_entropy(probability)


def combine_probability_entropy(
    probability_map: np.ndarray,
    entropy_map: np.ndarray,
    *,
    probability_weight: float,
    entropy_weight: float,
) -> np.ndarray:
    """Combine probability and uncertainty without changing the calibrated inputs."""

    probability = np.asarray(probability_map, dtype=np.float32)
    entropy = np.asarray(entropy_map, dtype=np.float32)
    if probability.shape != entropy.shape or probability.ndim != 2:
        raise ValueError("probability and entropy maps must be same-shaped 2D arrays")
    if probability_weight < 0 or entropy_weight < 0:
        raise ValueError("routing weights must be non-negative")
    total = probability_weight + entropy_weight
    if total <= 0:
        raise ValueError("at least one routing weight must be positive")
    result = (probability_weight * probability + entropy_weight * entropy) / total
    return np.clip(np.nan_to_num(result, nan=0.0, posinf=1.0, neginf=0.0), 0.0, 1.0).astype(
        np.float32
    )


def _ultralytics_head(detection_model: Any) -> Any:
    wrapper = getattr(detection_model, "model", None)
    if wrapper is None:
        raise RuntimeError("SAHI detection model does not expose its Ultralytics model")
    core = getattr(wrapper, "model", wrapper)
    layers = getattr(core, "model", None)
    if layers is None or not hasattr(layers, "__getitem__"):
        raise RuntimeError("Ultralytics model does not expose a layer sequence")
    head = layers[-1]
    if not hasattr(head, "register_forward_hook"):
        raise RuntimeError("Ultralytics detection head cannot be observed")
    return head


def _captured_predictions(output: Any) -> dict[str, Any]:
    raw = output[1] if isinstance(output, tuple) and len(output) >= 2 else output
    if isinstance(raw, dict) and "one2many" in raw:
        raw = raw["one2many"]
    if not isinstance(raw, dict) or not {"scores", "feats"}.issubset(raw):
        raise RuntimeError(
            "unsupported Ultralytics detection-head output; pin a supported version or use --coarse-mode boxes"
        )
    return raw


def _level_logits_from_capture(
    captured_output: Any,
    *,
    strides: Sequence[float],
    original_size: tuple[int, int],
) -> tuple[list[np.ndarray], tuple[tuple[int, int], ...], tuple[int, int]]:
    raw = _captured_predictions(captured_output)
    scores = raw["scores"]
    features = raw["feats"]
    if not hasattr(scores, "detach") or not isinstance(features, (list, tuple)):
        raise RuntimeError("Ultralytics capture does not contain tensor scores and FPN features")
    if len(features) != len(strides):
        raise RuntimeError("Ultralytics FPN feature and stride counts differ")
    score_array = scores.detach().float().cpu().numpy()
    if score_array.ndim != 3 or score_array.shape[0] != 1:
        raise RuntimeError("dense routing currently requires a single-image YOLO coarse pass")

    shapes = tuple((int(feature.shape[-2]), int(feature.shape[-1])) for feature in features)
    counts = [height * width for height, width in shapes]
    if sum(counts) != score_array.shape[-1]:
        raise RuntimeError("Ultralytics raw score count does not match FPN shapes")
    input_height = max(
        int(round(height * stride))
        for (height, _), stride in zip(shapes, strides, strict=True)
    )
    input_width = max(
        int(round(width * stride))
        for (_, width), stride in zip(shapes, strides, strict=True)
    )

    original_width, original_height = original_size
    scale = min(input_width / original_width, input_height / original_height)
    resized_width = min(input_width, int(round(original_width * scale)))
    resized_height = min(input_height, int(round(original_height * scale)))
    pad_x = (input_width - resized_width) / 2.0
    pad_y = (input_height - resized_height) / 2.0

    logits_by_level: list[np.ndarray] = []
    start = 0
    for (height, width), count in zip(shapes, counts, strict=True):
        stop = start + count
        level = score_array[0, :, start:stop].reshape(score_array.shape[1], height, width)
        start = stop
        x1 = max(0, min(width - 1, int(math.floor(pad_x * width / input_width))))
        y1 = max(0, min(height - 1, int(math.floor(pad_y * height / input_height))))
        x2 = max(x1 + 1, min(width, int(math.ceil((pad_x + resized_width) * width / input_width))))
        y2 = max(y1 + 1, min(height, int(math.ceil((pad_y + resized_height) * height / input_height))))
        logits_by_level.append(level[:, y1:y2, x1:x2])
    return logits_by_level, shapes, (input_height, input_width)


def run_dense_coarse_pass(
    *,
    image: Any,
    detection_model: Any,
    confidence_threshold: float,
    output_shape: tuple[int, int],
) -> DenseCoarseResult:
    """Run SAHI full-image prediction and capture pre-NMS FPN logits once."""

    from sahi.predict import get_prediction

    head = _ultralytics_head(detection_model)
    captured: list[Any] = []

    def capture(_module: Any, _inputs: Any, output: Any) -> None:
        captured.append(output)

    handle = head.register_forward_hook(capture)
    try:
        prediction_result = get_prediction(
            image=image,
            detection_model=detection_model,
            confidence_threshold=confidence_threshold,
            verbose=0,
        )
    finally:
        handle.remove()
    if not captured:
        raise RuntimeError(
            "Ultralytics head hook captured no output; use --coarse-mode boxes for this model"
        )
    stride_values = getattr(head, "stride", None)
    if stride_values is None:
        raise RuntimeError("Ultralytics detection head has no stride metadata")
    if hasattr(stride_values, "detach"):
        stride_values = stride_values.detach().float().cpu().tolist()
    strides = tuple(float(value) for value in stride_values)
    logits, shapes, input_shape = _level_logits_from_capture(
        captured[-1],
        strides=strides,
        original_size=image.size,
    )
    probability, entropy = aggregate_fpn_logits(logits, output_shape=output_shape)
    return DenseCoarseResult(
        prediction_result=prediction_result,
        probability_map=probability,
        entropy_map=entropy,
        fpn_shapes=shapes,
        input_shape=input_shape,
    )
