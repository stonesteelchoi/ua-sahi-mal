"""Occlusion mechanics and the artifact controls that make the measurement valid."""

from __future__ import annotations

import numpy as np
import pytest

from ua_sahi_mal.evidence import occlusion


def sample_bytes(size=20_000, seed=0):
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=size, dtype=np.uint8)


def test_histogram_fill_reproduces_the_sample_distribution():
    data = np.concatenate(
        [np.full(9000, 0x41, np.uint8), np.full(1000, 0x42, np.uint8)]
    )
    plan = occlusion.make_fill_plan(occlusion.FILL_HISTOGRAM, data)
    drawn = plan.draw(20_000, np.random.default_rng(0))

    share = float((drawn == 0x41).mean())
    assert 0.85 < share < 0.95  # the source is 90% 0x41
    assert set(np.unique(drawn)).issubset({0x41, 0x42})


def test_histogram_fill_ignores_invalid_bytes():
    data = np.concatenate([np.full(100, 0xAA, np.uint8), np.zeros(900, np.uint8)])
    valid = np.concatenate([np.ones(100, bool), np.zeros(900, bool)])
    plan = occlusion.make_fill_plan(occlusion.FILL_HISTOGRAM, data, valid)
    drawn = plan.draw(500, np.random.default_rng(0))
    assert (drawn == 0xAA).all()


def test_constant_fills_are_what_they_claim():
    rng = np.random.default_rng(0)
    assert (occlusion.FillPlan(occlusion.FILL_ZERO).draw(50, rng) == 0).all()
    assert (occlusion.FillPlan(occlusion.FILL_INT3).draw(50, rng) == 0xCC).all()


def test_histogram_fill_without_a_histogram_is_refused():
    with pytest.raises(ValueError, match="histogram"):
        occlusion.FillPlan(occlusion.FILL_HISTOGRAM)


def test_unknown_fill_is_refused():
    with pytest.raises(ValueError, match="unknown fill"):
        occlusion.FillPlan("blur")


def test_occlusion_replaces_only_the_named_range():
    data = sample_bytes()
    plan = occlusion.FillPlan(occlusion.FILL_ZERO)
    masked = occlusion.occlude(data, [(4096, 8192)], plan, np.random.default_rng(0))

    np.testing.assert_array_equal(masked[:4096], data[:4096])
    np.testing.assert_array_equal(masked[8192:], data[8192:])
    assert (masked[4096:8192] == 0).all()
    assert masked is not data  # the caller's array is untouched


def test_keep_only_masks_the_complement():
    data = sample_bytes()
    plan = occlusion.FillPlan(occlusion.FILL_ZERO)
    kept = occlusion.occlude(data, [(100, 200)], plan, np.random.default_rng(0), keep_only=True)

    np.testing.assert_array_equal(kept[100:200], data[100:200])
    assert (kept[:100] == 0).all()
    assert (kept[200:] == 0).all()


def test_ranges_outside_the_sample_are_refused():
    data = sample_bytes(1000)
    plan = occlusion.FillPlan(occlusion.FILL_ZERO)
    with pytest.raises(ValueError, match="must not exceed"):
        occlusion.occlude(data, [(500, 5000)], plan, np.random.default_rng(0))
    with pytest.raises(ValueError, match="non-empty"):
        occlusion.occlude(data, [(500, 500)], plan, np.random.default_rng(0))


def test_random_control_matches_the_geometry_it_controls_for():
    rng = np.random.default_rng(0)
    ranges = np.array([[0, 4096], [8192, 16384]])
    control = occlusion.random_control_ranges(ranges, 100_000, rng)

    assert control.shape == ranges.shape
    np.testing.assert_array_equal(
        np.sort(control[:, 1] - control[:, 0]), np.sort(ranges[:, 1] - ranges[:, 0])
    )
    assert (control[:, 0] >= 0).all() and (control[:, 1] <= 100_000).all()


def test_random_control_avoids_overlapping_itself_when_there_is_room():
    rng = np.random.default_rng(3)
    ranges = np.array([[0, 1000], [2000, 3000], [5000, 6000]])
    control = occlusion.random_control_ranges(ranges, 500_000, rng)
    assert (control[1:, 0] >= control[:-1, 1]).all()


def test_random_control_does_not_overlap_the_evidence_it_controls_for():
    rng = np.random.default_rng(7)
    evidence = np.array([[10_000, 20_000], [40_000, 50_000]])
    control = occlusion.random_control_ranges(evidence, 200_000, rng)

    for start, end in control:
        assert all(end <= source_start or start >= source_end for source_start, source_end in evidence)


def test_random_control_refuses_impossible_disjoint_geometry():
    rng = np.random.default_rng(0)
    with pytest.raises(ValueError, match="cannot place a random control disjoint"):
        occlusion.random_control_ranges(np.array([[0, 70]]), 100, rng)


def test_block_entropy_separates_uniform_noise_from_a_constant_run():
    rng = np.random.default_rng(0)
    data = np.concatenate(
        [rng.integers(0, 256, 4096, dtype=np.uint8), np.zeros(4096, np.uint8)]
    )
    entropy = occlusion.block_entropy(data, 4096)
    assert entropy.shape == (2,)
    assert entropy[0] > 7.9
    assert entropy[1] == 0.0


def test_constant_fill_falls_outside_a_high_entropy_sample_and_histogram_fill_does_not():
    rng = np.random.default_rng(0)
    data = rng.integers(0, 256, size=40_960, dtype=np.uint8)

    zero_report = occlusion.fill_is_in_distribution(
        data, occlusion.FillPlan(occlusion.FILL_ZERO), rng
    )
    histogram_report = occlusion.fill_is_in_distribution(
        data, occlusion.make_fill_plan(occlusion.FILL_HISTOGRAM, data), rng
    )

    assert zero_report["in_distribution"] is False
    assert histogram_report["in_distribution"] is True


def test_range_mask_marks_exactly_the_named_bytes():
    mask = occlusion.range_mask([(10, 20), (30, 35)], 100)
    assert mask.sum() == 15
    assert mask[10] and mask[19] and not mask[20]
    assert mask[30] and mask[34] and not mask[35]
