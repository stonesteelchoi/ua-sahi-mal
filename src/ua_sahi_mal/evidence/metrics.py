"""Metrics and statistics for the evidence protocol.

Everything here is deliberately dependency-free (NumPy only) and deterministic
given a seed, because these numbers go into a pre-registered decision table and
have to be reproducible from the repository alone.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Sequence

import numpy as np

T_CRITICAL_95 = {
    2: 12.706205,
    3: 4.302653,  # 3 seeds.  The v1 aggregate used the rounded 4.3030; v2 uses this.
    4: 3.182446,
    5: 2.776445,
    6: 2.570582,
}

DEFAULT_BOOTSTRAP = 1000


@dataclass(frozen=True)
class Interval:
    """A point estimate with a 95% interval."""

    estimate: float
    low: float
    high: float
    method: str

    @property
    def excludes_zero(self) -> bool:
        return (self.low > 0.0) or (self.high < 0.0)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "excludes_zero": self.excludes_zero}


def mean_interval_t(values: Sequence[float]) -> Interval:
    """Mean with a t-based 95% interval.  Used for the 3-seed summaries."""
    array = np.asarray(list(values), dtype=np.float64)
    if array.size == 0:
        raise ValueError("cannot summarize an empty sequence")
    mean = float(array.mean())
    if array.size == 1:
        return Interval(mean, mean, mean, "single-observation")
    critical = T_CRITICAL_95.get(array.size)
    if critical is None:
        return bootstrap_mean_interval(array)
    margin = critical * float(array.std(ddof=1)) / np.sqrt(array.size)
    return Interval(mean, mean - margin, mean + margin, f"t({array.size - 1})=,{critical:.6f}".replace(",", ""))


def bootstrap_mean_interval(
    values: Sequence[float], *, iterations: int = DEFAULT_BOOTSTRAP, seed: int = 0
) -> Interval:
    """Percentile bootstrap interval for a mean."""
    array = np.asarray(list(values), dtype=np.float64)
    if array.size == 0:
        raise ValueError("cannot bootstrap an empty sequence")
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, array.size, size=(iterations, array.size))
    means = array[draws].mean(axis=1)
    return Interval(
        float(array.mean()),
        float(np.percentile(means, 2.5)),
        float(np.percentile(means, 97.5)),
        f"bootstrap-{iterations}",
    )


def paired_bootstrap_difference(
    treatment: Sequence[float],
    control: Sequence[float],
    *,
    iterations: int = DEFAULT_BOOTSTRAP,
    seed: int = 0,
) -> Interval:
    """Sample-level paired bootstrap of ``mean(treatment - control)``.

    Pairing matters: the candidate range and its random-location control are
    measured on the *same* sample, and between-sample variance is far larger
    than the effect being tested.
    """
    left = np.asarray(list(treatment), dtype=np.float64)
    right = np.asarray(list(control), dtype=np.float64)
    if left.shape != right.shape:
        raise ValueError(f"paired inputs must match in shape: {left.shape} vs {right.shape}")
    if left.size == 0:
        raise ValueError("cannot bootstrap an empty pairing")
    differences = left - right
    return bootstrap_mean_interval(differences, iterations=iterations, seed=seed)


def cohens_d_paired(treatment: Sequence[float], control: Sequence[float]) -> float:
    """Effect size for a paired comparison (mean difference / sd of differences)."""
    differences = np.asarray(list(treatment), dtype=np.float64) - np.asarray(list(control), dtype=np.float64)
    if differences.size < 2:
        return float("nan")
    deviation = float(differences.std(ddof=1))
    if deviation == 0.0:
        return float("inf") if differences.mean() != 0 else 0.0
    return float(differences.mean() / deviation)


def kendall_tau(first: Sequence[float], second: Sequence[float]) -> float:
    """Kendall's tau-b between two rankings, ties handled.

    Used for D4: if the block ranking survives changing the fill value, the
    ranking is about the bytes, not about the mask.
    """
    left = np.asarray(list(first), dtype=np.float64)
    right = np.asarray(list(second), dtype=np.float64)
    if left.shape != right.shape:
        raise ValueError(f"inputs must match in shape: {left.shape} vs {right.shape}")
    n = left.size
    if n < 2:
        return float("nan")

    left_difference = left[:, None] - left[None, :]
    right_difference = right[:, None] - right[None, :]
    upper = np.triu(np.ones((n, n), dtype=bool), k=1)
    left_sign = np.sign(left_difference[upper])
    right_sign = np.sign(right_difference[upper])

    concordant_minus_discordant = float((left_sign * right_sign).sum())
    left_pairs = float((left_sign != 0).sum())
    right_pairs = float((right_sign != 0).sum())
    denominator = np.sqrt(left_pairs * right_pairs)
    return float(concordant_minus_discordant / denominator) if denominator > 0 else float("nan")


def byte_iou(
    predicted: Sequence[Sequence[int]], truth: Sequence[Sequence[int]], byte_count: int
) -> float:
    """1-D IoU between two sets of byte ranges.

    The domain-native accuracy measure: a 2-D box IoU would score the padding
    columns of a 512-byte-wide raster, which carry no meaning.
    """
    from ua_sahi_mal.evidence.occlusion import range_mask

    predicted_mask = range_mask(predicted, byte_count)
    truth_mask = range_mask(truth, byte_count)
    union = int((predicted_mask | truth_mask).sum())
    if union == 0:
        return 0.0
    return float((predicted_mask & truth_mask).sum() / union)


def evidence_mass(deltas: Sequence[float], indices: Sequence[int] | None = None) -> float:
    """Total positive evidence carried by the given blocks.

    Negative deltas -- occlusions that *helped* the classifier -- are clipped to
    zero.  They are not evidence for the correct family, and letting them cancel
    real evidence would make a recall ratio uninterpretable.
    """
    array = np.asarray(list(deltas), dtype=np.float64)
    if indices is not None:
        array = array[np.asarray(list(indices), dtype=np.int64)]
    return float(np.clip(array, 0.0, None).sum())


def evidence_recall_at_budget(
    exhaustive_deltas: Sequence[float], selected_indices: Sequence[int]
) -> float:
    """Fraction of the exhaustive evidence mass recovered by a budgeted search.

    The denominator is what a full sweep found, so the number answers "how much
    do we lose by only looking at K blocks?" -- which is the question that makes
    budgeted routing a claim rather than a convenience.
    """
    total = evidence_mass(exhaustive_deltas)
    if total <= 0.0:
        return float("nan")
    return evidence_mass(exhaustive_deltas, selected_indices) / total


def top_k_indices(scores: Sequence[float], k: int) -> np.ndarray:
    """Indices of the ``k`` highest scores, ties broken by index for determinism."""
    array = np.asarray(list(scores), dtype=np.float64)
    if k <= 0:
        return np.zeros(0, dtype=np.int64)
    k = min(k, array.size)
    order = np.lexsort((np.arange(array.size), -array))
    return np.sort(order[:k])


def deletion_curve(
    ordered_deltas: Sequence[float], baseline_nll: float
) -> dict[str, list[float] | float]:
    """Cumulative NLL as blocks are removed in the given order, plus its AUC.

    Petsiuk et al.'s deletion metric, in the byte-range domain.  Reported
    alongside the single-range delta because a curve distinguishes "evidence is
    concentrated in a few blocks" from "evidence is spread thin", and those two
    have opposite implications for evasion resistance.
    """
    array = np.asarray(list(ordered_deltas), dtype=np.float64)
    cumulative = baseline_nll + np.cumsum(array)
    fractions = np.arange(1, array.size + 1) / max(array.size, 1)
    auc = float(np.trapezoid(cumulative, fractions)) if array.size > 1 else float(cumulative.sum())
    return {
        "baseline_nll": float(baseline_nll),
        "curve": [float(value) for value in cumulative],
        "fractions": [float(value) for value in fractions],
        "auc": auc,
    }


def summarize_paired(
    treatment: Sequence[float],
    control: Sequence[float],
    *,
    label: str,
    iterations: int = DEFAULT_BOOTSTRAP,
    seed: int = 0,
) -> dict[str, Any]:
    """The full paired report: means, difference interval, and effect size."""
    left = np.asarray(list(treatment), dtype=np.float64)
    right = np.asarray(list(control), dtype=np.float64)
    difference = paired_bootstrap_difference(left, right, iterations=iterations, seed=seed)
    return {
        "label": label,
        "n": int(left.size),
        "treatment_mean": float(left.mean()),
        "control_mean": float(right.mean()),
        "difference": difference.to_dict(),
        "cohens_d": cohens_d_paired(left, right),
    }
