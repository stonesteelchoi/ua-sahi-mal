"""Synthetic-only checks: no dataset payloads are opened."""

import struct
import hashlib

import numpy as np
import pytest

from ua_sahi_mal.kisa_xai.representation import build_interval_map
from ua_sahi_mal.kisa_xai.structure import (
    RegionSpan,
    StructureMap,
    build_unknown_structure_map,
    build_p2_structure_map,
    build_structure_map,
    compare_pefile,
    p2_section_disagreement_reason,
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


def test_conservative_unknown_fallback_covers_entire_file():
    data = fixture() + b"extra"
    result = build_unknown_structure_map(data, "synthetic_policy_case")
    assert [(s.start, s.end, s.region) for s in result.spans] == [(0, len(data), "unknown")]
    assert result.to_dict()["region_bytes"]["unknown"] == len(data)
    assert result.warnings == ("conservative_unknown_v1:synthetic_policy_case",)


@pytest.mark.parametrize("reason", [
    "directory_count_exceeds_optional_header_capacity",
    "declared_optional_header_missing_or_truncated",
])
def test_p2_malformed_optional_header_policy_v1_expected_map(reason):
    # Synthetic bytes only: the census records parser detection separately.
    data = b"synthetic-malformed-optional-header"
    result = build_unknown_structure_map(data, reason)
    assert [(s.start, s.end, s.region) for s in result.spans] == [
        (0, len(data), "unknown")]
    assert result.to_dict()["region_bytes"] == {
        "dos_and_pe_headers": 0,
        "executable_sections": 0,
        "non_executable_sections": 0,
        "resource_like_sections": 0,
        "certificate_table": 0,
        "overlay": 0,
        "unknown": len(data),
    }
    assert result.warnings == (f"conservative_unknown_v1:{reason}",)


@pytest.mark.parametrize("fault,reason", [
    ("directory_count", "directory_count_exceeds_optional_header_capacity"),
    ("short_optional_header", "declared_optional_header_missing_or_truncated"),
    ("truncated_optional_header", "declared_optional_header_missing_or_truncated"),
])
def test_p2_fallback_requires_peatlas_malformed_header(fault, reason):
    data = bytearray(build_pe(sections=[SectionSpec(".data", 0x1000, 0x200, 0x200, 0x200)]))
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    optional_offset = pe_offset + 24
    if fault == "directory_count":
        struct.pack_into("<I", data, optional_offset + 92, 1000)
    elif fault == "short_optional_header":
        struct.pack_into("<H", data, pe_offset + 20, 80)
    else:
        struct.pack_into("<H", data, pe_offset + 20, len(data))
    result = build_p2_structure_map(bytes(data))
    assert result.spans == (RegionSpan(0, len(data), "unknown"),)
    assert result.warnings == (f"conservative_unknown_v1:{reason}",)


def test_p2_fallback_does_not_accept_unclassified_parse_error():
    with pytest.raises(ValueError):
        build_p2_structure_map(b"not a PE")


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


@pytest.mark.parametrize("fields,reason", [
    (["section_count"], "section_count_disagreement"),
    (["raw_section_overlay_boundary"], "raw_section_boundary_disagreement"),
    (["section_count", "raw_section_overlay_boundary"], "section_count_disagreement"),
    (["section[0].raw_size"], None),
    (["section_count", "section[0].raw_size"], None),
    ([], None),
])
def test_p2_section_policy_synthetic_ledger(tmp_path, monkeypatch, fields, reason):
    from scripts import psa_structure_audit as audit
    from ua_sahi_mal.kisa_xai import structure as structure_module

    data = fixture()
    comparison = {
        "raw_fields_agree": not fields,
        "mismatches": [{"field": field, "peatlas": 1, "pefile": 2} for field in fields],
        "native_overlay": {"peatlas": 2, "pefile": 1, "agrees": False},
    }
    monkeypatch.setattr(structure_module, "compare_pefile", lambda unused: comparison)
    monkeypatch.setattr(audit, "compare_pefile", lambda unused: comparison)
    assert p2_section_disagreement_reason(comparison) == reason
    path = tmp_path / "17"
    path.write_bytes(data)
    record = audit.audit_one((tmp_path, "17", "train", len(data),
                              hashlib.sha256(data).hexdigest(), audit.POLICY_UNKNOWN))
    mapped = build_p2_structure_map(data)
    if reason:
        assert mapped.spans == (RegionSpan(0, len(data), "unknown"),)
        assert record["status"] == "accepted_unknown_fallback"
        assert record["adjudication"]["reason"] == reason
        assert record["adjudication"]["policy_version"] == "P2-SECTION-DISAGREEMENT-V1"
        assert record["structure"]["region_bytes"]["unknown"] == len(data)
    else:
        assert mapped == build_structure_map(data)
        assert record["status"] == ("disagreement" if fields else "agreement")
        assert "adjudication" not in record
    assert record["crosscheck"]["native_overlay"]["agrees"] is False
