"""E2 v3 learned selectors: positional prior (torch-free) + model scorers (torch, CI/cau)."""

from __future__ import annotations

import numpy as np
import pytest

from ua_sahi_mal.sorel.e2_dataset import bytes_to_tiles
from ua_sahi_mal.sorel.e2_learned import (
    LEARNED_NAMES,
    PositionalPrior,
    fit_positional_prior_from_results,
    score_file,
)
from ua_sahi_mal.sorel.e2_tiles import TILE_BYTES


def test_positional_prior_fits_front_loaded_silver():
    # silver always in the first 10% of every file -> density peaks in the first bin
    files = [(n, np.concatenate([np.array([1000.0]), np.zeros(n - 1)])) for n in (10, 20, 40)]
    prior = PositionalPrior.fit(files, bins=10)
    assert prior.n_files == 3
    assert prior.density.argmax() == 0 and prior.density[1:].sum() == 0
    scores = prior.score(20)
    assert scores.shape == (20,) and scores[:2].sum() > 0 and scores[2:].sum() == 0
    rt = PositionalPrior.from_dict(prior.to_dict())
    assert np.allclose(rt.density, prior.density)


def test_positional_prior_from_results_uses_only_files_with_silver():
    tail = [[3 * TILE_BYTES, 3 * TILE_BYTES + 100]]
    results = [
        {"ok": True, "file_size": 4 * TILE_BYTES, "silver": {"union_intervals": tail}},
        {"ok": True, "file_size": 4 * TILE_BYTES, "silver": {"union_intervals": []}},        # ignored
        {"ok": False, "file_size": 4 * TILE_BYTES, "silver": {"union_intervals": [[0, 10]]}},  # ignored
    ]
    prior = fit_positional_prior_from_results(results, bins=4)
    assert prior.n_files == 1
    assert prior.density.argmax() == 3            # silver in the last quarter


def test_score_file_position_only_without_torch():
    bag = bytes_to_tiles(b"\x00" * (3 * TILE_BYTES))
    prior = PositionalPrior(bins=3, density=np.array([0.7, 0.2, 0.1]))
    out = score_file(bag, prior=prior)
    assert list(out) == ["position_only"] and out["position_only"] == [0.7, 0.2, 0.1]
    assert set(LEARNED_NAMES) >= {"position_only"}


def test_model_scorers_shapes_and_attention_sums_to_one():
    pytest.importorskip("torch")
    from ua_sahi_mal.sorel.e2_learned import score_attr_occlusion, score_attr_tile_conf, score_mil_attention
    from ua_sahi_mal.sorel.e2_models import build_model, resolve_device

    device = resolve_device("cpu")
    rng = np.random.default_rng(0)
    data = rng.integers(0, 256, 2 * TILE_BYTES + 500, dtype=np.uint8).tobytes()
    bag = bytes_to_tiles(data)                                   # 3 tiles, last ragged
    meanmax = build_model(3, pooling="meanmax", seed=1).to(device).eval()
    attention = build_model(3, pooling="attention", seed=1).to(device).eval()

    conf = score_attr_tile_conf(meanmax, bag, device)
    occ = score_attr_occlusion(meanmax, bag, device, seed=0)
    att = score_mil_attention(attention, bag, device)
    assert conf.shape == occ.shape == att.shape == (3,)
    assert np.all(conf <= 0.0)                                   # log-probabilities
    assert np.isclose(att.sum(), 1.0, atol=1e-5) and np.all(att >= 0)
    out = score_file(bag, meanmax_model=meanmax, attention_model=attention, device=device)
    assert set(out) == {"attr_tile_conf", "attr_occlusion", "mil_attention"}
