"""E2 selectors and per-file retrieval evaluation (frozen: ``E2_prereg_v1``).

Selectors score/choose tiles; the evaluation measures how much of a file's
silver-evidence mass the chosen tiles capture at each budget. All metrics are
computed in *tile space* from a precomputed per-tile silver-byte vector, so a
300-file run touches no whole-file byte masks in the inner loop.

Pilot selectors need no trained model:
``random``, ``uniform``, ``front_first``, ``back_first``, ``entropy``,
``entropy_boundary``; ``oracle_silver`` is the (unfair) silver-density ceiling.
``attribution``/``MIL`` are deferred to full E2.
"""

from __future__ import annotations

import numpy as np

from ua_sahi_mal.evidence.metrics import top_k_indices
from ua_sahi_mal.evidence.routing import budget_size
from ua_sahi_mal.sorel.e2_tiles import BUDGETS, DEFAULT_GEOMETRY, Geometry

SELECTOR_NAMES: tuple[str, ...] = (
    "random",
    "uniform",
    "front_first",
    "back_first",
    "entropy",
    "entropy_boundary",
    "oracle_silver",
)


def entropy_boundary_score(entropy: np.ndarray) -> np.ndarray:
    """Per-tile score = max entropy step to either neighbour (region boundaries)."""
    n = entropy.size
    score = np.zeros(n, dtype=np.float64)
    if n <= 1:
        return score
    step = np.abs(np.diff(entropy))
    score[:-1] = np.maximum(score[:-1], step)
    score[1:] = np.maximum(score[1:], step)
    return score


def _uniform_exact(n_tiles: int, k: int) -> np.ndarray:
    """``k`` distinct, evenly spaced tile indices (exact budget, unlike the
    dedup-collapsing ``routing.uniform_block_indices``)."""
    if k >= n_tiles:
        return np.arange(n_tiles, dtype=np.int64)
    idx = np.floor(np.arange(k) * n_tiles / k).astype(np.int64)
    return np.unique(idx)


def select_tiles(
    name: str,
    *,
    n_tiles: int,
    k: int,
    entropy: np.ndarray | None = None,
    silver_tile_bytes: np.ndarray | None = None,
    seed: int = 0,
) -> np.ndarray:
    """Selected tile indices (sorted) for one selector at budget size ``k``."""
    if k <= 0 or n_tiles <= 0:
        return np.zeros(0, dtype=np.int64)
    k = min(k, n_tiles)
    if name == "random":
        rng = np.random.default_rng([seed, n_tiles])
        return np.sort(rng.choice(n_tiles, size=k, replace=False))
    if name == "uniform":
        return _uniform_exact(n_tiles, k)
    if name == "front_first":
        return np.arange(k, dtype=np.int64)
    if name == "back_first":
        return np.arange(n_tiles - k, n_tiles, dtype=np.int64)
    if name == "entropy":
        if entropy is None:
            raise ValueError("entropy selector needs an entropy vector")
        return top_k_indices(entropy, k)
    if name == "entropy_boundary":
        if entropy is None:
            raise ValueError("entropy_boundary selector needs an entropy vector")
        return top_k_indices(entropy_boundary_score(entropy), k)
    if name == "oracle_silver":
        if silver_tile_bytes is None:
            raise ValueError("oracle_silver selector needs per-tile silver bytes")
        return top_k_indices(silver_tile_bytes.astype(np.float64), k)
    raise ValueError(f"unknown selector {name!r}")


def _silver_tile_layout(
    intervals: list[tuple[int, int]], geom: Geometry, n_tiles: int
) -> tuple[np.ndarray, list[tuple[int, list[tuple[int, int]]]]]:
    """Per-tile silver-byte vector + per-interval ``(length, [(tile, overlap)])``.

    Computed by tile-arithmetic on each interval; no whole-file byte mask.
    """
    tb = geom.tile_bytes
    per_tile = np.zeros(n_tiles, dtype=np.int64)
    per_interval: list[tuple[int, list[tuple[int, int]]]] = []
    for start, end in intervals:
        length = end - start
        if length <= 0:
            continue
        first = start // tb
        last = (end - 1) // tb
        parts: list[tuple[int, int]] = []
        for tile in range(first, last + 1):
            overlap = min(end, (tile + 1) * tb) - max(start, tile * tb)
            if overlap > 0:
                per_tile[tile] += overlap
                parts.append((tile, overlap))
        per_interval.append((length, parts))
    return per_tile, per_interval


def _selection_metrics(
    selected: np.ndarray,
    per_tile_silver: np.ndarray,
    per_interval: list[tuple[int, list[tuple[int, int]]]],
    tile_lengths: np.ndarray,
    silver_bytes: int,
) -> dict[str, float | bool | int]:
    selected = np.asarray(selected, dtype=np.int64)
    intersection = int(per_tile_silver[selected].sum()) if selected.size else 0
    selected_bytes = int(tile_lengths[selected].sum()) if selected.size else 0
    coverage = intersection / silver_bytes if silver_bytes > 0 else float("nan")
    union = selected_bytes + silver_bytes - intersection
    byte_iou = intersection / union if union > 0 else 0.0
    hit = bool((per_tile_silver[selected] > 0).any()) if selected.size else False

    selected_set = {int(t) for t in selected}
    covered = 0
    for length, parts in per_interval:
        overlap = sum(o for tile, o in parts if tile in selected_set)
        if length > 0 and overlap / length >= 0.5:
            covered += 1
    interval_recall = covered / len(per_interval) if per_interval else float("nan")
    return {
        "coverage": coverage,
        "byte_iou": byte_iou,
        "interval_recall_50": interval_recall,
        "evidence_hit": hit,
        "k": int(selected.size),
    }


def evaluate_file(
    byte_count: int,
    silver_intervals: list[tuple[int, int]],
    entropy: np.ndarray,
    *,
    geom: Geometry = DEFAULT_GEOMETRY,
    budgets: tuple[float, ...] = BUDGETS,
    seed: int = 0,
) -> dict[str, object]:
    """All selectors x budgets for one file. Coverage is defined only when the
    file has silver mass; ``has_silver=False`` files are reported but excluded
    from coverage aggregation downstream."""
    tile_ranges = geom.tile_ranges(byte_count)
    n_tiles = int(len(tile_ranges))
    tile_lengths = (tile_ranges[:, 1] - tile_ranges[:, 0]).astype(np.int64)
    per_tile_silver, per_interval = _silver_tile_layout(silver_intervals, geom, n_tiles)
    silver_bytes = int(per_tile_silver.sum())

    results: dict[str, dict[str, dict[str, float | bool | int]]] = {}
    for name in SELECTOR_NAMES:
        by_budget: dict[str, dict[str, float | bool | int]] = {}
        for budget in budgets:
            k = budget_size(n_tiles, budget)
            selected = select_tiles(
                name, n_tiles=n_tiles, k=k, entropy=entropy,
                silver_tile_bytes=per_tile_silver, seed=seed,
            )
            by_budget[f"{budget:.2f}"] = _selection_metrics(
                selected, per_tile_silver, per_interval, tile_lengths, silver_bytes
            )
        results[name] = by_budget
    return {
        "n_tiles": n_tiles,
        "silver_bytes": silver_bytes,
        "has_silver": silver_bytes > 0,
        "n_silver_regions": len(per_interval),
        "selectors": results,
    }
