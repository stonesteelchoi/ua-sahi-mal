"""Tests for the G0-S aggregate publication gate."""

from __future__ import annotations

import pytest

from ua_sahi_mal.sorel.aggregate import (
    SampleLinkedLeakError,
    assert_no_sample_link,
    build_report,
    summarize,
)
from ua_sahi_mal.sorel.static_stage import StaticResult


def _results():
    return [
        StaticResult(sorel_original_sha256="a" * 64, disarmed_local_sha256="1" * 64,
                     decompressed_size=100, disarm_ok=True, peatlas_status="ok",
                     independent_parser_status="ok", coverage_ok_fraction=0.90,
                     status_histogram={"ok": 90, "overlay": 10}),
        StaticResult(sorel_original_sha256="b" * 64, disarmed_local_sha256="2" * 64,
                     decompressed_size=200, disarm_ok=True, peatlas_status="ok",
                     independent_parser_status="mismatch:section_count",
                     coverage_ok_fraction=0.80, status_histogram={"ok": 160, "padding": 40}),
        StaticResult(sorel_original_sha256="c" * 64, decompressed_size=50, disarm_ok=False,
                     exclusion_reason="not_disarmed:Machine/Subsystem nonzero"),
    ]


def test_summarize_rates():
    s = summarize(_results())
    assert s["n"] == 3
    assert s["disarm_ok_rate"] == pytest.approx(2 / 3, abs=1e-6)
    assert s["decompress_ok_rate"] == pytest.approx(1.0)
    assert s["peatlas_ok_rate"] == pytest.approx(2 / 3, abs=1e-6)
    # 2 considered for independent check (ok + mismatch), 1 agrees
    assert s["independent_considered"] == 2
    assert s["independent_agree_rate"] == pytest.approx(0.5)
    assert s["coverage_mean"] == pytest.approx(0.85, abs=1e-6)
    assert s["coverage_median"] == pytest.approx(0.85, abs=1e-6)
    assert s["status_histogram_bytes"] == {"ok": 250, "overlay": 10, "padding": 40}
    assert s["exclusion_reasons"] == {"not_disarmed": 1}


def test_report_internal_by_default():
    r = build_report(_results())
    assert r["publication_status"] == "INTERNAL_ONLY"
    assert "pending" in r["note"].lower()


def test_report_cleared_with_auth_but_aggregate_only():
    r = build_report(_results(), authorization_ref="LEGAL-2026-014")
    assert r["publication_status"] == "cleared"
    assert r["authorization_ref"] == "LEGAL-2026-014"
    # still no SHA anywhere
    assert_no_sample_link(r)


def test_report_never_contains_sha():
    r = build_report(_results())
    # none of the 64-hex shas from the inputs leak into the aggregate
    assert_no_sample_link(r)


def test_leak_guard_detects_sha():
    bad = {"n": 1, "leaked": "a" * 64}
    with pytest.raises(SampleLinkedLeakError):
        assert_no_sample_link(bad)


def test_empty_results():
    s = summarize([])
    assert s["n"] == 0
    assert s["coverage_mean"] is None
    assert s["disarm_ok_rate"] == 0.0
