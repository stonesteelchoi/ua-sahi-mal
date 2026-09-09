"""E2 tile geometry + per-tile entropy (E2_prereg_v1)."""

from __future__ import annotations

import numpy as np

from ua_sahi_mal.sorel.e2_tiles import BUDGETS, DEFAULT_GEOMETRY, TILE_BYTES, per_tile_entropy


def test_tile_ranges_are_contiguous_tile_bytes():
    byte_count = 2 * TILE_BYTES + 500
    ranges = DEFAULT_GEOMETRY.tile_ranges(byte_count)
    assert ranges.tolist() == [[0, TILE_BYTES], [TILE_BYTES, 2 * TILE_BYTES], [2 * TILE_BYTES, byte_count]]
    assert DEFAULT_GEOMETRY.tile_count(byte_count) == 3


def test_budgets_frozen():
    assert BUDGETS == (0.02, 0.05, 0.10, 0.20, 0.50)
    assert TILE_BYTES == 49_152


def test_per_tile_entropy_low_high_and_ragged_tail():
    data = np.concatenate([
        np.zeros(TILE_BYTES, np.uint8),                                         # tile0: 0 bits
        np.random.default_rng(0).integers(0, 256, TILE_BYTES, dtype=np.uint8),  # tile1: ~8 bits
        np.full(TILE_BYTES // 2, 65, np.uint8),                                 # ragged tile2: 0 bits
    ])
    entropy = per_tile_entropy(data)
    assert entropy.shape == (3,)
    assert entropy[0] == 0.0
    assert entropy[1] > 7.9
    assert entropy[2] == 0.0  # ragged tail scored on real bytes


def test_tiles_touched_spanning_boundary():
    touched = DEFAULT_GEOMETRY.tiles_touched(np.array([[TILE_BYTES - 10, TILE_BYTES + 10]]))
    assert touched.tolist() == [0, 1]
