# PEAtlas coordinate contract (v3, Tier 0)

- **Status:** first implementation (P1 / Tier 0 slice)
- **Module:** `src/ua_sahi_mal/peatlas/`
- **Scope of this document:** the coordinate data contract and the parts of it
  implemented in the `codex/peatlas-tier0` change. Pixel projection, real
  analyzer integration, and Tier 1 data generation are explicitly deferred.

## Purpose

The v3 estimand is stated in file-offset space (`paper/plan/RESEARCH_PLAN_v3.md`
§2.2): a predicted component is a **union of half-open file-offset intervals**
`[start, end)`. Models predict in pixel space and prior systems
(DeepReflect/capa/Binary Ninja) report in RVA/VA space. PEAtlas is the single,
tested authority that converts between these coordinate systems so that every
method is scored on the same canonical file-offset intervals. Passing the Tier 0
tests establishes **coordinate correctness only**, never localization quality.

## Coordinate systems

| Name | Meaning | Notes |
|---|---|---|
| **file offset** | byte position in the on-disk file | **canonical** coordinate |
| **RVA** | relative virtual address (offset within the loaded image) | per-section |
| **VA** | virtual address = `image_base + RVA` | absolute loaded address |
| pixel (row,col) | position in the byte/opcode raster | **deferred** — see below |

All ranges are half-open `[start, end)` with `end > start`. A component is a union
of disjoint intervals; adjacency (`[a,b)`+`[b,c)`) merges to `[a,c)`.
Bounds and point coordinates must be Python integers; floats, strings and booleans
raise `TypeError` rather than being silently converted. Empty intervals raise
`ValueError`; use `IntervalSet.empty()` for an empty union.

## Interval algebra (`peatlas.intervals`)

`Interval(start, end)` and `IntervalSet` provide the canonical set algebra:
normalize/merge, `union`, `intersection`, `difference`, `clamp`, `contains_point`,
`total_length`, `overlaps`, `jaccard` (1-D IoU), and `to_mask`/`from_mask` for
interoperability with the numpy mask helpers in `ua_sahi_mal.evidence` (which are
**not** re-implemented here). `IntervalSet` is always normalized, so equality is
structural.

## Mapping results and failure states (`peatlas.atlas`)

Point mappings return a `MapResult(status, value, detail)`. `value` is populated
**only** when `status.is_ok`. There is no fabricated coordinate for an
unmappable input. `MapStatus`:

| status | meaning | has value |
|---|---|---|
| `OK` | mapped inside a section | yes |
| `HEADERS` | inside the header region, mapped 1:1 | yes |
| `VIRTUAL_ONLY` | RVA backed by no on-disk bytes (e.g. `.bss` tail where VirtualSize > SizeOfRawData) | no |
| `PADDING` | file-alignment padding or an inter-region gap; present on disk, not loaded | no |
| `OVERLAY` | bytes after the mapped image; no RVA | no |
| `CERTIFICATE` | attribute certificate table (data dir 4); a file offset with no RVA | no |
| `TRUNCATED` | claimed by the layout but past the actual end-of-file | no |
| `UNMAPPED` | outside every known region | no |
| `OVERLAPPING` | conflicting section/header/certificate claims in either coordinate space | no |

`parse_pe` raises `PeFormatError` **only** when the header region itself cannot be
read. Body-level anomalies (raw data past EOF, overlapping sections) are recorded
in `PeLayout.warnings` and surface as the per-coordinate statuses above, so a
corrupted real sample is describable rather than fatal.
The declared optional-header size must cover its fixed fields and declared data
directories, and the entire declared section table must be readable. Missing or
inconsistent header bounds raise `PeFormatError`; no partial section layout is
returned. Section counts above the Windows loader limit of 96 are rejected before
section overlap analysis. This is structural validation, not an independent-parser
cross-check.

## Per-section mapping rules

For a section with `rva`, `virtual_size`, `raw_offset`, `raw_size`
(`mapped_raw_size = min(raw_size, virtual_size)` when `raw_offset > 0` and
`raw_size > 0`, otherwise zero):

- `offset → rva`: if `raw_offset ≤ offset < raw_offset + mapped_raw_size` then
  `rva = section.rva + (offset − raw_offset)`. Between `mapped_raw_size` and
  `raw_size` the on-disk bytes are file-alignment padding → `PADDING`.
