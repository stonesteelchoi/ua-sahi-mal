from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Iterable, List, Sequence, Tuple, cast

import cv2
import numpy as np
from PIL import Image

BBox = Tuple[int, int, int, int]


@dataclass(frozen=True)
class TileCandidate:
    index: int
    bbox: BBox
    score: float
    guarded: bool
    selected: bool = False

    @property
    def center(self) -> Tuple[float, float]:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


@dataclass(frozen=True)
class TileSelection:
    candidates: Tuple[TileCandidate, ...]
    selected_indices: Tuple[int, ...]
    requested_count: int

    @property
    def selected(self) -> Tuple[TileCandidate, ...]:
        selected_set = set(self.selected_indices)
        return tuple(candidate for candidate in self.candidates if candidate.index in selected_set)


def _score_value(prediction: object) -> float:
    score = getattr(prediction, "score", 0.0)
    return float(getattr(score, "value", score))


def _bbox_xyxy(prediction: object) -> Tuple[float, float, float, float]:
    bbox = cast(Any, prediction).bbox
    if hasattr(bbox, "to_xyxy"):
        values = bbox.to_xyxy()
    else:
        values = bbox
    return tuple(float(value) for value in values)  # type: ignore[return-value]


def _normalize_map(array: np.ndarray) -> np.ndarray:
    finite = np.nan_to_num(array.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    high = float(np.percentile(finite, 99.0)) if finite.size else 0.0
    if high <= 1e-8:
        return np.zeros_like(finite, dtype=np.float32)
    return np.clip(finite / high, 0.0, 1.0).astype(np.float32)


def build_low_routing_map(
    padded_image: Image.Image,
    predictions: Iterable[object],
    route_scale: int,
    box_weight: float,
    texture_weight: float,
) -> np.ndarray:
    """Create a coarse routing map from full-image boxes and an image texture prior."""
    width, height = padded_image.size
    if height % route_scale or width % route_scale:
        raise ValueError("padded image dimensions must be divisible by route_scale")

    low_height = height // route_scale
    low_width = width // route_scale
    box_map = np.zeros((low_height, low_width), dtype=np.float32)

    for prediction in predictions:
        score = np.clip(_score_value(prediction), 0.0, 1.0)
        x1, y1, x2, y2 = _bbox_xyxy(prediction)
        lx1 = max(0, min(low_width - 1, int(math.floor(x1 / route_scale))))
        ly1 = max(0, min(low_height - 1, int(math.floor(y1 / route_scale))))
        lx2 = max(lx1 + 1, min(low_width, int(math.ceil(x2 / route_scale))))
        ly2 = max(ly1 + 1, min(low_height, int(math.ceil(y2 / route_scale))))

        region_height = ly2 - ly1
        region_width = lx2 - lx1
        yy, xx = np.mgrid[0:region_height, 0:region_width]
        cy = max((region_height - 1) / 2.0, 0.5)
        cx = max((region_width - 1) / 2.0, 0.5)
        gaussian = np.exp(-0.5 * (((yy - cy) / (cy + 0.5)) ** 2 + ((xx - cx) / (cx + 0.5)) ** 2))
        box_map[ly1:ly2, lx1:lx2] = np.maximum(
            box_map[ly1:ly2, lx1:lx2], (score * gaussian).astype(np.float32)
        )

    rgb = np.asarray(padded_image.convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    gray_low = cv2.resize(gray, (low_width, low_height), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    grad_x = cv2.Sobel(gray_low, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray_low, cv2.CV_32F, 0, 1, ksize=3)
    texture_map = _normalize_map(cv2.magnitude(grad_x, grad_y))

    weight_sum = box_weight + texture_weight
    routing_map = (box_weight * box_map + texture_weight * texture_map) / max(weight_sum, 1e-8)
    return np.clip(routing_map, 0.0, 1.0).astype(np.float32)


def top_mean_score(route_map: np.ndarray, bbox: Sequence[int], fraction: float) -> float:
    x1, y1, x2, y2 = (int(value) for value in bbox)
    crop = route_map[max(0, y1) : max(0, y2), max(0, x1) : max(0, x2)]
    if crop.size == 0:
        return 0.0
    flat = crop.reshape(-1)
    count = max(1, int(math.ceil(flat.size * fraction)))
    if count >= flat.size:
        return float(flat.mean())
    top_values = np.partition(flat, flat.size - count)[-count:]
    return float(top_values.mean())


def _intersects(box_a: Sequence[float], box_b: Sequence[float]) -> bool:
    return not (box_a[2] <= box_b[0] or box_a[0] >= box_b[2] or box_a[3] <= box_b[1] or box_a[1] >= box_b[3])


def build_candidates(
    route_map: np.ndarray,
    tile_bboxes: Sequence[Sequence[int]],
    predictions: Iterable[object],
    top_fraction: float,
    guard_threshold: float,
) -> List[TileCandidate]:
    guard_boxes = [
        _bbox_xyxy(prediction)
        for prediction in predictions
        if _score_value(prediction) >= guard_threshold
    ]
    candidates = []
    for index, bbox_values in enumerate(tile_bboxes):
        bbox = tuple(int(value) for value in bbox_values)
        candidates.append(
            TileCandidate(
                index=index,
                bbox=bbox,  # type: ignore[arg-type]
                score=top_mean_score(route_map, bbox, top_fraction),
                guarded=any(_intersects(bbox, guard_box) for guard_box in guard_boxes),
            )
        )
    return candidates


def _normalized_center(candidate: TileCandidate, image_width: int, image_height: int) -> Tuple[float, float]:
    x, y = candidate.center
    return (x / max(image_width, 1), y / max(image_height, 1))


def _pick_farthest(
    candidates: Sequence[TileCandidate],
    selected: Sequence[int],
    image_width: int,
    image_height: int,
) -> int:
    selected_set = set(selected)
    remaining = [candidate for candidate in candidates if candidate.index not in selected_set]
    if not remaining:
        raise ValueError("no candidate remains")
    if not selected:
        return max(remaining, key=lambda candidate: (candidate.score, -candidate.index)).index

    selected_centers = [
        _normalized_center(candidates[index], image_width, image_height) for index in selected
    ]

    def spatial_value(candidate: TileCandidate) -> Tuple[float, float, int]:
        cx, cy = _normalized_center(candidate, image_width, image_height)
        minimum_distance = min((cx - sx) ** 2 + (cy - sy) ** 2 for sx, sy in selected_centers)
        return (minimum_distance, candidate.score, -candidate.index)

    return max(remaining, key=spatial_value).index


def select_tiles(
    candidates: Sequence[TileCandidate],
    budget: float,
    coverage_ratio: float,
    image_width: int,
    image_height: int,
) -> TileSelection:
    if not candidates:
        raise ValueError("at least one tile candidate is required")
    if not 0 < budget <= 1:
        raise ValueError("budget must be in (0, 1]")

    requested_count = max(1, min(len(candidates), int(math.ceil(len(candidates) * budget))))
    guarded = sorted(
        (candidate for candidate in candidates if candidate.guarded),
        key=lambda candidate: (-candidate.score, candidate.index),
    )
    selected = [candidate.index for candidate in guarded[:requested_count]]

    coverage_slots = min(requested_count - len(selected), int(math.ceil(requested_count * coverage_ratio)))
    for _ in range(coverage_slots):
        selected.append(_pick_farthest(candidates, selected, image_width, image_height))

    selected_set = set(selected)
    ranked = sorted(candidates, key=lambda candidate: (-candidate.score, candidate.index))
    for candidate in ranked:
        if len(selected) >= requested_count:
            break
        if candidate.index not in selected_set:
            selected.append(candidate.index)
            selected_set.add(candidate.index)

    selected_tuple = tuple(sorted(selected))
    marked = tuple(replace(candidate, selected=candidate.index in selected_set) for candidate in candidates)
    return TileSelection(candidates=marked, selected_indices=selected_tuple, requested_count=requested_count)
