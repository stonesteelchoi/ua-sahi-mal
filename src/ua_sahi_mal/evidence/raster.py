"""Parse BIG2015 ``.bytes`` dumps and rasterize them at a fixed width.

Coordinate contract
-------------------
A dump is a virtual-address-indexed hexadecimal listing.  Parsing yields a flat
byte array plus a validity mask (``??`` placeholders and address gaps are not
real bytes).  Offsets in this package always mean *offsets into that flat
array*, never file offsets of the original PE, because the original PE is not
recoverable from a BIG2015 dump.

Rasterizing at ``width`` bytes per row maps offset ``o`` to row ``o // width``
and column ``o % width``.  Row ``r`` covers ``[r * width, (r + 1) * width)``.
The width is fixed across samples so the coordinate system is comparable; a
variable width (Nataraj et al.) would make the same offset land on different
pixels depending on file size.

This module reads bytes and hexadecimal text.  It never disassembles, imports,
loads, or executes an input artifact.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, PngImagePlugin

DEFAULT_WIDTH = 512
"""Bytes per raster row.  512 = PE ``FileAlignment`` default (0x200)."""

MAX_DUMP_BYTES = 256 * 1024 * 1024
"""Refuse dumps whose decoded length exceeds this, to bound memory."""

_HEX_LUT = np.full(256, 0xFF, dtype=np.uint8)
for _i, _ch in enumerate(b"0123456789abcdef"):
    _HEX_LUT[_ch] = _i
for _i, _ch in enumerate(b"0123456789ABCDEF"):
    _HEX_LUT[_ch] = _i

RASTER_FORMAT_VERSION = "evidence-raster-1"


class DumpParseError(ValueError):
    """The input is not a well-formed address-indexed hexadecimal dump."""


@dataclass(frozen=True)
class ByteDump:
    """A parsed dump: the bytes, which of them are real, and where they start."""

    data: np.ndarray  # uint8, shape (n,)
    valid: np.ndarray  # bool, shape (n,)
    base_address: int
    source_name: str

    def __post_init__(self) -> None:
        if self.data.dtype != np.uint8:
            raise TypeError(f"data must be uint8, got {self.data.dtype}")
        if self.valid.dtype != np.bool_:
            raise TypeError(f"valid must be bool, got {self.valid.dtype}")
        if self.data.shape != self.valid.shape:
            raise ValueError(f"shape mismatch: data {self.data.shape} vs valid {self.valid.shape}")

    @property
    def size(self) -> int:
        return int(self.data.size)

    @property
    def valid_fraction(self) -> float:
        return float(self.valid.mean()) if self.data.size else 0.0


@dataclass(frozen=True)
class Raster:
    """A dump laid out as a fixed-width image."""

    image: np.ndarray  # uint8, shape (height, width)
    valid: np.ndarray  # bool, shape (height, width)
    width: int
    byte_count: int  # bytes before row padding
    base_address: int
    source_name: str

    @property
    def height(self) -> int:
        return int(self.image.shape[0])

    def row_byte_range(self, row: int) -> tuple[int, int]:
        """Byte range covered by ``row``, clipped to the real byte count."""
        if not 0 <= row < self.height:
            raise IndexError(f"row {row} out of range for height {self.height}")
        start = row * self.width
        return start, min(start + self.width, self.byte_count)

    def flat_bytes(self) -> np.ndarray:
        return self.image.reshape(-1)[: self.byte_count]

    def flat_valid(self) -> np.ndarray:
        return self.valid.reshape(-1)[: self.byte_count]

    def metadata(self) -> dict[str, Any]:
        return {
            "format": RASTER_FORMAT_VERSION,
            "width": self.width,
            "height": self.height,
            "byte_count": self.byte_count,
            "base_address": self.base_address,
            "source_name": self.source_name,
            "valid_fraction": round(float(self.valid.reshape(-1)[: self.byte_count].mean()), 6)
            if self.byte_count
            else 0.0,
        }


def parse_bytes_dump(path: str | Path, *, max_bytes: int = MAX_DUMP_BYTES) -> ByteDump:
    """Parse an address-indexed hexadecimal dump into bytes plus a validity mask.

    Lines look like ``00401000 56 8D 44 24 08 ... CC`` where the first token is a
    hexadecimal address and the rest are byte tokens.  ``??`` marks a byte the
    dump does not carry; it becomes ``0`` with ``valid=False``.  Gaps between the
    end of one line and the address of the next are filled the same way.
    """
    path = Path(path)
    raw = path.read_bytes()
    if not raw:
        raise DumpParseError(f"{path.name}: empty file")
    if b"\x00" in raw[:4096]:
        raise DumpParseError(f"{path.name}: looks binary, not a hexadecimal dump")

    lines = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n")

    addresses: list[int] = []
    payloads: list[bytes] = []
    for line in lines:
        if not line:
            continue
        split_at = line.find(b" ")
        if split_at <= 0:
            continue
        try:
            address = int(line[:split_at], 16)
        except ValueError:
            continue  # not an address-prefixed line
        payload = line[split_at + 1 :].strip()
        if not payload:
            continue
        addresses.append(address)
        payloads.append(payload)

    if not addresses:
        raise DumpParseError(f"{path.name}: no address-prefixed lines found")

    counts = np.fromiter(((len(p) + 1) // 3 for p in payloads), dtype=np.int64, count=len(payloads))
    address_array = np.asarray(addresses, dtype=np.int64)
    base_address = int(address_array[0])
    offsets = address_array - base_address

    keep = offsets >= 0
    if not keep.all():
        offsets = offsets[keep]
        counts = counts[keep]
        payloads = [p for p, k in zip(payloads, keep, strict=False) if k]
        if not payloads:
            raise DumpParseError(f"{path.name}: every line precedes the base address")

    total = int(offsets[-1] + counts[-1])
    if total <= 0:
        raise DumpParseError(f"{path.name}: dump decodes to zero bytes")
    if total > max_bytes:
        raise DumpParseError(f"{path.name}: dump decodes to {total} bytes, over the {max_bytes} limit")

    tokens = np.frombuffer(b" ".join(payloads), dtype=np.uint8)
    token_count = int(counts.sum())
    expected_len = 3 * token_count - 1
    if tokens.size != expected_len:
        raise DumpParseError(
            f"{path.name}: byte tokens are not uniformly 2 characters "
            f"(expected {expected_len} characters, found {tokens.size})"
        )

    high = _HEX_LUT[tokens[0 : 3 * token_count : 3]]
    low = _HEX_LUT[tokens[1 : 3 * token_count : 3]]
    unknown = (high == 0xFF) | (low == 0xFF)
    values = ((high << 4) | low).astype(np.uint8)
    values[unknown] = 0

    token_starts = np.concatenate(([0], np.cumsum(counts)[:-1]))
    positions = (
        np.arange(token_count, dtype=np.int64)
        - np.repeat(token_starts, counts)
        + np.repeat(offsets, counts)
    )

    data = np.zeros(total, dtype=np.uint8)
    valid = np.zeros(total, dtype=bool)
    data[positions] = values
    valid[positions] = ~unknown

    return ByteDump(data=data, valid=valid, base_address=base_address, source_name=path.name)


def rasterize(dump: ByteDump, *, width: int = DEFAULT_WIDTH) -> Raster:
    """Lay a dump out as a ``width``-byte-per-row image, zero-padding the last row."""
    if width <= 0:
        raise ValueError(f"width must be positive, got {width}")
    byte_count = dump.size
    if byte_count == 0:
        raise ValueError("cannot rasterize an empty dump")
    height = (byte_count + width - 1) // width
    padded = height * width

    image = np.zeros(padded, dtype=np.uint8)
    valid = np.zeros(padded, dtype=bool)
    image[:byte_count] = dump.data
    valid[:byte_count] = dump.valid

    return Raster(
        image=image.reshape(height, width),
        valid=valid.reshape(height, width),
        width=width,
        byte_count=byte_count,
        base_address=dump.base_address,
        source_name=dump.source_name,
    )


def load_raster_from_dump(path: str | Path, *, width: int = DEFAULT_WIDTH) -> Raster:
    return rasterize(parse_bytes_dump(path), width=width)


def save_raster(raster: Raster, png_path: str | Path) -> Path:
    """Write the raster losslessly, with the validity mask in the alpha channel.

    Alpha is 255 for a real byte and 0 for a ``??`` placeholder, address gap, or
    row padding.  PNG is lossless, so the bytes survive a round trip exactly.
    """
    png_path = Path(png_path)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    stacked = np.stack(
        [raster.image, np.where(raster.valid, np.uint8(255), np.uint8(0))],
        axis=-1,
    )
    image = Image.fromarray(stacked, mode="LA")
    info = PngImagePlugin.PngInfo()
    for key, value in raster.metadata().items():
        info.add_text(f"uasm_{key}", json.dumps(value))
    image.save(png_path, format="PNG", optimize=False, compress_level=6, pnginfo=info)
    return png_path


def load_raster(png_path: str | Path) -> Raster:
    """Read back a raster written by :func:`save_raster`."""
    png_path = Path(png_path)
    with Image.open(png_path) as handle:
        if handle.mode != "LA":
            raise ValueError(f"{png_path.name}: expected mode LA, got {handle.mode}")
        text = dict(getattr(handle, "text", {}))
        array = np.array(handle)

    def meta(key: str, default: Any = None) -> Any:
        raw = text.get(f"uasm_{key}")
        return default if raw is None else json.loads(raw)

    image = np.ascontiguousarray(array[..., 0])
    valid = array[..., 1] > 0
    width = int(meta("width", image.shape[1]))
    if width != image.shape[1]:
        raise ValueError(f"{png_path.name}: stored width {width} != image width {image.shape[1]}")
    return Raster(
        image=image,
        valid=valid,
        width=width,
        byte_count=int(meta("byte_count", image.size)),
        base_address=int(meta("base_address", 0)),
        source_name=str(meta("source_name", png_path.stem)),
    )


def block_count(byte_count: int, block_bytes: int) -> int:
    """Number of ``block_bytes``-sized candidate blocks covering ``byte_count``."""
    if block_bytes <= 0:
        raise ValueError(f"block_bytes must be positive, got {block_bytes}")
    return (byte_count + block_bytes - 1) // block_bytes


def block_ranges(byte_count: int, block_bytes: int) -> np.ndarray:
    """``(n, 2)`` array of ``[start, end)`` byte ranges, the last one clipped."""
    n = block_count(byte_count, block_bytes)
    starts = np.arange(n, dtype=np.int64) * block_bytes
    ends = np.minimum(starts + block_bytes, byte_count)
    return np.stack([starts, ends], axis=1)
