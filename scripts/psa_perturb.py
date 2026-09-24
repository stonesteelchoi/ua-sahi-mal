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
import os
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from itertools import groupby
from pathlib import Path

import numpy as np
from scipy.ndimage import median_filter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from ua_sahi_mal.kisa_xai.representation import POLICY_MEAN_POOL, encode_interval_binned, raster_sha256  # noqa: E402
from psa_gradcam import FROZEN, load_protocol, sha256  # noqa: E402


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
                    cam_offsets: np.ndarray, regions: np.ndarray | None = None,
                    entropy: np.ndarray | None = None) -> np.ndarray:
    size = len(data)
    if not 0 <= budget <= size:
        raise ValueError("budget outside source")
    if control == "front_position":
        return np.arange(budget, dtype=np.int64)
    if control == "entropy":
        ranked = entropy if entropy is not None else np.argsort(-entropy_scores(data), kind="stable")
        return np.sort(ranked[:budget])
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
    return local_median_grid(data, side, window)[selected]


def local_median_grid(data: bytes, side: int, window: tuple[int, int]) -> np.ndarray:
    """Cache exact clipped-neighbour medians on the source-byte grid."""
    if window != (5, 5):
        raise ValueError("frozen local median window must be 5x5")
    size = len(data)
    if not size:
        return np.empty(0, dtype=np.uint8)
    height = (size + side - 1) // side
    grid = np.full((height, side), 256, dtype=np.uint16)
    grid.flat[:size] = np.frombuffer(data, dtype=np.uint8)
    medians = median_filter(grid, size=window, mode="constant", cval=256).ravel()[:size].astype(np.uint8)
    positions = np.arange(size)
    rows, cols = divmod(positions, side)
    edge = (rows < 2) | (rows >= height - 3) | (cols < 2) | (cols >= side - 2)
    boundary = positions[edge]
    if len(boundary):
        rr = rows[edge, None] + np.repeat(np.arange(-2, 3), 5)[None, :]
        cc = cols[edge, None] + np.tile(np.arange(-2, 3), 5)[None, :]
        valid = (rr >= 0) & (rr < height) & (cc >= 0) & (cc < side) & (rr * side + cc < size)
        neighbors = grid[np.clip(rr, 0, height - 1), np.clip(cc, 0, side - 1)].astype(np.float32)
        medians[boundary] = np.nanmedian(np.where(valid, neighbors, np.nan), axis=1).astype(np.uint8)
    return medians


def fill_values(data: bytes, selected: np.ndarray, fill: str, rng: np.random.Generator,
                regions: np.ndarray | None, window: tuple[int, int], side: int,
                medians: np.ndarray | None = None) -> np.ndarray:
    raw = np.frombuffer(data, dtype=np.uint8)
    if fill == "zero":
        return np.zeros(len(selected), dtype=np.uint8)
    if fill == "local_median":
        return (medians if medians is not None else local_median_grid(data, side, window))[selected]
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
                     window: tuple[int, int], side: int,
                     medians: np.ndarray | None = None, cache=None) -> np.ndarray:
    raw, imap, sums, counts = cache if cache is not None else raster_cache(data, side)
    mask = np.zeros(len(data), dtype=bool)
    mask[selected] = True
    change = selected if mode == "deletion" else np.flatnonzero(~mask)
    values = fill_values(data, change, fill, rng, regions, window, side, medians)
    delta = values.astype(np.int64) - raw[change].astype(np.int64)
    if imap.policy == POLICY_MEAN_POOL:
        pixels = np.searchsorted(imap.ends, change, side="right")
        updates = np.bincount(pixels, weights=delta, minlength=side * side).astype(np.int64)
        updated = sums + updates
    else:
        byte_delta = np.zeros(len(raw), dtype=np.int64)
        byte_delta[change] = delta
        updated = sums + byte_delta[imap.starts]
    return (updated / counts).astype(np.float32).reshape(side, side)


def raster_cache(data: bytes, side: int, imap=None):
    raw = np.frombuffer(data, dtype=np.uint8)
    if imap is None:
        _, imap = encode_interval_binned(data, side=side)
    sums = (np.add.reduceat(raw.astype(np.int64), imap.starts) if imap.policy == POLICY_MEAN_POOL
            else raw[imap.starts].astype(np.int64))
    return raw, imap, sums, imap.ends - imap.starts


def full_fill(raw: np.ndarray, fill: str, rng: np.random.Generator,
              regions: np.ndarray | None, medians: np.ndarray) -> np.ndarray:
    """Draw one replacement byte per source position for a paired pass seed."""
    if fill == "zero":
        return np.zeros_like(raw)
    if fill == "local_median":
        return medians
    if fill == "structure_conditioned_resampling":
        result = np.empty_like(raw)
        labels = regions if regions is not None else np.zeros(len(raw), dtype=np.int16)
        for rid in np.unique(labels):
            positions = np.flatnonzero(labels == rid)
            result[positions] = raw[rng.choice(positions, size=len(positions), replace=True)]
        return result
    raise ValueError(f"unsupported fill: {fill}")


