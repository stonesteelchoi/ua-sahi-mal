"""Synthetic V1.2 statistics only; no held-out ledgers or source files."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from psa_xai_stats import (FROZEN, build, build_v12, collect_v11_scatter,
                           digest, render, render_v12)  # noqa: E402
from psa_perturb import FROZEN_ADDENDUM_SHA256  # noqa: E402

ADDENDUM = ROOT / "paper/v5-kisa-xai/protocol/PSA_XAI_V1_2_ADDENDUM.yaml"


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def make_inputs(tmp_path, effect=1.0, mutations=None):
    mutations = mutations or {}
    new, old = [], []
    for pop in ("main", "era"):
        for seed in (42, 43, 44):
            directory = tmp_path / f"{pop}_{seed}"
            directory.mkdir()
            v12, cam, v11 = (directory / name for name in ("perturb_ledger.jsonl", "cam.jsonl", "v11.jsonl"))
            cams, rows, old_rows = [], [], []
            for sid in ("0", "1", "2", "3"):
                for budget in (0.10, 0.20):
                    cams.append({"sample_id": sid, "group": f"g{int(sid)//2}",
                        "representation_policy": "nearest_byte_repetition" if int(sid) % 2 == 0 else "contiguous_interval_mean_pool",
                        "predicted_label": 1, "budget": {"requested_fraction": budget, "achieved_bytes": 4}})
                    for repeat in range(20):
                        key = (pop, seed, sid, budget, repeat)
                        state = mutations.get(key, {})
                        base = {"sample_id": sid, "group": f"g{int(sid)//2}", "checkpoint_seed": seed,
                            "budget": budget, "fill": "structure_conditioned_resampling", "repeat": repeat,
                            "eligible": not state.get("ineligible", False)}
                        shape = {"n_runs": 2, "mean_run_len": 2.0, "pixels_touched": 2, "pixels_intact": 2,
                                 "run_length_multiset": [2, 2], "region_byte_counts": {"1": 4},
                                 "total_selected_unique_source_bytes": 4}
                        control = {**shape, "pixels_touched": 3, "pixels_intact": 1,
                                   "control_realized_n_runs": 1, "control_realized_mean_run_len": 4.0,
                                   "control_realized_run_length_multiset": [4]}
                        row = {**base, "control": "shape_matched_random",
                            "structure_ineligible": state.get("ineligible", False),
                            "run_split": state.get("split", False), "placement_fallback": state.get("unplaced", False),
                            "unplaced_byte_count": 1 if state.get("unplaced", False) else 0,
                            "gradcam_shape": shape, "control_shape": control,
                            "total_bytes_match": True, "region_bytes_match": True,
                            "run_length_multiset_match": None if state.get("split", False) else True,
                            "gradcam_deletion_delta_nll": 2 + state.get("effect", effect),
                            "control_deletion_delta_nll": 2.0,
                            "gradcam_keep_only_malicious_score": 4 + state.get("effect", effect) / 2,
                            "control_keep_only_malicious_score": 4.0}
                        rows.append(row)
                        old_rows.append({**base, "checkpoint_seed": state.get("old_seed", seed),
                            "control": "structure_matched_random_20_repeats",
                            "control_deletion_delta_nll": 1.0, "control_keep_only_malicious_score": 3.0})
                        old_rows.append({**base, "control": "front_position",
                            "control_deletion_delta_nll": 999.0, "control_keep_only_malicious_score": 999.0})
            write_jsonl(v12, rows)
            write_jsonl(cam, cams)
            write_jsonl(v11, old_rows)
            summary = directory / "perturb_summary.json"
            summary.write_text(json.dumps({"ledger_sha256": digest(v12), "addendum_sha256": FROZEN_ADDENDUM_SHA256,
                "parent_protocol_sha256": digest(FROZEN), "checkpoint_seed": seed}), encoding="utf-8")
            old_summary = directory / "v11_summary.json"
            old_summary.write_text(json.dumps({"ledger_sha256": digest(v11)}), encoding="utf-8")
            new.append((pop, seed, v12, cam))
            old.append((pop, seed, v11, old_summary))
    return new, old


@pytest.mark.parametrize("effect,significant", [(1.0, True), (-1.0, False), (0.0, False)])
def test_direction_ci_holm_and_template(tmp_path, effect, significant):
    new, old = make_inputs(tmp_path, effect)
    report = build_v12(new, old, ADDENDUM, FROZEN_ADDENDUM_SHA256)
    main = report["populations"]["main"]["seed_average"]
    for h, value in (("h1", effect), ("h2", effect / 2)):
        r = main["primary"][h]
        assert r["effect"] == pytest.approx(value)
        assert r["ci_95_lower"] <= value <= r["ci_95_upper"]
        assert (r["holm_adjusted_p"] < 0.05) is significant
    flags = main["adjudication_conditions"]["template_conditions"]
    assert flags["h1prime_supported"] is significant
    assert flags["h1prime_not_supported"] is not significant
    assert flags["h2prime_supported"] is significant
    assert flags["h2prime_not_supported_ci_includes_zero"] is (effect == 0)
    assert report["populations"]["era"]["seed_average"]["primary"]["h1"]["effect"] == pytest.approx(effect)
    assert "holm_adjusted_p" not in report["populations"]["era"]["seed_average"]["primary"]["h1"]
    assert "Adjudication template conditions" in render_v12(report)
    assert report["populations"]["main"]["seed_42"]["budget_0_20"]["h1"]["p_value"] is None


def test_unplaced_split_seed_intersection_and_matching(tmp_path):
    changes = {("main", 42, "0", 0.10, 0): {"unplaced": True},
               ("main", 42, "0", 0.10, 1): {"split": True, "effect": 5.0}}
    changes.update({("main", 43, "1", 0.10, r): {"unplaced": True} for r in range(20)})
    new, old = make_inputs(tmp_path, 1.0, changes)
    report = build_v12(new, old, ADDENDUM, FROZEN_ADDENDUM_SHA256)
    main = report["populations"]["main"]
    s42, s43 = main["seed_42"], main["seed_43"]
    assert s42["exclusions"]["0.1"]["unplaced_rows"] == 1
    assert s42["exclusions"]["0.1"]["unplaced_files"] == 1
    assert s42["exclusions"]["0.1"]["split_rows"] == 1
    assert s42["primary"]["h1"]["effect"] > s42["run_split_excluded_sensitivity"]["h1"]["effect"]
    assert s43["exclusions"]["0.1"]["all_repeats_excluded_files"] == 1
    assert s43["primary"]["h1"]["eligible_n"] == 3
    assert main["seed_average"]["counts"]["eligible_n"] == 3
    assert s42["matching"]["shape_minus_gradcam"]["pixels_touched"]["mean"] == 1
    assert s42["matching"]["counts"]["control_realized_merged_rows"] > 0


def test_dispersion_filter_seed_join_and_sha_gate(tmp_path):
    changes = {("main", 42, "0", 0.10, r): {"old_seed": 99} for r in range(20)}
    new, old = make_inputs(tmp_path, 1.0, changes)
    report = build_v12(new, old, ADDENDUM, FROZEN_ADDENDUM_SHA256)
    d = report["populations"]["main"]["seed_42"]["dispersion_effect"]["0.1"]["h1"]
    assert d["eligible_n"] == 3
    assert d["effect"] == pytest.approx(1.0)
    assert d["p_value"] is None
    scatter = collect_v11_scatter(old[0][2], 42)
    assert len(scatter) == 7  # one wrong-seed key filtered; front_position rows filtered
    old[0][2].write_text(old[0][2].read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="V1.1 ledger SHA"):
        build_v12(new, old, ADDENDUM, FROZEN_ADDENDUM_SHA256)


def test_v11_output_bit_identical_to_head(tmp_path):
    from test_psa_xai_stats import ledgers
    source = subprocess.check_output(["git", "show", "HEAD:scripts/psa_xai_stats.py"], cwd=ROOT).decode("utf-8")
    spec = importlib.util.spec_from_loader("baseline_psa_xai_stats", loader=None)
    baseline = importlib.util.module_from_spec(spec)
    baseline.__file__ = str(ROOT / "scripts/psa_xai_stats.py")
    exec(compile(source, baseline.__file__, "exec"), baseline.__dict__)
    inputs = []
    for pop in ("main", "era"):
        for seed in (42, 43, 44):
            perturb, cam = ledgers(tmp_path / f"{pop}_{seed}", seed, 1.0)
            inputs.append((pop, seed, perturb, cam))
    current, previous = build(inputs), baseline.build(inputs)
    assert (json.dumps(current, indent=2, allow_nan=False) + "\n").encode() == (json.dumps(previous, indent=2, allow_nan=False) + "\n").encode()
    assert render(current).encode() == baseline.render(previous).encode()
