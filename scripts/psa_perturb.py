"""Frozen, static byte perturbations paired to a Grad-CAM budget ledger.

Source files are opened read-only. Modified bytes exist only in memory and are
encoded through the same interval-binned function as psa_build_rasters.py.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ua_sahi_mal.kisa_xai.representation import encode_interval_binned, raster_sha256  # noqa: E402
from scripts.psa_gradcam import FROZEN, load_protocol, sha256  # noqa: E402


def offsets(intervals: list[list[int]], size: int) -> np.ndarray:
    result = np.concatenate([np.arange(a, b, dtype=np.int64) for a, b in intervals]) if intervals else np.empty(0, dtype=np.int64)
    if len(result) and (result.min() < 0 or result.max() >= size or len(np.unique(result)) != len(result)):
        raise ValueError("invalid or overlapping Grad-CAM intervals")
    return result


def region_ids(spans: list[dict], size: int) -> np.ndarray:
    ids = np.empty(size, dtype=np.int16)
    cursor = 0
    names = {name: i for i, name in enumerate(sorted({s["region"] for s in spans}))}
    for span in spans:
        if span["start"] != cursor or span["end"] <= cursor or span["end"] > size:
            raise ValueError("invalid structure partition")
        ids[cursor:span["end"]] = names[span["region"]]
        cursor = span["end"]
    if cursor != size:
        raise ValueError("incomplete structure partition")
    return ids


def entropy_scores(data: bytes, window: int = 256) -> np.ndarray:
    """Entropy of the fixed source window containing each byte."""
    raw = np.frombuffer(data, dtype=np.uint8)
    scores = np.empty(len(raw), dtype=np.float32)
    for start in range(0, len(raw), window):
        block = raw[start:start + window]
        counts = np.bincount(block, minlength=256)
        p = counts[counts > 0] / len(block)
        scores[start:start + len(block)] = -np.sum(p * np.log2(p))
    return scores


def control_offsets(control: str, data: bytes, budget: int, rng: np.random.Generator,
                    cam_offsets: np.ndarray, regions: np.ndarray | None = None) -> np.ndarray:
    size = len(data)
    if not 0 <= budget <= size:
        raise ValueError("budget outside source")
    if control == "front_position":
        return np.arange(budget, dtype=np.int64)
    if control == "entropy":
        scores = entropy_scores(data)
        return np.sort(np.argsort(-scores, kind="stable")[:budget])
    if control == "uniform_random_20_repeats":
        return np.sort(rng.choice(size, size=budget, replace=False))
    if control == "structure_matched_random_20_repeats":
        if regions is None:
            raise ValueError("structure matching requires agreement")
        parts = []
        for rid in np.unique(regions):
            count = int(np.count_nonzero(regions[cam_offsets] == rid))
            if count:
                candidates = np.flatnonzero(regions == rid)
                parts.append(rng.choice(candidates, size=count, replace=False))
        return np.sort(np.concatenate(parts)) if parts else np.empty(0, dtype=np.int64)
    raise ValueError(f"unsupported control: {control}")


def local_median(data: bytes, selected: np.ndarray, side: int, window: tuple[int, int]) -> np.ndarray:
    """5x5 neighbourhood on a row-major source-byte grid, clipped at the edge."""
    if window != (5, 5):
        raise ValueError("frozen local median window must be 5x5")
    raw = np.frombuffer(data, dtype=np.uint8)
    out = np.empty(len(selected), dtype=np.uint8)
    for j, pos in enumerate(selected):
        row, col = divmod(int(pos), side)
        neighbors = [raw[r * side + c] for r in range(max(0, row - 2), row + 3)
                     for c in range(max(0, col - 2), min(side, col + 3)) if r * side + c < len(raw)]
        out[j] = int(np.median(neighbors))
    return out


def fill_values(data: bytes, selected: np.ndarray, fill: str, rng: np.random.Generator,
                regions: np.ndarray | None, window: tuple[int, int], side: int) -> np.ndarray:
    raw = np.frombuffer(data, dtype=np.uint8)
    if fill == "zero":
        return np.zeros(len(selected), dtype=np.uint8)
    if fill == "local_median":
        return local_median(data, selected, side, window)
    if fill == "structure_conditioned_resampling":
        result = np.empty(len(selected), dtype=np.uint8)
        labels = regions if regions is not None else np.zeros(len(data), dtype=np.int16)
        for rid in np.unique(labels[selected]):
            destination = np.flatnonzero(labels[selected] == rid)
            pool = np.flatnonzero(labels == rid)
            result[destination] = raw[rng.choice(pool, size=len(destination), replace=True)]
        return result
    raise ValueError(f"unsupported fill: {fill}")


def perturbed_raster(data: bytes, selected: np.ndarray, mode: str, fill: str,
                     rng: np.random.Generator, regions: np.ndarray | None,
                     window: tuple[int, int], side: int) -> np.ndarray:
    mask = np.zeros(len(data), dtype=bool)
    mask[selected] = True
    change = selected if mode == "deletion" else np.flatnonzero(~mask)
    modified = bytearray(data)
    modified_values = fill_values(data, change, fill, rng, regions, window, side)
    for pos, value in zip(change, modified_values, strict=True):
        modified[int(pos)] = int(value)
    raster, _ = encode_interval_binned(modified, side=side)
    return raster


def pair_seed(base: int, sample: str, budget: float, fill: str, control: str, repeat: int) -> int:
    key = f"{base}|{sample}|{budget:.8g}|{fill}|{control}|{repeat}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(key).digest()[:8], "big")


def nll(logits: np.ndarray, label: int) -> float:
    maximum = float(np.max(logits))
    return maximum + math.log(float(np.exp(logits - maximum).sum())) - float(logits[label])


def score(model, raster: np.ndarray, device: str, malicious: int) -> tuple[float, float]:
    import torch
    from psa_train import preprocess_raster
    with torch.no_grad():
        logits = model(preprocess_raster(raster).unsqueeze(0).to(device))[0].detach().cpu().numpy()
    return nll(logits, malicious), float(logits[malicious])


def manifest_records(path: Path, wanted: set[str]) -> dict[str, dict]:
    found = {}
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row["sample_id"] in wanted:
                found[row["sample_id"]] = row
    if found.keys() != wanted:
        raise ValueError("stage-2 manifest lacks ledger sample IDs")
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--checkpoint", type=Path, required=True)
    ap.add_argument("--checkpoint-sha256", required=True)
    ap.add_argument("--gradcam-ledger", type=Path, required=True)
    ap.add_argument("--gradcam-ledger-sha256", required=True)
    ap.add_argument("--structure-ledger", type=Path, required=True)
    ap.add_argument("--structure-ledger-sha256", required=True)
    ap.add_argument("--stage2-manifest", type=Path, required=True)
    ap.add_argument("--samples-dir", type=Path, required=True)
    ap.add_argument("--rasters-dir", type=Path, required=True)
    ap.add_argument("--outdir", type=Path, required=True)
    ap.add_argument("--device", default="auto")
    args = ap.parse_args()
    protocol = load_protocol(FROZEN)
    xai = protocol["xai"]
    repeats = protocol["statistics"]["random_control_repeats_per_file"]
    controls = xai["controls"]
    fills = [xai["fills"][name] for name in ("primary", "robustness", "diagnostic")]
    window = tuple(xai["fills"]["local_median_window"])
    if repeats != 20 or len(set(fills)) != 3 or controls != ["uniform_random_20_repeats", "front_position", "entropy", "structure_matched_random_20_repeats"]:
        raise ValueError("unsupported frozen perturbation protocol")
    expected = {args.checkpoint: args.checkpoint_sha256.lower(), args.gradcam_ledger: args.gradcam_ledger_sha256.lower(),
                args.structure_ledger: args.structure_ledger_sha256.lower(), args.stage2_manifest: protocol["tooling"]["manifest_stage2_sha256"],
                args.rasters_dir / "raster_index.csv": protocol["representation"]["materialised"]["raster_index_sha256"],
                args.rasters_dir / "rasters_meta.json": protocol["representation"]["materialised"]["rasters_meta_sha256"]}
    for path, digest in expected.items():
        if sha256(path) != digest:
            raise ValueError(f"SHA-256 mismatch: {path}")
    import torch
    from psa_train import build_model
    device = ("cuda" if torch.cuda.is_available() else "cpu") if args.device == "auto" else args.device
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    side = protocol["representation"]["shape"][1]
    if (checkpoint["arch"] != protocol["model"]["primary"] or checkpoint["input"] != [1, side, side]
            or checkpoint["init"] != protocol["model"]["initialization"] or checkpoint["seed"] not in protocol["model"]["seeds"]):
        raise ValueError("checkpoint disagrees with frozen model")
    model = build_model("random", device)
    model.load_state_dict(checkpoint["model"], strict=True)
    model.eval()
    ledger = [json.loads(line) for line in args.gradcam_ledger.open(encoding="utf-8")]
    wanted = {entry["sample_id"] for entry in ledger}
    manifest = manifest_records(args.stage2_manifest, wanted)
    index = {}
    with (args.rasters_dir / "raster_index.csv").open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row["sample_id"] in wanted:
                index[row["sample_id"]] = row
    if index.keys() != wanted:
        raise ValueError("raster index lacks ledger sample IDs")
    structures = {}
    with args.structure_ledger.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["sample_id"] in wanted:
                structures[row["sample_id"]] = row
    if structures.keys() != wanted:
        raise ValueError("structure ledger lacks sample IDs")
    rasters = np.load(args.rasters_dir / protocol["representation"]["materialised"]["file"], mmap_mode="r")
    args.outdir.mkdir(parents=True, exist_ok=False)
    output = args.outdir / "perturb_ledger.jsonl"
    counts = {"samples": 0, "rows": 0, "forward_passes": 0, "structure_ineligible_rows": 0}
    cached_id, data, regions, original_nll, source_sha = None, None, None, None, None
    malicious = max(protocol["eligibility"]["labels"])
    with output.open("x", encoding="utf-8") as out:
        for entry in ledger:
            sid, budget = entry["sample_id"], entry["budget"]
            if sid != cached_id:
                data = (args.samples_dir / sid).read_bytes()
                source_sha = hashlib.sha256(data).hexdigest()
                if len(data) != int(index[sid]["file_size"]) or source_sha != manifest[sid]["sha256"]:
                    raise ValueError(f"source integrity mismatch: {sid}")
                original, imap = encode_interval_binned(data, side=side)
                if raster_sha256(original) != index[sid]["raster_sha256"] or imap.map_sha256() != index[sid]["map_sha256"]:
                    raise ValueError(f"source/raster mismatch: {sid}")
                if raster_sha256(np.asarray(rasters[int(index[sid]["row"])], dtype=np.float32).reshape(side, side)) != index[sid]["raster_sha256"]:
                    raise ValueError(f"materialised raster mismatch: {sid}")
                structure = structures[sid]
                regions = region_ids(structure["structure"]["spans"], len(data)) if structure["status"] == "agreement" else None
                original_nll = nll(np.asarray([entry["benign_logit"], entry["malicious_logit"]]), malicious)
                cached_id = sid
                counts["samples"] += 1
            selected = offsets(budget["intervals"], len(data))
            if len(selected) != budget["achieved_bytes"] or entry["file_size"] != len(data):
                raise ValueError(f"achieved budget mismatch: {sid}")
            for fill in fills:
                for control in controls:
                    eligible = control != "structure_matched_random_20_repeats" or regions is not None
                    times = repeats if control.endswith("_20_repeats") else 1
                    for repeat in range(times):
                        if not eligible:
                            result = {"sample_id": sid, "source_sha256": source_sha, "group": entry["group"], "checkpoint_seed": checkpoint["seed"],
                                      "budget": budget["requested_fraction"], "achieved_bytes": len(selected),
                                      "fill": fill, "control": control, "repeat": repeat, "eligible": False,
                                      "structure_status": entry["structure_status"], "reason": "structure_status_not_agreement"}
                            counts["structure_ineligible_rows"] += 1
                        else:
                            seed = pair_seed(checkpoint["seed"], sid, budget["requested_fraction"], fill, control, repeat)
                            selection_rng = np.random.default_rng(seed)
                            matched = control_offsets(control, data, len(selected), selection_rng, selected, regions)
                            if len(matched) != len(selected):
                                raise AssertionError("control byte budget mismatch")
                            result = {"sample_id": sid, "source_sha256": source_sha, "group": entry["group"], "checkpoint_seed": checkpoint["seed"],
                                      "budget": budget["requested_fraction"], "achieved_bytes": len(selected),
                                      "fill": fill, "control": control, "repeat": repeat, "eligible": True,
                                      "structure_status": entry["structure_status"], "pair_seed": seed,
                                      "gradcam_intervals": budget["intervals"], "control_intervals": compress_offsets(matched)}
                            for name, chosen in (("gradcam", selected), ("control", matched)):
                                # Reset the same random state for both arms and each metric.
                                for mode in ("deletion", "keep_only"):
                                    raster = perturbed_raster(data, chosen, mode, fill, np.random.default_rng(seed), regions, window, side)
                                    value_nll, malicious_score = score(model, raster, device, malicious)
                                    counts["forward_passes"] += 1
                                    if mode == "deletion":
                                        result[f"{name}_deletion_delta_nll"] = value_nll - original_nll
                                    else:
                                        result[f"{name}_keep_only_malicious_score"] = malicious_score
                        out.write(json.dumps(result, allow_nan=False, ensure_ascii=True) + "\n")
                        counts["rows"] += 1
            out.flush()
    (args.outdir / "perturb_summary.json").write_text(json.dumps({"protocol_sha256": sha256(FROZEN),
        "inputs": {str(p): v for p, v in expected.items()}, "checkpoint_seed": checkpoint["seed"],
        "counts": counts, "ledger_sha256": sha256(output)}, indent=2) + "\n", encoding="utf-8")
    return 0


def compress_offsets(selected: np.ndarray) -> list[list[int]]:
    if len(selected) == 0:
        return []
    starts = np.r_[0, np.flatnonzero(np.diff(selected) != 1) + 1]
    ends = np.r_[starts[1:], len(selected)]
    return [[int(selected[a]), int(selected[b - 1]) + 1] for a, b in zip(starts, ends, strict=True)]


if __name__ == "__main__":
    raise SystemExit(main())
