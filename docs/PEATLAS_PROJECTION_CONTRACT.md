# PEAtlas pixel <-> file-offset projection contract

- **Status:** first implementation (follow-up to the Tier 0 PEAtlas slice)
- **Module:** `src/ua_sahi_mal/peatlas/projection.py`
- **Depends on:** `ua_sahi_mal.encoding` (metadata only) and `peatlas.intervals`
- **Scope:** connect the model's pixel space to the canonical file-offset space so
  a pixel prediction becomes a file-offset `IntervalSet` (and, via PEAtlas, a
  region-classified result). Coordinate correctness only — no training, no
  analyzer run, no Tier 1 data generation.

## Supported encodings (file-byte correspondence provable)

Only encodings whose `EncodingMetadata.source_unit == "byte_offset"` and that
perform **no image resize**:

| mode | stride | bytes/pixel | channel meaning |
|---|---|---|---|
| `raw-rgb` | 3 | 3 | channels 0,1,2 = 3 consecutive file bytes |
| `word16-rgb` | 2 | 2 | channel 0 = high byte, 1 = low byte, 2 = high XOR low (derived, **not** a file byte) |

For these, pixel `p` covers file offsets `[p*stride, (p+1)*stride)` (clamped to the
real byte count), a direct, verifiable correspondence.

## Explicitly unsupported (no fabricated offsets)

- `opcode-3gram-rgb` — pixels are sliding windows over disassembly *tokens*; the
  source unit is an opcode, not a raw file byte, so there is no file-offset map.
- `existing-image` — a pre-made image with no source-byte mapping.
- **resized / letterboxed model-input images** — a lossy transform. This module
  works in the *encoded* (lossless) image space only; if coordinates come from a
  resized model input, undo the resize first. `from_metadata(..., resized=True)`
  raises rather than guessing.

Calling `PixelProjection.from_metadata` on any of these raises
`UnsupportedProjectionError`.

## Projection contract (`PixelProjection`)

Fields: `mode`, `width`, `height`, `channels` (=3), `stride`, `source_byte_count`,
`pixel_count`, `padded_pixel_count`, `resized`, `lossless_bytes`. Built from an
`EncodingMetadata` (or its `to_dict()`).

Image size is `width × height` pixels; `pixel_count` real pixels plus
`padded_pixel_count` rectangle-padding pixels fill it.

## Padding exclusion

Bytes never present in the original file are always excluded from projections:

- **channel padding** — the last real pixel may cover fewer than `stride` real
  bytes (raw: up to 2 padding channels; word16: up to 1). Spans are clamped to
  `source_byte_count`.
- **image-rectangle padding pixels** — indices `>= pixel_count` map to nothing.

Non-contiguous results (e.g. a one-column bbox spanning rows) are returned as an
interval **union**.

## Operations

- `byte_to_pixel_channel(offset) -> (pixel, channel)` — inverse locator; raises for
  offsets outside `[0, source_byte_count)`.
- `pixel_to_byte_span(pixel) -> Interval | None` — a pixel's file-offset span, or
  `None` for a padding pixel.
- `pixels_to_bytes(IntervalSet) -> IntervalSet` — pixel union → file-offset union
  (padding excluded). **Primary direction** for mapping model output.
- `bytes_to_pixels(IntervalSet) -> IntervalSet` — file-offset union → covering
  pixels.
- `bbox_to_bytes(x, y, w, h) -> IntervalSet` — row-decomposed pixel bbox → offsets.
- `mask_to_bytes(flat_mask) -> IntervalSet` — row-major pixel mask → offsets.
- `project_pixels_to_atlas(pixels, projection, atlas)` — the full connection:
  pixels → file offsets → PEAtlas per-region segments (OK / virtual-only / …).

## Reversibility / loss

- `pixel -> bytes -> pixel` is **exact**.
- `byte -> pixel -> byte` widens to whole-pixel granularity when `stride > 1`
  (a sub-pixel byte boundary cannot be recovered); this is inherent and documented,
  not hidden.
- The word16 XOR channel (channel 2) is a derived feature, not a file byte;
  `byte_to_pixel_channel` only ever returns channels `0 .. stride-1`.

## Coordinate space

All pixel coordinates are in the **encoded lossless image** space (the space
`encoding` produces), not the model's resized training input. Composition with
PEAtlas is by shared file-offset space: `pixels_to_bytes` output feeds
`PeAtlas.map_offset_interval` (or use `project_pixels_to_atlas`).

## Out of scope (later tasks)

Real analyzer (DeepReflect) execution, Tier 1 synthetic data generation, and any
model training are not part of this change.
