import csv
import json
from pathlib import Path

import pytest

from ua_sahi_mal.evaluation import (
    LocalizationBox,
    assess_primary_success,
    bbox_iou_xywh,
    detector_call_reduction,
    evaluate_localization,
    load_ground_truth_boxes,
    load_prediction_boxes,
    tile_recall,
    write_localization_evaluation,
)
from ua_sahi_mal.strategies import Tile


def test_tile_recall_uses_object_coverage() -> None:
    tiles = [Tile(0, (0, 0, 10, 10)), Tile(1, (10, 0, 20, 10))]
    ground_truth = [(2.0, 2.0, 8.0, 8.0), (18.0, 2.0, 22.0, 8.0)]

    assert tile_recall(tiles, ground_truth, minimum_object_coverage=0.5) == 1.0
    assert tile_recall(tiles[:1], ground_truth, minimum_object_coverage=0.5) == 0.5


def test_detector_call_reduction_is_fractional() -> None:
    assert detector_call_reduction(10, 6) == pytest.approx(0.4)


def test_primary_success_requires_all_three_gates() -> None:
    passed = assess_primary_success(
        full_sahi_ap_s=40.0,
        candidate_ap_s=38.5,
        full_sahi_detector_calls=100,
        candidate_detector_calls=60,
        full_sahi_latency_ms=100.0,
        candidate_latency_ms=75.0,
        ap_scale="points_0_100",
    )
    failed = assess_primary_success(
        full_sahi_ap_s=40.0,
        candidate_ap_s=38.4,
        full_sahi_detector_calls=100,
        candidate_detector_calls=60,
        full_sahi_latency_ms=100.0,
        candidate_latency_ms=75.0,
        ap_scale="points_0_100",
    )

    assert passed.passed
    assert not failed.passed
    assert not failed.accuracy_non_inferior


def test_primary_success_requires_explicit_ap_scale() -> None:
    assessment = assess_primary_success(
        full_sahi_ap_s=0.40,
        candidate_ap_s=0.385,
        full_sahi_detector_calls=100,
        candidate_detector_calls=60,
        full_sahi_latency_ms=100.0,
        candidate_latency_ms=75.0,
        ap_scale="fraction_0_1",
    )

    assert assessment.passed

    with pytest.raises(ValueError, match="ap_scale"):
        assess_primary_success(
            full_sahi_ap_s=0.40,
            candidate_ap_s=0.385,
            full_sahi_detector_calls=100,
            candidate_detector_calls=60,
            full_sahi_latency_ms=100.0,
            candidate_latency_ms=75.0,
            ap_scale="unknown",
        )


def test_bbox_iou_xywh_uses_union_area() -> None:
    assert bbox_iou_xywh((0.0, 0.0, 10.0, 10.0), (5.0, 0.0, 10.0, 10.0)) == pytest.approx(1 / 3)
    assert bbox_iou_xywh((0.0, 0.0, 2.0, 2.0), (3.0, 3.0, 2.0, 2.0)) == 0.0

    with pytest.raises(ValueError, match="positive"):
        bbox_iou_xywh((0.0, 0.0, 0.0, 2.0), (1.0, 1.0, 2.0, 2.0))


def test_localization_evaluation_is_class_aware_and_confidence_ranked() -> None:
    predictions = [
        LocalizationBox("dropper", 1, (0.0, 0.0, 10.0, 10.0), 0.4),
        LocalizationBox("dropper", 1, (1.0, 1.0, 10.0, 10.0), 0.9),
        LocalizationBox("worm", 2, (20.0, 20.0, 5.0, 5.0), 0.8),
    ]
    ground_truth = [
        LocalizationBox("dropper", 1, (0.0, 0.0, 10.0, 10.0)),
        LocalizationBox("ransomware", 3, (20.0, 20.0, 5.0, 5.0)),
    ]

    evaluation = evaluate_localization(predictions, ground_truth, iou_threshold=0.5)

    assert evaluation.true_positives == 1
    assert evaluation.false_positives == 2
    assert evaluation.false_negatives == 1
    assert evaluation.precision == pytest.approx(1 / 3)
    assert evaluation.recall == pytest.approx(0.5)
    assert evaluation.matches[0].prediction_index == 1
    assert len(evaluation.class_mismatches) == 1
    assert evaluation.class_mismatches[0].label == "worm -> ransomware"


def test_load_fixture_predictions_and_write_evaluation(tmp_path: Path) -> None:
    predictions_path = tmp_path / "predictions.json"
    predictions_path.write_text(
        json.dumps(
            [
                {
                    "category_id": 0,
                    "category_name": "process_evidence",
                    "bbox": [4, 5, 8, 6],
                    "score": 0.9,
                }
            ]
        ),
        encoding="utf-8",
    )
    ground_truth_path = tmp_path / "expected.json"
    ground_truth_path.write_text(
        json.dumps(
            {
                "schema": "ua-sahi-mal-safe-fixture-v1",
                "image": "sample.png",
                "annotations": [
                    {
                        "class_id": 0,
                        "class_name": "process_evidence",
                        "bbox_xywh": [4, 5, 8, 6],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    predictions = load_prediction_boxes(predictions_path)
    ground_truth = load_ground_truth_boxes(ground_truth_path, image_name="sample.png")
    evaluation = evaluate_localization(predictions, ground_truth)
    json_output = tmp_path / "evaluation.json"
    csv_output = tmp_path / "evaluation.csv"
    write_localization_evaluation(evaluation, json_path=json_output, csv_path=csv_output)
    document = json.loads(json_output.read_text(encoding="utf-8"))
    rows = list(csv.DictReader(csv_output.open(encoding="utf-8")))

    assert evaluation.f1 == 1.0
    assert document["true_positives"] == 1
    assert rows[0]["status"] == "true_positive"
    assert rows[0]["iou"] == "1.0"

    with pytest.raises(ValueError, match="refusing to overwrite"):
        write_localization_evaluation(evaluation, json_path=json_output, csv_path=csv_output)


def test_load_coco_ground_truth_requires_unique_image_selection(tmp_path: Path) -> None:
    path = tmp_path / "ground-truth.json"
    path.write_text(
        json.dumps(
            {
                "images": [
                    {"id": 1, "file_name": "first.png"},
                    {"id": 2, "file_name": "second.png"},
                ],
                "categories": [{"id": 7, "name": "malicious_evidence"}],
                "annotations": [
                    {"image_id": 1, "category_id": 7, "bbox": [1, 2, 3, 4]},
                    {"image_id": 2, "category_id": 7, "bbox": [5, 6, 7, 8]},
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="image-name"):
        load_ground_truth_boxes(path)

    boxes = load_ground_truth_boxes(path, image_name="SECOND.PNG")
    assert boxes == (LocalizationBox("malicious_evidence", 7, (5.0, 6.0, 7.0, 8.0)),)
