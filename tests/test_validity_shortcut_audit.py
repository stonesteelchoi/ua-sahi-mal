from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_validity_shortcut.py"
SPEC = importlib.util.spec_from_file_location("audit_validity_shortcut", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def test_nearest_centroid_exposes_a_perfect_scalar_shortcut():
    train = [
        {"label": 0, "valid_fraction": 0.1},
        {"label": 0, "valid_fraction": 0.2},
        {"label": 1, "valid_fraction": 0.8},
        {"label": 1, "valid_fraction": 0.9},
    ]
    test = [
        {"label": 0, "valid_fraction": 0.15},
        {"label": 1, "valid_fraction": 0.85},
    ]

    accuracy, centroids = audit.nearest_centroids(train, test)

    assert accuracy == pytest.approx(1.0)
    assert centroids == pytest.approx({0: 0.15, 1: 0.85})
