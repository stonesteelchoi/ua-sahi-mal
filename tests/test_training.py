import csv
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import ua_sahi_mal.training as training
from ua_sahi_mal.training import (
    YoloEvaluateConfig,
    evaluate_yolo,
    evaluation_metrics_document,
)


def _dataset_yaml(tmp_path: Path) -> Path:
    path = tmp_path / "dataset.yaml"
    path.write_text("names: [malicious_evidence]\n", encoding="utf-8")
    return path


def test_evaluate_yolo_exports_stable_json_and_csv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = SimpleNamespace(
        results_dict={"metrics/precision(B)": 0.8, "ignored": "not-a-number"},
        box=SimpleNamespace(map=0.51, map50=0.72, map75=0.42),
        speed={"inference": 2.5, "invalid": float("nan")},
    )
    calls: list[tuple[str, dict[str, object]]] = []

    class FakeYolo:
        def __init__(self, model: str) -> None:
            calls.append((model, {}))

        def val(self, **kwargs):
            calls[0][1].update(kwargs)
            return result

    monkeypatch.setattr(training, "_ultralytics_yolo", lambda: FakeYolo)
    json_path = tmp_path / "metrics.json"
    csv_path = tmp_path / "metrics.csv"
    config = YoloEvaluateConfig(
        data=_dataset_yaml(tmp_path),
        model="best.pt",
        split="test",
        image_size=320,
        batch_size=4,
        device="cpu",
        metrics_json=json_path,
        metrics_csv=csv_path,
        dataset_revision="decode-r1",
    )

    returned = evaluate_yolo(config)
    document = json.loads(json_path.read_text(encoding="utf-8"))
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))

    assert returned is result
    assert calls == [
        (
            "best.pt",
            {
                "data": str(config.data),
                "split": "test",
                "imgsz": 320,
                "batch": 4,
                "device": "cpu",
                "project": "runs\\val" if "\\" in str(config.project) else "runs/val",
                "name": "ua-sahi-mal-evaluation",
                "plots": False,
            },
        )
    ]
    assert document["schema"] == "ua-sahi-mal-yolo-evaluation-v1"
    assert document["dataset_revision"] == "decode-r1"
    assert document["metrics"]["box_map50_95"] == pytest.approx(0.51)
    assert "ignored" not in document["metrics"]
    assert document["speed_ms_per_image"] == {"inference": 2.5}
    assert {row["metric"] for row in rows} >= {"box_map50_95", "inference"}


def test_evaluation_metrics_document_marks_unmeasured_routing_metrics(tmp_path: Path) -> None:
    config = YoloEvaluateConfig(data=_dataset_yaml(tmp_path), model="best.pt")

    document = evaluation_metrics_document(SimpleNamespace(), config)

    assert document["measured"] is True
    assert document["metrics"] == {}
    assert document["speed_ms_per_image"] == {}
    assert document["notes"]["tile_recall"].startswith("not measured")
    assert document["notes"]["vram"].startswith("not measured")


def test_evaluate_config_rejects_colliding_or_existing_output_paths(tmp_path: Path) -> None:
    data = _dataset_yaml(tmp_path)
    same = tmp_path / "metrics.out"
    config = YoloEvaluateConfig(data=data, model="best.pt", metrics_json=same, metrics_csv=same)

    with pytest.raises(ValueError, match="different files"):
        config.validate()

    existing = tmp_path / "existing.json"
    existing.write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError, match="refusing to overwrite"):
        YoloEvaluateConfig(data=data, model="best.pt", metrics_json=existing).validate()
