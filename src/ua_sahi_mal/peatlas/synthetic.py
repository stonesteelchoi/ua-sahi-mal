"""Tier 1 controlled-provenance synthetic generator (planted component + control).

Purpose (``paper/plan/RESEARCH_PLAN_v3.md`` §5 Tier 1): produce a coordinate
**recoverability / shortcut-resistance** benchmark with exact provenance, without
any real malware. Each item is a pair:

- a **planted** sample: an inert, distinctive marker region placed at a known
  file-offset interval inside a section, with provenance recorded in file-offset,
  RVA, and (optional) pixel space;
- a size/section/entropy-**matched control**: the identical PE with a same-length,
  same-entropy inert region at the same place that is **not** the marker, so a
  detector keying on "a high-entropy block exists" cannot trivially win.

Safety and honesty boundaries (enforced by construction):

- nothing is executed; nothing is disassembled;
- the marker is inert pseudo-random bytes, **not** in-the-wild malicious behaviour
  and not an executable payload — it is only a localizable region;
- "layout variants" are synthetic section layouts, **not** real compiler builds;
- generated PE bytes are written to a caller-chosen output directory at run time
  and are never committed to the repository.

Provenance uses ``annotation_source = "synthetic"`` per ``docs/DATA_CONTRACT.md``.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .atlas import PeAtlas
from .intervals import IntervalSet
from .pebuild import SectionSpec, build_pe

CATEGORY_ID = 1
CATEGORY_NAME = "planted_component"
_CONTROL_SALT = 0x5EED  # makes the control's matched region differ from the marker


@dataclass(frozen=True)
class PlantSpec:
    """One planted-component request (drives a planted+control pair)."""

    layout: str
    sections: tuple[SectionSpec, ...]
    section_index: int
    plant_offset_in_section: int
    plant_length: int
    width: int = 256
    split: str = "train"
    image_base: int = 0x00400000
    pe32_plus: bool = False


@dataclass(frozen=True)
class SyntheticSample:
    sample_id: str
    role: str                 # "planted" | "control"
    pe_bytes: bytes
    file_offsets: IntervalSet  # marker region (planted) / matched region (control)
    rva: IntervalSet
    sha256: str
    entropy_bits_per_byte: float
    width: int
    provenance: dict = field(default_factory=dict)


def _entropy(data: bytes) -> float:
    if not data:
        return 0.0
    n = len(data)
    return -sum((c / n) * math.log2(c / n) for c in Counter(data).values())


def _random_bytes(seed: int, length: int) -> bytes:
    rng = random.Random(seed)
    return bytes(rng.randrange(256) for _ in range(length))


def _plant_region(spec: PlantSpec) -> tuple[int, int]:
    sec = spec.sections[spec.section_index]
    start = sec.raw_offset + spec.plant_offset_in_section
    end = start + spec.plant_length
    if spec.plant_offset_in_section < 0 or end > sec.raw_offset + sec.raw_size:
        raise ValueError("planted region does not fit inside the target section's raw data")
    return start, end


def _rva_of(atlas: PeAtlas, start: int, end: int) -> IntervalSet:
    rva, _ = atlas.map_offset_interval(start, end)
    return rva


def _pixel_bbox_intervals(start: int, end: int, width: int, source_len: int) -> list[list[int]]:
    """raw-rgb pixel bbox rectangles (x, y, w, h) for a file-offset interval.

    Pure raw-rgb geometry (stride 3), so pixel provenance is available without
    importing the PIL-backed encoder.
    """
    stride = 3
    p0 = start // stride
    p1 = math.ceil(end / stride)
    p1 = min(p1, math.ceil(source_len / stride))
    if p1 <= p0:
        return []
    boxes: list[list[int]] = []
    row = p0 // width
    col = p0 % width
    remaining = p1 - p0
    while remaining > 0:
        take = min(width - col, remaining)
        boxes.append([col, row, take, 1])
        remaining -= take
        row += 1
        col = 0
    return boxes


def generate_pair(spec: PlantSpec, *, seed: int, index: int = 0) -> tuple[SyntheticSample, SyntheticSample]:
    """Generate a matched (planted, control) pair for one spec."""
    base = build_pe(
        sections=list(spec.sections), image_base=spec.image_base, pe32_plus=spec.pe32_plus,
    )
    atlas = PeAtlas.from_bytes(base)  # parse the layout once; both share it
    start, end = _plant_region(spec)
    length = end - start

    marker = _random_bytes(seed + index, length)
    control_fill = _random_bytes(seed + index + _CONTROL_SALT, length)
    if marker == control_fill:  # astronomically unlikely; keep them distinct
        control_fill = bytes((b ^ 0xFF) for b in marker)

    planted_bytes = bytearray(base)
    planted_bytes[start:end] = marker
    control_bytes = bytearray(base)
    control_bytes[start:end] = control_fill

    region = IntervalSet.single(start, end)
    rva = _rva_of(atlas, start, end)
    pixel_boxes = _pixel_bbox_intervals(start, end, spec.width, len(base))
    sid = f"{spec.layout}-s{spec.section_index}-o{spec.plant_offset_in_section}-l{length}-w{spec.width}-{index:03d}"

    common_prov = {
        "layout_variant": spec.layout,
        "note": "synthetic inert marker; not in-the-wild malicious; not executed",
        "section_index": spec.section_index,
        "section_name": spec.sections[spec.section_index].name,
        "file_offset": [start, end],
        "rva_intervals": [[iv.start, iv.end] for iv in rva],
        "pixel_bbox_xywh_raw_rgb": pixel_boxes,
        "width": spec.width,
        "seed": seed + index,
    }

    planted = SyntheticSample(
        sample_id=f"{sid}-planted",
        role="planted",
        pe_bytes=bytes(planted_bytes),
        file_offsets=region,
        rva=rva,
        sha256=hashlib.sha256(planted_bytes).hexdigest(),
        entropy_bits_per_byte=_entropy(planted_bytes),
        width=spec.width,
        provenance={**common_prov, "marker_sha256": hashlib.sha256(marker).hexdigest()},
    )
    control = SyntheticSample(
        sample_id=f"{sid}-control",
        role="control",
        pe_bytes=bytes(control_bytes),
        file_offsets=IntervalSet.empty(),   # control has NO planted component
        rva=IntervalSet.empty(),
        sha256=hashlib.sha256(control_bytes).hexdigest(),
        entropy_bits_per_byte=_entropy(control_bytes),
        width=spec.width,
        provenance={
            **common_prov,
            "matched_region_only": True,
            "matched_region_sha256": hashlib.sha256(control_fill).hexdigest(),
        },
    )
    return planted, control


def _manifest_sample(sample: SyntheticSample, source_name: str) -> dict:
    annotations: list[dict] = []
    if sample.role == "planted":
        for iv in sample.file_offsets:
            annotations.append({
                "category_id": CATEGORY_ID,
                "annotation_source": "synthetic",
                "source_start": iv.start,
                "source_end": iv.end,
            })
    return {
        "sample_id": sample.sample_id,
        "source": source_name,
        "sha256": sample.sha256,
        "split": "train",
        "encoding": "raw-rgb",
        "width": sample.width,
        "annotations": annotations,
    }


def write_dataset(out_dir: str | Path, specs: list[PlantSpec], *, seed: int = 0,
                  name: str = "peatlas-tier1-synthetic") -> dict:
    """Generate all pairs, write PE .bin files + manifest.json + provenance.jsonl.

    Returns the manifest dict. Generated PE bytes are inert and are written under
    ``out_dir`` only (never committed).
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    samples: list[dict] = []
    provenance_lines: list[str] = []

    for i, spec in enumerate(specs):
        planted, control = generate_pair(spec, seed=seed, index=i)
        for sample in (planted, control):
            bin_name = f"{sample.sample_id}.bin"
            (out / bin_name).write_bytes(sample.pe_bytes)
            samples.append(_manifest_sample(sample, bin_name))
            provenance_lines.append(json.dumps({
                "sample_id": sample.sample_id,
                "role": sample.role,
                "sha256": sample.sha256,
                "entropy_bits_per_byte": sample.entropy_bits_per_byte,
                **sample.provenance,
            }, ensure_ascii=False))

    manifest = {
        "version": 1,
        "name": name,
        "categories": [{"id": CATEGORY_ID, "name": CATEGORY_NAME}],
        "samples": samples,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "provenance.jsonl").write_text("\n".join(provenance_lines) + "\n", encoding="utf-8")
    return manifest


