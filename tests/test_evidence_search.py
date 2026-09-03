"""The search itself: does occlusion find a range that actually carries the signal?

These use a stub classifier whose decision rule is known, so a failure points at
the search code rather than at a network that did not learn anything.
"""

from __future__ import annotations

import numpy as np
import pytest

from ua_sahi_mal.evidence import features, metrics, occlusion, routing, search


class MarkerClassifier:
    """Says class 1 when a known marker byte is dense in a known range.

    Deliberately crude: the point is that exactly one range carries the evidence,
    so the search has a right answer to be checked against.
    """

    name = "marker"
    class_count = 2

    def __init__(self, marker: int = 0xE7, threshold: float = 0.2) -> None:
        self.marker = marker
        self.threshold = threshold
        self.calls = 0

    def log_probabilities(self, data: np.ndarray, valid=None) -> np.ndarray:
        self.calls += 1
        density = float((data == self.marker).mean())
        score = min(density / self.threshold, 1.0)
        probability = 0.02 + 0.96 * score
        return np.log(np.array([1.0 - probability, probability]))

    def negative_log_likelihood(self, data: np.ndarray, label: int, valid=None) -> float:
        return float(-self.log_probabilities(data)[label])


def planted_sample(size=200_000, start=40_960, length=16_384, marker=0xE7, seed=0):
    rng = np.random.default_rng(seed)
    data = rng.integers(0, 224, size=size, dtype=np.uint8)  # marker never occurs by chance
    data[start : start + length] = marker
    return data, (start, start + length)


def test_exhaustive_search_probes_every_block_once():
    data, _ = planted_sample(size=40_960)
    model = MarkerClassifier()
    result = search.exhaustive_search(model, data, 1, sample_id="s", block_bytes=4096)

    assert result.block_count == 10
    assert result.probed.all()
    assert result.forward_passes == 11  # 10 probes plus the baseline
    assert np.isfinite(result.deltas).all()


def test_exhaustive_search_ranks_the_planted_range_first():
    data, truth = planted_sample()
    model = MarkerClassifier()
    result = search.exhaustive_search(model, data, 1, sample_id="s", block_bytes=4096)

    planted_blocks = (truth[1] - truth[0]) // 4096
    top = set(result.top_blocks(planted_blocks).tolist())
    expected = set(range(truth[0] // 4096, truth[1] // 4096))
    assert top == expected


def test_evidence_ranges_recovers_the_planted_interval():
    data, truth = planted_sample()
    model = MarkerClassifier()
    result = search.exhaustive_search(model, data, 1, sample_id="s", block_bytes=4096)

    ranges = search.evidence_ranges(result, budget=4 / result.block_count)
    assert ranges.shape == (1, 2)  # adjacent blocks merged into one interval
    assert metrics.byte_iou(ranges, [truth], data.size) == 1.0


def test_budgeted_search_probes_only_its_budget():
    data, _ = planted_sample()
    model = MarkerClassifier()
    result = search.budgeted_search(
        model,
        data,
        1,
        sample_id="s",
        block_bytes=4096,
        budget=1 / 8,
        router=routing.ROUTE_ENTROPY,
    )
    expected = routing.budget_size(result.block_count, 1 / 8)
    assert int(result.probed.sum()) == expected
    assert np.isnan(result.deltas[~result.probed]).all()


def test_budgeted_search_costs_far_less_than_the_sweep_it_replaces():
    data, _ = planted_sample(size=1_000_000)
    model = MarkerClassifier()
    full = search.exhaustive_search(model, data, 1, sample_id="s", block_bytes=4096)
    budgeted = search.budgeted_search(
        model, data, 1, sample_id="s", block_bytes=4096, budget=1 / 16, router=routing.ROUTE_ENTROPY
    )
    assert budgeted.forward_passes < full.forward_passes / 8


def test_evidence_recall_is_one_when_the_router_finds_the_planted_blocks():
    data, truth = planted_sample()
    model = MarkerClassifier()
    full = search.exhaustive_search(model, data, 1, sample_id="s", block_bytes=4096)

    planted = list(range(truth[0] // 4096, truth[1] // 4096))
    assert metrics.evidence_recall_at_budget(full.probed_deltas(), planted) == pytest.approx(1.0)


def test_necessity_beats_a_random_control_on_a_planted_sample():
    data, truth = planted_sample()
    model = MarkerClassifier()
    report = search.verify_necessity(
        model, data, 1, np.array([truth]), sample_id="s", model_name="marker"
    )
    assert report.delta_evidence > report.delta_control
    assert report.delta_evidence > 0


def test_sufficiency_keeps_the_evidence_and_drops_everything_else():
    data, truth = planted_sample()
    model = MarkerClassifier()
    report = search.verify_necessity(
        model, data, 1, np.array([truth]), sample_id="s", model_name="marker"
    )
    # Keeping only the planted range preserves marker density, so the NLL stays low.
    assert report.sufficiency_nll < report.evidence_nll


def test_prober_reuses_the_tile_cache_when_the_classifier_offers_one():
    class TiledStub(MarkerClassifier):
        tile_rows = 512
        width = 512

        def __init__(self):
            super().__init__()
            self.cache_calls = 0

        def build_cache(self, data):
            return {"data": data}

        def log_probabilities_with_cache(self, cache, replacement):
            self.cache_calls += 1
            return np.log(np.array([0.5, 0.5]))

    data, _ = planted_sample()
    model = TiledStub()
    prober = search.Prober(
        model,
        data,
        1,
        fill=occlusion.FillPlan(occlusion.FILL_ZERO),
        rng=np.random.default_rng(0),
    )
    prober.probe([(0, 4096)])
    assert model.cache_calls == 1


def test_tiles_touched_reports_every_tile_a_range_crosses():
    span = features.tile_bytes()
    touched = features.tiles_touched(np.array([[span - 10, span + 10]]))
    assert touched.tolist() == [0, 1]
