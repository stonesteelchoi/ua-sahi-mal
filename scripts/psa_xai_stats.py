"""Summarise frozen PSA-XAI ledgers without opening source files or models."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "paper/v5-kisa-xai/protocol/PSA_XAI_V1_1_FROZEN.yaml"
METRICS = {"h1": "deletion_delta_nll", "h2": "keep_only_malicious_score"}
BOOTSTRAP_SEED = 20260924


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def protocol_settings(path: Path) -> dict:
    p = yaml.safe_load(path.read_text(encoding="utf-8"))
    x, s = p["xai"], p["statistics"]
    if (p["protocol"]["status"] != "frozen" or s["unit"] != "imphash_group"
            or s["sensitivity_analysis"] != "file" or s["paired_bootstrap_repeats"] != 2000
            or s["random_control_repeats_per_file"] != 20 or s["confidence_level"] != 0.95
            or p["primary_hypotheses"]["familywise_tests"] != 2
            or p["primary_hypotheses"]["correction"] != "holm"
            or p["primary_hypotheses"]["h1"] != "gradcam_top10_deletion_delta_nll_gt_structure_matched_random"
            or p["primary_hypotheses"]["h2"] != "gradcam_top10_keep_only_malicious_score_gt_structure_matched_random"
            or x["primary_comparator"] != "structure_matched_random"
            or x["primary_budget"] != 0.10 or x["fills"]["primary"] != "structure_conditioned_resampling"
            or p["eligibility"]["require_structure_map"] is not True):
        raise ValueError("unsupported frozen statistics settings")
    return p


def jsonl(path: Path):
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            try:
                yield json.loads(line)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"invalid JSONL {path}:{number}") from exc


def bootstrap(values: np.ndarray, repeats: int, seed: int) -> dict:
    if not len(values) or not np.isfinite(values).all():
        raise ValueError("bootstrap requires finite, nonempty effects")
    rng = np.random.default_rng(seed)
    draws = np.empty(repeats)
    # Chunk sampling so large file-level sensitivity analyses fit in memory.
    batch = max(1, min(128, 2_000_000 // len(values)))
    for start in range(0, repeats, batch):
        n = min(batch, repeats - start)
        draws[start:start + n] = values[rng.integers(0, len(values), (n, len(values)))].mean(axis=1)
    lower, upper = np.quantile(draws, [0.025, 0.975])
    # One-sided H1/H2 superiority test; plus-one correction prevents zero p.
    p = (1 + int(np.count_nonzero(draws <= 0))) / (repeats + 1)
    return {"effect": float(values.mean()), "ci_95_lower": float(lower),
            "ci_95_upper": float(upper), "p_unadjusted": p, "unit_n": len(values)}


def holm(results: dict) -> None:
    ordered = sorted(results, key=lambda key: results[key]["p_unadjusted"])
    adjusted = 0.0
    for rank, key in enumerate(ordered):
        adjusted = max(adjusted, min(1.0, (len(ordered) - rank) * results[key]["p_unadjusted"]))
        results[key]["holm_adjusted_p"] = adjusted


def inference(files: dict[str, dict], repeats: int, seed: int) -> dict:
    if not files:
        return {h: {"eligible_n": 0, "group_n": 0, "status": "no_eligible_files"} for h in METRICS}
    groups = defaultdict(list)
    for row in files.values():
        groups[row["group"]].append(row)
    result = {}
    for i, hypothesis in enumerate(METRICS):
        file_values = np.asarray([r[hypothesis] for r in files.values()], dtype=float)
        group_values = np.asarray([np.mean([r[hypothesis] for r in members])
                                   for members in groups.values()], dtype=float)
        primary = bootstrap(group_values, repeats, seed + i)
        primary.update(eligible_n=len(files), group_n=len(groups),
                       sensitivity_file=bootstrap(file_values, repeats, seed + 100 + i))
        result[hypothesis] = primary
    holm(result)
    return result


def collect(perturb: Path, gradcam: Path, protocol: dict, seed: int) -> dict:
    x, s = protocol["xai"], protocol["statistics"]
    primary_budget, primary_fill = x["primary_budget"], x["fills"]["primary"]
    primary_control = x["primary_comparator"] + "_20_repeats"
    expected_controls = {"uniform_random_20_repeats": 20, "front_position": 1,
                         "entropy": 1, primary_control: 20}
    cams = {}
    mass = defaultdict(lambda: [0.0, 0])
    for row in jsonl(gradcam):
        key = (str(row["sample_id"]), float(row["budget"]["requested_fraction"]))
        if key in cams:
            raise ValueError(f"duplicate CAM sample/budget {key}")
        cams[key] = row
        if math.isclose(key[1], primary_budget, abs_tol=1e-9) and row.get("structure_cam_mass"):
            for region, value in row["structure_cam_mass"].items():
                if value is not None:
                    mass[region][0] += float(value)
                    mass[region][1] += 1
    if not cams:
        raise ValueError("empty Grad-CAM ledger")
    summaries = defaultdict(lambda: [0.0, 0.0, 0])
    primary_files = {}
    excluded_empty = {sid for (sid, budget), row in cams.items()
                      if budget == primary_budget and int(row["budget"]["achieved_bytes"]) == 0}
    excluded_ineligible = set()
    seen_keys = set()
    sample_rows = []
    current = None
    seen_samples = set()

    def flush():
        if not sample_rows:
            return
        sid = str(sample_rows[0]["sample_id"])
        by_combo = defaultdict(list)
        for r in sample_rows:
            budget = float(r["budget"])
            cam = cams[(sid, budget)]
            if r["group"] != cam["group"] or int(r["achieved_bytes"]) != int(cam["budget"]["achieved_bytes"]):
                raise ValueError(f"CAM/perturb pairing mismatch {sid}")
            combo = (budget, r["fill"], r["control"])
            by_combo[combo].append(r)
        expected_combos = {(budget, x["fills"][fill], control)
                           for budget in x["budgets"]
                           for fill in ("primary", "robustness", "diagnostic")
                           for control in expected_controls}
        if set(by_combo) != expected_combos:
            raise ValueError(f"missing or unexpected perturb combinations {sid}")
        for (budget, fill, control), rows in by_combo.items():
            cam = cams[(sid, budget)]
            repeats_expected = expected_controls[control]
            if len(rows) != repeats_expected or {int(r["repeat"]) for r in rows} != set(range(repeats_expected)):
                raise ValueError(f"incomplete or duplicate repeats {sid} {budget} {fill} {control}")
            eligible = [r for r in rows if r["eligible"] is True]
            if eligible and len(eligible) != len(rows):
                raise ValueError(f"mixed eligibility {sid} {control}")
            if not eligible:
                if budget == primary_budget and fill == primary_fill and control == primary_control:
                    excluded_ineligible.add(sid)
                continue
            if int(cam["budget"]["achieved_bytes"]) == 0:
                continue
            for h, suffix in METRICS.items():
                grad = np.asarray([float(r[f"gradcam_{suffix}"]) for r in eligible])
                ctrl = np.asarray([float(r[f"control_{suffix}"]) for r in eligible])
                if not np.isfinite(grad).all() or not np.isfinite(ctrl).all():
                    raise ValueError("nonfinite perturbation metric")
                # The same CAM perturbation is computed for each repeat.
                if not np.allclose(grad, grad[0], rtol=1e-6, atol=1e-6):
                    raise ValueError(f"inconsistent Grad-CAM repeat scores {sid}")
                diff = float(grad[0] - ctrl.mean())
                stat = summaries[(budget, fill, control, h)]
                stat[0] += diff
                stat[1] += float(ctrl.mean())
                stat[2] += 1
                if budget == primary_budget and fill == primary_fill and control == primary_control:
                    entry = primary_files.setdefault(sid, {"group": cam["group"],
                        "repr_policy": cam["representation_policy"], "predicted_label": cam["predicted_label"]})
                    entry[h] = diff

    for row in jsonl(perturb):
        sid = str(row["sample_id"])
        if current is not None and sid != current:
            flush()
            sample_rows = []
            seen_samples.add(current)
            if sid in seen_samples:
                raise ValueError("perturb ledger sample blocks must be contiguous")
        current = sid
        if int(row["checkpoint_seed"]) != seed:
            raise ValueError("checkpoint seed mismatch")
        key = (sid, float(row["budget"]))
        if key not in cams:
            raise ValueError(f"missing CAM row {key}")
        if row["fill"] not in {x["fills"][n] for n in ("primary", "robustness", "diagnostic")} or row["control"] not in expected_controls:
            raise ValueError("unexpected fill or control")
        sample_rows.append(row)
        seen_keys.add(key)
    flush()
    if seen_keys != cams.keys():
        raise ValueError("perturb ledger does not cover every CAM sample/budget")
    if any(set(METRICS) - row.keys() for row in primary_files.values()):
        raise ValueError("incomplete primary metrics")
    table = [{"budget": k[0], "fill": k[1], "control": k[2], "hypothesis": k[3],
              "paired_mean": v[0] / v[2], "control_mean": v[1] / v[2], "eligible_n": v[2]}
             for k, v in sorted(summaries.items())]
    return {"files": primary_files, "descriptive": table,
            "counts": {"cam_sample_n": len({sid for sid, _ in cams}),
                       "excluded_empty_cam_n": len(excluded_empty),
                       "excluded_ineligible_n": len(excluded_ineligible),
                       "eligible_n": len(primary_files)},
            "structure_cam_mass": {k: {"mean": v[0] / v[1], "n": v[1]} for k, v in sorted(mass.items())}}


def render(report: dict) -> str:
    lines = ["# PSA-XAI statistics", "", f"Protocol SHA-256: `{report['protocol_sha256']}`", "",
             "One-sided superiority p values use 2,000 paired bootstrap draws; Holm adjusts H1/H2 within each population and scope.", ""]
    for population, pop in report["populations"].items():
        lines += [f"## {population}", "", "| Scope | H | Effect | 95% CI | Holm p | Eligible files | Groups | Empty CAM excluded |",
                  "|---|---|---:|---:|---:|---:|---:|---:|"]
        for scope, data in pop.items():
            if scope == "inputs":
                continue
            for h, r in data["primary"].items():
                if "effect" in r:
                    lines.append(f"| {scope} | {h.upper()} | {r['effect']:.6g} | [{r['ci_95_lower']:.6g}, {r['ci_95_upper']:.6g}] | {r['holm_adjusted_p']:.6g} | {r['eligible_n']} | {r['group_n']} | {data['counts']['excluded_empty_cam_n']} |")
        lines += ["", "### File bootstrap sensitivity", "", "| Scope | H | Effect | 95% CI | p |",
                  "|---|---|---:|---:|---:|"]
        for scope, data in pop.items():
            if scope == "inputs":
                continue
            for h, r in data["primary"].items():
                if "sensitivity_file" in r:
                    f = r["sensitivity_file"]
                    lines.append(f"| {scope} | {h.upper()} | {f['effect']:.6g} | [{f['ci_95_lower']:.6g}, {f['ci_95_upper']:.6g}] | {f['p_unadjusted']:.6g} |")
        lines += [""]
        lines += ["### Correctly detected malicious subset", "", "| Scope | H | Effect | 95% CI | Eligible files |",
                  "|---|---|---:|---:|---:|"]
        for scope, data in pop.items():
            for h, r in data["correctly_detected_malicious"].items():
                if "effect" in r:
                    lines.append(f"| {scope} | {h.upper()} | {r['effect']:.6g} | [{r['ci_95_lower']:.6g}, {r['ci_95_upper']:.6g}] | {r['eligible_n']} |")
        lines.append("")
        for scope, data in pop.items():
            if scope == "inputs":
                continue
            lines += [f"### {scope} subgroups", "", "| Repr policy | H | Effect | 95% CI | Eligible files |",
                      "|---|---|---:|---:|---:|"]
            for name, effects in data["repr_policy"].items():
                for h, r in effects.items():
                    if "effect" in r:
                        lines.append(f"| {name} | {h.upper()} | {r['effect']:.6g} | [{r['ci_95_lower']:.6g}, {r['ci_95_upper']:.6g}] | {r['eligible_n']} |")
            lines += ["", "### Descriptive combinations", "", "| Budget | Fill | Control | H | Paired mean | Control mean | Eligible files |",
                      "|---:|---|---|---|---:|---:|---:|"]
            for r in data.get("descriptive", []):
                lines.append(f"| {r['budget']} | {r['fill']} | {r['control']} | {r['hypothesis'].upper()} | {r['paired_mean']:.6g} | {r['control_mean']:.6g} | {r['eligible_n']} |")
            lines += ["", "### Structure CAM mass", "", "| Region | Mean mass | N |", "|---|---:|---:|"]
            for region, r in data.get("structure_cam_mass", {}).items():
                lines.append(f"| {region} | {r['mean']:.6g} | {r['n']} |")
            lines.append("")
    return "\n".join(lines) + "\n"


def build(inputs: list[tuple[str, int, Path, Path]], protocol_path: Path = FROZEN) -> dict:
    p = protocol_settings(protocol_path)
    seeds = set(map(int, p["model"]["seeds"]))
    by_population = defaultdict(dict)
    hashes = {}
    for population, seed, perturb, gradcam in inputs:
        if population not in {"main", "era"} or seed not in seeds or seed in by_population[population]:
            raise ValueError("unexpected population/seed or duplicate ledger pair")
        hashes[f"{population}/seed_{seed}"] = {"perturb": digest(perturb), "gradcam": digest(gradcam)}
        by_population[population][seed] = collect(perturb, gradcam, p, seed)
    if set(by_population) != {"main", "era"} or any(set(v) != seeds for v in by_population.values()):
        raise ValueError("three seeds are required for both main and era")
    report = {"protocol_sha256": digest(protocol_path), "ledger_sha256": hashes,
              "bootstrap": {"repeats": 2000, "seed": BOOTSTRAP_SEED, "p_tail": "one_sided_greater"},
              "populations": {}}
    for population, seed_data in by_population.items():
        result = {}
        file_sets = [set(seed_data[seed]["files"]) for seed in sorted(seeds)]
        if len(set(map(frozenset, file_sets))) != 1:
            raise ValueError(f"seed sample coverage differs for {population}")
        for seed in sorted(seeds):
            data = seed_data[seed]
            files = data["files"]
            result[f"seed_{seed}"] = {
                "counts": data["counts"], "primary": inference(files, 2000, BOOTSTRAP_SEED + seed),
                "correctly_detected_malicious": inference(
                    {sid: r for sid, r in files.items() if r["predicted_label"] == max(p["eligibility"]["labels"])},
                    2000, BOOTSTRAP_SEED + seed + 500),
                "repr_policy": {name: inference({sid: r for sid, r in files.items() if r["repr_policy"] == policy},
                    2000, BOOTSTRAP_SEED + seed + j * 1000)
                    for j, (name, policy) in enumerate((("mean_pool", p["representation"]["long_file_policy"]),
                                                         ("nearest_repetition", p["representation"]["short_file_policy"])), 1)},
                "descriptive": data["descriptive"], "structure_cam_mass": data["structure_cam_mass"]}
        common = set.intersection(*file_sets)
        averaged = {}
        for sid in common:
            rows = [seed_data[seed]["files"][sid] for seed in sorted(seeds)]
            if len({(r["group"], r["repr_policy"]) for r in rows}) != 1:
                raise ValueError("seed metadata mismatch")
            averaged[sid] = {"group": rows[0]["group"], "repr_policy": rows[0]["repr_policy"],
                             "predicted_label": max(p["eligibility"]["labels"]) if all(
                                 r["predicted_label"] == max(p["eligibility"]["labels"]) for r in rows) else -1,
                             **{h: float(np.mean([r[h] for r in rows])) for h in METRICS}}
        result["seed_average"] = {
            "counts": {"eligible_n": len(averaged), "excluded_empty_cam_n": seed_data[min(seeds)]["counts"]["excluded_empty_cam_n"]},
            "primary": inference(averaged, 2000, BOOTSTRAP_SEED + 900),
            "correctly_detected_malicious": inference(
                {sid: r for sid, r in averaged.items() if r["predicted_label"] == max(p["eligibility"]["labels"])},
                2000, BOOTSTRAP_SEED + 1400),
            "repr_policy": {name: inference({sid: r for sid, r in averaged.items() if r["repr_policy"] == policy},
                2000, BOOTSTRAP_SEED + 1900 + j * 1000)
                for j, (name, policy) in enumerate((("mean_pool", p["representation"]["long_file_policy"]),
                                                     ("nearest_repetition", p["representation"]["short_file_policy"])), 1)}}
        descriptive = defaultdict(list)
        mass = defaultdict(list)
        for seed in sorted(seeds):
            for row in seed_data[seed]["descriptive"]:
                key = (row["budget"], row["fill"], row["control"], row["hypothesis"])
                descriptive[key].append(row)
            for region, row in seed_data[seed]["structure_cam_mass"].items():
                mass[region].append(row)
        result["seed_average"]["descriptive"] = [
            {"budget": key[0], "fill": key[1], "control": key[2], "hypothesis": key[3],
             "paired_mean": float(np.mean([r["paired_mean"] for r in rows])),
             "control_mean": float(np.mean([r["control_mean"] for r in rows])),
             "eligible_n": min(r["eligible_n"] for r in rows)}
            for key, rows in sorted(descriptive.items())]
        result["seed_average"]["structure_cam_mass"] = {
            region: {"mean": float(np.mean([r["mean"] for r in rows])), "n": min(r["n"] for r in rows)}
            for region, rows in sorted(mass.items())}
        report["populations"][population] = result
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ledger", nargs=4, action="append", metavar=("POPULATION", "SEED", "PERTURB", "GRADCAM"), required=True)
    ap.add_argument("--outdir", type=Path, required=True)
    args = ap.parse_args()
    rows = [(pop, int(seed), Path(pert), Path(cam)) for pop, seed, pert, cam in args.ledger]
    report = build(rows)
    args.outdir.mkdir(parents=True, exist_ok=False)
    (args.outdir / "psa_xai_stats.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (args.outdir / "psa_xai_stats.md").write_text(render(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
