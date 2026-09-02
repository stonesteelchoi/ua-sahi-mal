from PIL import Image, ImageDraw

from ua_sahi_mal.strategies import (
    BudgetedSahiStrategy,
    Detection,
    FullSahiStrategy,
    RedBlobFakeDetector,
    generate_tile_grid,
    greedy_nmm,
    select_budgeted_tiles,
)


def test_grid_covers_bottom_and_right_edges() -> None:
    tiles = generate_tile_grid(100, 70, tile_width=40, tile_height=32, overlap=0.25)

    assert tiles[0].bbox_xyxy == (0, 0, 40, 32)
    assert max(tile.bbox_xyxy[2] for tile in tiles) == 100
    assert max(tile.bbox_xyxy[3] for tile in tiles) == 70
    assert {tile.index for tile in tiles} == set(range(len(tiles)))


def test_budget_selection_honors_guard_and_is_deterministic() -> None:
    tiles = generate_tile_grid(100, 100, tile_width=50, tile_height=50, overlap=0.0)
    scores = (0.9, 0.1, 0.2, 0.3)

    first = select_budgeted_tiles(
        tiles,
        scores,
        budget=0.5,
        guarded_indices=(1,),
        coverage_ratio=0.0,
        image_width=100,
        image_height=100,
    )
    second = select_budgeted_tiles(
        tiles,
        scores,
        budget=0.5,
        guarded_indices=(1,),
        coverage_ratio=0.0,
        image_width=100,
        image_height=100,
    )

    assert first == second == (0, 1)


def test_greedy_nmm_merges_same_class_and_keeps_other_class() -> None:
    detections = [
        Detection(1, 0.9, (0, 0, 10, 10)),
        Detection(1, 0.8, (1, 1, 9, 9)),
        Detection(2, 0.7, (1, 1, 9, 9)),
    ]

    merged = greedy_nmm(detections, match_threshold=0.5, match_metric="ios")

    assert len(merged) == 2
    assert {detection.category_id for detection in merged} == {1, 2}


def test_full_and_budgeted_sahi_share_detector_contract() -> None:
    image = Image.new("RGB", (64, 64), color="black")
    ImageDraw.Draw(image).rectangle((40, 40, 51, 51), fill="red")
    detector = RedBlobFakeDetector()

    full = FullSahiStrategy(32, 32, overlap=0.0, batch_size=2).run(image, detector)
    budgeted = BudgetedSahiStrategy(
        32,
        32,
        overlap=0.0,
        budget=0.5,
        coverage_ratio=0.0,
        batch_size=2,
    ).run(image, detector, risk_scores=(0.1, 0.2, 0.3, 1.0))

    assert len(full.detections) == len(budgeted.detections) == 1
    assert full.detector_images == 4
    assert budgeted.detector_images == 2
    assert 3 in budgeted.selected_indices
