"""Synthetic ledgers only; no held-out data is opened."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from psa_xai_stats import FROZEN, build, collect, holm, protocol_settings, render  # noqa: E402


def ledgers(directory, seed, effect):
    directory.mkdir()
    cam_path = directory / "gradcam.jsonl"
    perturb_path = directory / "perturb.jsonl"
    controls = {"uniform_random_20_repeats": 20, "front_position": 1,
                "entropy": 1, "structure_matched_random_20_repeats": 20}
    fills = ("structure_conditioned_resampling", "local_median", "zero")
    with cam_path.open("w", encoding="utf-8") as cam, perturb_path.open("w", encoding="utf-8") as pert:
        for i in range(8):
            sid = str(i)
            for budget in (0.05, 0.10, 0.20, 0.40):
                empty = i == 7
                eligible = i != 6
                record = {"sample_id": sid, "group": f"g{i // 2}",
                          "representation_policy": ("contiguous_interval_mean_pool" if i % 2 else "nearest_byte_repetition"),
                          "predicted_label": 1, "structure_cam_mass": {"executable_sections": 0.7, "overlay": 0.3},
                          "budget": {"requested_fraction": budget, "achieved_bytes": 0 if empty else 10}}
                cam.write(json.dumps(record) + "\n")
                for control, repeats in controls.items():
                    for repeat in range(repeats):
                        for fill in fills:
                            is_eligible = eligible or control != "structure_matched_random_20_repeats"
                            row = {"sample_id": sid, "group": record["group"], "checkpoint_seed": seed,
                                   "budget": budget, "achieved_bytes": record["budget"]["achieved_bytes"],
                                   "fill": fill, "control": control, "repeat": repeat, "eligible": is_eligible}
                            if is_eligible:
                                row.update(gradcam_deletion_delta_nll=2.0 + effect,
                                           control_deletion_delta_nll=2.0,
                                           gradcam_keep_only_malicious_score=4.0 + effect / 2,
                                           control_keep_only_malicious_score=4.0)
                            pert.write(json.dumps(row) + "\n")
    return perturb_path, cam_path


@pytest.mark.parametrize("effect", [1.5, 0.0])
def test_synthetic_ledgers_direction_ci_exclusions_and_hashes(tmp_path, effect):
    inputs = []
    for population in ("main", "era"):
        for seed in (42, 43, 44):
            perturb, cam = ledgers(tmp_path / f"{population}_{seed}", seed, effect)
            inputs.append((population, seed, perturb, cam))
    report = build(inputs)
    assert len(report["ledger_sha256"]) == 6
    assert report["protocol_sha256"]
    for population in ("main", "era"):
        for scope in ("seed_42", "seed_43", "seed_44", "seed_average"):
            row = report["populations"][population][scope]
            assert row["counts"]["eligible_n"] == 6
            assert row["counts"].get("excluded_empty_cam_n", 1) == 1
            for h, expected in (("h1", effect), ("h2", effect / 2)):
                result = row["primary"][h]
                assert result["effect"] == pytest.approx(expected)
                assert result["ci_95_lower"] <= expected <= result["ci_95_upper"]
                assert result["sensitivity_file"]["effect"] == pytest.approx(expected)
            assert row["primary"]["h1"]["group_n"] == 3
        assert report["populations"][population]["seed_42"]["repr_policy"]["mean_pool"]["h1"]["eligible_n"] == 3
    assert "Structure CAM mass" in render(report)


def test_holm_order_and_monotonicity():
    values = {"h1": {"p_unadjusted": 0.04}, "h2": {"p_unadjusted": 0.01}}
    holm(values)
    assert values["h2"]["holm_adjusted_p"] == pytest.approx(0.02)
    assert values["h1"]["holm_adjusted_p"] == pytest.approx(0.04)


def test_collect_accepts_out_of_order_complete_sample_blocks(tmp_path):
    perturb, cam = ledgers(tmp_path / "ledgers", 42, 1.5)
    protocol = protocol_settings(FROZEN)
    expected = collect(perturb, cam, protocol, 42)
    blocks = {}
    for line in perturb.read_text(encoding="utf-8").splitlines(keepends=True):
        blocks.setdefault(json.loads(line)["sample_id"], []).append(line)
    perturb.write_text("".join(line for sid in reversed(list(blocks)) for line in blocks[sid]), encoding="utf-8")
    actual = collect(perturb, cam, protocol, 42)
    assert actual["counts"] == expected["counts"]
    assert actual["files"] == expected["files"]


def test_secondary_controls_paired_group_ci_and_seed_intersection(tmp_path):
    inputs = []
    for population in ("main", "era"):
        for seed in (42, 43, 44):
            perturb, cam = ledgers(tmp_path / f"{population}_{seed}", seed, 1.0)
            changed = []
            for line in perturb.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                if row["budget"] == 0.10 and row["fill"] == "structure_conditioned_resampling" and row["control"] in (
                        "uniform_random_20_repeats", "entropy", "front_position"):
                    if row["control"] == "uniform_random_20_repeats":
                        row.update(gradcam_deletion_delta_nll=10 + row["repeat"],
                                   control_deletion_delta_nll=2 + 2 * row["repeat"])
                    elif row["control"] == "entropy":
                        row.update(gradcam_deletion_delta_nll=6, control_deletion_delta_nll=3)
                        if seed == 43 and row["sample_id"] == "6":
                            row["eligible"] = False
                    else:
                        row.update(gradcam_deletion_delta_nll=6 if row["sample_id"] == "6" else 1,
                                   control_deletion_delta_nll=4)
                changed.append(json.dumps(row) + "\n")
            perturb.write_text("".join(changed), encoding="utf-8")
            inputs.append((population, seed, perturb, cam))
    report = build(inputs, secondary_controls=True)
    expected = {"uniform_random_20_repeats": (-1.5, 19.5, 21.0, 7, 4),
                "entropy": (3.0, 6.0, 3.0, 6, 3),
                "front_position": (-1.75, 12 / 7, 4.0, 7, 4)}
    for population in ("main", "era"):
        scopes = report["populations"][population]
        for scope in ("seed_42", "seed_43", "seed_44", "seed_average"):
            for control, (effect, grad, comparison, n, groups) in expected.items():
                row = scopes[scope]["secondary_controls"][control]["h1"]
                scope_n = 7 if control == "entropy" and scope != "seed_43" and scope != "seed_average" else n
                assert row["eligible_n"] == scope_n
                assert row["group_n"] == (4 if scope_n == 7 else groups)
                assert row["effect"] == pytest.approx(effect)
                assert row["ci_95_lower"] <= effect <= row["ci_95_upper"]
                if control != "front_position":
                    assert row["ci_95_lower"] == pytest.approx(effect)
                    assert row["ci_95_upper"] == pytest.approx(effect)
                assert row["gradcam_mean"] == pytest.approx(grad)
                assert row["control_mean"] == pytest.approx(comparison)
                assert row["preregistered"] is False and row["family"] == "secondary"
                assert not any("p_unadjusted" in key or "holm" in key for key in row)
                assert scopes[scope]["secondary_controls"][control]["h2"]["eligible_n"] == scope_n
        assert scopes["seed_average"]["primary"]["h1"]["eligible_n"] == 6
