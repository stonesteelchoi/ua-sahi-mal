import csv
import json
from pathlib import Path

import pytest

from ua_sahi_mal.paper_results import (
    PaperResultError,
    load_paper_table,
    paper_table_template,
    validate_paper_table,
    write_paper_table,
)


def _template() -> dict:
    return paper_table_template(
        experiment_id="decode-primary-v1",
        dataset_revision="decode-static-v1",
        checkpoint_sha256="a" * 64,
    )


def _measure(document: dict, strategy: str, metric: str, value: float | int) -> None:
    row = next(item for item in document["rows"] if item["strategy"] == strategy)
    row["metrics"][metric]["status"] = "measured"
    row["metrics"][metric]["value"] = value
    row["execution_status"] = "partial"


def test_template_never_fabricates_measurements() -> None:
    document = validate_paper_table(_template())

    assert all(
        cell["value"] is None
        for row in document["rows"]
        for cell in row["metrics"].values()
    )
    assert document["primary_assessments"]["jbu-50"]["status"] == "not_measured"
    full_image = next(row for row in document["rows"] if row["strategy"] == "full-image")
    assert full_image["metrics"]["tile_recall"]["status"] == "not_applicable"


def test_primary_gate_is_calculated_only_from_measured_cells() -> None:
    document = _template()
    _measure(document, "full-sahi-100", "ap_s", 0.50)
    _measure(document, "full-sahi-100", "detector_images", 100)
    _measure(document, "full-sahi-100", "latency_p95_ms", 100.0)
    _measure(document, "jbu-50", "ap_s", 0.49)
    _measure(document, "jbu-50", "detector_images", 50)
    _measure(document, "jbu-50", "latency_p95_ms", 70.0)

    validated = validate_paper_table(document)

    assessment = validated["primary_assessments"]["jbu-50"]
    assert assessment == {
        "status": "measured",
        "accuracy_non_inferior": True,
        "detector_calls_improved": True,
        "latency_improved": True,
        "passed": True,
    }
    assert validated["primary_assessments"]["ua-sahi-mal-50"]["status"] == "not_measured"


def test_measured_status_requires_numeric_value() -> None:
    document = _template()
    row = next(item for item in document["rows"] if item["strategy"] == "jbu-50")
    row["metrics"]["ap_s"]["status"] = "measured"

    with pytest.raises(PaperResultError, match="numeric when measured"):
        validate_paper_table(document)


def test_load_and_write_paper_table_preserves_explicit_statuses(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    source.write_text(json.dumps(_template()), encoding="utf-8")
    output_json = tmp_path / "compiled.json"
    output_csv = tmp_path / "compiled.csv"

    write_paper_table(
        load_paper_table(source),
        json_path=output_json,
        csv_path=output_csv,
    )

    compiled = json.loads(output_json.read_text(encoding="utf-8"))
    rows = list(csv.DictReader(output_csv.open(encoding="utf-8")))
    assert compiled["schema"] == "ua-sahi-mal-paper-table-v1"
    assert rows[0]["ap_s"] == ""
    assert rows[0]["ap_s_status"] == "not_measured"
    assert rows[1]["primary_gate_status"] == "not_applicable"

    with pytest.raises(PaperResultError, match="refusing to overwrite"):
        write_paper_table(compiled, json_path=output_json, csv_path=tmp_path / "other.csv")
