"""Tier 0 malformed-layout regressions; no analyzer or localization claims."""

import struct
from dataclasses import replace

import pytest
from peatlas_fixtures import SecSpec, build_pe, simple_two_section

from ua_sahi_mal.peatlas import Interval, IntervalSet, MapStatus, PeAtlas, PeFormatError, parse_pe


def test_truncated_rva_interval_stops_at_actual_eof():
    atlas = PeAtlas.from_bytes(simple_two_section()[:0x500])
    offsets, segments = atlas.map_rva_interval(0x2000, 0x2200)
    assert offsets == IntervalSet([(0x400, 0x500)])
    assert [(s.source, s.status) for s in segments] == [
        (Interval(0x2000, 0x2100), MapStatus.OK),
        (Interval(0x2100, 0x2200), MapStatus.TRUNCATED),
    ]


def test_zero_raw_pointer_is_virtual_only():
    atlas = PeAtlas.from_bytes(build_pe(sections=[SecSpec('.bss', 0x1000, 0x200, 0, 0x200)]))
    assert atlas.rva_to_offset(0x1000).status is MapStatus.VIRTUAL_ONLY
    assert not atlas.map_rva_interval(0x1000, 0x1200)[0]


@pytest.mark.parametrize('pe32_plus', [False, True])
def test_every_truncated_header_prefix_raises_format_error(pe32_plus):
    data = build_pe(sections=[SecSpec('.text', 0x1000, 0x200, 0x200, 0x200)], pe32_plus=pe32_plus)
    header_end = 0x58 + (240 if pe32_plus else 224) + 40
    for length in range(header_end):
        with pytest.raises(PeFormatError):
            parse_pe(data[:length])


@pytest.mark.parametrize('field,value', [(0x54, 0), (0x54, 64), (0x54, 96), (0xB4, 17)])
def test_declared_optional_header_bounds_are_enforced(field, value):
    data = bytearray(simple_two_section())
    struct.pack_into('<H' if field == 0x54 else '<I', data, field, value)
    with pytest.raises(PeFormatError):
        parse_pe(bytes(data))


def test_section_count_above_windows_loader_limit_is_rejected():
    data = bytearray(simple_two_section())
    struct.pack_into('<H', data, 0x46, 97)
    with pytest.raises(PeFormatError, match="section count 97"):
        parse_pe(bytes(data))


@pytest.mark.parametrize('pair', [(1.9, 3.9), ('1', '3'), (True, 3)])
def test_interval_pairs_do_not_coerce_coordinates(pair):
    with pytest.raises(TypeError):
        IntervalSet([pair])


@pytest.mark.parametrize('method,args', [
    ('offset_to_rva', (1.5,)), ('rva_to_offset', (1.5,)),
    ('va_to_offset', (1.5,)), ('offset_to_rva', (True,)),
    ('map_rva_interval', (0, 1.5)), ('map_offset_interval', (0.5, 2)),
])
def test_coordinate_inputs_are_integers(method, args):
    with pytest.raises(TypeError):
        getattr(PeAtlas.from_bytes(simple_two_section()), method)(*args)


def anomalous_layouts():
    base = parse_pe(simple_two_section())
    a, b = base.sections
    return [
        base,
        replace(base, file_size=0x500, overlay_offset=0x500),
        replace(base, sections=(), size_of_headers=0x800),
        replace(base, sections=(a, replace(b, rva=0x1100))),  # target RVA overlap
        replace(base, sections=(a, replace(b, raw_offset=0x300))),  # target raw overlap
        replace(base, sections=(replace(a, rva=0x100), b)),  # header RVA overlap
        replace(base, sections=(replace(a, raw_offset=0x100), b)),  # header raw overlap
        replace(base, certificate=Interval(0x280, 0x2A0)),  # certificate/raw conflict
        replace(base, certificate=Interval(0x80, 0xA0)),  # certificate/header conflict
        replace(base, certificate=Interval(0x600, 0x680)),  # certificate past EOF
    ]


@pytest.mark.parametrize('layout', anomalous_layouts(), ids=[
    'normal', 'truncated', 'oversized-headers', 'rva-overlap', 'raw-overlap',
    'header-rva', 'header-raw', 'certificate-raw', 'certificate-header', 'certificate-eof',
])
def test_all_successful_points_round_trip_and_intervals_match_points(layout):
    atlas = PeAtlas(layout)
    for point_map, reverse, interval_map, limit in [
        (atlas.offset_to_rva, atlas.rva_to_offset, atlas.map_offset_interval, 0x850),
        (atlas.rva_to_offset, atlas.offset_to_rva, atlas.map_rva_interval, 0x2500),
    ]:
        expected = set()
        for coordinate in range(limit):
            result = point_map(coordinate)
            if result.ok:
                back = reverse(result.value)
                assert back.ok and back.value == coordinate, (coordinate, result, back)
                expected.add(result.value)
            else:
                assert result.value is None
        mapped, segments = interval_map(0, limit)
        assert {p for iv in mapped for p in range(iv.start, iv.end)} == expected
        assert segments[0].source.start == 0 and segments[-1].source.end == limit
        for first, second in zip(segments, segments[1:], strict=False):
            assert first.source.end == second.source.start
        for segment in segments:
            for coordinate in range(segment.source.start, segment.source.end):
                point = point_map(coordinate)
                assert segment.status is point.status
                if point.ok:
                    assert segment.mapped.start + coordinate - segment.source.start == point.value
                else:
                    assert segment.mapped is None


def test_target_only_overlap_has_no_coordinate():
    base = parse_pe(simple_two_section())
    a, b = base.sections
    rva_conflict = PeAtlas(replace(base, sections=(a, replace(b, rva=0x1100))))
    assert rva_conflict.offset_to_rva(0x300).status is MapStatus.OVERLAPPING
    raw_conflict = PeAtlas(replace(base, sections=(a, replace(b, raw_offset=0x300))))
    assert raw_conflict.rva_to_offset(0x2000).status is MapStatus.OVERLAPPING


def test_certificate_conflicts_and_truncation_are_explicit():
    base = parse_pe(simple_two_section())
    atlas = PeAtlas(replace(base, certificate=Interval(0x280, 0x2A0)))
    assert atlas.offset_to_rva(0x280).status is MapStatus.OVERLAPPING
    assert atlas.rva_to_offset(0x1080).status is MapStatus.OVERLAPPING
    atlas = PeAtlas(replace(base, certificate=Interval(0x600, 0x680)))
    assert atlas.offset_to_rva(0x610).status is MapStatus.TRUNCATED


def test_header_interval_stops_at_eof_and_va_preserves_status():
    base = parse_pe(simple_two_section())
    atlas = PeAtlas(replace(base, sections=(), size_of_headers=0x800))
    offsets, segments = atlas.map_rva_interval(0x600, 0x800)
    assert offsets == IntervalSet([(0x600, 0x610)])
    assert segments[-1].status is MapStatus.TRUNCATED
    assert atlas.offset_to_va(0x10).status is MapStatus.HEADERS