def raster_delta(cache, positions: np.ndarray, delta: np.ndarray, side: int,
                 base_sums: np.ndarray | None = None) -> np.ndarray:
    _, imap, sums, counts = cache
    if base_sums is None:
        base_sums = sums
    if imap.policy == POLICY_MEAN_POOL:
        pixels = np.searchsorted(imap.ends, positions, side="right")
        updates = np.bincount(pixels, weights=delta, minlength=side * side).astype(np.int64)
    else:
        changes = np.zeros(len(cache[0]), dtype=np.int64)
        changes[positions] = delta
        updates = changes[imap.starts]
    return ((base_sums + updates) / counts).astype(np.float32).reshape(side, side)


def replacement_sums(replacements: np.ndarray, cache) -> np.ndarray:
    imap = cache[1]
    return (np.add.reduceat(replacements.astype(np.int64), imap.starts)
            if imap.policy == POLICY_MEAN_POOL else replacements[imap.starts].astype(np.int64))


def selected_pixel_map(cache, selected: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Map selected source bytes to affected pixels once for a position set."""
    imap = cache[1]
    if imap.policy == POLICY_MEAN_POOL:
        return np.searchsorted(imap.ends, selected, side="right"), np.arange(len(selected))
    # Short files repeat one source byte across several pixels; take every pixel that uses a selected byte.
    pixels = np.flatnonzero(np.isin(imap.starts, selected))
    sorter = np.argsort(selected, kind="stable")
    byte_indices = sorter[np.searchsorted(selected, imap.starts[pixels], sorter=sorter)]
    return pixels, byte_indices


def paired_rasters(cache, selected: np.ndarray, replacements: np.ndarray,
                   side: int, fill_sums: np.ndarray,
                   pixel_map: tuple[np.ndarray, np.ndarray] | None = None) -> tuple[np.ndarray, np.ndarray]:
    raw, _, raw_sums, counts = cache
    pixels, byte_indices = pixel_map if pixel_map is not None else selected_pixel_map(cache, selected)
    delta = replacements[selected].astype(np.int64) - raw[selected].astype(np.int64)
    updates = np.bincount(pixels, weights=delta[byte_indices], minlength=side * side).astype(np.int64)
    deletion = ((raw_sums + updates) / counts).astype(np.float32).reshape(side, side)
    keep_only = ((fill_sums - updates) / counts).astype(np.float32).reshape(side, side)
    return deletion, keep_only


def control_offsets_sha256(selected: np.ndarray) -> str:
    """Hash sorted offsets as canonical little-endian signed int64 bytes."""
    ordered = np.sort(np.asarray(selected, dtype=np.int64))
    return hashlib.sha256(ordered.astype("<i8", copy=False).tobytes()).hexdigest()


def verify_control_offsets(row: dict, data: bytes, cam_offsets: np.ndarray,
                           regions: np.ndarray | None = None,
                           entropy: np.ndarray | None = None) -> bool:
    """Regenerate ledger control positions and check their count and digest."""
    if not row["eligible"]:
        raise ValueError("ineligible row has no control offsets")
    generated = control_offsets(row["control"], data, int(row["achieved_bytes"]),
        np.random.default_rng(offset_seed(int(row["checkpoint_seed"]), row["sample_id"],
                                   float(row["budget"]), row["control"], int(row["repeat"]))),
        cam_offsets, regions, entropy)
    return (len(generated) == int(row["control_offsets_n"])
            and control_offsets_sha256(generated) == row["control_offsets_sha256"])


def pair_seed(base: int, sample: str, budget: float, fill: str, control: str, repeat: int) -> int:
    key = f"{base}|{sample}|{budget:.8g}|{fill}|{control}|{repeat}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(key).digest()[:8], "big")


def offset_seed(base: int, sample: str, budget: float, control: str, repeat: int) -> int:
    key = f"{base}|{sample}|{budget:.8g}|{control}|{repeat}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(key).digest()[:8], "big")


def nll(logits: np.ndarray, label: int) -> float:
    maximum = float(np.max(logits))
    return maximum + math.log(float(np.exp(logits - maximum).sum())) - float(logits[label])


def score_batch(model, rasters: np.ndarray, device: str, malicious: int,
                batch_size: int = 512) -> list[tuple[float, float]]:
    import torch
    from psa_train import preprocess_raster
    scores = []
    with torch.inference_mode():
        for start in range(0, len(rasters), batch_size):
            inputs = torch.stack([preprocess_raster(r) for r in rasters[start:start + batch_size]]).to(device)
            with torch.amp.autocast("cuda", enabled=device == "cuda"):
                logits = model(inputs).float().cpu().numpy()
            scores.extend((nll(row, malicious), float(row[malicious])) for row in logits)
    return scores


def prepare_sample(task):
    entries, sample_path, manifest_row, index_row, structure, materialised, side, fills, controls, repeats, window, seed_base, malicious = task
    sid = entries[0]["sample_id"]
    data = sample_path.read_bytes()
    source_sha = hashlib.sha256(data).hexdigest()
    if len(data) != int(index_row["file_size"]) or source_sha != manifest_row["sha256"]:
        raise ValueError(f"source integrity mismatch: {sid}")
    original, imap = encode_interval_binned(data, side=side)
    if raster_sha256(original) != index_row["raster_sha256"] or imap.map_sha256() != index_row["map_sha256"]:
        raise ValueError(f"source/raster mismatch: {sid}")
    if raster_sha256(materialised.reshape(side, side)) != index_row["raster_sha256"]:
        raise ValueError(f"materialised raster mismatch: {sid}")
    regions = region_ids(structure["structure"]["spans"], len(data)) if structure["status"] == "agreement" else None
    entropy = np.argsort(-entropy_scores(data), kind="stable")
    medians = local_median_grid(data, side, window)
    cache = raster_cache(data, side, imap)
    raw = cache[0]
    fixed_fills = {"zero": np.zeros_like(raw), "local_median": medians}
    fixed_sums = {name: replacement_sums(values, cache) for name, values in fixed_fills.items()}
    rows, rasters, targets = [], [], []
    ineligible = 0
    pixel_maps = {}
    def pixels_for(chosen):
        key = chosen.tobytes()
        if key not in pixel_maps:
            pixel_maps[key] = selected_pixel_map(cache, chosen)
        return pixel_maps[key]
    for entry in entries:
        budget = entry["budget"]
        original_nll = nll(np.asarray([entry["benign_logit"], entry["malicious_logit"]]), malicious)
        selected = offsets(budget["intervals"], len(data))
        if len(selected) != budget["achieved_bytes"] or entry["file_size"] != len(data):
            raise ValueError(f"achieved budget mismatch: {sid}")
        selected_map = pixels_for(selected)
        for control in controls:
            for repeat in range(repeats if control.endswith("_20_repeats") else 1):
                eligible = control != "structure_matched_random_20_repeats" or regions is not None
                matched = None
                if eligible:
                    matched = control_offsets(control, data, len(selected),
                        np.random.default_rng(offset_seed(seed_base, sid, budget["requested_fraction"], control, repeat)),
                        selected, regions, entropy)
                    if len(matched) != len(selected):
                        raise AssertionError("control byte budget mismatch")
                    matched_map = pixels_for(matched)
                for fill in fills:
                    result = {"sample_id": sid, "source_sha256": source_sha, "group": entry["group"], "checkpoint_seed": seed_base,
                              "budget": budget["requested_fraction"], "achieved_bytes": len(selected),
                              "fill": fill, "control": control, "repeat": repeat, "eligible": eligible,
                              "structure_status": entry["structure_status"]}
                    if not eligible:
                        result["reason"] = "structure_status_not_agreement"
                        ineligible += 1
                    else:
                        seed = pair_seed(seed_base, sid, budget["requested_fraction"], fill, control, repeat)
                        result.update(pair_seed=seed, control_offsets_sha256=control_offsets_sha256(matched),
                                      control_offsets_n=len(matched))
                        if fill in fixed_fills:
                            replacements, fill_sums = fixed_fills[fill], fixed_sums[fill]
                        else:
                            replacements = full_fill(raw, fill, np.random.default_rng(seed), regions, medians)
                            fill_sums = replacement_sums(replacements, cache)
                        for name, chosen, pixel_map in (("gradcam", selected, selected_map),
                                                        ("control", matched, matched_map)):
                            for mode, raster in zip(("deletion", "keep_only"),
                                                    paired_rasters(cache, chosen, replacements, side, fill_sums,
                                                                   pixel_map)):
                                rasters.append(raster)
                                targets.append((len(rows), name, mode, original_nll))
                    rows.append(result)
    prepared = np.ascontiguousarray(np.stack(rasters)) if rasters else np.empty((0, side, side), dtype=np.float32)
    return rows, prepared, targets, ineligible


def completed_samples(output: Path, expected_rows: dict[str, int]) -> tuple[set[str], dict[str, int]]:
    """Truncate a partial final file; only complete contiguous sample groups resume."""
    complete = set()
    counts = {"samples": 0, "rows": 0, "forward_passes": 0, "structure_ineligible_rows": 0}
    with output.open("rb+") as stream:
        group_start, last_valid_end, sid, group_rows, group_forward, group_ineligible = 0, 0, None, 0, 0, 0
        while line := stream.readline():
            try:
                row = json.loads(line)
                current = row["sample_id"]
            except (ValueError, KeyError):
                break
            if current != sid:
                if sid is not None:
                    if group_rows != expected_rows.get(sid) or sid in complete:
                        break
                    complete.add(sid)
                    counts["samples"] += 1
                    counts["rows"] += group_rows
                    counts["forward_passes"] += group_forward
                    counts["structure_ineligible_rows"] += group_ineligible
                group_start = stream.tell() - len(line)
                sid, group_rows, group_forward, group_ineligible = current, 0, 0, 0
            group_rows += 1
            group_forward += 4 if row["eligible"] else 0
            group_ineligible += not row["eligible"]
            last_valid_end = stream.tell()
        if sid is not None and group_rows == expected_rows.get(sid) and sid not in complete:
            complete.add(sid)
            counts["samples"] += 1
            counts["rows"] += group_rows
            counts["forward_passes"] += group_forward
            counts["structure_ineligible_rows"] += group_ineligible
            group_start = last_valid_end
        stream.truncate(group_start)
    return complete, counts


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
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 1) - 4))
    ap.add_argument("--prefetch", type=int, default=8)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--limit-samples", type=int)
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
    if args.workers < 1 or args.prefetch < 1 or (args.limit_samples is not None and args.limit_samples < 1):
        raise ValueError("workers, prefetch and limit-samples must be positive")
    args.outdir.mkdir(parents=True, exist_ok=args.resume)
    output = args.outdir / "perturb_ledger.jsonl"
    malicious = max(protocol["eligibility"]["labels"])
    grouped = [(sid, list(entries)) for sid, entries in groupby(ledger, key=lambda row: row["sample_id"])]
    if len({sid for sid, _ in grouped}) != len(grouped):
        raise ValueError("Grad-CAM ledger sample IDs must be contiguous")
    if args.limit_samples is not None:
        grouped = grouped[:args.limit_samples]
    expected_rows = {sid: len(entries) * len(fills) * sum(repeats if c.endswith("_20_repeats") else 1 for c in controls)
                     for sid, entries in grouped}
    if args.resume and output.exists():
        complete, counts = completed_samples(output, expected_rows)
    else:
        complete = set()
        counts = {"samples": 0, "rows": 0, "forward_passes": 0, "structure_ineligible_rows": 0}
    def tasks():
        for sid, entries in grouped:
            if sid in complete:
                continue
            yield (entries, args.samples_dir / sid, manifest[sid], index[sid], structures[sid],
                   np.asarray(rasters[int(index[sid]["row"])], dtype=np.float32), side, fills, controls,
                   repeats, window, checkpoint["seed"], malicious)
    started = time.monotonic()
    initial_samples = counts["samples"]
    gpu_wait_seconds = 0.0
    with ProcessPoolExecutor(max_workers=args.workers) as pool, output.open("a" if args.resume else "x", encoding="utf-8") as out:
        task_iter = iter(tasks())
        pending = set()

        def submit_next():
            task = next(task_iter, None)
            if task is not None:
                pending.add(pool.submit(prepare_sample, task))

        for _ in range(args.prefetch):
            submit_next()
        try:
            while pending:
                wait_started = time.monotonic()
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                gpu_wait_seconds += time.monotonic() - wait_started
                future = next(iter(done))
                pending.update(done - {future})
                rows, prepared, targets, ineligible = future.result()
                submit_next()  # CPU preparation continues during this sample's GPU inference.
                for (row_number, target_name, mode, original_nll), (value_nll, malicious_score) in zip(
                        targets, score_batch(model, prepared, device, malicious), strict=True):
                    if mode == "deletion":
                        rows[row_number][f"{target_name}_deletion_delta_nll"] = value_nll - original_nll
                    else:
                        rows[row_number][f"{target_name}_keep_only_malicious_score"] = malicious_score
                out.writelines(json.dumps(row, allow_nan=False, ensure_ascii=True) + "\n" for row in rows)
                out.flush()
                counts["samples"] += 1
                counts["rows"] += len(rows)
                counts["forward_passes"] += len(prepared)
                counts["structure_ineligible_rows"] += ineligible
                elapsed = time.monotonic() - started
                processed = counts["samples"] - initial_samples
                per_sample = elapsed / processed
                remaining = per_sample * (len(grouped) - counts["samples"])
                print(f"samples={counts['samples']}/{len(grouped)} elapsed={elapsed:.1f}s "
                      f"seconds_per_sample={per_sample:.1f} eta={remaining:.1f}s "
                      f"gpu_wait={gpu_wait_seconds:.1f}s", file=sys.stderr, flush=True)
        finally:
            for future in pending:
                if future.cancel():
                    continue
                try:
                    future.result()
                except Exception:
                    pass
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
