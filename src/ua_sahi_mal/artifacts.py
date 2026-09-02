from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, cast

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ua_sahi_mal.config import PredictConfig
from ua_sahi_mal.inference import SelectiveSahiResult


@dataclass(frozen=True)
class ArtifactPaths:
    run_dir: Path
    annotated: Path
    predictions: Path
    routing_heatmap: Path
    selected_tiles: Path
    summary: Path


def _json_default(value: Any):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _score_value(prediction: object) -> float:
    score = getattr(prediction, "score", 0.0)
    return float(getattr(score, "value", score))


def _bbox_xyxy(prediction: object):
    bbox = cast(Any, prediction).bbox
    return bbox.to_xyxy() if hasattr(bbox, "to_xyxy") else bbox


def _save_annotated(image: Image.Image, result: SelectiveSahiResult, path: Path) -> None:
    canvas = image.convert("RGB").copy()
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    for prediction in result.prediction_result.object_prediction_list:
        x1, y1, x2, y2 = (int(round(value)) for value in _bbox_xyxy(prediction))
        category = getattr(getattr(prediction, "category", None), "name", "object")
        label = f"{category} {_score_value(prediction):.2f}"
        draw.rectangle((x1, y1, x2, y2), outline=(255, 64, 64), width=3)
        text_bbox = draw.textbbox((x1, y1), label, font=font)
        draw.rectangle(text_bbox, fill=(255, 64, 64))
        draw.text((x1, y1), label, fill=(255, 255, 255), font=font)
    canvas.save(path)


def _save_heatmap(route_map: np.ndarray, path: Path) -> None:
    normalized = route_map - float(np.min(route_map))
    maximum = float(np.max(normalized))
    if maximum > 1e-8:
        normalized = normalized / maximum
    heatmap = cv2.applyColorMap((normalized * 255).astype(np.uint8), cv2.COLORMAP_TURBO)
    Image.fromarray(cv2.cvtColor(heatmap, cv2.COLOR_BGR2RGB)).save(path)


def _save_tiles(image: Image.Image, result: SelectiveSahiResult, path: Path) -> None:
    canvas = image.convert("RGB").copy()
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    for candidate in result.selection.candidates:
        color = (0, 255, 80) if candidate.selected else (120, 120, 120)
        width = 4 if candidate.selected else 1
        draw.rectangle(candidate.bbox, outline=color, width=width)
        x1, y1, _, _ = candidate.bbox
        flag = "G" if candidate.guarded else ""
        draw.text((x1 + 3, y1 + 3), f"{candidate.index}:{candidate.score:.3f}{flag}", fill=color, font=font)
    canvas.save(path)


def save_artifacts(
    image: Image.Image,
    result: SelectiveSahiResult,
    config: PredictConfig,
    device: str,
    versions: Dict[str, str],
) -> ArtifactPaths:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = config.output_dir / f"{config.source.stem}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=False)

    paths = ArtifactPaths(
        run_dir=run_dir,
        annotated=run_dir / "annotated.png",
        predictions=run_dir / "predictions.json",
        routing_heatmap=run_dir / "routing_heatmap.png",
        selected_tiles=run_dir / "selected_tiles.png",
        summary=run_dir / "summary.json",
    )

    _save_annotated(image, result, paths.annotated)
    _save_heatmap(result.routing_map, paths.routing_heatmap)
    _save_tiles(image, result, paths.selected_tiles)

    predictions = result.prediction_result.to_coco_annotations()
    paths.predictions.write_text(
        json.dumps(predictions, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    summary = {
        "config": asdict(config),
        "device": device,
        "upsampler": result.upsampler_name,
        "coarse_mode": result.coarse_mode,
        "versions": versions,
        "candidate_tiles": len(result.selection.candidates),
        "selected_tiles": len(result.selection.selected_indices),
        "selected_indices": result.selection.selected_indices,
        "tile_candidates": [asdict(candidate) for candidate in result.selection.candidates],
        "prediction_count": len(result.prediction_result.object_prediction_list),
        "durations_seconds": result.durations,
        "dense_probability_range": (
            [float(result.low_probability_map.min()), float(result.low_probability_map.max())]
            if result.low_probability_map is not None
            else None
        ),
        "dense_entropy_range": (
            [float(result.low_entropy_map.min()), float(result.low_entropy_map.max())]
            if result.low_entropy_map is not None
            else None
        ),
        "artifacts": {key: str(value) for key, value in asdict(paths).items()},
    }
    paths.summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    return paths
