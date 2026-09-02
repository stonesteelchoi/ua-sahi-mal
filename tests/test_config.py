from pathlib import Path

import pytest

from ua_sahi_mal.config import PredictConfig


def test_predict_config_accepts_valid_values(tmp_path: Path) -> None:
    source = tmp_path / "image.jpg"
    source.touch()

    PredictConfig(source=source).validate()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("route_scale", 1),
        ("overlap", 1.0),
        ("budget", 0.0),
        ("confidence", 1.1),
        ("coverage_ratio", -0.1),
        ("batch_size", 0),
    ],
)
def test_predict_config_rejects_invalid_values(tmp_path: Path, field: str, value: object) -> None:
    source = tmp_path / "image.jpg"
    source.touch()
    values = {field: value}

    with pytest.raises(ValueError):
        PredictConfig(source=source, **values).validate()


def test_routing_threshold_cannot_exceed_final_threshold(tmp_path: Path) -> None:
    source = tmp_path / "image.jpg"
    source.touch()

    with pytest.raises(ValueError, match="route_confidence"):
        PredictConfig(source=source, confidence=0.25, route_confidence=0.5).validate()
