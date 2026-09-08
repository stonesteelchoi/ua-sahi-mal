"""Tier 0 tests for PE layout parsing and coordinate mapping.

These verify coordinate correctness only. No malware is executed or disassembled;
fixtures are synthetic PE headers with inert filler bodies. Passing here is a
mapping-correctness result, NOT a malicious-component localization result.
"""

from __future__ import annotations

import pytest
from peatlas_fixtures import SecSpec, build_pe, simple_two_section

from ua_sahi_mal.peatlas import (
    CoordinateComponent,
    Interval,
    IntervalSet,
    MapStatus,
    PeAtlas,
    PeFormatError,
    Provenance,
    parse_pe,
)


# --- parsing --------------------------------------------------------------
def test_parse_rejects_non_pe():
    with pytest.raises(PeFormatError):
        parse_pe(b"MZ")  # too small
    with pytest.raises(PeFormatError):
        parse_pe(b"XX" + b"\x00" * 0x80)  # no MZ
    good = simple_two_section()
    broken = bytearray(good)
    broken[good[0x3C]] = 0x00  # corrupt the 'PE' signature's first byte
    with pytest.raises(PeFormatError):
        parse_pe(bytes(broken))


def test_parse_basic_layout():
    lay = parse_pe(simple_two_section())
    assert not lay.is_pe32_plus
    assert lay.image_base == 0x00400000
    assert lay.size_of_headers == 0x200
    assert [s.name for s in lay.sections] == [".text", ".data"]
    assert lay.overlay_offset == 0x600
    assert lay.file_size == 0x610
    assert lay.warnings == ()


def test_pe32_plus_image_base():
    sections = [SecSpec(".text", rva=0x1000, virtual_size=0x100, raw_offset=0x200, raw_size=0x200)]
    data = build_pe(sections=sections, pe32_plus=True, image_base=0x140000000)
    lay = parse_pe(data)
    assert lay.is_pe32_plus
    assert lay.image_base == 0x140000000
    atlas = PeAtlas(lay)
    assert atlas.offset_to_va(0x200).value == 0x140000000 + 0x1000


# --- headers & normal mapping --------------------------------------------
def test_header_region_maps_one_to_one():
    atlas = PeAtlas.from_bytes(simple_two_section())
    r = atlas.offset_to_rva(0x10)
    assert r.status is MapStatus.HEADERS and r.value == 0x10
    assert atlas.rva_to_offset(0x10).value == 0x10


def test_offset_rva_va_round_trip_in_mapped_regions():
    atlas = PeAtlas.from_bytes(simple_two_section())
    for offset in (0x200, 0x37F, 0x400, 0x5FF):
        r = atlas.offset_to_rva(offset)
        assert r.ok, (offset, r)
        back = atlas.rva_to_offset(r.value)
        assert back.ok and back.value == offset
        # VA is image base + RVA and round-trips too
        va = atlas.offset_to_va(offset).value
        assert va == atlas.layout.image_base + r.value
        assert atlas.va_to_offset(va).value == offset


def test_text_section_boundaries():
    atlas = PeAtlas.from_bytes(simple_two_section())
    # first mapped byte
    assert atlas.offset_to_rva(0x200).value == 0x1000
    # last mapped byte (virtual_size 0x180 -> mapped raw [0x200, 0x380))
    assert atlas.offset_to_rva(0x37F).value == 0x117F
    # raw padding tail [0x380, 0x400): raw exists but virtual does not
    assert atlas.offset_to_rva(0x380).status is MapStatus.PADDING
    assert atlas.offset_to_rva(0x3FF).status is MapStatus.PADDING


def test_virtual_only_tail():
    atlas = PeAtlas.from_bytes(simple_two_section())
    # .data virtual_size 0x400 but raw only 0x200 -> rva [0x2200, 0x2400) is virtual-only
    assert atlas.rva_to_offset(0x2000).value == 0x400
    assert atlas.rva_to_offset(0x21FF).value == 0x5FF
    assert atlas.rva_to_offset(0x2200).status is MapStatus.VIRTUAL_ONLY
    assert atlas.rva_to_offset(0x23FF).status is MapStatus.VIRTUAL_ONLY
    # just past the section virtual end is unmapped
    assert atlas.rva_to_offset(0x2400).status is MapStatus.UNMAPPED


def test_overlay_and_out_of_file():
    atlas = PeAtlas.from_bytes(simple_two_section())
    assert atlas.offset_to_rva(0x600).status is MapStatus.OVERLAY
    assert atlas.offset_to_rva(0x60F).status is MapStatus.OVERLAY
    assert atlas.offset_to_rva(0x610).status is MapStatus.UNMAPPED  # == file_size
    with pytest.raises(ValueError):
        atlas.offset_to_rva(-1)


def test_certificate_region():
    sections = [SecSpec(".text", rva=0x1000, virtual_size=0x200, raw_offset=0x200, raw_size=0x200)]
    data = build_pe(sections=sections, certificate=(0x400, 0x40))
    atlas = PeAtlas.from_bytes(data)
    assert atlas.layout.certificate == Interval(0x400, 0x440)
    assert atlas.offset_to_rva(0x410).status is MapStatus.CERTIFICATE


