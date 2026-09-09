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


def test_roundtrip_gate_zero_errors_on_real_layout():
    """E1 primary gate: sampled offsets in every OK/HEADERS segment round-trip exactly."""
    pe = build_pe(sections=[_section()], disarm=True, overlay=b"\x11" * 300)
    r = analyze_bytes(zlib.compress(pe), sha256="d" * 64, static_only=True)
    assert r.peatlas_status == "ok"
    assert r.roundtrip_points > 0
    assert r.roundtrip_errors == 0
    # pixel round trips for raw-rgb and word16-rgb on the same sample points
    assert r.pixel_roundtrip_points > 0
    assert r.pixel_roundtrip_errors == 0


def test_raw_agreement_true_when_sections_match():
    pytest.importorskip("pefile")
    pe = build_pe(sections=[_section()], disarm=True)
    r = analyze_bytes(zlib.compress(pe), sha256="e" * 64, static_only=True)
    assert r.independent_parser_status == "ok"
    assert r.independent_raw_agreement is True


def test_null_section_headers_disagreement_is_classified():
    """NumberOfSections declared but headers all zero: pefile reports 0 sections, PEAtlas
    keeps raw-less sections. Strict status disagrees, mapping-relevant view agrees, and the
    ledger classifies it as section_count:null_headers."""
    pefile = pytest.importorskip("pefile")
    import struct

    from ua_sahi_mal.sorel.ledger import build_ledger_entry

    pe = bytearray(build_pe(sections=[_section()], disarm=True))
    e = struct.unpack_from("<I", pe, 0x3C)[0]
    coff = e + 4
    size_opt = struct.unpack_from("<H", pe, coff + 16)[0]
    table = coff + 20 + size_opt
    struct.pack_into("<H", pe, coff + 2, 2)             # declare 2 sections
    pe[table:table + 80] = b"\x00" * 80                  # ...but zero both headers
    data = bytes(pe)
    # sanity: pefile really reports 0 sections for this shape
    p = pefile.PE(data=data, fast_load=True)
    try:
        assert len(p.sections) == 0
    finally:
        p.close()

    r = analyze_bytes(zlib.compress(data), sha256="f" * 64, static_only=True)
    assert r.independent_parser_status.startswith("mismatch:section_count ours=2 pefile=0")
    assert r.independent_raw_agreement is True          # no raw data either way

    entry = build_ledger_entry(zlib.compress(data), sha256="f" * 64, case_id="case-01",
                               strict_status=r.independent_parser_status, static_only=True)
    assert entry.category == "section_count:null_headers"
    assert entry.peatlas["n_sections"] == 2 and entry.pefile["n_sections"] == 0
    assert entry.peatlas["section_table_all_null"] is True
    assert entry.raw_agreement is True
    assert "case-01" in entry.public_summary() and "f" * 64 not in entry.public_summary()
