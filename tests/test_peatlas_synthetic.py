"""Tests for the Tier 1 controlled-provenance synthetic generator.

Coordinate/recoverability correctness only. No malware, nothing executed; the
planted marker is inert pseudo-random filler.
"""

from __future__ import annotations

import json

import pytest

from ua_sahi_mal.encoding import encode_raw_bytes
from ua_sahi_mal.peatlas import (
    IntervalSet,
    PeAtlas,
    PixelProjection,
    PlantSpec,
    SectionSpec,
    default_specs,
    generate_pair,
    write_dataset,
)


def _one_spec() -> PlantSpec:
    sections = (
        SectionSpec(".text", rva=0x1000, virtual_size=0x1000, raw_offset=0x200, raw_size=0x1000),
        SectionSpec(".data", rva=0x2000, virtual_size=0x1000, raw_offset=0x1200, raw_size=0x1000),
    )
    return PlantSpec("two_section", sections, section_index=0,
                     plant_offset_in_section=0x40, plant_length=0x30, width=64)


def test_planted_marker_is_present_and_recoverable():
    spec = _one_spec()
    planted, _ = generate_pair(spec, seed=123)
    start, end = 0x240, 0x270  # raw_offset 0x200 + 0x40, length 0x30
    assert planted.file_offsets == IntervalSet([(start, end)])
    # marker bytes actually sit at the recorded offsets
    marker = planted.pe_bytes[start:end]
    assert len(marker) == 0x30
    assert planted.provenance["marker_sha256"] == __import__("hashlib").sha256(marker).hexdigest()
    # the region maps cleanly through PEAtlas (fully OK), giving rva provenance
    atlas = PeAtlas.from_bytes(planted.pe_bytes)
    rva_set, segments = atlas.map_offset_interval(start, end)
    assert all(s.status.name == "OK" for s in segments)
    assert rva_set == planted.rva
    assert planted.rva == IntervalSet([(0x1040, 0x1070)])  # .text rva 0x1000 + 0x40


def test_control_is_matched_but_has_no_component():
    spec = _one_spec()
    planted, control = generate_pair(spec, seed=123)
    start, end = 0x240, 0x270
    # same file size and section layout
    assert len(planted.pe_bytes) == len(control.pe_bytes)
    # identical everywhere except the planted region
    assert planted.pe_bytes[:start] == control.pe_bytes[:start]
    assert planted.pe_bytes[end:] == control.pe_bytes[end:]
    # the region differs (control is not the marker) but is the same length
    assert planted.pe_bytes[start:end] != control.pe_bytes[start:end]
    # entropy is matched (both regions are random of equal length)
    assert abs(planted.entropy_bits_per_byte - control.entropy_bits_per_byte) < 0.1
    # control carries no planted component
    assert control.file_offsets.is_empty()


def test_determinism():
    spec = _one_spec()
    a, _ = generate_pair(spec, seed=7)
    b, _ = generate_pair(spec, seed=7)
    assert a.sha256 == b.sha256
    c, _ = generate_pair(spec, seed=8)
    assert a.sha256 != c.sha256


def test_pixel_bbox_provenance_matches_projection():
    spec = _one_spec()
    planted, _ = generate_pair(spec, seed=1)
    proj = PixelProjection.from_metadata(encode_raw_bytes(planted.pe_bytes, width=spec.width).metadata)
    # pixels from the recorded bbox boxes
    boxes = planted.provenance["pixel_bbox_xywh_raw_rgb"]
    pixel_intervals = []
    for x, y, w, h in boxes:
        for row in range(y, y + h):
            s = row * spec.width + x
            pixel_intervals.append((s, s + w))
    from_boxes = IntervalSet(pixel_intervals)
    assert from_boxes == proj.bytes_to_pixels(planted.file_offsets)


def test_plant_out_of_section_raises():
    sections = (SectionSpec(".text", rva=0x1000, virtual_size=0x100, raw_offset=0x200, raw_size=0x100),)
    bad = PlantSpec("tiny", sections, section_index=0, plant_offset_in_section=0xF0, plant_length=0x40)
    with pytest.raises(ValueError):
        generate_pair(bad, seed=0)


def test_write_dataset(tmp_path):
    specs = default_specs()
    manifest = write_dataset(tmp_path, specs, seed=42, name="tier1-test")
    assert manifest["version"] == 1
    assert manifest["categories"] == [{"id": 1, "name": "planted_component"}]
    # one planted + one control per spec
    assert len(manifest["samples"]) == 2 * len(specs)

    planted = [s for s in manifest["samples"] if s["sample_id"].endswith("planted")]
    control = [s for s in manifest["samples"] if s["sample_id"].endswith("control")]
    assert len(planted) == len(control) == len(specs)
    for s in planted:
        assert len(s["annotations"]) == 1
        a = s["annotations"][0]
        assert a["annotation_source"] == "synthetic" and a["source_end"] > a["source_start"]
    for s in control:
        assert s["annotations"] == []

    # files exist and re-parse; planted annotation region maps OK in the written file
    files = list(tmp_path.glob("*.bin"))
    assert len(files) == 2 * len(specs)
    assert (tmp_path / "manifest.json").exists()
    prov_lines = (tmp_path / "provenance.jsonl").read_text().strip().splitlines()
    assert len(prov_lines) == 2 * len(specs)
    assert all(json.loads(line)["note"].startswith("synthetic inert") for line in prov_lines)

    sample0 = planted[0]
    data = (tmp_path / sample0["source"]).read_bytes()
    atlas = PeAtlas.from_bytes(data)
    a = sample0["annotations"][0]
    _, segs = atlas.map_offset_interval(a["source_start"], a["source_end"])
    assert all(seg.status.name == "OK" for seg in segs)
