"""Finding the byte ranges a family classifier relies on.

The search is occlusion: mask a candidate block, ask the classifier again, and
record how much the true-class negative log-likelihood rose.  A block whose
masking costs the classifier nothing is not evidence, whatever a saliency map
would have said about it.

Two modes:

``exhaustive``
    Probe every block.  This is the ground truth a budgeted run is measured
    against, and it is affordable only because the tiled classifier re-encodes
    the single tile an occlusion touches instead of the whole sample.

``budgeted``
    Score all blocks with a cheap router, probe the top K.  Recovering the
    exhaustive evidence mass at K = N/16 is pre-registered criterion D5.

Necessity and sufficiency are both measured, because a range can be necessary
and still not be the evidence -- masking anything large enough hurts.  That is
what the random-location control is for.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

from ua_sahi_mal.evidence import features, metrics, occlusion, raster, routing


@dataclass
class SearchResult:
    """Per-block occlusion deltas for one sample, plus what the search cost."""

    sample_id: str
    label: int
    block_bytes: int
    byte_count: int
    baseline_nll: float
    deltas: np.ndarray  # (n_blocks,), NaN where not probed
    probed: np.ndarray  # (n_blocks,) bool
    forward_passes: int
    mode: str
    fill: str
    router: str | None = None
    upsampler: str | None = None
    budget: float | None = None
    routing_score: np.ndarray | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def block_count(self) -> int:
        return int(self.deltas.size)

    def probed_deltas(self) -> np.ndarray:
        """Deltas with unprobed blocks read as zero evidence."""
        return np.nan_to_num(self.deltas, nan=0.0)

    def top_blocks(self, k: int) -> np.ndarray:
        return metrics.top_k_indices(self.probed_deltas(), k)

    def block_ranges(self) -> np.ndarray:
        return raster.block_ranges(self.byte_count, self.block_bytes)

    def ranges_for(self, indices: Sequence[int]) -> np.ndarray:
        table = self.block_ranges()
        chosen = np.asarray(list(indices), dtype=np.int64)
        return table[chosen] if chosen.size else np.zeros((0, 2), dtype=np.int64)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "label": self.label,
            "block_bytes": self.block_bytes,
            "byte_count": self.byte_count,
            "baseline_nll": self.baseline_nll,
            "block_count": self.block_count,
            "probed_count": int(self.probed.sum()),
            "forward_passes": self.forward_passes,
            "mode": self.mode,
            "fill": self.fill,
            "router": self.router,
            "upsampler": self.upsampler,
            "budget": self.budget,
            "evidence_mass": metrics.evidence_mass(self.probed_deltas()),
            "max_delta": float(np.nanmax(self.deltas)) if np.isfinite(self.deltas).any() else float("nan"),
            **self.extras,
        }


def _tile_slice(data: np.ndarray, tile_index: int, tile_rows: int, width: int) -> np.ndarray:
    """The bytes of one tile, zero-padded to a full tile."""
    span = tile_rows * width
    start = tile_index * span
    chunk = data[start : start + span]
    if chunk.size == span:
        return chunk.reshape(tile_rows, width)
    padded = np.zeros(span, dtype=np.uint8)
    padded[: chunk.size] = chunk
    return padded.reshape(tile_rows, width)


class Prober:
    """Scores masked variants of one sample, reusing whatever can be reused.

    For the tiled classifier this is the difference between one tile forward
    pass and a whole-sample pass per probe; over a corpus it is the difference
    between minutes and hours.
    """

    def __init__(
        self,
        classifier: Any,
        data: np.ndarray,
        label: int,
        *,
        fill: occlusion.FillPlan,
        rng: np.random.Generator,
    ) -> None:
        self.classifier = classifier
        self.data = data
        self.label = label
        self.fill = fill
        self.rng = rng
        self.forward_passes = 0
        self._cache = None
        self._tile_rows = getattr(classifier, "tile_rows", None)
        self._width = getattr(classifier, "width", features.DEFAULT_WIDTH)
        if self._tile_rows is not None and hasattr(classifier, "build_cache"):
            self._cache = classifier.build_cache(data)
        self.baseline_nll = float(classifier.negative_log_likelihood(data, label))
        self.forward_passes += 1

    def probe(self, ranges: Sequence[Sequence[int]], *, keep_only: bool = False) -> float:
        """NLL of the masked sample.  ``keep_only`` masks the complement instead."""
        masked = occlusion.occlude(self.data, ranges, self.fill, self.rng, keep_only=keep_only)
        self.forward_passes += 1
        if self._cache is not None and not keep_only:
            touched = features.tiles_touched(
                np.asarray(list(ranges), dtype=np.int64).reshape(-1, 2),
                tile_rows=self._tile_rows,
                width=self._width,
            )
            replacement = {
                int(index): _tile_slice(masked, int(index), self._tile_rows, self._width)
                for index in touched
            }
            log_probabilities = self.classifier.log_probabilities_with_cache(self._cache, replacement)
            return float(-log_probabilities[self.label])
        return float(self.classifier.negative_log_likelihood(masked, self.label))

    def delta(self, ranges: Sequence[Sequence[int]]) -> float:
        return self.probe(ranges) - self.baseline_nll


def exhaustive_search(
    classifier: Any,
    data: np.ndarray,
    label: int,
    *,
    sample_id: str,
    block_bytes: int = routing.DEFAULT_BLOCK_BYTES,
    fill: occlusion.FillPlan | None = None,
    seed: int = 0,
) -> SearchResult:
    """Probe every block.  The denominator for Evidence Recall."""
    rng = np.random.default_rng(seed)
    plan = fill or occlusion.make_fill_plan(occlusion.PRIMARY_FILL, data)
    prober = Prober(classifier, data, label, fill=plan, rng=rng)

    ranges = raster.block_ranges(data.size, block_bytes)
    deltas = np.empty(ranges.shape[0], dtype=np.float64)
    for index, (start, end) in enumerate(ranges):
        deltas[index] = prober.delta([(int(start), int(end))])

    return SearchResult(
        sample_id=sample_id,
        label=label,
        block_bytes=block_bytes,
        byte_count=int(data.size),
        baseline_nll=prober.baseline_nll,
        deltas=deltas,
        probed=np.ones(ranges.shape[0], dtype=bool),
        forward_passes=prober.forward_passes,
        mode="exhaustive",
        fill=plan.name,
    )


def budgeted_search(
    classifier: Any,
    data: np.ndarray,
    label: int,
    *,
    sample_id: str,
    block_bytes: int = routing.DEFAULT_BLOCK_BYTES,
    budget: float = routing.DEFAULT_BUDGET,
    router: str = routing.ROUTE_COARSE,
    upsampler: str = routing.UPSAMPLE_LINEAR,
    fill: occlusion.FillPlan | None = None,
    seed: int = 0,
    coarse_classifier: Any = None,
) -> SearchResult:
    """Score every block cheaply, then probe only the top K."""
    rng = np.random.default_rng(seed)
    plan = fill or occlusion.make_fill_plan(occlusion.PRIMARY_FILL, data)
    block_table = raster.block_ranges(data.size, block_bytes)
    block_count = block_table.shape[0]

    coarse_map = None
    routing_cost = 0
    if router == routing.ROUTE_COARSE:
        scorer = coarse_classifier or classifier
        coarse_map = routing.coarse_occlusion_map(
            scorer,
            data,
            label,
            fill=plan,
            rng=np.random.default_rng(seed + 1),
            tile_rows=getattr(scorer, "tile_rows", features.DEFAULT_TILE_ROWS),
            width=getattr(scorer, "width", features.DEFAULT_WIDTH),
        )
        routing_cost = coarse_map.forward_passes

    guide = routing.block_entropy_guide(data, block_bytes)
    scores = routing.routing_scores(
        router,
        block_count=block_count,
        data=data,
        block_bytes=block_bytes,
        coarse=coarse_map,
        upsampler=upsampler,
        guide=guide,
        rng=np.random.default_rng(seed + 2),
    )
    if router == routing.ROUTE_UNIFORM:
        selected = routing.uniform_block_indices(block_count, routing.budget_size(block_count, budget))
    else:
        selected = routing.select_blocks(scores, budget)

    prober = Prober(classifier, data, label, fill=plan, rng=rng)
    deltas = np.full(block_count, np.nan, dtype=np.float64)
    probed = np.zeros(block_count, dtype=bool)
    for index in selected:
        start, end = block_table[int(index)]
        deltas[int(index)] = prober.delta([(int(start), int(end))])
        probed[int(index)] = True

    return SearchResult(
        sample_id=sample_id,
        label=label,
        block_bytes=block_bytes,
        byte_count=int(data.size),
        baseline_nll=prober.baseline_nll,
        deltas=deltas,
        probed=probed,
        forward_passes=prober.forward_passes + routing_cost,
        mode="budgeted",
        fill=plan.name,
        router=router,
        upsampler=upsampler if router == routing.ROUTE_COARSE else None,
        budget=budget,
        routing_score=scores,
        extras={"routing_forward_passes": routing_cost},
    )


@dataclass
class NecessityReport:
    """What masking the candidate range does, against a matched random control."""

    sample_id: str
    label: int
    model: str
    baseline_nll: float
    evidence_nll: float
    control_nll: float
    sufficiency_nll: float
    covered_bytes: int
    block_indices: list[int]

    @property
    def delta_evidence(self) -> float:
        return self.evidence_nll - self.baseline_nll

    @property
    def delta_control(self) -> float:
        return self.control_nll - self.baseline_nll

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "label": self.label,
            "model": self.model,
            "baseline_nll": self.baseline_nll,
            "evidence_nll": self.evidence_nll,
            "control_nll": self.control_nll,
            "sufficiency_nll": self.sufficiency_nll,
            "delta_evidence": self.delta_evidence,
            "delta_control": self.delta_control,
            "delta_over_control": self.delta_evidence - self.delta_control,
            "covered_bytes": self.covered_bytes,
            "block_indices": self.block_indices,
        }


def verify_necessity(
    classifier: Any,
    data: np.ndarray,
    label: int,
    ranges: np.ndarray,
    *,
    sample_id: str,
    model_name: str,
    fill: occlusion.FillPlan | None = None,
    seed: int = 0,
) -> NecessityReport:
    """Mask the candidate range on a model that did not take part in the search.

    Also masks a random range of the same geometry, because without that control
    "masking the evidence hurts" cannot be told apart from "masking hurts".
    """
    rng = np.random.default_rng(seed)
    plan = fill or occlusion.make_fill_plan(occlusion.PRIMARY_FILL, data)
    table = np.asarray(ranges, dtype=np.int64).reshape(-1, 2)

    baseline = float(classifier.negative_log_likelihood(data, label))
    evidence = float(
        classifier.negative_log_likelihood(occlusion.occlude(data, table, plan, rng), label)
    )
    control_ranges = occlusion.random_control_ranges(table, int(data.size), rng)
    control = float(
        classifier.negative_log_likelihood(occlusion.occlude(data, control_ranges, plan, rng), label)
    )
    sufficiency = float(
        classifier.negative_log_likelihood(
            occlusion.occlude(data, table, plan, rng, keep_only=True), label
        )
    )
    covered = int((table[:, 1] - table[:, 0]).sum()) if table.size else 0

    return NecessityReport(
        sample_id=sample_id,
        label=label,
        model=model_name,
        baseline_nll=baseline,
        evidence_nll=evidence,
        control_nll=control,
        sufficiency_nll=sufficiency,
        covered_bytes=covered,
        block_indices=[],
    )


def cumulative_deletion_curve(
    classifier: Any,
    data: np.ndarray,
    label: int,
    ordered_ranges: Sequence[Sequence[int]],
    *,
    fill: occlusion.FillPlan | None = None,
    seed: int = 0,
) -> dict[str, Any]:
    """Re-infer after each cumulative deletion; do not sum one-block effects.

    One fill vector is drawn up front and reused at every step, so each input is
    a strict extension of the previous mask.  This preserves block interactions
    that an additive sum of independent occlusion deltas necessarily loses.
    """
    if data.dtype != np.uint8:
        raise TypeError(f"data must be uint8, got {data.dtype}")
    table = np.asarray(list(ordered_ranges), dtype=np.int64).reshape(-1, 2)
    # range_mask performs the bounds and non-empty checks for the full table.
    occlusion.range_mask(table, int(data.size))
    plan = fill or occlusion.make_fill_plan(occlusion.PRIMARY_FILL, data)
    rng = np.random.default_rng(seed)
    replacement = plan.draw(int(data.size), rng)
    cumulative = np.zeros(data.size, dtype=bool)

    baseline_nll = float(classifier.negative_log_likelihood(data, label))
    nll = [baseline_nll]
    fractions = [0.0]
    for start, end in table:
        cumulative[int(start) : int(end)] = True
        masked = data.copy()
        masked[cumulative] = replacement[cumulative]
        nll.append(float(classifier.negative_log_likelihood(masked, label)))
        fractions.append(float(cumulative.mean()))

    auc = float(np.trapezoid(nll, fractions)) if len(nll) > 1 else 0.0
    return {
        "baseline_nll": baseline_nll,
        "nll": nll,
        "delta_nll": [float(value - baseline_nll) for value in nll],
        "fractions": fractions,
        "auc": auc,
        "forward_passes": len(nll),
        "fill": plan.name,
    }


def evidence_ranges(
    result: SearchResult, *, budget: float = routing.DEFAULT_BUDGET, merge: bool = True
) -> np.ndarray:
    """The top-budget blocks as byte ranges, adjacent blocks merged.

    Merging matters for reporting -- an analyst wants "0x1A400-0x1C800", not
    six adjacent 4 KB blocks -- and it does not change any masked byte.
    """
    k = routing.budget_size(result.block_count, budget)
    indices = result.top_blocks(k)
    table = result.ranges_for(indices)
    if not merge or table.shape[0] <= 1:
        return table
    merged: list[list[int]] = []
    for start, end in table:
        if merged and int(start) <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], int(end))
        else:
            merged.append([int(start), int(end)])
    return np.asarray(merged, dtype=np.int64)
