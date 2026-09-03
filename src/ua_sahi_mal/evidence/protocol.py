"""The end-to-end evidence protocol, wired to the pre-registered decision table.

Stage order matters and is not arbitrary:

1. **Calibrate (D1).**  Run the search on the synthetic control set, where the
   answer was planted.  If it cannot recover a known range, nothing after this
   point is interpretable, so the run says so and keeps going only to record it.
2. **Sweep (the D5 denominator).**  Exhaustive occlusion on a stratified subset
   with model A.  This is what a budget is later measured against.
3. **Route (D5, D6).**  The same samples under each router and upsampler, at the
   pre-registered budget.
4. **Cross-check (D2, D3, D4).**  Take A's ranges to model B, to the text model,
   and across the three fill values.  These are the numbers the paper leads with,
   because they are the ones A cannot manufacture.

Every stage writes its raw per-sample rows, not just summaries: the decision
table has to be recomputable from the artifacts without re-running the search.
"""

from __future__ import annotations

import json
import platform
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from ua_sahi_mal.evidence import (
    classifiers,
    corpus,
    criteria,
    metrics,
    occlusion,
    routing,
    search,
    synthetic,
)

RESULT_FORMAT = "evidence-protocol-1"


@dataclass
class ProtocolConfig:
    """Frozen before the run.  Nothing here may be tuned on the test split."""

    block_bytes: int = criteria.PRIMARY_BLOCK_BYTES
    budget: float = criteria.PRIMARY_BUDGET
    subset_per_family: int = 5
    synthetic_pairs: int = 24
    bootstrap_iterations: int = metrics.DEFAULT_BOOTSTRAP
    seed: int = 0
    fills: tuple[str, ...] = occlusion.ROBUSTNESS_FILLS
    upsamplers: tuple[str, ...] = (routing.UPSAMPLE_NEAREST, routing.UPSAMPLE_LINEAR, routing.UPSAMPLE_JBU)
    routers: tuple[str, ...] = (
        routing.ROUTE_COARSE,
        routing.ROUTE_ENTROPY,
        routing.ROUTE_RANDOM,
        routing.ROUTE_UNIFORM,
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_bytes": self.block_bytes,
            "budget": self.budget,
            "subset_per_family": self.subset_per_family,
            "synthetic_pairs": self.synthetic_pairs,
            "bootstrap_iterations": self.bootstrap_iterations,
            "seed": self.seed,
            "fills": list(self.fills),
            "upsamplers": list(self.upsamplers),
            "routers": list(self.routers),
        }


@dataclass
class StageResult:
    name: str
    rows: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "summary": self.summary, "seconds": round(self.seconds, 2), "rows": self.rows}


# ---------------------------------------------------------------------------
# stage 1 -- calibration on the synthetic control set (D1)
# ---------------------------------------------------------------------------


def calibrate_on_synthetic(
    model: Any,
    samples: Sequence[synthetic.SyntheticSample],
    *,
    config: ProtocolConfig,
) -> StageResult:
    """Search each control sample for the evidence of the *donor's* family.

    A positive carries a foreign range that is the only support for that family,
    so the protocol should return it.  Its matched negative carries a range from
    the host's own family at the same offset: same seam, no foreign content.  The
    gap between the two is the protocol's specificity, and a protocol that scores
    the seam will show no gap at all.
    """
    started = time.time()
    stage = StageResult(name="synthetic-calibration")

    for sample in samples:
        plan = occlusion.make_fill_plan(occlusion.PRIMARY_FILL, sample.data)
        result = search.exhaustive_search(
            model,
            sample.data,
            sample.query_label,
            sample_id=sample.sample_id,
            block_bytes=config.block_bytes,
            fill=plan,
            seed=config.seed,
        )
        planted_blocks = max(
            1, int(np.ceil((sample.injection[1] - sample.injection[0]) / config.block_bytes))
        )
        predicted = result.ranges_for(result.top_blocks(planted_blocks))
        iou = metrics.byte_iou(predicted, sample.truth_ranges(), int(sample.data.size))
        hit = float(
            metrics.byte_iou(predicted, sample.truth_ranges(), int(sample.data.size)) > 0.0
        )
        stage.rows.append(
            {
                **sample.to_dict(),
                "byte_iou": iou,
                "any_overlap": hit,
                "baseline_nll": result.baseline_nll,
                "evidence_mass": metrics.evidence_mass(result.probed_deltas()),
                "planted_blocks": planted_blocks,
                "predicted": [[int(a), int(b)] for a, b in predicted],
            }
        )

    positives = [row for row in stage.rows if row["is_positive"]]
    negatives = [row for row in stage.rows if not row["is_positive"]]
    stage.summary = {
        "positives": len(positives),
        "negatives": len(negatives),
        "mean_byte_iou_positive": float(np.mean([row["byte_iou"] for row in positives]))
        if positives
        else float("nan"),
        "mean_byte_iou_negative": float(np.mean([row["byte_iou"] for row in negatives]))
        if negatives
        else float("nan"),
        "hit_rate_positive": float(np.mean([row["any_overlap"] for row in positives]))
        if positives
        else float("nan"),
        "false_hit_rate_negative": float(np.mean([row["any_overlap"] for row in negatives]))
        if negatives
        else float("nan"),
    }
    if positives and negatives:
        paired = min(len(positives), len(negatives))
        stage.summary["sensitivity_minus_specificity_gap"] = metrics.summarize_paired(
            [row["byte_iou"] for row in positives[:paired]],
            [row["byte_iou"] for row in negatives[:paired]],
            label="synthetic positive vs matched hard negative",
            iterations=config.bootstrap_iterations,
            seed=config.seed,
        )
    stage.seconds = time.time() - started
    return stage


