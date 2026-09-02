"""Detector-neutral baselines for synthetic and research evaluation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol, Sequence

from PIL import Image

BBoxXYXY = tuple[float, float, float, float]


@dataclass(frozen=True)
class Detection:
    category_id: int
    score: float
    bbox_xyxy: BBoxXYXY

    def validate(self) -> None:
        x1, y1, x2, y2 = self.bbox_xyxy
        if self.category_id < 1:
            raise ValueError("category_id must be positive")
        if not 0 <= self.score <= 1:
            raise ValueError("score must be in [0, 1]")
        if x2 <= x1 or y2 <= y1:
            raise ValueError("bbox must have positive width and height")


@dataclass(frozen=True)
class Tile:
    index: int
    bbox_xyxy: tuple[int, int, int, int]

    @property
    def center(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.bbox_xyxy
        return ((x1 + x2) / 2, (y1 + y2) / 2)


class Detector(Protocol):
    def predict_batch(self, images: Sequence[Image.Image]) -> Sequence[Sequence[Detection]]:
        """Return local-coordinate detections for every input image."""


@dataclass(frozen=True)
class StrategyResult:
    detections: tuple[Detection, ...]
    detector_invocations: int
    detector_images: int
    candidate_tiles: int
    selected_indices: tuple[int, ...]

    @property
    def selected_tiles(self) -> int:
        return len(self.selected_indices)


def _axis_starts(length: int, tile_size: int, overlap: float) -> tuple[int, ...]:
    if length <= tile_size:
        return (0,)
    step = max(1, int(round(tile_size * (1 - overlap))))
    final = length - tile_size
    starts = list(range(0, final + 1, step))
    if starts[-1] != final:
        starts.append(final)
    return tuple(starts)


def generate_tile_grid(
    image_width: int,
    image_height: int,
    *,
    tile_width: int,
    tile_height: int,
    overlap: float,
) -> tuple[Tile, ...]:
    """Generate a deterministic edge-covering grid."""

    if image_width < 1 or image_height < 1:
        raise ValueError("image dimensions must be positive")
    if tile_width < 1 or tile_height < 1:
        raise ValueError("tile dimensions must be positive")
    if not 0 <= overlap < 1:
        raise ValueError("overlap must be in [0, 1)")

    x_starts = _axis_starts(image_width, tile_width, overlap)
    y_starts = _axis_starts(image_height, tile_height, overlap)
    tiles: list[Tile] = []
    for y1 in y_starts:
        for x1 in x_starts:
            tiles.append(
                Tile(
                    index=len(tiles),
                    bbox_xyxy=(
                        x1,
                        y1,
                        min(x1 + tile_width, image_width),
                        min(y1 + tile_height, image_height),
                    ),
                )
            )
    return tuple(tiles)


def _overlap_ratio(left: Detection, right: Detection, metric: str) -> float:
    ax1, ay1, ax2, ay2 = left.bbox_xyxy
    bx1, by1, bx2, by2 = right.bbox_xyxy
    intersection = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(
        0.0, min(ay2, by2) - max(ay1, by1)
    )
    if intersection <= 0:
        return 0.0
    left_area = (ax2 - ax1) * (ay2 - ay1)
    right_area = (bx2 - bx1) * (by2 - by1)
    if metric == "iou":
        return intersection / (left_area + right_area - intersection)
    if metric == "ios":
        return intersection / min(left_area, right_area)
    raise ValueError("match_metric must be iou or ios")


def greedy_nmm(
    detections: Sequence[Detection],
    *,
    match_threshold: float = 0.5,
    match_metric: str = "ios",
    class_aware: bool = True,
) -> tuple[Detection, ...]:
    """Merge overlapping boxes using score-weighted coordinates."""

    if not 0 <= match_threshold <= 1:
        raise ValueError("match_threshold must be in [0, 1]")
    remaining = sorted(detections, key=lambda item: (-item.score, item.category_id, item.bbox_xyxy))
    for detection in remaining:
        detection.validate()

    merged: list[Detection] = []
    while remaining:
        seed = remaining.pop(0)
        group = [seed]
        retained: list[Detection] = []
        for candidate in remaining:
            same_class = candidate.category_id == seed.category_id
            if (same_class or not class_aware) and _overlap_ratio(seed, candidate, match_metric) >= match_threshold:
                group.append(candidate)
            else:
                retained.append(candidate)
        remaining = retained
        weight_sum = sum(max(item.score, 1e-8) for item in group)
        coordinates = tuple(
            sum(item.bbox_xyxy[axis] * max(item.score, 1e-8) for item in group) / weight_sum
            for axis in range(4)
        )
        merged.append(
            Detection(
                category_id=seed.category_id,
                score=max(item.score for item in group),
                bbox_xyxy=coordinates,  # type: ignore[arg-type]
            )
        )
    return tuple(sorted(merged, key=lambda item: (-item.score, item.category_id, item.bbox_xyxy)))


def _normalized_center(tile: Tile, image_width: int, image_height: int) -> tuple[float, float]:
    x, y = tile.center
    return x / image_width, y / image_height


def select_budgeted_tiles(
    tiles: Sequence[Tile],
    risk_scores: Sequence[float],
    *,
    budget: float,
    guarded_indices: Sequence[int] = (),
    coverage_ratio: float = 0.2,
    image_width: int,
    image_height: int,
) -> tuple[int, ...]:
    """Select exact-budget tiles with guard priority and farthest-point coverage."""

    if not tiles or len(tiles) != len(risk_scores):
        raise ValueError("tiles and risk_scores must have the same non-zero length")
    if not 0 < budget <= 1:
        raise ValueError("budget must be in (0, 1]")
    if not 0 <= coverage_ratio <= 1:
        raise ValueError("coverage_ratio must be in [0, 1]")
    if any(not math.isfinite(score) for score in risk_scores):
        raise ValueError("risk_scores must be finite")

    requested = max(1, min(len(tiles), math.ceil(len(tiles) * budget)))
    valid_indices = {tile.index for tile in tiles}
    if valid_indices != set(range(len(tiles))):
        raise ValueError("tile indices must be contiguous from zero")
    guarded = sorted(
        set(guarded_indices),
        key=lambda index: (-risk_scores[index], index),
    )
    if any(index not in valid_indices for index in guarded):
        raise ValueError("guarded_indices contains an unknown tile")
    selected = guarded[:requested]
    selected_set = set(selected)

    coverage_slots = min(requested - len(selected), math.ceil(requested * coverage_ratio))
    for _ in range(coverage_slots):
        remaining = [tile for tile in tiles if tile.index not in selected_set]
        if not selected:
            chosen = max(remaining, key=lambda tile: (risk_scores[tile.index], -tile.index))
        else:
            chosen_centers = [
                _normalized_center(tiles[index], image_width, image_height) for index in selected
            ]

            def distance_value(
                tile: Tile,
                centers: tuple[tuple[float, float], ...] = tuple(chosen_centers),
            ) -> tuple[float, float, int]:
                x, y = _normalized_center(tile, image_width, image_height)
                minimum = min((x - sx) ** 2 + (y - sy) ** 2 for sx, sy in centers)
                return minimum, risk_scores[tile.index], -tile.index

            chosen = max(remaining, key=distance_value)
        selected.append(chosen.index)
        selected_set.add(chosen.index)

    ranked = sorted(range(len(tiles)), key=lambda index: (-risk_scores[index], index))
    for index in ranked:
        if len(selected) >= requested:
            break
        if index not in selected_set:
            selected.append(index)
            selected_set.add(index)
    return tuple(sorted(selected))


def _shift_detection(detection: Detection, shift_x: int, shift_y: int) -> Detection:
    x1, y1, x2, y2 = detection.bbox_xyxy
    return Detection(
        category_id=detection.category_id,
        score=detection.score,
        bbox_xyxy=(x1 + shift_x, y1 + shift_y, x2 + shift_x, y2 + shift_y),
    )


def _predict_tiles(
    image: Image.Image,
    detector: Detector,
    tiles: Sequence[Tile],
    selected_indices: Sequence[int],
    *,
    batch_size: int,
    match_threshold: float,
) -> StrategyResult:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    shifted: list[Detection] = []
    invocations = 0
    for batch_start in range(0, len(selected_indices), batch_size):
        batch_indices = selected_indices[batch_start : batch_start + batch_size]
        batch_tiles = [tiles[index] for index in batch_indices]
        crops = [image.crop(tile.bbox_xyxy) for tile in batch_tiles]
        batch_predictions = detector.predict_batch(crops)
        invocations += 1
        if len(batch_predictions) != len(crops):
            raise ValueError("detector returned a different number of prediction groups than images")
        for tile, predictions in zip(batch_tiles, batch_predictions, strict=True):
            x1, y1, _, _ = tile.bbox_xyxy
            shifted.extend(_shift_detection(detection, x1, y1) for detection in predictions)
    return StrategyResult(
        detections=greedy_nmm(shifted, match_threshold=match_threshold),
        detector_invocations=invocations,
        detector_images=len(selected_indices),
        candidate_tiles=len(tiles),
        selected_indices=tuple(selected_indices),
    )


@dataclass(frozen=True)
class FullImageStrategy:
    def run(self, image: Image.Image, detector: Detector) -> StrategyResult:
        predictions = detector.predict_batch([image])
        if len(predictions) != 1:
            raise ValueError("detector must return one prediction group for one image")
        return StrategyResult(
            detections=tuple(predictions[0]),
            detector_invocations=1,
            detector_images=1,
            candidate_tiles=1,
            selected_indices=(0,),
        )


@dataclass(frozen=True)
class FullSahiStrategy:
    tile_width: int
    tile_height: int
    overlap: float = 0.2
    batch_size: int = 1
    match_threshold: float = 0.5

    def run(self, image: Image.Image, detector: Detector) -> StrategyResult:
        tiles = generate_tile_grid(
            image.width,
            image.height,
            tile_width=self.tile_width,
            tile_height=self.tile_height,
            overlap=self.overlap,
        )
        selected = tuple(range(len(tiles)))
        return _predict_tiles(
            image,
            detector,
            tiles,
            selected,
            batch_size=self.batch_size,
            match_threshold=self.match_threshold,
        )


@dataclass(frozen=True)
class BudgetedSahiStrategy:
    tile_width: int
    tile_height: int
    budget: float = 0.5
    overlap: float = 0.2
    coverage_ratio: float = 0.2
    batch_size: int = 1
    match_threshold: float = 0.5

    def run(
        self,
        image: Image.Image,
        detector: Detector,
        *,
        risk_scores: Sequence[float],
        guarded_indices: Sequence[int] = (),
    ) -> StrategyResult:
        tiles = generate_tile_grid(
            image.width,
            image.height,
            tile_width=self.tile_width,
            tile_height=self.tile_height,
            overlap=self.overlap,
        )
        selected = select_budgeted_tiles(
            tiles,
            risk_scores,
            budget=self.budget,
            guarded_indices=guarded_indices,
            coverage_ratio=self.coverage_ratio,
            image_width=image.width,
            image_height=image.height,
        )
        return _predict_tiles(
            image,
            detector,
            tiles,
            selected,
            batch_size=self.batch_size,
            match_threshold=self.match_threshold,
        )


class RedBlobFakeDetector:
    """Synthetic-only detector used by smoke tests; it is not a research model."""

    def predict_batch(self, images: Sequence[Image.Image]) -> Sequence[Sequence[Detection]]:
        results: list[list[Detection]] = []
        for image in images:
            pixels = image.convert("RGB")
            points = [
                (x, y)
                for y in range(pixels.height)
                for x in range(pixels.width)
                if (lambda rgb: rgb[0] >= 220 and rgb[1] <= 40 and rgb[2] <= 40)(
                    pixels.getpixel((x, y))
                )
            ]
            if not points:
                results.append([])
                continue
            x_values, y_values = zip(*points, strict=True)
            results.append(
                [
                    Detection(
                        category_id=1,
                        score=1.0,
                        bbox_xyxy=(
                            float(min(x_values)),
                            float(min(y_values)),
                            float(max(x_values) + 1),
                            float(max(y_values) + 1),
                        ),
                    )
                ]
            )
        return results
