from pathlib import Path

import pytest

from ua_sahi_mal.experiment import load_experiment_protocol


def test_primary_experiment_example_is_valid() -> None:
    path = Path(__file__).resolve().parents[1] / "configs/experiments/decode_primary.example.yaml"

    protocol = load_experiment_protocol(path)

    assert protocol.success.primary_metric == "AP_S"
    assert protocol.slicing.budget_fraction == 0.5
    assert protocol.success.minimum_detector_call_reduction == 0.4


def test_primary_metric_cannot_be_silently_substituted(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1] / "configs/experiments/decode_primary.example.yaml"
    config = tmp_path / "bad.yaml"
    config.write_text(source.read_text(encoding="utf-8").replace("AP_S", "AP50"), encoding="utf-8")

    with pytest.raises(ValueError, match="primary metric"):
        load_experiment_protocol(config)


def test_duplicate_yaml_key_is_rejected(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1] / "configs/experiments/decode_primary.example.yaml"
    config = tmp_path / "duplicate.yaml"
    config.write_text(
        source.read_text(encoding="utf-8").replace(
            "experiment_id: decode-yolo11-primary-v1",
            "experiment_id: first\nexperiment_id: second",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate key"):
        load_experiment_protocol(config)


def test_unknown_root_key_is_rejected(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1] / "configs/experiments/decode_primary.example.yaml"
    config = tmp_path / "unknown.yaml"
    config.write_text(source.read_text(encoding="utf-8") + "typo_budget: 0.1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unknown experiment config fields"):
        load_experiment_protocol(config)