# ---------------------------------------------------------------------------
# stage 2 -- exhaustive sweep (the denominator)
# ---------------------------------------------------------------------------


def exhaustive_sweep(
    model: Any,
    entries: Sequence[corpus.CorpusEntry],
    store: Any,
    *,
    config: ProtocolConfig,
    fill_name: str = occlusion.PRIMARY_FILL,
) -> tuple[StageResult, dict[str, search.SearchResult]]:
    """Probe every block of every subset sample.  Slow by design; it is the truth."""
    started = time.time()
    stage = StageResult(name=f"exhaustive-{fill_name}")
    results: dict[str, search.SearchResult] = {}

    for entry in entries:
        data = store.get(entry)
        plan = occlusion.make_fill_plan(fill_name, data)
        result = search.exhaustive_search(
            model,
            data,
            entry.label,
            sample_id=entry.sample_id,
            block_bytes=config.block_bytes,
            fill=plan,
            seed=config.seed,
        )
        results[entry.sample_id] = result
        stage.rows.append(result.to_dict())

    stage.summary = {
        "samples": len(results),
        "total_forward_passes": int(sum(row["forward_passes"] for row in stage.rows)),
        "mean_blocks": float(np.mean([row["block_count"] for row in stage.rows])) if stage.rows else 0.0,
        "mean_evidence_mass": float(np.mean([row["evidence_mass"] for row in stage.rows]))
        if stage.rows
        else 0.0,
        "fill": fill_name,
    }
    stage.seconds = time.time() - started
    return stage, results


# ---------------------------------------------------------------------------
# stage 3 -- budgeted routing and the upsampler ablation (D5, D6)
# ---------------------------------------------------------------------------


def budget_ablation(
    model: Any,
    entries: Sequence[corpus.CorpusEntry],
    store: Any,
    exhaustive: dict[str, search.SearchResult],
    *,
    config: ProtocolConfig,
) -> StageResult:
    """Every router x upsampler at the pre-registered budget, scored by recall."""
    started = time.time()
    stage = StageResult(name="budget-ablation")

    arms: list[tuple[str, str | None]] = []
    for router in config.routers:
        if router == routing.ROUTE_COARSE:
            arms.extend((router, upsampler) for upsampler in config.upsamplers)
        else:
            arms.append((router, None))

    for router, upsampler in arms:
        recalls: list[float] = []
        passes: list[int] = []
        for entry in entries:
            reference = exhaustive.get(entry.sample_id)
            if reference is None:
                continue
            data = store.get(entry)
            result = search.budgeted_search(
                model,
                data,
                entry.label,
                sample_id=entry.sample_id,
                block_bytes=config.block_bytes,
                budget=config.budget,
                router=router,
                upsampler=upsampler or routing.UPSAMPLE_LINEAR,
                seed=config.seed,
            )
            selected = np.flatnonzero(result.probed)
            recall = metrics.evidence_recall_at_budget(reference.probed_deltas(), selected)
            recalls.append(recall)
            passes.append(result.forward_passes)
            stage.rows.append(
                {
                    "sample_id": entry.sample_id,
                    "label": entry.label,
                    "router": router,
                    "upsampler": upsampler,
                    "evidence_recall": recall,
                    "forward_passes": result.forward_passes,
                    "exhaustive_forward_passes": reference.forward_passes,
                }
            )
        finite = [value for value in recalls if np.isfinite(value)]
        stage.summary.setdefault("arms", []).append(
            {
                "router": router,
                "upsampler": upsampler,
                "n": len(finite),
                "mean_evidence_recall": float(np.mean(finite)) if finite else float("nan"),
                "mean_forward_passes": float(np.mean(passes)) if passes else float("nan"),
            }
        )

    reference_passes = float(
        np.mean([result.forward_passes for result in exhaustive.values()]) if exhaustive else float("nan")
    )
    stage.summary["exhaustive_mean_forward_passes"] = reference_passes
    stage.seconds = time.time() - started
    return stage


# ---------------------------------------------------------------------------
# stage 4 -- cross-model, cross-representation, cross-fill (D2, D3, D4)
# ---------------------------------------------------------------------------