def default_specs() -> list[PlantSpec]:
    """A small preregistered spec set: varied location, length, width, and layout."""
    two = (
        SectionSpec(".text", rva=0x1000, virtual_size=0x1000, raw_offset=0x200, raw_size=0x1000),
        SectionSpec(".data", rva=0x2000, virtual_size=0x1000, raw_offset=0x1200, raw_size=0x1000),
    )
    three = (
        SectionSpec(".text", rva=0x1000, virtual_size=0x800, raw_offset=0x200, raw_size=0x800),
        SectionSpec(".rdata", rva=0x2000, virtual_size=0x800, raw_offset=0xA00, raw_size=0x800),
        SectionSpec(".data", rva=0x3000, virtual_size=0x800, raw_offset=0x1200, raw_size=0x800),
    )
    return [
        PlantSpec("two_section", two, section_index=0,
                  plant_offset_in_section=0x40, plant_length=0x30, width=64),
        PlantSpec("two_section", two, section_index=1,
                  plant_offset_in_section=0x100, plant_length=0x80, width=128),
        PlantSpec("three_section", three, section_index=1,
                  plant_offset_in_section=0x10, plant_length=0x40, width=32),
        PlantSpec("three_section", three, section_index=2,
                  plant_offset_in_section=0x200, plant_length=0x100, width=256),
    ]
