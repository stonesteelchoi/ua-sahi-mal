from dataclasses import dataclass

import numpy as np
from PIL import Image

from ua_sahi_mal.routing import (
    TileCandidate,
    build_candidates,
    build_low_routing_map,
    select_tiles,
    top_mean_score,
)


@dataclass
class FakeScore:
    value: float


@dataclass
class FakeBBox:
    values: tuple[float, float, float, float]

    def to_xyxy(self) -> tuple[float, float, float, float]:
        return self.values


@dataclass
class FakePrediction:
    bbox: FakeBBox
    score: FakeScore


def prediction(box: tuple[float, float, float, float], score: float) -> FakePrediction:
    return FakePrediction(FakeBBox(box), FakeScore(score))


def test_low_routing_map_contains_detection_signal() -> None:
    image = Image.new("RGB", (64, 64), color="black")

    result = build_low_routing_map(
        padded_image=image,
        predictions=[prediction((16, 16, 48, 48), 0.8)],
        route_scale=8,
        box_weight=1.0,
        texture_weight=0.0,
    )

    assert result.shape == (8, 8)
    assert 0.0 <= float(result.min()) <= float(result.max()) <= 1.0
    assert result[3:5, 3:5].mean() > result[:2, :2].mean()


def test_top_mean_focuses_on_peak_pixels() -> None:
    route_map = np.zeros((10, 10), dtype=np.float32)
    route_map[4:6, 4:6] = 1.0

    assert top_mean_score(route_map, (0, 0, 10, 10), fraction=0.04) == 1.0
    assert 0.03 < top_mean_score(route_map, (0, 0, 10, 10), fraction=1.0) < 0.05


def test_budget_preserves_guarded_tile_and_spatial_coverage() -> None:
    route_map = np.zeros((100, 100), dtype=np.float32)
    route_map[:50, :50] = 0.9
    boxes = [(0, 0, 50, 50), (50, 0, 100, 50), (0, 50, 50, 100), (50, 50, 100, 100)]
    candidates = build_candidates(
        route_map=route_map,
        tile_bboxes=boxes,
        predictions=[prediction((60, 10, 90, 40), 0.8)],
        top_fraction=0.1,
        guard_threshold=0.5,
    )

    selection = select_tiles(
        candidates=candidates,
        budget=0.5,
        coverage_ratio=0.5,
        image_width=100,
        image_height=100,
    )

    assert len(selection.selected_indices) == 2
    assert 1 in selection.selected_indices
    assert selection.requested_count == 2
    assert sum(candidate.selected for candidate in selection.candidates) == 2


def test_selection_is_deterministic_for_equal_scores() -> None:
    candidates = [
        TileCandidate(index=index, bbox=(index * 10, 0, index * 10 + 10, 10), score=0.5, guarded=False)
        for index in range(4)
    ]

    first = select_tiles(candidates, budget=0.5, coverage_ratio=0.0, image_width=40, image_height=10)
    second = select_tiles(candidates, budget=0.5, coverage_ratio=0.0, image_width=40, image_height=10)

    assert first.selected_indices == second.selected_indices == (0, 1)
