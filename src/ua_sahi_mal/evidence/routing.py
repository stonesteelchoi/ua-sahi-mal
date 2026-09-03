"""Budgeted routing: spend K block probes where a cheap map says evidence is.

An exhaustive sweep of a 4 MB sample costs 1,024 forward passes at a 4 KB block
size; the corpus costs hours.  Routing spends one cheap pass per *tile* (a few
dozen blocks' worth), upsamples that coarse map to block resolution, and probes
only the top K blocks.  Whether that recovers the exhaustive result is measured,
not assumed -- pre-registered criterion D5.

The upsampler is the one place the original UA-SAHI idea survives into v2, and
it enters as an ablation term, not a premise.  Earlier measurements on real byte
images (``docs/results/big2015/``) found edge-aware upsampling losing to plain
bilinear, because a region boundary in a byte image is a change in *distribution*
rather than in value (Cohen's d 8.50 for row entropy against 0.96 for raw byte
value).  So the guided upsampler here is guided by entropy, and the pre-registered
expectation is that it still fails to beat bilinear -- D6.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

import numpy as np

from ua_sahi_mal.evidence import features, occlusion, raster

UPSAMPLE_NEAREST = "nearest"
UPSAMPLE_LINEAR = "bilinear"
UPSAMPLE_JBU = "jbu"
UPSAMPLE_UA = "ua"
SUPPORTED_UPSAMPLERS = (UPSAMPLE_NEAREST, UPSAMPLE_LINEAR, UPSAMPLE_JBU, UPSAMPLE_UA)

ROUTE_COARSE = "coarse-occlusion"
ROUTE_ENTROPY = "entropy"
ROUTE_RANDOM = "random"
ROUTE_UNIFORM = "uniform"
SUPPORTED_ROUTERS = (ROUTE_COARSE, ROUTE_ENTROPY, ROUTE_RANDOM, ROUTE_UNIFORM)

DEFAULT_BLOCK_BYTES = 4096
DEFAULT_BUDGET = 1.0 / 16.0


class UpsamplerUnavailable(RuntimeError):
    """The requested upsampler cannot run in this environment."""


# ---------------------------------------------------------------------------
# 1-D upsampling
# ---------------------------------------------------------------------------


def upsample_nearest(coarse: np.ndarray, target: int) -> np.ndarray:
    values = np.asarray(coarse, dtype=np.float64)
    if values.size == 0 or target <= 0:
        return np.zeros(max(target, 0), dtype=np.float64)
    index = np.minimum((np.arange(target) * values.size) // target, values.size - 1)
    return values[index]


def upsample_linear(coarse: np.ndarray, target: int) -> np.ndarray:
    """Linear interpolation between coarse-cell centres."""
    values = np.asarray(coarse, dtype=np.float64)
    if values.size == 0 or target <= 0:
        return np.zeros(max(target, 0), dtype=np.float64)
    if values.size == 1:
        return np.full(target, values[0], dtype=np.float64)
    scale = values.size / target
    centres = (np.arange(target) + 0.5) * scale - 0.5
    return np.interp(centres, np.arange(values.size, dtype=np.float64), values)


def upsample_jbu(
    coarse: np.ndarray,
    target: int,
    guide: np.ndarray,
    *,
    sigma_spatial: float = 1.0,
    sigma_range: float = 0.15,
) -> np.ndarray:
    """Joint bilateral upsampling along one axis, guided by a fine-scale signal.

    ``guide`` is the fine-resolution guidance (one value per target cell).  The
    coarse guidance is its block average, so the range kernel compares like with
    like.  Kopf et al. in one dimension.
    """
    values = np.asarray(coarse, dtype=np.float64)
    fine_guide = np.asarray(guide, dtype=np.float64)
    if fine_guide.size != target:
        raise ValueError(f"guide has {fine_guide.size} entries but target is {target}")
    if values.size == 0 or target <= 0:
        return np.zeros(max(target, 0), dtype=np.float64)
    if values.size == 1:
        return np.full(target, values[0], dtype=np.float64)

    scale = target / values.size
    edges = np.round(np.arange(values.size + 1) * scale).astype(np.int64)
    edges[-1] = target
    coarse_guide = np.array(
        [
            fine_guide[start:end].mean() if end > start else fine_guide[min(start, target - 1)]
            for start, end in zip(edges[:-1], edges[1:], strict=False)
        ]
    )

    coarse_centres = (np.arange(values.size) + 0.5) * scale
    fine_centres = np.arange(target) + 0.5

    spatial = np.exp(
        -0.5 * ((fine_centres[:, None] - coarse_centres[None, :]) / (sigma_spatial * scale)) ** 2
    )
    range_term = np.exp(
        -0.5 * ((fine_guide[:, None] - coarse_guide[None, :]) / max(sigma_range, 1e-6)) ** 2
    )
    weights = spatial * range_term
    total = weights.sum(axis=1, keepdims=True)
    safe = np.where(total > 0, total, 1.0)
    result = (weights @ values)[:, None] / safe
    fallback = upsample_linear(values, target)[:, None]
    return np.where(total > 0, result, fallback).reshape(-1)


def upsample_ua(coarse: np.ndarray, target: int, guide: np.ndarray, **_: Any) -> np.ndarray:
    """Upsample Anything.

    The published implementation hard-codes ``.cuda()`` and runs 5,100
    test-time optimization steps (the paper's text says 50).  Neither is usable
    on the CPU-only budget this study runs on, so this raises rather than
    silently substituting a different method and reporting it as UA.
    """
    raise UpsamplerUnavailable(
        "The UA reference implementation requires CUDA and 5,100 optimization steps. "
        "D6 is reported as unmeasured on CPU-only runs; see research plan v2 R7."
    )


def upsample(
    coarse: np.ndarray,
    target: int,
    method: str,
    guide: np.ndarray | None = None,
    **kwargs: Any,
) -> np.ndarray:
    if method == UPSAMPLE_NEAREST:
        return upsample_nearest(coarse, target)
    if method == UPSAMPLE_LINEAR:
        return upsample_linear(coarse, target)
    if method == UPSAMPLE_JBU:
        if guide is None:
            raise ValueError("the JBU upsampler needs a guidance signal")
        return upsample_jbu(coarse, target, guide, **kwargs)
    if method == UPSAMPLE_UA:
        if guide is None:
            raise ValueError("the UA upsampler needs a guidance signal")
        return upsample_ua(coarse, target, guide, **kwargs)
    raise ValueError(f"unknown upsampler {method!r}; expected one of {list(SUPPORTED_UPSAMPLERS)}")


# ---------------------------------------------------------------------------
# guidance and coarse maps
# ---------------------------------------------------------------------------


def block_entropy_guide(data: np.ndarray, block_bytes: int) -> np.ndarray:
    """Per-block entropy in ``[0, 1]`` -- the guidance channel and the Entropy-K score."""
    ranges = raster.block_ranges(data.size, block_bytes)
    guide = np.zeros(ranges.shape[0], dtype=np.float64)
    for index, (start, end) in enumerate(ranges):
        segment = data[start:end]
        if segment.size == 0:
            continue
        counts = np.bincount(segment, minlength=256).astype(np.float64)
        probabilities = counts / segment.size
        nonzero = probabilities[probabilities > 0]
        guide[index] = float(-(nonzero * np.log2(nonzero)).sum())
    return guide / 8.0


@dataclass
class CoarseMap:
    """A cheap tile-resolution evidence map plus what it cost to make."""

    scores: np.ndarray  # (n_tiles,)
    tile_ranges: np.ndarray  # (n_tiles, 2)
    forward_passes: int

    def to_block_scores(
        self, block_count: int, method: str, guide: np.ndarray | None = None, **kwargs: Any
    ) -> np.ndarray:
        return upsample(self.scores, block_count, method, guide, **kwargs)


def coarse_occlusion_map(
    classifier: Any,
    data: np.ndarray,
    label: int,
    *,
    fill: occlusion.FillPlan,
    rng: np.random.Generator,
    tile_rows: int = features.DEFAULT_TILE_ROWS,
    width: int = features.DEFAULT_WIDTH,
) -> CoarseMap:
    """Occlude one tile at a time and record how much the true-class NLL rises."""
    tile_ranges = features.tile_byte_ranges(data.size, tile_rows=tile_rows, width=width)
    baseline = classifier.negative_log_likelihood(data, label)
    scores = np.zeros(tile_ranges.shape[0], dtype=np.float64)
    for index, (start, end) in enumerate(tile_ranges):
        masked = occlusion.occlude(data, [(int(start), int(end))], fill, rng)
        scores[index] = classifier.negative_log_likelihood(masked, label) - baseline
    return CoarseMap(scores=scores, tile_ranges=tile_ranges, forward_passes=int(tile_ranges.shape[0]) + 1)


def routing_scores(
    router: str,
    *,
    block_count: int,
    data: np.ndarray | None = None,
    block_bytes: int = DEFAULT_BLOCK_BYTES,
    coarse: CoarseMap | None = None,
    upsampler: str = UPSAMPLE_LINEAR,
    guide: np.ndarray | None = None,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Score every candidate block so the top K can be probed.

    ``entropy`` is the baseline a security reviewer asks about first ("can you
    not just do this with entropy?"), ``random`` and ``uniform`` separate the
    effect of the budget itself from the effect of the ranking.
    """
    if router == ROUTE_COARSE:
        if coarse is None:
            raise ValueError("the coarse router needs a CoarseMap")
        return coarse.to_block_scores(block_count, upsampler, guide)
    if router == ROUTE_ENTROPY:
        if data is None:
            raise ValueError("the entropy router needs the sample bytes")
        return block_entropy_guide(data, block_bytes)
    if router == ROUTE_RANDOM:
        if rng is None:
            raise ValueError("the random router needs a generator")
        return rng.random(block_count)
    if router == ROUTE_UNIFORM:
        # Evenly spaced: a maximally spread ranking, independent of content.
        positions = np.arange(block_count, dtype=np.float64)
        return -np.abs(positions % max(block_count / max(block_count, 1), 1.0))
    raise ValueError(f"unknown router {router!r}; expected one of {list(SUPPORTED_ROUTERS)}")


def budget_size(block_count: int, budget: float = DEFAULT_BUDGET) -> int:
    """How many blocks a budget buys -- at least one, never more than all of them."""
    if not 0 < budget <= 1:
        raise ValueError(f"budget must be in (0, 1], got {budget}")
    return int(min(block_count, max(1, np.ceil(budget * block_count))))


def select_blocks(scores: Sequence[float], budget: float = DEFAULT_BUDGET) -> np.ndarray:
    from ua_sahi_mal.evidence.metrics import top_k_indices

    array = np.asarray(list(scores), dtype=np.float64)
    return top_k_indices(array, budget_size(array.size, budget))


def uniform_block_indices(block_count: int, k: int) -> np.ndarray:
    """Evenly spaced block indices -- the coverage baseline."""
    if k <= 0 or block_count <= 0:
        return np.zeros(0, dtype=np.int64)
    k = min(k, block_count)
    return np.unique(np.linspace(0, block_count - 1, k).round().astype(np.int64))


def available_upsamplers(include_ua: bool = False) -> tuple[str, ...]:
    """Upsamplers this environment can actually run."""
    base = (UPSAMPLE_NEAREST, UPSAMPLE_LINEAR, UPSAMPLE_JBU)
    if not include_ua:
        return base
    try:
        import torch

        if torch.cuda.is_available():
            return base + (UPSAMPLE_UA,)
    except ImportError:
        pass
    return base


def make_router_callable(
    router: str, **defaults: Any
) -> Callable[..., np.ndarray]:  # pragma: no cover - thin convenience wrapper
    def call(**kwargs: Any) -> np.ndarray:
        return routing_scores(router, **{**defaults, **kwargs})

    return call