def test_inter_region_padding_gap():
    # .text raw ends at 0x400; .data raw starts at 0x600 -> gap [0x400,0x600) is padding
    sections = [
        SecSpec(".text", rva=0x1000, virtual_size=0x200, raw_offset=0x200, raw_size=0x200),
        SecSpec(".data", rva=0x2000, virtual_size=0x200, raw_offset=0x600, raw_size=0x200),
    ]
    atlas = PeAtlas.from_bytes(build_pe(sections=sections))
    assert atlas.offset_to_rva(0x500).status is MapStatus.PADDING


# --- malformed layouts ----------------------------------------------------
def test_overlapping_sections_are_flagged_and_ambiguous():
    sections = [
        SecSpec(".a", rva=0x1000, virtual_size=0x2000, raw_offset=0x200, raw_size=0x400),
        SecSpec(".b", rva=0x1800, virtual_size=0x2000, raw_offset=0x400, raw_size=0x400),
    ]
    atlas = PeAtlas.from_bytes(build_pe(sections=sections))
    assert any("overlap" in w for w in atlas.layout.warnings)
    # offset 0x500 is inside both raw ranges [0x200,0x600) and [0x400,0x800)
    assert atlas.offset_to_rva(0x500).status is MapStatus.OVERLAPPING
    # rva 0x1900 is inside both virtual ranges
    assert atlas.rva_to_offset(0x1900).status is MapStatus.OVERLAPPING


def test_truncated_file():
    data = simple_two_section()[:0x500]  # cut inside .data raw [0x400,0x600)
    atlas = PeAtlas.from_bytes(data)
    assert any("truncated" in w for w in atlas.layout.warnings)
    # offset claimed by .data but past actual EOF
    assert atlas.offset_to_rva(0x580).status is MapStatus.TRUNCATED
    # rva that maps to a truncated offset
    assert atlas.rva_to_offset(0x2180).status is MapStatus.TRUNCATED
    # the part that is still present maps fine
    assert atlas.offset_to_rva(0x400).value == 0x2000


# --- interval mapping with boundary splitting -----------------------------
def test_rva_interval_splits_at_raw_virtual_boundary():
    atlas = PeAtlas.from_bytes(simple_two_section())
    # .data: [0x2100, 0x2300) crosses the raw(->0x2200)/virtual boundary
    offsets, segs = atlas.map_rva_interval(0x2100, 0x2300)
    assert offsets == IntervalSet([(0x500, 0x600)])
    assert [(s.source.start, s.source.end, s.status) for s in segs] == [
        (0x2100, 0x2200, MapStatus.OK),
        (0x2200, 0x2300, MapStatus.VIRTUAL_ONLY),
    ]


def test_offset_interval_splits_across_sections_and_padding():
    atlas = PeAtlas.from_bytes(simple_two_section())
    # [0x300, 0x500): .text mapped part, .text raw padding, then .data mapped part
    offsets, segs = atlas.map_offset_interval(0x300, 0x500)
    statuses = [(s.source.start, s.source.end, s.status) for s in segs]
    assert statuses == [
        (0x300, 0x380, MapStatus.OK),       # .text mapped
        (0x380, 0x400, MapStatus.PADDING),  # .text raw>virtual padding
        (0x400, 0x500, MapStatus.OK),       # .data mapped
    ]
    # OK parts map to rva unions [0x1100,0x1180) and [0x2000,0x2100)
    assert offsets == IntervalSet([(0x1100, 0x1180), (0x2000, 0x2100)])


def test_map_interval_rejects_empty():
    atlas = PeAtlas.from_bytes(simple_two_section())
    with pytest.raises(ValueError):
        atlas.map_rva_interval(0x1000, 0x1000)


# --- analyzer component interface -----------------------------------------
def test_map_component_attaches_provenance_and_reports_gaps():
    atlas = PeAtlas.from_bytes(simple_two_section())
    prov = Provenance(source="synthetic", version="test-v1", extra={"note": "planted"})
    comp = CoordinateComponent(
        identifier="fn_1",
        kind="function",
        rva_intervals=IntervalSet([(0x2100, 0x2300)]),  # half mapped, half virtual-only
        provenance=prov,
    )
    mapped = atlas.map_component(comp)
    assert mapped.identifier == "fn_1"
    assert mapped.kind == "function"
    assert mapped.provenance.source == "synthetic"
    assert mapped.file_offsets == IntervalSet([(0x500, 0x600)])
    assert not mapped.fully_mapped
    assert mapped.unmapped_length == 0x100  # the virtual-only tail


def test_map_component_fully_mapped():
    atlas = PeAtlas.from_bytes(simple_two_section())
    comp = CoordinateComponent(
        identifier="bb_1",
        kind="basic_block",
        rva_intervals=IntervalSet([(0x1000, 0x1080)]),
        provenance=Provenance(source="capa"),
    )
    mapped = atlas.map_component(comp)
    assert mapped.fully_mapped
    assert mapped.file_offsets == IntervalSet([(0x200, 0x280)])
    assert mapped.unmapped_length == 0
