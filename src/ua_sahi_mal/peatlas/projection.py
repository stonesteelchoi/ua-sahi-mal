"""Pixel <-> file-offset projection: the encoding <-> PEAtlas connection.

The model predicts in the pixel space of an encoded image; PEAtlas and the v3
estimand live in file-offset space. This module projects between them for the
encodings whose pixels demonstrably correspond to original file bytes, and
returns results as a canonical :class:`IntervalSet` in the same file-offset space
PEAtlas uses.

Supported encodings (``EncodingMetadata.source_unit == "byte_offset"``):

- ``raw-rgb``   — 3 file bytes per pixel (stride 3)
- ``word16-rgb`` — 2 file bytes per pixel (stride 2)

Both are lossless byte encodings performed **without image resize**, so a pixel
maps to a known, contiguous run of file offsets. Everything else is refused:

- ``opcode-3gram-rgb`` — pixels are sliding windows over disassembly *tokens*, not
  raw file bytes; there is no direct file-offset correspondence.
- ``existing-image``   — a pre-made image with no source-byte mapping.
- any **resized / letterboxed model-input** image — a lossy transform; this module
  operates in the *encoded* (lossless) image space only. Undo the resize before
  projecting; this module will not fabricate offsets for resized coordinates.

Padding never present in the original file (last-pixel channel padding and the
image-rectangle padding pixels) is excluded from every projection. Non-contiguous
results are returned as an interval union.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .intervals import Interval, IntervalSet

BYTE_OFFSET = "byte_offset"
SUPPORTED_MODES = ("raw-rgb", "word16-rgb")
RGB_CHANNELS = 3


class UnsupportedProjectionError(ValueError):
    """Raised when an encoding has no honest pixel<->file-offset correspondence."""


def _get(meta: object, name: str):
    if isinstance(meta, dict):
        return meta.get(name)
    return getattr(meta, name, None)


@dataclass(frozen=True)
class PixelProjection:
    """Projection contract between encoded-image pixels and file offsets.

    Records image size, channels, stride, and the padding/transform history needed
    to exclude non-original bytes. Build with :meth:`from_metadata` from an
    ``EncodingMetadata`` (or its ``to_dict()``); unsupported encodings raise.
    """

    mode: str
    width: int
    height: int
    channels: int
    stride: int
    source_byte_count: int
    pixel_count: int
    padded_pixel_count: int

    # transform history / contract flags
    resized: bool = False
    lossless_bytes: bool = True

    @classmethod
    def from_metadata(cls, meta: object, *, resized: bool = False) -> PixelProjection:
        mode = _get(meta, "mode")
        source_unit = _get(meta, "source_unit")
        if resized:
            raise UnsupportedProjectionError(
                "resized/letterboxed images are not projectable; undo the resize first"
            )
        if mode not in SUPPORTED_MODES or source_unit != BYTE_OFFSET:
            raise UnsupportedProjectionError(
                f"encoding mode={mode!r} source_unit={source_unit!r} has no file-byte "
                f"correspondence; supported: {SUPPORTED_MODES} with source_unit={BYTE_OFFSET!r}"
            )
        stride = int(_get(meta, "stride"))
        if stride < 1:
            raise UnsupportedProjectionError("stride must be >= 1")
        width = int(_get(meta, "width"))
        pixel_count = int(_get(meta, "pixel_count"))
        source_byte_count = int(_get(meta, "source_unit_count"))
        height = int(_get(meta, "height") or math.ceil(pixel_count / width))
        padded = _get(meta, "padded_pixel_count")
        padded = int(padded) if padded is not None else width * height - pixel_count
        return cls(
            mode=mode, width=width, height=height, channels=RGB_CHANNELS, stride=stride,
            source_byte_count=source_byte_count, pixel_count=pixel_count,
            padded_pixel_count=padded, resized=resized, lossless_bytes=True,
        )

    # -- byte <-> pixel/channel ------------------------------------------
    def byte_to_pixel_channel(self, offset: int) -> tuple[int, int]:
        """Map a source-file byte offset to ``(pixel_index, channel)``.

        For word16-rgb, channel 0 is the high byte and channel 1 the low byte.
        """
        if not 0 <= offset < self.source_byte_count:
            raise ValueError(f"offset {offset} outside source bytes [0, {self.source_byte_count})")
        return divmod(offset, self.stride)

    def pixel_to_byte_span(self, pixel: int) -> Interval | None:
        """File-offset span of one pixel, or None for a padding pixel.

        The span is clamped to the real byte count, so the last pixel's channel
        padding is excluded.
        """
        if pixel < 0:
            raise ValueError("pixel index must be non-negative")
        if pixel >= self.pixel_count:
            return None  # image-rectangle padding pixel; no original bytes
        lo = pixel * self.stride
        hi = min(lo + self.stride, self.source_byte_count)
        return Interval(lo, hi) if lo < hi else None

    # -- interval projections --------------------------------------------
    def pixels_to_bytes(self, pixels: IntervalSet) -> IntervalSet:
        """Project a pixel interval union to a file-offset interval union.

        Padding pixels (index >= pixel_count) and last-pixel channel padding are
        excluded; the result is a normalized union.
        """
        out: list[Interval] = []
        for iv in pixels:
            lo_pixel = max(0, iv.start)
            hi_pixel = min(self.pixel_count, iv.end)
            if lo_pixel >= hi_pixel:
                continue
            byte_lo = lo_pixel * self.stride
            byte_hi = min(hi_pixel * self.stride, self.source_byte_count)
            if byte_lo < byte_hi:
                out.append(Interval(byte_lo, byte_hi))
        return IntervalSet(out)

    def bytes_to_pixels(self, byte_offsets: IntervalSet) -> IntervalSet:
        """Project a file-offset interval union to the pixels that carry them.

        A byte maps to the pixel whose stride-window contains it; sub-pixel byte
        boundaries widen to whole pixels (inherent to a >1 stride).
        """
        out: list[Interval] = []
        for iv in byte_offsets:
            lo = max(0, iv.start)
            hi = min(self.source_byte_count, iv.end)
            if lo >= hi:
                continue
            p0 = lo // self.stride
            p1 = math.ceil(hi / self.stride)
            out.append(Interval(p0, p1))
        return IntervalSet(out)

    # -- bbox / mask -> file offsets -------------------------------------
    def bbox_to_bytes(self, x: int, y: int, w: int, h: int) -> IntervalSet:
        """Project a pixel bbox ``(x, y, w, h)`` (row-major) to file offsets.

        The bbox is decomposed row by row so that only its columns contribute (a
        multi-row bbox does not sweep unrelated pixels), then projected to bytes.
        """
        if w <= 0 or h <= 0:
            raise ValueError("bbox width and height must be positive")
        if x < 0 or y < 0 or x + w > self.width or y + h > self.height:
            raise ValueError("bbox is outside the encoded image")
        rows: list[Interval] = []
        for row in range(y, y + h):
            start = row * self.width + x
            rows.append(Interval(start, start + w))
        return self.pixels_to_bytes(IntervalSet(rows))

    def mask_to_bytes(self, mask: list[int] | list[bool]) -> IntervalSet:
        """Project a flat row-major pixel mask (truthy = selected) to file offsets."""
        if len(mask) > self.width * self.height:
            raise ValueError("mask longer than the encoded image")
        return self.pixels_to_bytes(IntervalSet.from_mask(mask))


def project_pixels_to_atlas(pixels: IntervalSet, projection: PixelProjection, atlas):  # type: ignore[no-untyped-def]
    """Full encoding->PEAtlas connection: pixels -> file offsets -> atlas segments.

    Returns ``(file_offsets, segments)`` where ``file_offsets`` is the projected
    file-offset union and ``segments`` is PEAtlas's per-region breakdown of it
    (OK / virtual-only / padding / overlay / ...). This is where a model's pixel
    prediction becomes canonical, region-classified file-offset evidence.
    """
    offsets = projection.pixels_to_bytes(pixels)
    all_segments = []
    for iv in offsets:
        _, segs = atlas.map_offset_interval(iv.start, iv.end)
        all_segments.extend(segs)
    return offsets, tuple(all_segments)
