"""E2 tile geometry (frozen: ``E2_prereg_v1``).

A *tile* is a contiguous ``tile_bytes``-byte file-offset interval. The pixel
interpretation (raw-rgb, stride 3, width 256 px, 64 rows -> 49,152 B) is recorded
in ``configs/sorel20m_e2_v1.yaml`` for the image-rendering stage; the retrieval
evaluation is byte-interval based, so every tiling computation here is in bytes
and only ``tile_bytes`` matters. Tiling, entropy, and touched-tile mapping all
reuse :mod:`ua_sahi_mal.evidence` so E2 shares one implementation with the
BIG2015 evidence track.

Nothing here disassembles, imports, or executes a sample.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ua_sahi_mal.evidence import features
from ua_sahi_mal.evidence.occlusion import block_entropy

TILE_BYTES = 49_152           # 256 px * 3 (stride) * 64 rows
BUDGETS: tuple[float, ...] = (0.02, 0.05, 0.10, 0.20, 0.50)
PRIMARY_BUDGET = 0.10


@dataclass(frozen=True)
class Geometry:
    """Byte-space tiling. ``tile_rows=1, width=tile_bytes`` factors the evidence
    helpers into contiguous ``tile_bytes`` intervals."""

    tile_bytes: int = TILE_BYTES

    def tile_ranges(self, byte_count: int) -> np.ndarray:
        """``(n, 2)`` int64 ``[start, end)`` byte ranges, one per tile."""
        return features.tile_byte_ranges(byte_count, tile_rows=1, width=self.tile_bytes)

    def tile_count(self, byte_count: int) -> int:
        return features.tile_count(byte_count, tile_rows=1, width=self.tile_bytes)

    def tiles_touched(self, ranges: np.ndarray) -> np.ndarray:
        """Indices of tiles overlapped by any ``[start, end)`` in ``ranges``."""
        return features.tiles_touched(ranges, tile_rows=1, width=self.tile_bytes)


DEFAULT_GEOMETRY = Geometry()


def _shannon(counts: np.ndarray, total: int) -> float:
    if total <= 0:
        return 0.0
    p = counts / float(total)
    with np.errstate(divide="ignore", invalid="ignore"):
        terms = np.where(p > 0, p * np.log2(p), 0.0)
    return float(-terms.sum())


def per_tile_entropy(data: np.ndarray, geom: Geometry = DEFAULT_GEOMETRY) -> np.ndarray:
    """Shannon entropy (bits/byte) per tile, including a ragged final tile.

    ``block_entropy`` covers only whole ``tile_bytes`` blocks; the trailing
    partial tile (if any) is scored on its real bytes so every tile in
    ``tile_ranges`` has an entropy value.
    """
    if data.dtype != np.uint8:
        raise TypeError(f"data must be uint8, got {data.dtype}")
    n = geom.tile_count(data.size)
    tb = geom.tile_bytes
    full = data.size // tb
    entropy = np.zeros(n, dtype=np.float64)
    if full > 0:
        entropy[:full] = block_entropy(data, tb)
    if full < n:  # ragged tail tile
        tail = data[full * tb:]
        counts = np.bincount(tail, minlength=256).astype(np.float64)
        entropy[full] = _shannon(counts, tail.size)
    return entropy
