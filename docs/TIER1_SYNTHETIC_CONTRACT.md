# Tier 1 controlled-provenance synthetic contract

- **Status:** first implementation (follow-up to the PEAtlas Tier 0 / projection work)
- **Module:** `src/ua_sahi_mal/peatlas/synthetic.py` (assembler: `peatlas/pebuild.py`)
- **Plan basis:** `paper/plan/RESEARCH_PLAN_v3.md` §5 Tier 1 (controlled provenance)

## Purpose

A coordinate **recoverability / shortcut-resistance** benchmark with exact
provenance, produced without any real malware. It lets the pipeline be validated
end to end (encode → detect → map back → score) against a *known answer* before
any GPU training or real-sample work.

## Safety and honesty boundaries (by construction)

- Nothing is executed and nothing is disassembled.
- The planted marker is **inert pseudo-random bytes** — a localizable region, not
  in-the-wild malicious behaviour and not an executable payload. The module never
  claims otherwise.
- "Layout variants" are synthetic section layouts, **not** real compiler builds.
- Generated PE `.bin` files are written to a caller-chosen output directory at run
  time and are **never committed** to the repository.

## What it produces

For each `PlantSpec`, a matched **pair**:

- **planted** — a PE with an inert marker region at a known file-offset interval
  inside a chosen section;
- **control** — the identical PE whose same-length region holds different inert
  random bytes (so it is size/section/**entropy-matched** but is **not** the
  marker and carries **no** planted component).

`write_dataset(out_dir, specs)` writes each sample's `.bin`, a
`manifest.json` (DATA_CONTRACT v1: category `planted_component`, planted samples
carry one annotation with `annotation_source="synthetic"` and `source_start/end`;
control samples carry none), and a `provenance.jsonl`.

## Provenance recorded per sample

- `file_offset` `[start, end)` of the marker (planted) region
- `rva_intervals` — mapped through **PEAtlas** (`map_offset_interval`), so the
  provenance is consistent with the coordinate authority
- `pixel_bbox_xywh_raw_rgb` — raw-rgb (stride 3) pixel rectangles for the region
  at the sample's raster `width`
- `width`, `seed`, `section_index`, `section_name`, `layout_variant`
- `marker_sha256` (planted) / `matched_region_sha256` (control)
- `entropy_bits_per_byte` and the inert-marker `note`

Generation is deterministic in `seed`: same seed → identical bytes/hashes.

## Coverage (default_specs)

Varied plant **location** (section + offset), **length**, raster **width**
(32/64/128/256), and **layout variant** (2- and 3-section). Extend by passing your
own `PlantSpec` list.

## Relationship to gates

This is **Tier 1 controlled provenance**, not gold. It exercises coordinate
recoverability and shortcut resistance; it does **not** provide
`MALICIOUS_COMPONENT` gold (Tier 3 needs real source-grounded builds + independent
analyst adjudication). It informs the G2 feasibility direction but is never
promoted to gold, and passing here is coordinate/recoverability correctness, not
malicious-component localization performance.

## Out of scope (later / gated tasks)

Real malware, any execution, real compiler builds, DeepReflect execution
(environment/licence gated), and model training are not part of this module.
