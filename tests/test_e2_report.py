"""E2 aggregation + pre-registered gate + leak guards (E2_prereg_v1)."""

from __future__ import annotations

import numpy as np
import pytest

from ua_sahi_mal.sorel.e2_report import (
    SampleLinkedLeakError,
    _holm,
    assert_no_sample_link,
    build_report,
)

_ALL = ("random", "uniform", "front_first", "back_first", "entropy", "entropy_boundary", "oracle_silver")


def _file(stratum: str, cov: dict[str, float]) -> dict:
    return {
        "ok": True, "stratum": stratum, "silver": {"capa_status": "ok"},
        "evaluation": {"has_silver": True,
                       "selectors": {n: {"0.10": {"coverage": float(cov.get(n, 0.0))}} for n in _ALL}},
    }


def _cohort(stratum: str, entropy_mu: float, base_mu: float, rng, n: int = 30) -> list[dict]:
    files = []
    for _ in range(n):
        cov = {
            "entropy": float(np.clip(entropy_mu + rng.normal(0, 0.05), 0, 1)),
            "entropy_boundary": float(np.clip(entropy_mu - 0.1 + rng.normal(0, 0.05), 0, 1)),
            "random": float(np.clip(base_mu + rng.normal(0, 0.05), 0, 1)),
            "front_first": float(np.clip(base_mu + rng.normal(0, 0.05), 0, 1)),
            "oracle_silver": 1.0,
        }
        files.append(_file(stratum, cov))
    return files


def test_gate_pass_when_byte_scope_beats_baselines_both_strata():
    rng = np.random.default_rng(0)
    results = _cohort("overlay_dominant", 0.80, 0.10, rng) + _cohort("non_dominant", 0.75, 0.15, rng)
    report = build_report(results, iterations=400, seed=1)
    assert report["gate"]["gate_pass"] is True
    assert report["gate"]["overlay_dominant_beats_front_first"] is True
    assert set(report["strata"]["overlay_dominant"]["winning_selectors"]) >= {"entropy"}


def test_gate_fail_when_no_separation():
    rng = np.random.default_rng(0)
    results = _cohort("overlay_dominant", 0.12, 0.10, rng) + _cohort("non_dominant", 0.12, 0.10, rng)
    report = build_report(results, iterations=400, seed=1)
    assert report["gate"]["gate_pass"] is False


def test_holm_step_down():
    assert _holm([0.001, 0.02, 0.5]) == [True, True, False]
    assert _holm([0.5, 0.5, 0.5]) == [False, False, False]


def test_leak_guards():
    with pytest.raises(SampleLinkedLeakError):
        assert_no_sample_link({"x": "a" * 64})
    with pytest.raises(SampleLinkedLeakError):
        assert_no_sample_link({"union_intervals": [[0, 1]]})


def test_report_is_sha_free_by_construction():
    rng = np.random.default_rng(0)
    results = _cohort("overlay_dominant", 0.5, 0.1, rng, n=5) + _cohort("non_dominant", 0.5, 0.1, rng, n=5)
    report = build_report(results, iterations=200, seed=1)  # build_report calls assert_no_sample_link
    assert report["publication_scope"] == "INTERNAL_ONLY"


def _file_v3(stratum: str, cov: dict[str, float]) -> dict:
    names = _ALL + ("attr_tile_conf", "attr_occlusion", "mil_attention", "position_only")
    return {
        "ok": True, "stratum": stratum, "silver": {"capa_status": "disabled"},
        "evaluation": {"has_silver": True,
                       "selectors": {n: {"0.10": {"coverage": float(cov.get(n, 0.0))}} for n in names}},
    }


def test_v3_gate_learned_beats_front_first_in_overlay():
    from ua_sahi_mal.sorel.e2_report import LEARNED_SELECTORS
    rng = np.random.default_rng(1)
    results = []
    for stratum, learned_mu, front_mu in (("overlay_dominant", 0.7, 0.3), ("non_dominant", 0.6, 0.2)):
        for _ in range(30):
            results.append(_file_v3(stratum, {
                "attr_occlusion": float(np.clip(learned_mu + rng.normal(0, 0.05), 0, 1)),
                "attr_tile_conf": float(np.clip(learned_mu - 0.2 + rng.normal(0, 0.05), 0, 1)),
                "mil_attention": float(np.clip(learned_mu - 0.1 + rng.normal(0, 0.05), 0, 1)),
                "front_first": float(np.clip(front_mu + rng.normal(0, 0.05), 0, 1)),
                "entropy_boundary": float(np.clip(front_mu + rng.normal(0, 0.05), 0, 1)),
                "random": 0.1, "position_only": float(np.clip(front_mu + 0.05 + rng.normal(0, 0.05), 0, 1)),
            }))
    rep = build_report(results, prereg_version="E2_prereg_v3", iterations=300, seed=2,
                       learned=LEARNED_SELECTORS, best_learned="attr_occlusion")
    gate = rep["gate"]
    assert gate["gate_pass"] is True and gate["primary_overlay_beats_front_first"] is True
    assert gate["strong_content_test_overlay_beats_position_only"] is True
    assert "position_only" in rep["strata"]["overlay_dominant"]["coverage_mean"]
    # without a validation-chosen best selector the gate is undecided, never silently passed
    undecided = build_report(results, iterations=200, seed=2, learned=LEARNED_SELECTORS)
    assert undecided["gate"]["gate_pass"] is None
