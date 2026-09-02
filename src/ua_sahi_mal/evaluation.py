"""Pure evaluation helpers for the UA-SAHI-MAL experiment protocol."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

from ua_sahi_mal.strategies import BBoxXYXY, Tile


def _intersection_area(left: BBoxXYXY, right: BBoxXYXY) -> float:
    return max(0.0, min(left[2], right[2]) - max(left[0], right[0])) * max(
        0.0, min(left[3], right[3]) - max(left[1], right[1])
    )


def tile_recall(
    selected_tiles: Sequence[Tile],
    ground_truth_boxes: Sequence[BBoxXYXY],
    *,
    minimum_object_coverage: float = 0.5,
) -> float:
    """Return the fraction of GT objects sufficiently covered by one selected tile."""

    if not 0 < minimum_object_coverage <= 1:
        raise ValueError("minimum_object_coverage must be in (0, 1]")
    if not ground_truth_boxes:
        return 1.0
    covered = 0
    tile_boxes = [tuple(float(value) for value in tile.bbox_xyxy) for tile in selected_tiles]
    for ground_truth in ground_truth_boxes:
        x1, y1, x2, y2 = ground_truth
        area = (x2 - x1) * (y2 - y1)
        if area <= 0:
            raise ValueError("ground-truth boxes must have positive area")
        best_coverage = max(
            (_intersection_area(ground_truth, tile_box) / area for tile_box in tile_boxes),
            default=0.0,
        )
        if best_coverage >= minimum_object_coverage:
            covered += 1
    return covered / len(ground_truth_boxes)


def detector_call_reduction(full_calls: int, selected_calls: int) -> float:
    if full_calls < 1:
        raise ValueError("full_calls must be positive")
    if not 0 <= selected_calls <= full_calls:
        raise ValueError("selected_calls must be between zero and full_calls")
    return 1 - selected_calls / full_calls


def latency_reduction(full_latency_ms: float, selected_latency_ms: float) -> float:
    if full_latency_ms <= 0 or selected_latency_ms < 0:
        raise ValueError("latencies must be non-negative and the baseline must be positive")
    return 1 - selected_latency_ms / full_latency_ms


@dataclass(frozen=True)
class PrimarySuccessCriteria:
    """Pre-registered thresholds from the project plan."""

    maximum_ap_s_loss_points: float = 1.5
    minimum_detector_call_reduction: float = 0.40
    minimum_latency_reduction: float = 0.25


@dataclass(frozen=True)
class SuccessAssessment:
    accuracy_non_inferior: bool
    detector_calls_improved: bool
    latency_improved: bool

    @property
    def passed(self) -> bool:
        return self.accuracy_non_inferior and self.detector_calls_improved and self.latency_improved


DEFAULT_PRIMARY_SUCCESS_CRITERIA = PrimarySuccessCriteria()


def assess_primary_success(
    *,
    full_sahi_ap_s: float,
    candidate_ap_s: float,
    full_sahi_detector_calls: int,
    candidate_detector_calls: int,
    full_sahi_latency_ms: float,
    candidate_latency_ms: float,
    ap_scale: str,
    criteria: PrimarySuccessCriteria = DEFAULT_PRIMARY_SUCCESS_CRITERIA,
) -> SuccessAssessment:
    """Assess all primary gates without silently substituting another metric."""

    if not math.isfinite(full_sahi_ap_s) or not math.isfinite(candidate_ap_s):
        raise ValueError("AP_S values must be finite")
    if ap_scale == "points_0_100":
        if not 0 <= full_sahi_ap_s <= 100 or not 0 <= candidate_ap_s <= 100:
            raise ValueError("points_0_100 AP_S values must be in [0, 100]")
        ap_loss_points = full_sahi_ap_s - candidate_ap_s
    elif ap_scale == "fraction_0_1":
        if not 0 <= full_sahi_ap_s <= 1 or not 0 <= candidate_ap_s <= 1:
            raise ValueError("fraction_0_1 AP_S values must be in [0, 1]")
        ap_loss_points = (full_sahi_ap_s - candidate_ap_s) * 100
    else:
        raise ValueError("ap_scale must be points_0_100 or fraction_0_1")
    return SuccessAssessment(
        accuracy_non_inferior=ap_loss_points <= criteria.maximum_ap_s_loss_points + 1e-12,
        detector_calls_improved=(
            detector_call_reduction(full_sahi_detector_calls, candidate_detector_calls)
            >= criteria.minimum_detector_call_reduction
        ),
        latency_improved=(
            latency_reduction(full_sahi_latency_ms, candidate_latency_ms)
            >= criteria.minimum_latency_reduction
        ),
    )


@dataclass(frozen=True)
class LocalizationBox:
    label: str
    category_id: int | None
    bbox_xywh: tuple[float, float, float, float]
    confidence: float | None = None


@dataclass(frozen=True)
class LocalizationMatch:
    prediction_index: int
    ground_truth_index: int
    label: str
    confidence: float
    iou: float
    class_match: bool


@dataclass(frozen=True)
class LocalizationEvaluation:
    iou_threshold: float
    predictions: int
    ground_truth: int
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float
    matches: tuple[LocalizationMatch, ...]
    class_mismatches: tuple[LocalizationMatch, ...]
    false_positive_records: tuple[LocalizationBox, ...]
    false_negative_records: tuple[LocalizationBox, ...]


def bbox_iou_xywh(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    for box in (left, right):
        if len(box) != 4 or any(not math.isfinite(value) for value in box):
            raise ValueError("bbox must contain four finite values")
        if box[0] < 0 or box[1] < 0 or box[2] <= 0 or box[3] <= 0:
            raise ValueError("bbox origin must be non-negative and size must be positive")
    left_xyxy = (left[0], left[1], left[0] + left[2], left[1] + left[3])
    right_xyxy = (right[0], right[1], right[0] + right[2], right[1] + right[3])
    intersection = _intersection_area(left_xyxy, right_xyxy)
    if intersection <= 0:
        return 0.0
    left_area = left[2] * left[3]
    right_area = right[2] * right[3]
    return intersection / (left_area + right_area - intersection)


def _localization_box(
    raw: Any,
    *,
    context: str,
    category_names: dict[int, str] | None = None,
    prediction: bool,
) -> LocalizationBox:
    if not isinstance(raw, dict):
        raise ValueError(f"{context} must be an object")
    bbox = raw.get("bbox", raw.get("bbox_xywh"))
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise ValueError(f"{context}.bbox must contain [x, y, width, height]")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in bbox):
        raise ValueError(f"{context}.bbox values must be numbers")
    values = tuple(float(value) for value in bbox)
    bbox_iou_xywh(values, values)
    category_id = raw.get("category_id", raw.get("class_id"))
    if category_id is not None and (isinstance(category_id, bool) or not isinstance(category_id, int)):
        raise ValueError(f"{context}.category_id must be an integer")
    label = raw.get("category_name", raw.get("class_name"))
    if label is None and category_names is not None and category_id in category_names:
        label = category_names[category_id]
    if label is None and category_id is not None:
        label = f"id:{category_id}"
    if not isinstance(label, str) or not label.strip():
        raise ValueError(f"{context} requires category/class name or id")
    confidence: float | None = None
    if prediction:
        raw_confidence = raw.get("score", raw.get("confidence"))
        if isinstance(raw_confidence, bool) or not isinstance(raw_confidence, (int, float)):
            raise ValueError(f"{context}.score must be a number in [0, 1]")
        confidence = float(raw_confidence)
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError(f"{context}.score must be a number in [0, 1]")
    return LocalizationBox(
        label=label.strip(),
        category_id=category_id,
        bbox_xywh=values,  # type: ignore[arg-type]
        confidence=confidence,
    )


def load_prediction_boxes(path: Path) -> tuple[LocalizationBox, ...]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read predictions JSON: {exc}") from exc
    if not isinstance(document, list):
        raise ValueError("predictions JSON must be an array")
    return tuple(
        _localization_box(item, context=f"predictions[{index}]", prediction=True)
        for index, item in enumerate(document)
    )


def load_ground_truth_boxes(
    path: Path,
    *,
    image_name: str | None = None,
) -> tuple[LocalizationBox, ...]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read ground-truth JSON: {exc}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("annotations"), list):
        raise ValueError("ground truth must be expected.json or a COCO object with annotations")
    categories: dict[int, str] = {}
    for index, category in enumerate(document.get("categories", [])):
        if not isinstance(category, dict) or not isinstance(category.get("id"), int):
            raise ValueError(f"categories[{index}] is invalid")
        categories[category["id"]] = str(category.get("name", f"id:{category['id']}"))
    records = document["annotations"]
    if isinstance(document.get("images"), list):
        images = document["images"]
        if image_name is None:
            if len(images) != 1:
                raise ValueError("--image-name is required for a multi-image COCO ground truth")
            image_id = images[0].get("id")
        else:
            matches = [
                item
                for item in images
                if isinstance(item, dict)
                and Path(str(item.get("file_name", ""))).name.casefold()
                == Path(image_name).name.casefold()
            ]
            if len(matches) != 1:
                raise ValueError(f"COCO ground truth has no unique image named {image_name!r}")
            image_id = matches[0].get("id")
        records = [item for item in records if isinstance(item, dict) and item.get("image_id") == image_id]
    elif image_name is not None and document.get("image") is not None:
        if Path(str(document["image"])).name.casefold() != Path(image_name).name.casefold():
            raise ValueError("fixture ground-truth image does not match --image-name")
    return tuple(
        _localization_box(
            item,
            context=f"ground_truth.annotations[{index}]",
            category_names=categories,
            prediction=False,
        )
        for index, item in enumerate(records)
    )


def evaluate_localization(
    predictions: Sequence[LocalizationBox],
    ground_truth: Sequence[LocalizationBox],
    *,
    iou_threshold: float = 0.5,
) -> LocalizationEvaluation:
    if not 0 < iou_threshold <= 1:
        raise ValueError("iou_threshold must be in (0, 1]")
    ranked_predictions = sorted(
        enumerate(predictions),
        key=lambda item: (-(item[1].confidence or 0.0), item[0]),
    )
    unmatched_ground_truth = set(range(len(ground_truth)))
    unmatched_predictions: set[int] = set(range(len(predictions)))
    matches: list[LocalizationMatch] = []
    for prediction_index, prediction in ranked_predictions:
        compatible = [
            index
            for index in unmatched_ground_truth
            if ground_truth[index].label.casefold() == prediction.label.casefold()
        ]
        if not compatible:
            continue
        best_index = max(
            compatible,
            key=lambda index: (
                bbox_iou_xywh(prediction.bbox_xywh, ground_truth[index].bbox_xywh),
                -index,
            ),
        )
        best_iou = bbox_iou_xywh(prediction.bbox_xywh, ground_truth[best_index].bbox_xywh)
        if best_iou < iou_threshold:
            continue
        unmatched_ground_truth.remove(best_index)
        unmatched_predictions.remove(prediction_index)
        matches.append(
            LocalizationMatch(
                prediction_index=prediction_index,
                ground_truth_index=best_index,
                label=prediction.label,
                confidence=float(prediction.confidence or 0.0),
                iou=best_iou,
                class_match=True,
            )
        )

    class_mismatches: list[LocalizationMatch] = []
    remaining_ground_truth = set(unmatched_ground_truth)
    for prediction_index in sorted(unmatched_predictions):
        if not remaining_ground_truth:
            break
        prediction = predictions[prediction_index]
        best_index = max(
            remaining_ground_truth,
            key=lambda index: (
                bbox_iou_xywh(prediction.bbox_xywh, ground_truth[index].bbox_xywh),
                -index,
            ),
        )
        best_iou = bbox_iou_xywh(prediction.bbox_xywh, ground_truth[best_index].bbox_xywh)
        if (
            best_iou >= iou_threshold
            and prediction.label.casefold() != ground_truth[best_index].label.casefold()
        ):
            class_mismatches.append(
                LocalizationMatch(
                    prediction_index=prediction_index,
                    ground_truth_index=best_index,
                    label=f"{prediction.label} -> {ground_truth[best_index].label}",
                    confidence=float(prediction.confidence or 0.0),
                    iou=best_iou,
                    class_match=False,
                )
            )
            remaining_ground_truth.remove(best_index)

    true_positives = len(matches)
    false_positives = len(predictions) - true_positives
    false_negatives = len(ground_truth) - true_positives
    precision = (
        true_positives / (true_positives + false_positives)
        if true_positives + false_positives
        else (1.0 if not ground_truth else 0.0)
    )
    recall = (
        true_positives / (true_positives + false_negatives)
        if true_positives + false_negatives
        else 1.0
    )
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return LocalizationEvaluation(
        iou_threshold=iou_threshold,
        predictions=len(predictions),
        ground_truth=len(ground_truth),
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        precision=precision,
        recall=recall,
        f1=f1,
        matches=tuple(matches),
        class_mismatches=tuple(class_mismatches),
        false_positive_records=tuple(predictions[index] for index in sorted(unmatched_predictions)),
        false_negative_records=tuple(ground_truth[index] for index in sorted(unmatched_ground_truth)),
    )


def write_localization_evaluation(
    evaluation: LocalizationEvaluation,
    *,
    json_path: Path,
    csv_path: Path | None = None,
) -> None:
    for output in (json_path, csv_path):
        if output is not None and output.exists():
            raise ValueError(f"refusing to overwrite localization evaluation: {output}")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(asdict(evaluation), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if csv_path is None:
        return
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=(
                "status",
                "prediction_index",
                "ground_truth_index",
                "label",
                "confidence",
                "iou",
                "class_match",
            ),
        )
        writer.writeheader()
        for match in evaluation.matches:
            writer.writerow({"status": "true_positive", **asdict(match)})
        for mismatch in evaluation.class_mismatches:
            writer.writerow({"status": "class_mismatch", **asdict(mismatch)})
        for index, record in enumerate(evaluation.false_positive_records):
            writer.writerow(
                {
                    "status": "false_positive",
                    "prediction_index": index,
                    "label": record.label,
                    "confidence": record.confidence,
                    "class_match": False,
                }
            )
        for index, record in enumerate(evaluation.false_negative_records):
            writer.writerow(
                {
                    "status": "false_negative",
                    "ground_truth_index": index,
                    "label": record.label,
                    "class_match": False,
                }
            )
