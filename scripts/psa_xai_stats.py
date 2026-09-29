"""Summarise frozen PSA-XAI ledgers without opening source files or models."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "paper/v5-kisa-xai/protocol/PSA_XAI_V1_1_FROZEN.yaml"
METRICS = {"h1": "deletion_delta_nll", "h2": "keep_only_malicious_score"}
BOOTSTRAP_SEED = 20260924
SECONDARY_CONTROLS = ("uniform_random_20_repeats", "entropy", "front_position")


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


def secondary_inference(files: dict[str, dict], repeats: int, seed: int) -> dict:
    """Paired file effects followed by an imphash-group bootstrap, without a p value."""
    if not files:
        return {h: {"preregistered": False, "family": "secondary", "eligible_n": 0,
                    "group_n": 0, "status": "no_eligible_files"} for h in METRICS}
    groups = defaultdict(list)
    for row in files.values():
        groups[row["group"]].append(row)
    result = {}
    for i, h in enumerate(METRICS):
        values = np.asarray([np.mean([r[h]["effect"] for r in members])
                             for members in groups.values()], dtype=float)
        rng = np.random.default_rng(seed + i)
        draws = np.empty(repeats)
        batch = max(1, min(128, 2_000_000 // len(values)))
        for start in range(0, repeats, batch):
            n = min(batch, repeats - start)
            draws[start:start + n] = values[rng.integers(0, len(values), (n, len(values)))].mean(axis=1)
        lower, upper = np.quantile(draws, [0.025, 0.975])
        result[h] = {"preregistered": False, "family": "secondary",
                     "effect": float(values.mean()), "ci_95_lower": float(lower),
                     "ci_95_upper": float(upper), "eligible_n": len(files),
                     "group_n": len(groups),
                     "gradcam_mean": float(np.mean([r[h]["gradcam_mean"] for r in files.values()])),
                     "control_mean": float(np.mean([r[h]["control_mean"] for r in files.values()]))}
    return result


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


def collect(perturb: Path, gradcam: Path, protocol: dict, seed: int,
            secondary_controls: bool = False) -> dict:
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
    secondary_files = {control: {} for control in SECONDARY_CONTROLS} if secondary_controls else None
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
            eligible = sorted((r for r in rows if r["eligible"] is True), key=lambda r: int(r["repeat"]))
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
                # Paired per repeat: gradcam and control share the fill random state
                # within a repeat, so the gradcam score itself varies across repeats
                # for random fills. The frozen paired difference is the repeat-wise mean.
                diff = float(np.mean(grad - ctrl))
                stat = summaries[(budget, fill, control, h)]
                stat[0] += diff
                stat[1] += float(ctrl.mean())
                stat[2] += 1
                if budget == primary_budget and fill == primary_fill and control == primary_control:
                    entry = primary_files.setdefault(sid, {"group": cam["group"],
                        "repr_policy": cam["representation_policy"], "predicted_label": cam["predicted_label"]})
                    entry[h] = diff
                if secondary_files is not None and budget == primary_budget and fill == primary_fill and control in secondary_files:
                    entry = secondary_files[control].setdefault(sid, {"group": cam["group"]})
                    entry[h] = {"effect": diff, "gradcam_mean": float(grad.mean()),
                                "control_mean": float(ctrl.mean())}

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
    result = {"files": primary_files, "descriptive": table,
            "counts": {"cam_sample_n": len({sid for sid, _ in cams}),
                       "excluded_empty_cam_n": len(excluded_empty),
                       "excluded_ineligible_n": len(excluded_ineligible),
                       "eligible_n": len(primary_files)},
            "structure_cam_mass": {k: {"mean": v[0] / v[1], "n": v[1]} for k, v in sorted(mass.items())}}
    if secondary_files is not None:
        if any(set(METRICS) - row.keys() for files in secondary_files.values() for row in files.values()):
            raise ValueError("incomplete secondary metrics")
        result["secondary_files"] = secondary_files
    return result


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
                    lines.append(f"| {scope} | {h.upper()} | {r['effect']:.6g} | [{r['ci_95_lower']:.6g}, {r['ci_95_upper']:.6g}] | {r['holm_adjusted_p']:.6g} | {r['eligible_n']} | {r['group_n']} | {data['counts'].get('excluded_empty_cam_n', data['counts'].get('excluded_empty_cam_by_seed'))} |")
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


def build(inputs: list[tuple[str, int, Path, Path]], protocol_path: Path = FROZEN,
          secondary_controls: bool = False) -> dict:
    p = protocol_settings(protocol_path)
    seeds = set(map(int, p["model"]["seeds"]))
    by_population = defaultdict(dict)
    hashes = {}
    for population, seed, perturb, gradcam in inputs:
        if population not in {"main", "era"} or seed not in seeds or seed in by_population[population]:
            raise ValueError("unexpected population/seed or duplicate ledger pair")
        hashes[f"{population}/seed_{seed}"] = {"perturb": digest(perturb), "gradcam": digest(gradcam)}
        by_population[population][seed] = collect(perturb, gradcam, p, seed, secondary_controls)
    if set(by_population) != {"main", "era"} or any(set(v) != seeds for v in by_population.values()):
        raise ValueError("three seeds are required for both main and era")
    report = {"protocol_sha256": digest(protocol_path), "ledger_sha256": hashes,
              "bootstrap": {"repeats": 2000, "seed": BOOTSTRAP_SEED, "p_tail": "one_sided_greater"},
              "populations": {}}
    for population, seed_data in by_population.items():
        result = {}
        file_sets = [set(seed_data[seed]["files"]) for seed in sorted(seeds)]
        # Empty-positive-CAM files differ by seed (retain_and_flag), so the seed average
        # uses the intersection and reports both sizes.
        coverage = {"seed_union_n": len(set.union(*file_sets)),
                    "seed_intersection_n": len(set.intersection(*file_sets))}
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
            "counts": {"eligible_n": len(averaged), **coverage,
                       "excluded_empty_cam_by_seed": {f"seed_{seed}": seed_data[seed]["counts"]["excluded_empty_cam_n"] for seed in sorted(seeds)}},
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
        if secondary_controls:
            for seed in sorted(seeds):
                result[f"seed_{seed}"]["secondary_controls"] = {
                    control: secondary_inference(seed_data[seed]["secondary_files"][control], 2000,
                                                 BOOTSTRAP_SEED + seed)
                    for control in SECONDARY_CONTROLS}
            secondary_average = {}
            for control in SECONDARY_CONTROLS:
                files_by_seed = [seed_data[seed]["secondary_files"][control] for seed in sorted(seeds)]
                shared = set.intersection(*(set(files) for files in files_by_seed))
                averaged_files = {}
                for sid in shared:
                    rows = [files[sid] for files in files_by_seed]
                    if len({row["group"] for row in rows}) != 1:
                        raise ValueError("secondary seed metadata mismatch")
                    averaged_files[sid] = {"group": rows[0]["group"], **{
                        h: {key: float(np.mean([row[h][key] for row in rows]))
                            for key in ("effect", "gradcam_mean", "control_mean")}
                        for h in METRICS}}
                secondary_average[control] = secondary_inference(averaged_files, 2000,
                                                                  BOOTSTRAP_SEED + 900)
            result["seed_average"]["secondary_controls"] = secondary_average
        report["populations"][population] = result
    return report


def descriptive_bootstrap(files: dict, repeats: int, seed: int) -> dict:
    """Group CI for a descriptive contrast; no hypothesis test is defined."""
    if not files:
        return {"eligible_n": 0, "group_n": 0, "p_value": None}
    groups = defaultdict(list)
    for row in files.values():
        groups[row["group"]].append(row["effect"])
    values = np.asarray([np.mean(x) for x in groups.values()])
    result = bootstrap(values, repeats, seed)
    result.pop("p_unadjusted")
    result.update(eligible_n=len(files), group_n=len(groups), p_value=None)
    return result


def distribution(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    a = np.asarray(values, dtype=float)
    return {"n": len(a), "mean": float(a.mean()), "median": float(np.median(a)),
            "q05": float(np.quantile(a, 0.05)), "q95": float(np.quantile(a, 0.95))}


def collect_v12(perturb: Path, seed: int, addendum: dict) -> dict:
    fills = set(addendum["experiment"]["fills"])
    budgets = set(map(float, addendum["experiment"]["budgets"]))
    repeat_n = addendum["experiment"]["repeats_per_file_budget"]
    metrics = {"h1": "deletion_delta_nll", "h2": "keep_only_malicious_score"}
    files = defaultdict(dict)
    counts = defaultdict(int)
    excluded = defaultdict(set)
    shapes = {arm: {name: [] for name in ("n_runs", "mean_run_len", "pixels_touched", "pixels_intact")}
              for arm in ("gradcam", "control")}
    differences = {name: [] for name in shapes["gradcam"]}
    realized = {name: [] for name in ("n_runs", "mean_run_len")}
    realized_run_lengths = Counter()
    row_exclusions = defaultdict(lambda: defaultdict(int))
    flagged_files = defaultdict(set)
    seen = set()
    for row in jsonl(perturb):
        sid, budget = str(row["sample_id"]), float(row["budget"])
        if int(row["checkpoint_seed"]) != seed or budget not in budgets or row["fill"] not in fills or row["control"] != "shape_matched_random":
            raise ValueError("unexpected V1.2 ledger row")
        repeat = int(row["repeat"])
        key = (sid, budget, repeat)
        if key in seen or not 0 <= repeat < repeat_n:
            raise ValueError("duplicate or invalid V1.2 repeat")
        seen.add(key)
        counts["rows"] += 1
        bucket = files[(sid, budget)]
        if "group" in bucket and bucket["group"] != row["group"]:
            raise ValueError("inconsistent V1.2 group")
        bucket["group"] = row["group"]
        if row["eligible"] is not True or row.get("structure_ineligible") is True:
            counts["structure_ineligible_rows"] += 1
            row_exclusions[budget]["structure_ineligible_rows"] += 1
            excluded[(sid, budget)].add("structure_ineligible")
            continue
        counts["eligible_rows"] += 1
        unplaced = int(row["unplaced_byte_count"])
        for name in ("placement_fallback", "run_split"):
            counts[name + "_rows"] += bool(row[name])
            if row[name]:
                flagged_files[name].add(sid)
        counts["unplaced_rows"] += unplaced > 0
        if unplaced:
            flagged_files["unplaced"].add(sid)
        row_exclusions[budget]["unplaced_rows"] += unplaced > 0
        row_exclusions[budget]["split_rows"] += bool(row["run_split"])
        counts["unplaced_bytes"] += unplaced
        for name in ("total_bytes_match", "region_bytes_match"):
            counts[name + "_violations"] += row[name] is not True
        if not row["run_split"]:
            counts["run_length_multiset_match_violations"] += row["run_length_multiset_match"] is not True
        counts["empty_cam_rows"] += int(row["gradcam_shape"]["n_runs"]) == 0
        if int(row["gradcam_shape"]["n_runs"]) == 0:
            flagged_files["empty_cam"].add(sid)
        for arm, field in (("gradcam", "gradcam_shape"), ("control", "control_shape")):
            for name in shapes[arm]:
                shapes[arm][name].append(float(row[field][name]))
        for name in differences:
            differences[name].append(float(row["control_shape"][name]) - float(row["gradcam_shape"][name]))
        for name in realized:
            realized[name].append(float(row["control_shape"]["control_realized_" + name]))
        realized_run_lengths.update(int(n) for n in row["control_shape"]["control_realized_run_length_multiset"])
        counts["control_realized_merged_rows"] += (row["control_shape"]["control_realized_n_runs"]
                                                   < row["control_shape"]["n_runs"])
        if unplaced:
            excluded[(sid, budget)].add("unplaced")
            continue
        effect = {}
        for h, suffix in metrics.items():
            value = float(row["gradcam_" + suffix]) - float(row["control_" + suffix])
            if not math.isfinite(value):
                raise ValueError("nonfinite V1.2 effect")
            effect[h] = value
        bucket.setdefault("repeats", {})[repeat] = {"effects": effect, "split": bool(row["run_split"]),
            "control": {h: float(row["control_" + suffix]) for h, suffix in metrics.items()}}
    expected = repeat_n * len(budgets)
    sample_ids = {sid for sid, _ in files}
    if len(seen) != expected * len(sample_ids):
        raise ValueError("incomplete V1.2 sample/budget/repeats")
    primary, no_split, all_budgets, controls = {}, {}, defaultdict(dict), {}
    exclusion = {str(b): {"unplaced_rows": 0, "unplaced_files": 0, "all_repeats_excluded_files": 0,
                          "split_rows": 0, "split_files": 0, "structure_ineligible_rows": 0,
                          "structure_ineligible_files": 0} for b in sorted(budgets)}
    for (sid, budget), bucket in files.items():
        label = str(budget)
        reasons = excluded[(sid, budget)]
        exclusion[label]["unplaced_files"] += "unplaced" in reasons
        exclusion[label]["structure_ineligible_files"] += "structure_ineligible" in reasons
        repeats = bucket.get("repeats", {})
        exclusion[label]["all_repeats_excluded_files"] += not repeats and "structure_ineligible" not in reasons
        exclusion[label]["split_files"] += any(r["split"] for r in repeats.values())
        if not repeats:
            continue
        entry = {"group": bucket["group"], **{h: float(np.mean([r["effects"][h] for r in repeats.values()])) for h in metrics}}
        all_budgets[budget][sid] = entry
        controls[(sid, budget)] = {h: float(np.mean([r["control"][h] for r in repeats.values()])) for h in metrics}
        if budget == float(addendum["experiment"]["primary_budget"]):
            primary[sid] = entry
            subset = [r for r in repeats.values() if not r["split"]]
            if subset:
                no_split[sid] = {"group": bucket["group"], **{h: float(np.mean([r["effects"][h] for r in subset])) for h in metrics}}
    # Row counts are recorded during streaming; files are distinct within each budget.
    for budget in budgets:
        label = str(budget)
        for name in ("unplaced_rows", "split_rows", "structure_ineligible_rows"):
            exclusion[label][name] = row_exclusions[budget][name]
    matching = {"arms": {arm: {n: distribution(v) for n, v in fields.items()} for arm, fields in shapes.items()},
                "shape_minus_gradcam": {n: distribution(v) for n, v in differences.items()},
                "control_realized": {**{n: distribution(v) for n, v in realized.items()},
                                     "run_length_histogram": {str(k): v for k, v in sorted(realized_run_lengths.items())}},
                "counts": {**dict(counts), **{k + "_files": len(v) for k, v in flagged_files.items()}}}
    return {"primary_files": primary, "split_excluded_files": no_split, "budget_files": dict(all_budgets),
            "controls": controls, "exclusions": exclusion, "matching": matching,
            "counts": {"samples": len(sample_ids), "primary_eligible_n": len(primary)}}


def collect_v11_scatter(path: Path, seed: int) -> dict:
    """Keep only the two relevant V1.1 combinations while streaming JSONL."""
    sums = defaultdict(lambda: {"h1": 0.0, "h2": 0.0, "n": 0})
    for row in jsonl(path):
        if (row.get("control") != "structure_matched_random_20_repeats"
                or row.get("fill") != "structure_conditioned_resampling"
                or float(row.get("budget", -1)) not in (0.10, 0.20)):
            continue
        if int(row["checkpoint_seed"]) != seed:
            continue
        if row["eligible"] is not True:
            continue
        key = (str(row["sample_id"]), seed, float(row["budget"]), row["fill"])
        item = sums[key]
        item["h1"] += float(row["control_deletion_delta_nll"])
        item["h2"] += float(row["control_keep_only_malicious_score"])
        item["n"] += 1
    return {key: {h: value[h] / value["n"] for h in ("h1", "h2")} for key, value in sums.items()}


def adjudication(primary: dict) -> dict:
    h1, h2 = primary["h1"], primary["h2"]
    if "holm_adjusted_p" not in h1 or "holm_adjusted_p" not in h2:
        return {"status": "insufficient_eligible_files"}
    h1_yes = h1["holm_adjusted_p"] < 0.05
    h2_yes = h2["holm_adjusted_p"] < 0.05
    h2_zero = h2["ci_95_lower"] <= 0 <= h2["ci_95_upper"]
    return {"h1prime_holm_p_lt_0_05": h1_yes, "h2prime_holm_p_lt_0_05": h2_yes,
            "h2prime_ci_includes_zero": h2_zero,
            "template_conditions": {"h1prime_supported": h1_yes, "h1prime_not_supported": not h1_yes,
                                    "h2prime_supported": h2_yes,
                                    "h2prime_not_supported_ci_includes_zero": not h2_yes and h2_zero}}


def ci_only(value):
    """Era is a directional replication, outside the main testing family."""
    if isinstance(value, dict):
        return {k: ci_only(v) for k, v in value.items() if k not in ("p_unadjusted", "holm_adjusted_p")}
    if isinstance(value, list):
        return [ci_only(v) for v in value]
    return value


def build_v12(inputs: list[tuple[str, int, Path, Path]], v11_inputs: list[tuple[str, int, Path, Path]],
              addendum_path: Path, expected_sha256: str) -> dict:
    from psa_perturb import load_addendum
    addendum = load_addendum(addendum_path, expected_sha256)
    parent_sha = digest(FROZEN)
    expected_pairs = {(p, s) for p in ("main", "era") for s in (42, 43, 44)}
    if {(p, s) for p, s, _, _ in inputs} != expected_pairs or len(inputs) != 6:
        raise ValueError("six distinct V1.2 population/seed inputs required")
    if {(p, s) for p, s, _, _ in v11_inputs} != expected_pairs or len(v11_inputs) != 6:
        raise ValueError("six distinct V1.1 population/seed inputs required")
    old = {(p, s): (ledger, summary) for p, s, ledger, summary in v11_inputs}
    report = {"addendum_sha256": digest(addendum_path), "parent_protocol_sha256": parent_sha,
              "inputs_sha256": {}, "v11_inputs_sha256": {}, "bootstrap": {"repeats": 2000,
              "seed": BOOTSTRAP_SEED}, "populations": {}}
    for pop, seed, ledger, cam in inputs:
        summary = ledger.parent / "perturb_summary.json"
        summary_data = json.loads(summary.read_text(encoding="utf-8"))
        sha = digest(ledger)
        if (summary_data.get("ledger_sha256") != sha or summary_data.get("addendum_sha256") != report["addendum_sha256"]
                or summary_data.get("parent_protocol_sha256") != parent_sha or int(summary_data["checkpoint_seed"]) != seed):
            raise ValueError("V1.2 summary SHA or seed mismatch")
        report["inputs_sha256"][f"{pop}/seed_{seed}"] = {"perturb": sha, "summary": digest(summary), "gradcam": digest(cam)}
        data = collect_v12(ledger, seed, addendum)
        # Reuse frozen CAM metadata rules for subset and representation scopes.
        cams = {}
        for row in jsonl(cam):
            if math.isclose(float(row["budget"]["requested_fraction"]), 0.10, abs_tol=1e-9):
                cams[str(row["sample_id"])] = row
        for sid, entry in data["primary_files"].items():
            c = cams[sid]
            entry.update(repr_policy=c["representation_policy"], predicted_label=c["predicted_label"])
        for sid, entry in data["split_excluded_files"].items():
            c = cams[sid]
            entry.update(repr_policy=c["representation_policy"], predicted_label=c["predicted_label"])
        old_ledger, old_summary = old[(pop, seed)]
        old_meta = json.loads(old_summary.read_text(encoding="utf-8"))
        old_sha = digest(old_ledger)
        if old_meta.get("ledger_sha256") != old_sha:
            raise ValueError("V1.1 ledger SHA-256 mismatch")
        report["v11_inputs_sha256"][f"{pop}/seed_{seed}"] = {"perturb": old_sha, "summary": digest(old_summary)}
        scatter = collect_v11_scatter(old_ledger, seed)
        dispersion = {}
        for budget in addendum["experiment"]["budgets"]:
            dispersion[str(budget)] = {}
            for i, h in enumerate(("h1", "h2")):
                joined = {}
                for sid, shape in data["budget_files"].get(float(budget), {}).items():
                    key = (sid, seed, float(budget), "structure_conditioned_resampling")
                    if key in scatter:
                        joined[sid] = {"group": shape["group"], "effect": data["controls"][(sid, float(budget))][h] - scatter[key][h]}
                dispersion[str(budget)][h] = descriptive_bootstrap(joined, 2000, BOOTSTRAP_SEED + seed + i)
        pop_data = report["populations"].setdefault(pop, {})
        pop_data[f"seed_{seed}"] = {"files": data["primary_files"], "split_files": data["split_excluded_files"],
                                    "counts": data["counts"], "exclusions": data["exclusions"],
                                    "matching": data["matching"], "dispersion_effect": dispersion,
                                    "budget_0_20": {h: descriptive_bootstrap(
                                        {sid: {"group": r["group"], "effect": r[h]} for sid, r in data["budget_files"].get(0.20, {}).items()},
                                        2000, BOOTSTRAP_SEED + seed + i) for i, h in enumerate(("h1", "h2"))}}
    protocol = protocol_settings(FROZEN)
    for pop, scopes in report["populations"].items():
        for seed in (42, 43, 44):
            scope = scopes[f"seed_{seed}"]
            f = scope["files"]
            scope["primary"] = inference(f, 2000, BOOTSTRAP_SEED + seed)
            scope["run_split_excluded_sensitivity"] = inference(scope["split_files"], 2000, BOOTSTRAP_SEED + seed + 300)
            scope["correctly_detected_malicious"] = inference(
                {sid: r for sid, r in f.items() if r["predicted_label"] == 1}, 2000, BOOTSTRAP_SEED + seed + 500)
            scope["repr_policy"] = {name: inference({sid: r for sid, r in f.items() if r["repr_policy"] == policy},
                2000, BOOTSTRAP_SEED + seed + j * 1000) for j, (name, policy) in enumerate((("mean_pool", protocol["representation"]["long_file_policy"]),
                ("nearest_repetition", protocol["representation"]["short_file_policy"])), 1)}
        common = set.intersection(*(set(scopes[f"seed_{s}"]["files"]) for s in (42, 43, 44)))
        average = {}
        for sid in common:
            rows = [scopes[f"seed_{s}"]["files"][sid] for s in (42, 43, 44)]
            if len({(r["group"], r["repr_policy"]) for r in rows}) != 1:
                raise ValueError("V1.2 seed metadata mismatch")
            average[sid] = {"group": rows[0]["group"], "repr_policy": rows[0]["repr_policy"],
                            "predicted_label": 1 if all(r["predicted_label"] == 1 for r in rows) else -1,
                            **{h: float(np.mean([r[h] for r in rows])) for h in ("h1", "h2")}}
        primary = inference(average, 2000, BOOTSTRAP_SEED + 900)
        scopes["seed_average"] = {"counts": {"eligible_n": len(common)}, "primary": primary,
            "adjudication_conditions": adjudication(primary),
            "correctly_detected_malicious": inference({sid: r for sid, r in average.items() if r["predicted_label"] == 1}, 2000, BOOTSTRAP_SEED + 1400),
            "repr_policy": {name: inference({sid: r for sid, r in average.items() if r["repr_policy"] == policy},
                2000, BOOTSTRAP_SEED + 1900 + j * 1000) for j, (name, policy) in enumerate((("mean_pool", protocol["representation"]["long_file_policy"]),
                ("nearest_repetition", protocol["representation"]["short_file_policy"])), 1)}}
        split_common = set.intersection(*(set(scopes[f"seed_{s}"]["split_files"]) for s in (42, 43, 44)))
        split_average = {sid: {"group": scopes["seed_42"]["split_files"][sid]["group"],
            **{h: float(np.mean([scopes[f"seed_{s}"]["split_files"][sid][h] for s in (42, 43, 44)])) for h in ("h1", "h2")}}
            for sid in split_common}
        scopes["seed_average"]["run_split_excluded_sensitivity"] = inference(split_average, 2000, BOOTSTRAP_SEED + 1200)
        for seed in (42, 43, 44):
            scopes[f"seed_{seed}"].pop("files")
            scopes[f"seed_{seed}"].pop("split_files")
        if pop == "era":
            report["populations"][pop] = ci_only(scopes)
            report["populations"][pop]["seed_average"].pop("adjudication_conditions")
    return report


def render_v12(report: dict) -> str:
    lines = ["# PSA-XAI V1.2 statistics", "", f"Addendum SHA-256: `{report['addendum_sha256']}`",
             f"Parent SHA-256: `{report['parent_protocol_sha256']}`", "",
             "Dispersion effect: descriptive only because fill random states differ by control name; p value: none.", ""]
    for pop, scopes in report["populations"].items():
        if pop == "main":
            lines += [f"## {pop}", "", "| Scope | H | Effect | 95% CI | One-sided p | Holm p | Eligible files | Groups |",
                      "|---|---|---:|---|---:|---:|---:|---:|"]
        else:
            lines += [f"## {pop}", "", "| Scope | H | Effect | 95% CI | Eligible files | Groups |",
                      "|---|---|---:|---|---:|---:|"]
        for name, scope in scopes.items():
            for h, r in scope["primary"].items():
                if "effect" in r:
                    if pop == "main":
                        lines.append(f"| {name} | {h} | {r['effect']:.6g} | [{r['ci_95_lower']:.6g}, {r['ci_95_upper']:.6g}] | {r['p_unadjusted']:.6g} | {r['holm_adjusted_p']:.6g} | {r['eligible_n']} | {r['group_n']} |")
                    else:
                        lines.append(f"| {name} | {h} | {r['effect']:.6g} | [{r['ci_95_lower']:.6g}, {r['ci_95_upper']:.6g}] | {r['eligible_n']} | {r['group_n']} |")
        if pop == "main":
            lines += ["", "### Adjudication template conditions", "", "```json",
                      json.dumps(scopes["seed_average"]["adjudication_conditions"], ensure_ascii=False, indent=2), "```", ""]
        for name, scope in scopes.items():
            lines += [f"### {name} details", "", "```json",
                      json.dumps({k: v for k, v in scope.items() if k not in ("primary", "adjudication_conditions")}, ensure_ascii=False, indent=2), "```", ""]
        lines += ["### Input SHA-256", "", "```json",
                  json.dumps({"v1_2": {k: v for k, v in report["inputs_sha256"].items() if k.startswith(pop + "/")},
                              "v1_1": {k: v for k, v in report["v11_inputs_sha256"].items() if k.startswith(pop + "/")}}, indent=2), "```", ""]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ledger", nargs=4, action="append", metavar=("POPULATION", "SEED", "PERTURB", "GRADCAM"), required=True)
    ap.add_argument("--addendum", type=Path)
    ap.add_argument("--addendum-sha256")
    ap.add_argument("--v11-ledger", nargs=4, action="append", metavar=("POPULATION", "SEED", "PERTURB", "SUMMARY"))
    ap.add_argument("--secondary-controls", action="store_true")
    ap.add_argument("--outdir", type=Path, required=True)
    args = ap.parse_args()
    rows = [(pop, int(seed), Path(pert), Path(cam)) for pop, seed, pert, cam in args.ledger]
    if any((args.addendum is not None, args.addendum_sha256 is not None, args.v11_ledger is not None)):
        if args.secondary_controls:
            ap.error("--secondary-controls applies to V1.1 statistics only")
        if args.addendum is None or args.addendum_sha256 is None or args.v11_ledger is None:
            ap.error("V1.2 requires --addendum, --addendum-sha256 and six --v11-ledger inputs")
        old = [(pop, int(seed), Path(pert), Path(summary)) for pop, seed, pert, summary in args.v11_ledger]
        report = build_v12(rows, old, args.addendum, args.addendum_sha256)
        rendered = render_v12(report)
    else:
        report = build(rows, secondary_controls=args.secondary_controls)
        rendered = render(report)
    args.outdir.mkdir(parents=True, exist_ok=False)
    (args.outdir / "psa_xai_stats.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (args.outdir / "psa_xai_stats.md").write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