def cross_checks(
    entries: Sequence[corpus.CorpusEntry],
    store: Any,
    exhaustive: dict[str, search.SearchResult],
    *,
    verifiers: dict[str, Any],
    config: ProtocolConfig,
) -> StageResult:
    """Take A's ranges elsewhere and see whether they still matter."""
    started = time.time()
    stage = StageResult(name="cross-checks")
    collected: dict[str, dict[str, list[float]]] = {
        name: {"evidence": [], "control": []} for name in verifiers
    }

    for entry in entries:
        result = exhaustive.get(entry.sample_id)
        if result is None:
            continue
        data = store.get(entry)
        ranges = search.evidence_ranges(result, budget=config.budget)
        if ranges.size == 0:
            continue
        plan = occlusion.make_fill_plan(occlusion.PRIMARY_FILL, data)
        for name, model in verifiers.items():
            report = search.verify_necessity(
                model,
                data,
                entry.label,
                ranges,
                sample_id=entry.sample_id,
                model_name=name,
                fill=plan,
                seed=config.seed,
            )
            collected[name]["evidence"].append(report.delta_evidence)
            collected[name]["control"].append(report.delta_control)
            stage.rows.append(report.to_dict())

    stage.summary["models"] = {
        name: metrics.summarize_paired(
            values["evidence"],
            values["control"],
            label=f"{name}: evidence range vs random-location control",
            iterations=config.bootstrap_iterations,
            seed=config.seed,
        )
        for name, values in collected.items()
        if values["evidence"]
    }
    stage.seconds = time.time() - started
    return stage


def fill_agreement(
    sweeps: dict[str, dict[str, search.SearchResult]], *, config: ProtocolConfig
) -> StageResult:
    """Kendall tau between block rankings produced under different fill values (D4)."""
    started = time.time()
    stage = StageResult(name="fill-agreement")
    names = [name for name in config.fills if name in sweeps]
    primary = occlusion.PRIMARY_FILL

    taus: list[float] = []
    for name in names:
        if name == primary or primary not in sweeps:
            continue
        for sample_id, result in sweeps[primary].items():
            other = sweeps[name].get(sample_id)
            if other is None or other.block_count != result.block_count:
                continue
            tau = metrics.kendall_tau(result.probed_deltas(), other.probed_deltas())
            if np.isfinite(tau):
                taus.append(tau)
                stage.rows.append({"sample_id": sample_id, "fill_a": primary, "fill_b": name, "kendall_tau": tau})

    stage.summary = {
        "pairs": len(taus),
        "mean_kendall_tau": float(np.mean(taus)) if taus else float("nan"),
        "min_kendall_tau": float(np.min(taus)) if taus else float("nan"),
        "fills_compared": names,
    }
    stage.seconds = time.time() - started
    return stage


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------


def build_decision_table(
    *,
    calibration: StageResult | None,
    ablation: StageResult | None,
    cross: StageResult | None,
    agreement: StageResult | None,
    ua_measured: bool = False,
) -> dict[str, Any]:
    """Turn stage summaries into the pre-registered verdicts."""
    iou = None
    if calibration and calibration.summary:
        value = calibration.summary.get("mean_byte_iou_positive")
        iou = None if value is None or not np.isfinite(value) else float(value)

    def paired(model_key: str) -> tuple[float | None, float | None]:
        if not cross or not cross.summary.get("models"):
            return None, None
        entry = cross.summary["models"].get(model_key)
        if not entry:
            return None, None
        return float(entry["difference"]["estimate"]), float(entry["difference"]["low"])

    b_difference, b_low = paired(classifiers.MODEL_THUMBNAIL)
    text_difference, text_low = paired(classifiers.MODEL_TEXT)

    tau = None
    if agreement and agreement.summary:
        value = agreement.summary.get("mean_kendall_tau")
        tau = None if value is None or not np.isfinite(value) else float(value)

    recall = None
    ua_margin = None
    if ablation and ablation.summary.get("arms"):
        by_arm = {
            (arm["router"], arm["upsampler"]): arm["mean_evidence_recall"] for arm in ablation.summary["arms"]
        }
        primary = by_arm.get((routing.ROUTE_COARSE, routing.UPSAMPLE_LINEAR))
        if primary is not None and np.isfinite(primary):
            recall = float(primary)
        ua = by_arm.get((routing.ROUTE_COARSE, routing.UPSAMPLE_UA))
        if ua is not None and primary is not None and np.isfinite(ua) and np.isfinite(primary):
            ua_margin = float((ua - primary) * 100.0)

    return criteria.assemble(
        [
            criteria.d1_synthetic_iou(iou),
            criteria.d2_cross_model(b_difference, b_low),
            criteria.d3_cross_representation(text_difference, text_low),
            criteria.d4_fill_agreement(tau),
            criteria.d5_evidence_recall(recall),
            criteria.d6_upsampler_margin(ua_margin, measured=ua_measured),
        ]
    )


def environment_record() -> dict[str, Any]:
    import importlib.metadata

    packages: dict[str, str] = {}
    for name in ("numpy", "torch", "pillow"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "not-installed"
    record = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": packages,
    }
    try:
        import torch

        record["torch_cuda_available"] = bool(torch.cuda.is_available())
    except ImportError:
        record["torch_cuda_available"] = False
    return record


def write_results(document: dict[str, Any], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
