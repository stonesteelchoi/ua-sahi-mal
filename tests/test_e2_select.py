"""E2 selectors + per-file retrieval evaluation (E2_prereg_v1)."""

from __future__ import annotations

import math

import numpy as np

from ua_sahi_mal.sorel.e2_select import SELECTOR_NAMES, evaluate_file, select_tiles
from ua_sahi_mal.sorel.e2_tiles import TILE_BYTES


def test_position_mechanic_silver_at_end():
    byte_count = 10 * TILE_BYTES
    silver = [(9 * TILE_BYTES, 9 * TILE_BYTES + 1000)]
    res = evaluate_file(byte_count, silver, np.zeros(10), seed=7)
    assert res["selectors"]["front_first"]["0.10"]["coverage"] == 0.0
    assert res["selectors"]["back_first"]["0.10"]["coverage"] == 1.0
    assert res["selectors"]["oracle_silver"]["0.10"]["coverage"] == 1.0


def test_position_mechanic_silver_at_front():
    byte_count = 10 * TILE_BYTES
    res = evaluate_file(byte_count, [(10, 1010)], np.zeros(10), seed=7)
    assert res["selectors"]["front_first"]["0.10"]["coverage"] == 1.0


def test_no_silver_excluded():
    res = evaluate_file(10 * TILE_BYTES, [], np.zeros(10), seed=7)
    assert res["has_silver"] is False
    assert math.isnan(res["selectors"]["front_first"]["0.10"]["coverage"])


def test_coverage_monotone_in_budget():
    byte_count = 10 * TILE_BYTES
    silver = [(0, TILE_BYTES + 500)]  # spans tiles 0 and 1
    res = evaluate_file(byte_count, silver, np.zeros(10), seed=7)
    cov = [res["selectors"]["front_first"][f"{b:.2f}"]["coverage"] for b in (0.02, 0.05, 0.10, 0.20, 0.50)]
    assert all(cov[i] <= cov[i + 1] + 1e-9 for i in range(len(cov) - 1))


def test_selectors_pick_exactly_k():
    n, k = 20, 5
    entropy = np.arange(n, dtype=float)
    silver_tile_bytes = np.arange(n, dtype=float)
    for name in SELECTOR_NAMES:
        idx = select_tiles(name, n_tiles=n, k=k, entropy=entropy, silver_tile_bytes=silver_tile_bytes, seed=1)
        assert idx.size == k, name
        assert np.all(np.diff(idx) > 0)  # sorted, distinct


def test_extra_scores_inject_learned_selector_and_record_mismatch():
    byte_count = 10 * TILE_BYTES
    silver = [(9 * TILE_BYTES, 9 * TILE_BYTES + 1000)]          # silver in the last tile
    learned = np.zeros(10)
    learned[9] = 5.0                                              # a "learned" scorer that found it
    bad = np.ones(7)                                              # wrong length -> recorded, not fatal
    res = evaluate_file(byte_count, silver, np.zeros(10), seed=1,
                        extra_scores={"attr_x": learned, "broken": bad})
    assert res["selectors"]["attr_x"]["0.10"]["coverage"] == 1.0
    assert "error" in res["selectors"]["broken"]
    assert res["selectors"]["front_first"]["0.10"]["coverage"] == 0.0   # baselines untouched
