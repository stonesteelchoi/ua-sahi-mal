"""E2 silver extraction: embedded-PE scan + capa RVA->offset mapping (E2_prereg_v1)."""

from __future__ import annotations

import pytest

from ua_sahi_mal.peatlas import PeAtlas, SectionSpec, build_pe, parse_pe
from ua_sahi_mal.sorel.e2_silver import (
    CapaMatch,
    CapaUnavailable,
    _default_capa_runner,
    build_silver,
    capa_matches_to_intervals,
    find_embedded_pes,
    yara_silver_intervals,
)


def _primary_with_overlay(overlay: bytes) -> bytes:
    return build_pe(
        sections=[SectionSpec(".text", rva=0x1000, virtual_size=0x400, raw_offset=0x400, raw_size=0x400)],
        overlay=overlay, disarm=True,
    )


def test_find_embedded_pe_in_overlay_not_primary():
    embedded = build_pe(sections=[SectionSpec(".x", rva=0x1000, virtual_size=0x200,
                                              raw_offset=0x200, raw_size=0x200)], disarm=True)
    primary = _primary_with_overlay(embedded)
    layout = parse_pe(primary)
    found = find_embedded_pes(primary)
    assert len(found) == 1
    assert found[0][0] == layout.overlay_offset  # detected at overlay start, offset-0 image ignored


def test_find_embedded_pe_ignores_bare_mz():
    primary = _primary_with_overlay(b"MZ" + b"\x00" * 4096)  # 'MZ' with no valid PE header
    assert find_embedded_pes(primary) == []


def test_capa_matches_map_rva_to_file_offsets():
    primary = _primary_with_overlay(b"")
    atlas = PeAtlas.from_bytes(primary)
    matches = [CapaMatch(rule="alloc-rwx", fn_start_rva=0x1000, fn_end_rva=0x1100)]
    intervals, meta = capa_matches_to_intervals(matches, atlas, version="test")
    assert [(iv.start, iv.end) for iv in intervals] == [(0x400, 0x500)]
    assert meta["rules"] == ["alloc-rwx"] and meta["functions"] == 1


def test_build_silver_union_and_capa_disabled():
    embedded = build_pe(sections=[SectionSpec(".x", rva=0x1000, virtual_size=0x200,
                                              raw_offset=0x200, raw_size=0x200)], disarm=True)
    primary = _primary_with_overlay(embedded)
    atlas = PeAtlas.from_bytes(primary)
    layout = parse_pe(primary)

    def runner(data, *, timeout, image_base, work_dir=None):
        return [CapaMatch(rule="r", fn_start_rva=0x1000, fn_end_rva=0x1100)]

    silver = build_silver(primary, atlas, image_base=layout.image_base, enable_capa=True, capa_runner=runner)
    assert silver.capa_status == "ok" and silver.has_silver
    assert silver.embedded_count == 1 and silver.capa_intervals == [(0x400, 0x500)]

    disabled = build_silver(primary, atlas, image_base=layout.image_base, enable_capa=False)
    assert disabled.capa_status == "disabled" and disabled.capa_intervals == []


def test_build_silver_degrades_when_capa_unavailable():
    primary = _primary_with_overlay(b"")
    atlas = PeAtlas.from_bytes(primary)
    layout = parse_pe(primary)

    def broken(data, *, timeout, image_base, work_dir=None):
        raise CapaUnavailable("not installed")

    silver = build_silver(primary, atlas, image_base=layout.image_base, enable_capa=True, capa_runner=broken)
    assert silver.capa_status.startswith("unavailable:")
    assert silver.capa_intervals == []


def test_capa_default_runner_refuses_disk_without_work_dir():
    with pytest.raises(CapaUnavailable, match="refused"):
        _default_capa_runner(b"MZ", timeout=1, image_base=0x400000, work_dir=None)


def test_yara_silver_intervals_with_injected_matcher():
    data = b"\x00" * 100
    # matcher returns (offset, length, rule) hits; overlapping spans merge
    def matcher(_data):
        return [(10, 5, "r1"), (12, 4, "r1"), (40, 8, "r2")]
    ivs, meta = yara_silver_intervals(data, matcher=matcher)
    assert ivs == [(10, 16), (40, 48)]           # (10,15)∪(12,16) merged
    assert meta["rules"] == ["r1", "r2"] and meta["n_strings"] == 3
    # out-of-range hits are dropped
    ivs2, _ = yara_silver_intervals(data, matcher=lambda d: [(98, 10, "x")])
    assert ivs2 == []


def test_build_silver_unions_yara():
    primary = _primary_with_overlay(b"")
    atlas = PeAtlas.from_bytes(primary)
    layout = parse_pe(primary)

    def matcher(_data):
        return [(0x410, 16, "susp_api")]   # inside the .text raw region

    silver = build_silver(primary, atlas, image_base=layout.image_base, enable_yara=True, yara_matcher=matcher)
    assert silver.yara_status == "ok" and silver.yara_intervals == [(0x410, 0x420)]
    assert silver.has_silver and (0x410, 0x420) in silver.union_intervals
