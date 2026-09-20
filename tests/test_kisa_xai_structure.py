"""Synthetic-only checks: no dataset payloads are opened."""

import struct

import numpy as np
import pytest

from ua_sahi_mal.kisa_xai.representation import build_interval_map
from ua_sahi_mal.kisa_xai.structure import (
    RegionSpan,
    StructureMap,
    build_structure_map,
    compare_pefile,
    structure_cam_mass,
)
from ua_sahi_mal.peatlas.pebuild import SectionSpec, build_pe


def fixture(plus=False, executable=False):
    data = bytearray(build_pe(
        sections=[SectionSpec("not_rsrc", 0x1000, 0x180, 0x200, 0x200,
                              characteristics=0x60000020 if executable else 0x40000040)],
        pe32_plus=plus, certificate=(0x400, 0x20), overlay=b"tail"))
    opt = 0x40 + 24
    struct.pack_into("<II", data, opt + (112 if plus else 96) + 16, 0x1000, 0x80)
    return bytes(data)


@pytest.mark.parametrize("plus", [False, True])
def test_resource_flags_padding_certificate_overlay(plus):
    result = build_structure_map(fixture(plus))
    result.validate()
    assert [(s.start, s.end, s.region) for s in result.spans] == [
        (0, 0x200, "dos_and_pe_headers"), (0x200, 0x380, "resource_like_sections"),
        (0x380, 0x400, "unknown"), (0x400, 0x420, "certificate_table"), (0x420, 0x424, "overlay")]
    assert sum(result.to_dict()["region_bytes"].values()) == len(fixture(plus))
    assert compare_pefile(fixture(plus))["raw_fields_agree"]


def test_executable_flag_precedes_resource_directory():
    result = build_structure_map(fixture(executable=True))
    assert result.to_dict()["region_bytes"]["executable_sections"] == 0x180
    assert result.to_dict()["region_bytes"]["resource_like_sections"] == 0


def test_name_alone_is_not_a_resource_region():
    data = build_pe(sections=[SectionSpec(".rsrc", 0x1000, 0x200, 0x200, 0x200)])
    assert build_structure_map(data).to_dict()["region_bytes"]["resource_like_sections"] == 0


def test_truncated_section_retains_actual_bytes_and_warning():
    data = build_pe(sections=[SectionSpec(".data", 0x1000, 0x400, 0x200, 0x400)], truncate_to=0x300)
    result = build_structure_map(data)
    assert result.to_dict()["region_bytes"]["non_executable_sections"] == 0x100
    assert any("truncated" in warning for warning in result.warnings)


def test_overlapping_sections_are_unknown():
    data = build_pe(sections=[SectionSpec("a", 0x1000, 0x200, 0x200, 0x200),
                              SectionSpec("b", 0x2000, 0x200, 0x300, 0x200)])
    assert build_structure_map(data).to_dict()["region_bytes"]["unknown"] == 0x100


@pytest.mark.parametrize("size", [7, 50176, 50177, 100003])
def test_cam_mass_conserved_across_pixel_boundaries(size):
    split = size // 2
    mapping = StructureMap(size, (RegionSpan(0, split, "dos_and_pe_headers"),
                                  RegionSpan(split, size, "unknown")), ())
    imap = build_interval_map(size)
    scores = np.random.default_rng(42).random(imap.pixel_count)
    mass = structure_cam_mass(scores, imap, mapping)
    assert sum(mass.values()) == pytest.approx(scores.sum())
    assert mass["dos_and_pe_headers"] > 0 and mass["unknown"] > 0


def test_invalid_partition_and_cam_rejected():
    with pytest.raises(ValueError):
        StructureMap(3, (RegionSpan(1, 3, "unknown"),), ()).validate()
    mapping = StructureMap(3, (RegionSpan(0, 3, "unknown"),), ())
    with pytest.raises(ValueError):
        structure_cam_mass(np.full(50176, np.nan), build_interval_map(3), mapping)


def test_malformed_header_does_not_pass():
    with pytest.raises(ValueError):
        build_structure_map(b"not a PE")
    with pytest.raises(ValueError):
        compare_pefile(b"not a PE")


def test_crosscheck_detects_independent_field_disagreement(monkeypatch):
    import pefile

    parsed = pefile.PE(data=fixture(), fast_load=True)
    parsed.sections[0].Characteristics ^= 0x20000000
    monkeypatch.setattr(pefile, "PE", lambda **kwargs: parsed)
    result = compare_pefile(fixture())
    assert not result["raw_fields_agree"]
    assert any(m["field"] == "section[0].characteristics" for m in result["mismatches"])


def test_unbacked_resource_directory_is_recorded():
    data = bytearray(fixture())
    struct.pack_into("<II", data, 0x40 + 24 + 96 + 16, 0x9000, 0x100)
    result = build_structure_map(bytes(data))
    assert "resource_directory_not_fully_section_backed" in result.warnings
