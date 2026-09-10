"""E2 aggregation and the pre-registered gate (frozen: ``E2_prereg_v1``).

Reads the per-file E2 results (SHA-carrying, isolated) and produces the
INTERNAL_ONLY aggregate report: per-stratum coverage means, paired bootstrap
comparisons of the byte-scope selectors against the naive baselines with
Holm-Bonferroni correction, and the pre-registered gate verdict. The report
carries only aggregate scalars; :func:`assert_no_sample_link` refuses to emit it
if any SHA or sample-linked offset list leaked in.
"""

from __future__ import annotations

import json
import re
from typing import Sequence

import numpy as np

from ua_sahi_mal.evidence.metrics import cohens_d_paired, paired_bootstrap_difference

STRATA = ("overlay_dominant", "non_dominant")
BYTE_SCOPE_SELECTORS = ("entropy", "entropy_boundary")
BASELINES = ("random", "front_first")
_SHA_RE = re.compile(r"\b[0-9a-fA-F]{64}\b")
_FORBIDDEN_KEYS = ("sorel_original_sha256", "embedded_intervals", "capa_intervals", "union_intervals")


class SampleLinkedLeakError(RuntimeError):
    """The aggregate report must never carry a SHA or a sample-linked offset list."""


def _coverage(file_result: dict, selector: str, budget_key: str) -> float | None:
    evaluation = file_result.get("evaluation") or {}
    if not evaluation.get("has_silver"):
        return None
    try:
        value = evaluation["selectors"][selector][budget_key]["coverage"]
    except (KeyError, TypeError):
        return None
    return None if value is None or (isinstance(value, float) and np.isnan(value)) else float(value)


def paired_bootstrap_pvalue(
    treatment: Sequence[float], control: Sequence[float], *, iterations: int = 1000, seed: int = 0
) -> float:
    """Two-sided percentile-bootstrap p-value for ``mean(treatment - control) == 0``."""
    diff = np.asarray(list(treatment), dtype=np.float64) - np.asarray(list(control), dtype=np.float64)
    if diff.size == 0:
        return float("nan")
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, diff.size, size=(iterations, diff.size))
    boot = diff[draws].mean(axis=1)
    p = 2.0 * min(float(np.mean(boot <= 0.0)), float(np.mean(boot >= 0.0)))
    return float(min(1.0, p))


def _holm(pvalues: list[float], alpha: float = 0.05) -> list[bool]:
    """Holm-Bonferroni step-down: return per-comparison significance flags."""
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    significant = [False] * m
    for rank, idx in enumerate(order):
        threshold = alpha / (m - rank)
        if pvalues[idx] <= threshold:
            significant[idx] = True
        else:
            break  # step-down: once one fails, all larger p-values fail
    return significant


BASE_SELECTOR_NAMES = ("random", "uniform", "front_first", "back_first",
                       "entropy", "entropy_boundary", "oracle_silver")
LEARNED_SELECTORS = ("attr_tile_conf", "attr_occlusion", "mil_attention")
V3_BASELINES = ("front_first", "entropy_boundary", "random", "position_only")


def _stratum_report(
    files: list[dict], *, budget_key: str, iterations: int, seed: int, alpha: float = 0.05,
    selectors: tuple[str, ...] = BYTE_SCOPE_SELECTORS, baselines: tuple[str, ...] = BASELINES,
    extra_names: tuple[str, ...] = (),
) -> dict[str, object]:
    with_silver = [f for f in files if (f.get("evaluation") or {}).get("has_silver")]
    selector_names = BASE_SELECTOR_NAMES + tuple(n for n in extra_names if n not in BASE_SELECTOR_NAMES)
    coverage_mean = {}
    for name in selector_names:
        vals = [c for f in with_silver if (c := _coverage(f, name, budget_key)) is not None]
        coverage_mean[name] = float(np.mean(vals)) if vals else float("nan")

    comparisons: list[dict[str, object]] = []
    pvalues: list[float] = []
    for selector in selectors:
        for baseline in baselines:
            treatment, control = [], []
            for f in with_silver:
                t = _coverage(f, selector, budget_key)
                c = _coverage(f, baseline, budget_key)
                if t is not None and c is not None:
                    treatment.append(t)
                    control.append(c)
            if len(treatment) >= 2:
                diff = paired_bootstrap_difference(treatment, control, iterations=iterations, seed=seed)
                pvalue = paired_bootstrap_pvalue(treatment, control, iterations=iterations, seed=seed)
                comparisons.append({
                    "selector": selector, "baseline": baseline, "n_pairs": len(treatment),
                    "difference": diff.to_dict(), "cohens_d": cohens_d_paired(treatment, control),
                    "p_value": pvalue, "positive": diff.estimate > 0.0,
                })
                pvalues.append(pvalue)
            else:
                comparisons.append({
                    "selector": selector, "baseline": baseline, "n_pairs": len(treatment),
                    "difference": None, "cohens_d": float("nan"), "p_value": float("nan"),
                    "positive": False,
                })
                pvalues.append(1.0)

    holm_flags = _holm(pvalues, alpha=alpha)
    for comparison, flag in zip(comparisons, holm_flags, strict=True):
        comparison["holm_significant"] = bool(flag and comparison["positive"])

    def selector_beats_all_baselines(selector: str) -> bool:
        rows = [c for c in comparisons if c["selector"] == selector]
        return bool(rows) and all(c["holm_significant"] for c in rows)

    stratum_pass = any(selector_beats_all_baselines(s) for s in selectors)
    return {
        "n_files": len(files),
        "n_with_silver": len(with_silver),
        "coverage_mean": coverage_mean,
        "comparisons": comparisons,
        "stratum_pass": stratum_pass,
        "winning_selectors": [s for s in selectors if selector_beats_all_baselines(s)],
    }


