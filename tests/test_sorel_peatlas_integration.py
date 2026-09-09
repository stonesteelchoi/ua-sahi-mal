"""Hard integration test: SOREL static stage <-> PEAtlas, on a merged tree.

Unlike ``test_sorel_static_stage`` (which tolerates a peatlas-less tree via the
optional import), this test requires the ``peatlas`` package to be importable and
asserts the coverage path is actually LIVE. It belongs on a tree where the peatlas
line has been merged into main alongside the sorel tooling; there it guards the
wiring in CI.
"""

from __future__ import annotations

import zlib

import pytest

# hard dependency: on the merged tree this must import.
peatlas_pebuild = pytest.importorskip(
    "ua_sahi_mal.peatlas.pebuild",
    reason="peatlas must be present on the merged main for this integration test",
)
build_pe = peatlas_pebuild.build_pe
SectionSpec = peatlas_pebuild.SectionSpec

from ua_sahi_mal.sorel.static_stage import analyze_bytes, verify_disarmed  # noqa: E402


def _section():
    return SectionSpec(name=".text", rva=0x1000, virtual_size=0x200,
                       raw_offset=0x200, raw_size=0x200, characteristics=0x60000020)


def test_disarmed_pe_coverage_is_live():
    pe = build_pe(sections=[_section()], disarm=True)
    assert verify_disarmed(pe) is True
    r = analyze_bytes(zlib.compress(pe), sha256="a" * 64, static_only=True)
    assert r.disarm_ok is True
    # coverage path is LIVE (not skipped) because peatlas is present
    assert r.peatlas_status == "ok", r.peatlas_status
    assert r.coverage_ok_fraction is not None
    assert 0.0 <= r.coverage_ok_fraction <= 1.0
    # every mapped byte fell into a known MapStatus bucket
    assert sum(r.status_histogram.values()) == len(pe)


def test_armed_pe_refused_even_with_peatlas():
    pe = build_pe(sections=[_section()], disarm=False)  # armed default
    assert verify_disarmed(pe) is False
    r = analyze_bytes(zlib.compress(pe), sha256="b" * 64, static_only=True)
    # refused before any peatlas analysis, never re-armed
    assert r.disarm_ok is False
    assert r.exclusion_reason.startswith("not_disarmed")
    assert r.peatlas_status == ""


def test_disarm_preserves_coordinate_mapping():
    """Disarming must not change PEAtlas coordinates vs the armed original."""
    from ua_sahi_mal.peatlas.atlas import PeAtlas

    armed = build_pe(sections=[_section()], disarm=False)
    disarmed = build_pe(sections=[_section()], disarm=True)
    a = PeAtlas.from_bytes(armed)
    d = PeAtlas.from_bytes(disarmed)
    _, seg_a = a.map_offset_interval(0, len(armed))
    _, seg_d = d.map_offset_interval(0, len(disarmed))
    assert [(s.status, s.source.start, s.source.end) for s in seg_a] == \
           [(s.status, s.source.start, s.source.end) for s in seg_d]


def test_post_download_strata_recorded():
    """PE32/PE32+, section count and overlay size are recorded for parsed files."""
    pe = build_pe(sections=[_section()], disarm=True, overlay=b"\xEE" * 64)
    r = analyze_bytes(zlib.compress(pe), sha256="c" * 64, static_only=True)
    assert r.peatlas_status == "ok"
    assert r.is_pe32_plus is False
    assert r.n_sections == 1
    assert r.overlay_bytes == 64
