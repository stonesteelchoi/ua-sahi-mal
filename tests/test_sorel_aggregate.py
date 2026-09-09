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


def test_aggregate_e1_gate_and_distributions():
    rs = [
        StaticResult(sorel_original_sha256="a" * 64, decompressed_size=1000, disarm_ok=True,
                     peatlas_status="ok", coverage_ok_fraction=0.9, status_histogram={"ok": 900, "overlay": 100},
                     overlay_bytes=100, roundtrip_points=30, roundtrip_errors=0,
                     pixel_roundtrip_points=60, pixel_roundtrip_errors=0,
                     independent_parser_status="ok", independent_raw_agreement=True),
        StaticResult(sorel_original_sha256="b" * 64, decompressed_size=4000, disarm_ok=True,
                     peatlas_status="ok", coverage_ok_fraction=0.2, status_histogram={"ok": 800, "overlay": 3200},
                     overlay_bytes=3200, roundtrip_points=12, roundtrip_errors=0,
                     pixel_roundtrip_points=24, pixel_roundtrip_errors=0,
                     independent_parser_status="mismatch:section_count ours=2 pefile=0",
                     independent_raw_agreement=True),
    ]
    s = summarize(rs)
    assert s["roundtrip_points"] == 42 and s["roundtrip_errors"] == 0
    assert s["pixel_roundtrip_points"] == 84 and s["pixel_roundtrip_errors"] == 0
    # strict agreement 1/2, mapping-relevant agreement 2/2
    assert s["independent_agree_rate"] == pytest.approx(0.5)
    assert s["independent_raw_agreement_rate"] == pytest.approx(1.0)
    # byte-weighted coverage = (900+800)/5000
    assert s["total_decompressed_bytes"] == 5000
    assert s["coverage_byte_weighted"] == pytest.approx(0.34)
    assert s["coverage_quantiles"]["p50"] in (0.2, 0.9)
    assert s["overlay_dominant_count"] == 1
    assert s["overlay_share_quantiles"]["p90"] == pytest.approx(0.8)
    assert_no_sample_link(s)
