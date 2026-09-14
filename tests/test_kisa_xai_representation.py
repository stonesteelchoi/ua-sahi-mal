"""interval-binned-v1: map invariants, raster semantics, projections, budget selection.

All inputs are synthetic byte strings (never real samples).
"""

from __future__ import annotations

import hashlib

import numpy as np
import pytest

from ua_sahi_mal.kisa_xai import (
    PIXELS,
    REPRESENTATION_ID,
    SIDE,
    IntervalBinnedMap,
    build_interval_map,
    encode_interval_binned,
    raster_sha256,
    select_source_bytes_by_budget,
)
from ua_sahi_mal.kisa_xai.representation import POLICY_MEAN_POOL, POLICY_NEAREST
from ua_sahi_mal.peatlas import Interval, IntervalSet

SIZES = [1, 2, 7, 223, 224, 4096, PIXELS - 1, PIXELS, PIXELS + 1, PIXELS + 13, 2 * PIXELS + 3, 1_000_003]


def _bytes(size: int, seed: int = 0) -> bytes:
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=size, dtype=np.uint8).tobytes()


# --- map construction and invariants -----------------------------------------


@pytest.mark.parametrize("size", SIZES)
def test_map_invariants_hold_for_all_regimes(size: int) -> None:
    imap = build_interval_map(size)
    imap.check_invariants()
    assert imap.representation_id == REPRESENTATION_ID
    assert imap.pixel_count == PIXELS
    assert imap.policy == (POLICY_MEAN_POOL if size >= PIXELS else POLICY_NEAREST)
    lengths = imap.pixel_lengths()
    if size >= PIXELS:
        # exact partition, lengths differ by at most one
        assert int(lengths.sum()) == size
        assert lengths.max() - lengths.min() <= 1
        assert (imap.starts[1:] == imap.ends[:-1]).all()
    else:
        assert (lengths == 1).all()
        # every byte is repeated floor(P/L) or ceil(P/L) times
        counts = np.bincount(imap.starts, minlength=size)
        assert counts.min() >= PIXELS // size
        assert counts.max() <= -(-PIXELS // size)


def test_map_is_pure_function_of_size_and_hash_is_stable() -> None:
    a = build_interval_map(12345)
    b = build_interval_map(12345)
    assert a.map_sha256() == b.map_sha256()
    assert a.map_sha256() != build_interval_map(12346).map_sha256()
    # hash is over the canonical arrays only
    expect = hashlib.sha256(a.starts.astype("<i8").tobytes() + a.ends.astype("<i8").tobytes()).hexdigest()
    assert a.map_sha256() == expect
    meta = a.metadata()
    assert meta["representation_version"] == REPRESENTATION_ID
    assert meta["map_sha256"] == expect
    assert meta["policy"] == POLICY_NEAREST


def test_empty_file_and_bad_inputs_are_rejected() -> None:
    with pytest.raises(ValueError):
        build_interval_map(0)
    with pytest.raises(TypeError):
        build_interval_map(10.0)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        build_interval_map(True)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        encode_interval_binned(b"")
    with pytest.raises(ValueError):
        IntervalBinnedMap(
            REPRESENTATION_ID, 5, SIDE, PIXELS, POLICY_NEAREST, np.zeros(3, np.int64), np.ones(3, np.int64)
        )


def test_map_arrays_are_read_only() -> None:
    imap = build_interval_map(100)
    with pytest.raises(ValueError):
        imap.starts[0] = 1


# --- raster semantics ----------------------------------------------------------


def test_long_file_raster_is_exact_interval_mean() -> None:
    data = _bytes(2 * PIXELS + 3, seed=1)
    raster, imap = encode_interval_binned(data)
    assert raster.shape == (SIDE, SIDE) and raster.dtype == np.float32
    view = np.frombuffer(data, dtype=np.uint8)
    flat = raster.reshape(-1)
    for p in [0, 1, 2, 12345, PIXELS - 2, PIXELS - 1]:
        s, e = int(imap.starts[p]), int(imap.ends[p])
        assert flat[p] == np.float32(view[s:e].sum() / (e - s))
    assert raster.min() >= 0.0 and raster.max() <= 255.0


def test_short_file_raster_is_nearest_repetition_of_bytes() -> None:
    data = _bytes(1000, seed=2)
    raster, imap = encode_interval_binned(data)
    view = np.frombuffer(data, dtype=np.uint8)
    flat = raster.reshape(-1)
    p = np.arange(PIXELS)
    expected = view[(p * 1000) // PIXELS].astype(np.float32)
    assert np.array_equal(flat, expected)
    assert imap.policy == POLICY_NEAREST


def test_exact_size_file_raster_is_the_file_itself() -> None:
    data = _bytes(PIXELS, seed=3)
    raster, imap = encode_interval_binned(data)
    assert imap.policy == POLICY_MEAN_POOL
    assert np.array_equal(raster.reshape(-1), np.frombuffer(data, dtype=np.uint8).astype(np.float32))


def test_raster_and_map_hashes_are_deterministic_and_input_sensitive() -> None:
    data = _bytes(70_000, seed=4)
    r1, m1 = encode_interval_binned(data)
    r2, m2 = encode_interval_binned(bytearray(data))
    assert raster_sha256(r1) == raster_sha256(r2)
    assert m1.map_sha256() == m2.map_sha256()
    changed = bytearray(data)
    changed[500] ^= 0xFF
    r3, _ = encode_interval_binned(bytes(changed))
    assert raster_sha256(r3) != raster_sha256(r1)
    assert not r1.flags.writeable


# --- projections ---------------------------------------------------------------


@pytest.mark.parametrize("size", [300, PIXELS, 3 * PIXELS + 7])
def test_pixel_byte_round_trips_are_supersets(size: int) -> None:
    imap = build_interval_map(size)
    pixels = IntervalSet([(0, 3), (1000, 1010), (PIXELS - 5, PIXELS)])
    as_bytes = imap.pixels_to_bytes(pixels)
    back = imap.bytes_to_pixels(as_bytes)
    # pixel -> bytes -> pixels recovers at least the original pixels
    assert back.intersection(pixels) == pixels
    # bytes -> pixels -> bytes recovers at least the original bytes
    byte_query = IntervalSet([(0, 1), (size // 2, size // 2 + 1), (size - 1, size)])
    covering = imap.bytes_to_pixels(byte_query)
    assert imap.pixels_to_bytes(covering).intersection(byte_query) == byte_query
    # whole image maps onto the whole file
    assert imap.pixels_to_bytes(IntervalSet.single(0, PIXELS)) == IntervalSet.single(0, size)
    assert imap.bytes_to_pixels(IntervalSet.single(0, size)) == IntervalSet.single(0, PIXELS)


def test_pixels_to_bytes_accepts_indices_and_rejects_out_of_range() -> None:
    imap = build_interval_map(PIXELS * 2)
    assert imap.pixels_to_bytes([0, 1]) == IntervalSet.single(0, 4)
    assert imap.pixels_to_bytes([]) == IntervalSet.empty()
    assert imap.pixel_interval(PIXELS - 1) == Interval(2 * PIXELS - 2, 2 * PIXELS)
    with pytest.raises(ValueError):
        imap.pixels_to_bytes([PIXELS])
    with pytest.raises(ValueError):
        imap.pixel_interval(-1)


def test_bytes_to_pixels_clamps_to_file_and_ignores_outside() -> None:
    imap = build_interval_map(500)
    assert imap.bytes_to_pixels(IntervalSet.single(600, 700)) == IntervalSet.empty()
    covering = imap.bytes_to_pixels(IntervalSet.single(499, 10_000))
    assert not covering.is_empty()
    assert covering.intervals[-1].end == PIXELS


# --- budget selection ------------------------------------------------------------


def test_budget_selection_reports_requested_and_achieved_with_overshoot() -> None:
    size = 10 * PIXELS + 5  # every pixel covers 10 or 11 bytes
    imap = build_interval_map(size)
    scores = np.zeros(PIXELS)
    scores[:200] = np.linspace(1.0, 0.5, 200)
    sel = select_source_bytes_by_budget(scores, imap, 0.001)
    assert sel.requested_bytes == -(-size // 1000)
    assert sel.achieved_bytes >= sel.requested_bytes
    assert sel.overshoot_bytes == sel.achieved_bytes - sel.requested_bytes
    assert sel.overshoot_bytes < imap.max_pixel_length
    assert (sel.overshoot_interval is None) == (sel.overshoot_bytes == 0)
    assert sel.intervals.total_length == sel.achieved_bytes
    assert sel.achieved_fraction == sel.achieved_bytes / size
    assert not sel.cam_empty and not sel.positive_pixels_exhausted
    # highest scores first: pixel 0 has the top score
    assert sel.selected_pixels[0] == 0
    d = sel.to_dict()
    assert d["selected_pixel_count"] == len(sel.selected_pixels) and "selected_pixels" not in d


def test_budget_ties_break_by_row_major_index_and_only_positive_scores_count() -> None:
    imap = build_interval_map(PIXELS)  # one byte per pixel
    scores = np.zeros(PIXELS)
    scores[[500, 20, 7000]] = 1.0  # tie
    scores[3] = -5.0  # negative is never selected
    sel = select_source_bytes_by_budget(scores, imap, 2 / PIXELS)
    assert sel.selected_pixels == (20, 500)
    assert sel.intervals == IntervalSet([(20, 21), (500, 501)])
    assert sel.requested_bytes == 2 and sel.achieved_bytes == 2 and sel.overshoot_bytes == 0


def test_budget_empty_cam_is_flagged_not_dropped() -> None:
    imap = build_interval_map(5000)
    sel = select_source_bytes_by_budget(np.zeros(PIXELS), imap, 0.1)
    assert sel.cam_empty and sel.positive_pixels_exhausted
    assert sel.selected_pixels == () and sel.intervals.is_empty()
    assert sel.requested_bytes == 500 and sel.achieved_bytes == 0


def test_budget_positive_mass_exhausted_before_budget_is_recorded() -> None:
    imap = build_interval_map(PIXELS)
    scores = np.zeros(PIXELS)
    scores[:10] = 1.0
    sel = select_source_bytes_by_budget(scores, imap, 0.5)
    assert sel.positive_pixels_exhausted and not sel.cam_empty
    assert sel.achieved_bytes == 10 and sel.requested_bytes == PIXELS // 2


def test_budget_short_file_counts_unique_bytes_not_pixels() -> None:
    size = 100
    imap = build_interval_map(size)  # ~502 pixels per byte
    scores = np.linspace(1.0, 2.0, PIXELS)  # last pixels first; many pixels share bytes
    sel = select_source_bytes_by_budget(scores, imap, 0.1)
    assert sel.requested_bytes == 10
    assert sel.achieved_bytes == 10 and sel.overshoot_bytes == 0
    assert len(sel.selected_pixels) > 10  # several pixels per unique byte
    assert sel.intervals.total_length == 10


def test_budget_uses_decimal_fraction_semantics() -> None:
    imap = build_interval_map(50)
    assert select_source_bytes_by_budget(np.ones(PIXELS), imap, 0.1).requested_bytes == 5
    assert select_source_bytes_by_budget(np.ones(PIXELS), imap, 0.2).requested_bytes == 10
    with pytest.raises(ValueError):
        select_source_bytes_by_budget(np.ones(PIXELS), imap, 0.0)
    with pytest.raises(ValueError):
        select_source_bytes_by_budget(np.ones(PIXELS - 1), imap, 0.1)
    bad = np.ones(PIXELS)
    bad[0] = np.nan
    with pytest.raises(ValueError):
        select_source_bytes_by_budget(bad, imap, 0.1)
