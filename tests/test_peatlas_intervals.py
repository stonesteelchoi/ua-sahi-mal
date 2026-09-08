"""Tier 0 tests for the half-open interval-union algebra."""

from __future__ import annotations

import pytest

from ua_sahi_mal.peatlas import Interval, IntervalSet


def test_interval_must_be_nonempty_half_open():
    with pytest.raises(ValueError):
        Interval(5, 5)
    with pytest.raises(ValueError):
        Interval(9, 4)
    iv = Interval(2, 7)
    assert iv.length == 5
    assert iv.contains(2) and iv.contains(6)
    assert not iv.contains(7)  # half-open: end excluded


@pytest.mark.parametrize("point", [True, 1.0, "1"])
def test_point_queries_require_exact_integers(point):
    with pytest.raises(TypeError):
        Interval(0, 2).contains(point)
    with pytest.raises(TypeError):
        IntervalSet.single(0, 2).contains_point(point)


@pytest.mark.parametrize("start,end", [(True, 2), (0.5, 2), (2.5, 1.5)])
def test_clamp_bounds_require_exact_integers(start, end):
    with pytest.raises(TypeError):
        IntervalSet.single(0, 3).clamp(start, end)


@pytest.mark.parametrize("length", [True, 2.0, "2"])
def test_mask_length_requires_exact_integer(length):
    with pytest.raises(TypeError):
        IntervalSet.single(0, 1).to_mask(length)


def test_normalization_merges_touching_and_overlapping():
    # touching [0,4)+[4,9) -> [0,9); overlapping [10,15)+[12,20) -> [10,20)
    s = IntervalSet([(4, 9), (0, 4), (12, 20), (10, 15)])
    assert s.intervals == (Interval(0, 9), Interval(10, 20))
    assert s.total_length == 9 + 10


def test_union():
    a = IntervalSet([(0, 5)])
    b = IntervalSet([(5, 8), (20, 25)])
    assert a.union(b) == IntervalSet([(0, 8), (20, 25)])


def test_intersection_hand_computed():
    a = IntervalSet([(0, 5), (10, 15)])
    b = IntervalSet([(3, 12)])
    assert a.intersection(b) == IntervalSet([(3, 5), (10, 12)])
    # disjoint -> empty
    assert IntervalSet([(0, 2)]).intersection(IntervalSet([(5, 9)])).is_empty()


def test_difference_hand_computed():
    a = IntervalSet([(0, 10)])
    b = IntervalSet([(2, 4), (6, 8)])
    assert a.difference(b) == IntervalSet([(0, 2), (4, 6), (8, 10)])
    # subtracting a superset yields empty
    assert IntervalSet([(3, 6)]).difference(IntervalSet([(0, 10)])).is_empty()


def test_clamp_and_contains_point():
    s = IntervalSet([(0, 5), (10, 20)])
    assert s.clamp(3, 12) == IntervalSet([(3, 5), (10, 12)])
    assert s.contains_point(4)
    assert not s.contains_point(5)
    assert s.contains_point(19)
    assert not s.contains_point(20)


def test_mask_round_trip():
    s = IntervalSet([(1, 3), (5, 6)])
    mask = s.to_mask(8)
    assert list(mask) == [0, 1, 1, 0, 0, 1, 0, 0]
    assert IntervalSet.from_mask(mask) == s
    # trailing run reaches the end
    assert IntervalSet.from_mask([0, 1, 1]) == IntervalSet([(1, 3)])


def test_jaccard():
    a = IntervalSet([(0, 10)])
    b = IntervalSet([(5, 15)])
    # inter=5, union=15
    assert a.jaccard(b) == pytest.approx(5 / 15)
    assert IntervalSet.empty().jaccard(IntervalSet.empty()) == 1.0
    assert a.jaccard(IntervalSet.empty()) == 0.0


def test_exhaustive_small_union_difference_against_bruteforce():
    # Enumerate every subset-pair of small intervals and check set algebra
    # against a brute-force integer-set model on the universe [0, 12).
    universe = 12
    base = [(0, 3), (2, 5), (5, 5 + 1), (7, 12), (9, 11)]
    valid = [Interval(a, b) for a, b in base]

    def to_set(iset: IntervalSet) -> set[int]:
        out: set[int] = set()
        for iv in iset:
            out.update(range(iv.start, iv.end))
        return out

    subsets = [IntervalSet([iv for i, iv in enumerate(valid) if bits & (1 << i)])
               for bits in range(1 << len(valid))]
    for a in subsets:
        for b in subsets:
            sa, sb = to_set(a), to_set(b)
            assert to_set(a.union(b)) == (sa | sb)
            assert to_set(a.intersection(b)) == (sa & sb)
            assert to_set(a.difference(b)) == (sa - sb)
            assert to_set(a.clamp(0, universe)) == {x for x in sa if x < universe}
            assert IntervalSet.from_mask(a.to_mask(universe)) == a
            assert a.jaccard(b) == pytest.approx(len(sa & sb) / len(sa | sb) if sa | sb else 1.0)