def _comparison(stratum: dict, selector: str, baseline: str) -> dict | None:
    for c in stratum["comparisons"]:  # type: ignore[index]
        if c["selector"] == selector and c["baseline"] == baseline:
            return c
    return None


def _sig(stratum: dict, selector: str, baseline: str) -> bool:
    c = _comparison(stratum, selector, baseline)
    return bool(c and c.get("holm_significant"))


def build_report(
    results: list[dict],
    *,
    prereg_version: str = "E2_prereg_v1",
    primary_budget: float = 0.10,
    iterations: int = 1000,
    seed: int = 0,
    authorization_ref: str | None = None,
    learned: tuple[str, ...] | None = None,
    best_learned: str | None = None,
) -> dict[str, object]:
    """Aggregate INTERNAL_ONLY report + pre-registered gate verdict.

    Without ``learned`` this is the v1/v2 gate (byte-scope heuristics vs random /
    front_first). With ``learned`` (E2_prereg_v3) each learned selector is compared
    against ``V3_BASELINES`` and the gate is evaluated for ``best_learned`` — the
    selector chosen on the validation split, never on test.
    """
    budget_key = f"{primary_budget:.2f}"
    ok = [r for r in results if r.get("ok")]
    excluded = [r for r in results if not r.get("ok")]
    v3 = learned is not None
    selectors = tuple(learned) if v3 else BYTE_SCOPE_SELECTORS
    baselines = V3_BASELINES if v3 else BASELINES
    extra_names = (tuple(learned) + ("position_only",)) if v3 else ()

    per_stratum: dict[str, object] = {}
    for stratum in STRATA:
        files = [r for r in ok if r.get("stratum") == stratum]
        per_stratum[stratum] = _stratum_report(files, budget_key=budget_key, iterations=iterations, seed=seed,
                                               selectors=selectors, baselines=baselines, extra_names=extra_names)

    overlay = per_stratum["overlay_dominant"]
    non_dom = per_stratum["non_dominant"]
    if not v3:
        both_pass = all(per_stratum[s]["stratum_pass"] for s in STRATA)
        overlay_beats_front = any(_sig(overlay, s, "front_first") for s in selectors)
        gate = {"both_strata_pass": both_pass, "overlay_dominant_beats_front_first": overlay_beats_front,
                "gate_pass": bool(both_pass and overlay_beats_front)}
    else:
        if best_learned is None:
            gate = {"gate_pass": None, "note": "best_learned (chosen on validation) is required for the v3 gate",
                    "learned": list(selectors)}
        else:
            primary = _sig(overlay, best_learned, "front_first")
            gate = {
                "best_learned": best_learned,
                "primary_overlay_beats_front_first": primary,
                "secondary": {
                    "overlay_beats_entropy_boundary": _sig(overlay, best_learned, "entropy_boundary"),
                    "non_dominant_beats_front_first": _sig(non_dom, best_learned, "front_first"),
                    "non_dominant_beats_entropy_boundary": _sig(non_dom, best_learned, "entropy_boundary"),
                },
                "strong_content_test_overlay_beats_position_only": _sig(overlay, best_learned, "position_only"),
                "gate_pass": bool(primary),
            }

    report = {
        "prereg_version": prereg_version,
        "publication_scope": "INTERNAL_ONLY" if authorization_ref is None else "authorized",
        "authorization_ref": authorization_ref,
        "note": ("G0-S: Terms §2(c) 서면 명확화 전까지 집계 결과 공개 불가. "
                 "이 보고서는 SHA·샘플연결 오프셋을 포함하지 않는다."),
        "primary_budget": primary_budget,
        "n_total": len(results),
        "n_ok": len(ok),
        "n_excluded": len(excluded),
        "exclusion_reasons": _reason_counts(excluded),
        "capa_status_counts": _capa_counts(ok),
        "strata": per_stratum,
        "gate": gate,
    }
    assert_no_sample_link(report)
    return report


def _reason_counts(excluded: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in excluded:
        key = str(r.get("exclusion_reason", "unknown")).split(":", 1)[0]
        counts[key] = counts.get(key, 0) + 1
    return counts


def _capa_counts(ok: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in ok:
        status = str((r.get("silver") or {}).get("capa_status", "?")).split(":", 1)[0]
        counts[status] = counts.get(status, 0) + 1
    return counts


def assert_no_sample_link(report: dict) -> None:
    """Refuse to emit a report that carries a SHA or a sample-linked offset list."""
    blob = json.dumps(report, ensure_ascii=False)
    if _SHA_RE.search(blob):
        raise SampleLinkedLeakError("aggregate report contains a 64-hex string (possible SHA)")
    for key in _FORBIDDEN_KEYS:
        if f'"{key}"' in blob:
            raise SampleLinkedLeakError(f"aggregate report contains sample-linked key {key!r}")
