"""Strict, non-fabricating result tables for the paper experiment matrix."""

from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ua_sahi_mal.evaluation import assess_primary_success

SCHEMA = "ua-sahi-mal-paper-table-v1"
REQUIRED_STRATEGIES = (
    "full-image",
    "full-sahi-100",
    "bilinear-50",
    "jbu-50",
    "ua-sahi-mal-50",
)
METRIC_UNITS = {
    "ap50": "fraction_0_1",
    "ap_s": "fraction_0_1",
    "map50_95": "fraction_0_1",
    "tile_recall": "fraction_0_1",
    "precision": "fraction_0_1",
    "recall": "fraction_0_1",
    "f1": "fraction_0_1",
    "false_negative_rate": "fraction_0_1",
    "detector_images": "count",
    "detector_invocations": "count",
    "latency_p50_ms": "milliseconds",
    "latency_p95_ms": "milliseconds",
    "peak_vram_mib": "mebibytes",
}
METRIC_STATUSES = frozenset({"measured", "not_measured", "not_applicable", "failed"})
ROW_STATUSES = frozenset({"measured", "partial", "not_executed", "failed"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class PaperResultError(ValueError):
    """Raised when a paper-table artifact would be ambiguous or misleading."""


def _metric_cell(unit: str, *, status: str = "not_measured") -> dict[str, Any]:
    return {"value": None, "status": status, "unit": unit}


def paper_table_template(
    *,
    experiment_id: str,
    dataset_revision: str,
    checkpoint_sha256: str | None,
) -> dict[str, Any]:
    """Return a table whose unexecuted cells are explicitly unmeasured."""

    descriptions = {
        "full-image": ("full-image", "none", 1.0),
        "full-sahi-100": ("all-tiles", "none", 1.0),
        "bilinear-50": ("dense-pre-nms", "bilinear", 0.5),
        "jbu-50": ("dense-pre-nms", "anisotropic-jbu", 0.5),
        "ua-sahi-mal-50": ("dense-pre-nms", "official-upa", 0.5),
    }
    rows = []
    for strategy in REQUIRED_STRATEGIES:
        coarse_source, upsampler, budget = descriptions[strategy]
        metrics = {
            name: _metric_cell(
                unit,
                status=(
                    "not_applicable"
                    if strategy == "full-image" and name == "tile_recall"
                    else "not_measured"
                ),
            )
            for name, unit in METRIC_UNITS.items()
        }
        rows.append(
            {
                "strategy": strategy,
                "coarse_source": coarse_source,
                "upsampler": upsampler,
                "budget_fraction": budget,
                "execution_status": "not_executed",
                "metrics": metrics,
                "notes": "",
            }
        )
    return {
        "schema": SCHEMA,
        "experiment_id": experiment_id,
        "dataset_revision": dataset_revision,
        "checkpoint_sha256": checkpoint_sha256,
        "metric_scale": "fractions use [0, 1]; never mix with percentage points",
        "primary_work_metric": "detector_images",
        "rows": rows,
        "primary_assessments": {},
    }


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PaperResultError(f"JSON contains duplicate key: {key}")
        result[key] = value
    return result


def load_paper_table(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
        )
    except PaperResultError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PaperResultError(f"cannot read paper result JSON: {exc}") from exc
    return validate_paper_table(document)


def _validate_metric(name: str, raw: Any, context: str) -> float | int | None:
    if not isinstance(raw, dict) or set(raw) != {"value", "status", "unit"}:
        raise PaperResultError(f"{context}.{name} must contain value, status, and unit")
    if raw["unit"] != METRIC_UNITS[name]:
        raise PaperResultError(f"{context}.{name}.unit must be {METRIC_UNITS[name]!r}")
    status = raw["status"]
    if status not in METRIC_STATUSES:
        raise PaperResultError(f"{context}.{name}.status is invalid")
    value = raw["value"]
    if status == "measured":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise PaperResultError(f"{context}.{name}.value must be numeric when measured")
        number = float(value)
        if not math.isfinite(number):
            raise PaperResultError(f"{context}.{name}.value must be finite")
        if METRIC_UNITS[name] == "fraction_0_1" and not 0 <= number <= 1:
            raise PaperResultError(f"{context}.{name}.value must be in [0, 1]")
        if METRIC_UNITS[name] in {"milliseconds", "mebibytes", "count"} and number < 0:
            raise PaperResultError(f"{context}.{name}.value must be non-negative")
        if METRIC_UNITS[name] == "count":
            if not number.is_integer():
                raise PaperResultError(f"{context}.{name}.value must be an integer count")
            return int(number)
        return number
    if value is not None:
        raise PaperResultError(f"{context}.{name}.value must be null unless status is measured")
    return None


def validate_paper_table(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise PaperResultError("paper result must be a JSON object")
    required_root = {
        "schema",
        "experiment_id",
        "dataset_revision",
        "checkpoint_sha256",
        "metric_scale",
        "primary_work_metric",
        "rows",
        "primary_assessments",
    }
    if set(document) != required_root:
        missing = sorted(required_root - set(document))
        unknown = sorted(set(document) - required_root)
        raise PaperResultError(f"paper result root keys differ; missing={missing}, unknown={unknown}")
    if document["schema"] != SCHEMA:
        raise PaperResultError(f"schema must be {SCHEMA!r}")
    if document["metric_scale"] != "fractions use [0, 1]; never mix with percentage points":
        raise PaperResultError("metric_scale must remain the frozen fraction contract")
    for field in ("experiment_id", "dataset_revision"):
        if not isinstance(document[field], str) or not document[field].strip():
            raise PaperResultError(f"{field} must be a non-empty string")
    digest = document["checkpoint_sha256"]
    if digest is not None and (not isinstance(digest, str) or _SHA256.fullmatch(digest) is None):
        raise PaperResultError("checkpoint_sha256 must be null or 64 lowercase hexadecimal characters")
    if document["primary_work_metric"] != "detector_images":
        raise PaperResultError("primary_work_metric must remain detector_images")
    rows = document["rows"]
    if not isinstance(rows, list) or len(rows) != len(REQUIRED_STRATEGIES):
        raise PaperResultError("rows must contain every required strategy exactly once")
    seen: set[str] = set()
    values_by_strategy: dict[str, dict[str, float | int | None]] = {}
    expected_design = {
        "full-image": ("full-image", "none", 1.0),
        "full-sahi-100": ("all-tiles", "none", 1.0),
        "bilinear-50": ("dense-pre-nms", "bilinear", 0.5),
        "jbu-50": ("dense-pre-nms", "anisotropic-jbu", 0.5),
        "ua-sahi-mal-50": ("dense-pre-nms", "official-upa", 0.5),
    }
    for index, row in enumerate(rows):
        context = f"rows[{index}]"
        if not isinstance(row, dict) or set(row) != {
            "strategy",
            "coarse_source",
            "upsampler",
            "budget_fraction",
            "execution_status",
            "metrics",
            "notes",
        }:
            raise PaperResultError(f"{context} has invalid fields")
        strategy = row["strategy"]
        if strategy not in REQUIRED_STRATEGIES or strategy in seen:
            raise PaperResultError(f"{context}.strategy is unknown or duplicated")
        seen.add(strategy)
        expected_coarse, expected_upsampler, expected_budget = expected_design[strategy]
        if row["coarse_source"] != expected_coarse or row["upsampler"] != expected_upsampler:
            raise PaperResultError(f"{context} changes the frozen strategy design")
        if row["execution_status"] not in ROW_STATUSES:
            raise PaperResultError(f"{context}.execution_status is invalid")
        if isinstance(row["budget_fraction"], bool) or not isinstance(
            row["budget_fraction"], (int, float)
        ):
            raise PaperResultError(f"{context}.budget_fraction must be numeric")
        if not 0 < float(row["budget_fraction"]) <= 1:
            raise PaperResultError(f"{context}.budget_fraction must be in (0, 1]")
        if not math.isclose(float(row["budget_fraction"]), expected_budget, abs_tol=1e-12):
            raise PaperResultError(f"{context}.budget_fraction changes the frozen strategy budget")
        if not isinstance(row["metrics"], dict) or set(row["metrics"]) != set(METRIC_UNITS):
            raise PaperResultError(f"{context}.metrics must contain the frozen metric set")
        values_by_strategy[strategy] = {
            name: _validate_metric(name, row["metrics"][name], context)
            for name in METRIC_UNITS
        }
    if seen != set(REQUIRED_STRATEGIES):
        raise PaperResultError("rows do not contain the frozen strategy set")
    document["primary_assessments"] = _primary_assessments(values_by_strategy)
    return document


def _primary_assessments(
    values: dict[str, dict[str, float | int | None]],
) -> dict[str, dict[str, Any]]:
    baseline = values["full-sahi-100"]
    results: dict[str, dict[str, Any]] = {}
    for strategy in ("bilinear-50", "jbu-50", "ua-sahi-mal-50"):
        candidate = values[strategy]
        required = (
            baseline["ap_s"],
            candidate["ap_s"],
            baseline["detector_images"],
            candidate["detector_images"],
            baseline["latency_p95_ms"],
            candidate["latency_p95_ms"],
        )
        if any(value is None for value in required):
            results[strategy] = {
                "status": "not_measured",
                "reason": "AP_S, detector_images, and p95 latency are all required",
            }
            continue
        assessment = assess_primary_success(
            full_sahi_ap_s=float(baseline["ap_s"]),
            candidate_ap_s=float(candidate["ap_s"]),
            full_sahi_detector_calls=int(baseline["detector_images"]),
            candidate_detector_calls=int(candidate["detector_images"]),
            full_sahi_latency_ms=float(baseline["latency_p95_ms"]),
            candidate_latency_ms=float(candidate["latency_p95_ms"]),
            ap_scale="fraction_0_1",
        )
        results[strategy] = {"status": "measured", **asdict(assessment), "passed": assessment.passed}
    return results


def write_paper_table(
    document: dict[str, Any],
    *,
    json_path: Path,
    csv_path: Path,
) -> None:
    for output in (json_path, csv_path):
        if output.exists():
            raise PaperResultError(f"refusing to overwrite paper result output: {output}")
    validated = validate_paper_table(document)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(validated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fieldnames = (
        "strategy",
        "coarse_source",
        "upsampler",
        "budget_fraction",
        "execution_status",
        *tuple(METRIC_UNITS),
        *tuple(f"{name}_status" for name in METRIC_UNITS),
        "primary_gate_status",
        "primary_gate_passed",
        "notes",
    )
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        assessments = validated["primary_assessments"]
        for row in validated["rows"]:
            strategy = row["strategy"]
            assessment = assessments.get(strategy, {})
            output_row = {
                "strategy": strategy,
                "coarse_source": row["coarse_source"],
                "upsampler": row["upsampler"],
                "budget_fraction": row["budget_fraction"],
                "execution_status": row["execution_status"],
                "primary_gate_status": assessment.get("status", "not_applicable"),
                "primary_gate_passed": assessment.get("passed", ""),
                "notes": row["notes"],
            }
            for name in METRIC_UNITS:
                cell = row["metrics"][name]
                output_row[name] = cell["value"] if cell["status"] == "measured" else ""
                output_row[f"{name}_status"] = cell["status"]
            writer.writerow(output_row)