- `rva → offset`: if `rva − section.rva < mapped_raw_size` then
  `offset = raw_offset + (rva − section.rva)`. Between `mapped_raw_size` and
  `virtual_size` the bytes are `VIRTUAL_ONLY`.
- header region maps 1:1 (`offset == rva`) for `[0, size_of_headers)`.
- `VA = image_base + RVA`; `va_to_offset` fails `UNMAPPED` below image base.
- A successful mapping must be unique in both source and destination spaces and
  round-trip to the original coordinate. Conflicting claims return `OVERLAPPING`
  without a value, including section/header and section/certificate conflicts.
- A mapped file byte must exist before EOF. Claimed section/header/certificate
  bytes beyond EOF return `TRUNCATED`; a zero raw pointer supplies no disk bytes.
- `offset_to_va` preserves `HEADERS` for a successful header mapping.

## Interval mapping across section boundaries

`map_rva_interval(start, end)` and `map_offset_interval(start, end)` split the
input at every region/section boundary and every raw↔virtual transition, then
classify each sub-segment independently. They return:

- an `IntervalSet` of the **OK** mapped sub-intervals (the canonical projection), and
- an ordered tuple of `Segment(source, status, mapped)` covering the whole input,
  including failure segments, so nothing is silently dropped.

Splits also include actual EOF and boundaries projected from the destination
space, so a conflict beginning inside a source section cannot be included in a
successful segment. Regression tests compare every segment against point
mapping across small malformed layouts and verify every successful point's
round trip. Interval algebra tests cover all 32 × 32 subset pairs of five small
intervals against integer-set union, intersection, difference and Jaccard.

## Analyzer component interface

`CoordinateComponent(identifier, kind, rva_intervals, provenance)` is the stable
hand-off point for external analyzer results (functions, basic blocks). `kind` is
free-form (`"function"`, `"basic_block"`, …). `Provenance(source, version, extra)`
records origin (`binaryninja`, `capa`, `deepreflect`, `synthetic`,
`human_verified`, …) and mirrors the DeepReflect adapter schema in
`external/deepreflect/README.md`. `PeAtlas.map_component` maps a component's RVA
intervals to a canonical `MappedComponent(file_offsets, segments, provenance)`
and reports `fully_mapped` / `unmapped_length`.

**Location is not label.** PEAtlas carries only coordinates and provenance; a
maliciousness label is a separate field owned by the annotation/adjudication
layer, per the plan's Tier separation.

## Implemented in this change

- PE32 / PE32+ header + section-table + certificate-directory + overlay parsing
- `offset ↔ rva`, `offset ↔ va`, `rva/va → offset`, `classify_offset`
- all `MapStatus` failure states above
- `IntervalSet` algebra and mask interop
- interval mapping with section-boundary / raw-virtual splitting
- analyzer component interface + provenance
- Tier 0 tests: hand-computed expectations, mapped-region round trips,
  section-boundary splitting, exhaustive small-fixture interval algebra, and the
  malformed-layout cases (overlap, truncation, padding, overlay, virtual-only,
  certificate, PE32+)

## Not implemented here (next tasks)

- **pixel ↔ byte projection.** Implemented in a follow-up on
  `peatlas.projection` (raw-rgb / word16-rgb) — see
  `docs/PEATLAS_PROJECTION_CONTRACT.md`. It reads `ua_sahi_mal.encoding` metadata
  rather than duplicating the encoder. (Added after this Tier 0 change.)
- **real analyzer runs** (Binary Ninja / capa / DeepReflect): only the interface
  exists; no disassembly is performed.
- **Tier 1 synthetic data generator** (planted-component corpus + matched
  controls): out of scope here; the test fixtures build minimal headers only.
- section-flag/permission semantics, relocations, `.NET`/managed layout, packed or
  self-modifying samples (these are separate v3 strata).

## Known unsupported / edge behaviour

- Coordinates in `OVERLAPPING` regions are intentionally not resolved; the caller
  must treat them as ambiguous (robustness stratum).
- `size_of_headers` is trusted from the optional header; a sample lying about it
  is describable but not corrected here.
- Duplicate-name sections are allowed; sections are addressed by index.
