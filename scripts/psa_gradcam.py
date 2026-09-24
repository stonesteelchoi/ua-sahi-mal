"""Frozen PSA Grad-CAM ledger. Reads derived test rasters and the prior P2 structure ledger.

No source PE is opened here. Run only with the designated checkpoint and its SHA-256;
the CLI deliberately has no diagnostic subset or alternate target option.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ua_sahi_mal.kisa_xai.representation import (  # noqa: E402
    build_interval_map, raster_sha256, select_source_bytes_by_budget,
)
from ua_sahi_mal.kisa_xai.structure import RegionSpan, StructureMap, structure_cam_mass  # noqa: E402

FROZEN = ROOT / "paper/v5-kisa-xai/protocol/PSA_XAI_V1_1_FROZEN.yaml"


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_protocol(path: Path) -> dict:
    protocol = yaml.safe_load(path.read_text(encoding="utf-8"))
    xai, rep = protocol["xai"], protocol["representation"]
    if (protocol["protocol"]["status"] != "frozen" or xai["method"] != "Grad-CAM"
            or xai["primary_target"] != "malicious_logit_on_all_malicious_test_files"
            or rep["selection_budget_denominator"] != "unique_source_bytes"
            or xai["interval_overshoot_policy"] != "record_requested_and_achieved_then_match_controls_to_achieved_bytes"
            or xai["empty_positive_cam_policy"] != "retain_and_flag"
            or xai["upsampling"] != {"method": "bilinear", "align_corners": False}):
        raise ValueError("unsupported frozen Grad-CAM settings")
    return protocol


def rows_for_test(index: Path, duplicate_groups: Path, split_manifest: Path | None,
                  malicious_label: int) -> list[dict]:
    seen_hashes, dropped = set(), set()
    with duplicate_groups.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row["raster_sha256"] in seen_hashes:
                dropped.add(row["sample_id"])
            seen_hashes.add(row["raster_sha256"])
    assignments = None
    if split_manifest is not None:
        assignments = {}
        with split_manifest.open(newline="", encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                sid = row["sample_id"]
                if sid in assignments or row["split"] not in ("train", "val", "test"):
                    raise ValueError("invalid split manifest")
                assignments[sid] = (row["split"], row["label"], row["group"])
    result, found = [], set()
    with index.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            sid = row["sample_id"]
            if assignments is not None:
                if sid not in assignments:
                    continue
                found.add(sid)
                split, label, group = assignments[sid]
                if (row["label"], row["group"]) != (label, group):
                    raise ValueError(f"manifest/index mismatch for {sid}")
            else:
                split = row["split"]
            if split == "test" and sid not in dropped and int(row["label"]) == malicious_label:
                result.append(row)
    if assignments is not None and found != assignments.keys():
        raise ValueError("split manifest contains IDs absent from raster index")
    result.sort(key=lambda row: int(row["sample_id"]))
    if len({row["sample_id"] for row in result}) != len(result):
        raise ValueError("duplicate test sample ID")
    return result


def structure_records(path: Path, wanted: set[str]) -> dict[str, dict]:
    records = {}
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            sid = record["sample_id"]
            if sid in wanted:
                if sid in records:
                    raise ValueError(f"duplicate structure row {sid}")
                records[sid] = record
    if records.keys() != wanted:
        raise ValueError("structure ledger does not cover selected test IDs")
    return records


def restored_structure(record: dict, file_size: int) -> StructureMap | None:
    if not record.get("structure_attribution_available", False):
        return None
    data = record["structure"]
    structure = StructureMap(data["file_size"], tuple(RegionSpan(**s) for s in data["spans"]),
                             tuple(data["warnings"]))
    structure.validate()
    if structure.file_size != file_size:
        raise ValueError("structure/index file size mismatch")
    return structure


def gradcam(model, layer, image, target_index: int, shape: tuple[int, int], upsampling: dict):
    """Validated forward/full-backward hook method from kisa_xai_gradcam_smoke.py."""
    import torch
    import torch.nn.functional as F

    acts, grads = {}, {}
    forward = layer.register_forward_hook(lambda _m, _i, out: acts.__setitem__("a", out))
    backward = layer.register_full_backward_hook(lambda _m, _gi, go: grads.__setitem__("g", go[0]))
    try:
        model.zero_grad(set_to_none=True)
        logits = model(image)
        logits[:, target_index].sum().backward()
    finally:
        forward.remove()
        backward.remove()
    weight = grads["g"].mean(dim=(2, 3), keepdim=True)
    native = F.relu((weight * acts["a"]).sum(dim=1, keepdim=True))
    aligned = F.interpolate(native, size=shape, mode=upsampling["method"],
                            align_corners=upsampling["align_corners"])[0, 0]
    scores = aligned.detach().cpu().numpy()
    if not np.isfinite(scores).all():
        raise ValueError("nonfinite Grad-CAM")
    scores = scores / (scores.max() + 1e-12)
    return logits.detach().cpu().numpy()[0].tolist(), scores


def ledger_rows(sample_id: str, row: dict, record: dict, logits: list[float], scores: np.ndarray,
                structure: StructureMap | None, protocol: dict):
    rep, xai = protocol["representation"], protocol["xai"]
    side = rep["shape"][1]
    imap = build_interval_map(int(row["file_size"]), side=side)
    if imap.policy not in (rep["long_file_policy"], rep["short_file_policy"]):
        raise ValueError("interval representation policy mismatch")
    masses = structure_cam_mass(scores, imap, structure) if structure is not None else None
    malicious_label = max(protocol["eligibility"]["labels"])
    benign_label = min(protocol["eligibility"]["labels"])
    for budget in xai["budgets"]:
        selection = select_source_bytes_by_budget(scores, imap, float(budget))
        yield {
            "sample_id": sample_id, "group": row["group"], "raster_row": int(row["row"]),
            "file_size": imap.file_size, "representation_policy": imap.policy,
            "malicious_logit": float(logits[malicious_label]), "benign_logit": float(logits[benign_label]),
            "predicted_label": int(np.argmax(logits)),
            "budget": selection.to_dict(),
            "empty_positive_cam_policy": xai["empty_positive_cam_policy"] if selection.cam_empty else None,
            "structure_attribution_available": structure is not None,
            "structure_attribution_reason": record.get("structure_attribution_reason"),
            "structure_cam_mass": masses,
            "structure_status": record["status"],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--checkpoint-sha256", required=True)
    parser.add_argument("--rasters-dir", type=Path, required=True)
    parser.add_argument("--structure-ledger", type=Path, required=True)
    parser.add_argument("--structure-ledger-sha256", required=True)
    parser.add_argument("--split-manifest", type=Path)
    parser.add_argument("--split-manifest-sha256")
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--device", default="auto")
    args = parser.parse_args()
    if (args.split_manifest is None) != (args.split_manifest_sha256 is None):
        parser.error("--split-manifest and its SHA-256 must be supplied together")
    protocol = load_protocol(FROZEN)
    expected = {args.checkpoint: args.checkpoint_sha256.lower(),
                args.structure_ledger: args.structure_ledger_sha256.lower(),
                args.rasters_dir / "raster_index.csv": protocol["representation"]["materialised"]["raster_index_sha256"],
                args.rasters_dir / "rasters_meta.json": protocol["representation"]["materialised"]["rasters_meta_sha256"]}
    if args.split_manifest is not None:
        expected[args.split_manifest] = args.split_manifest_sha256.lower()
    for path, digest in expected.items():
        if sha256(path) != digest:
            raise ValueError(f"SHA-256 mismatch: {path}")
    import torch
    from psa_train import build_model, preprocess_raster

    device = ("cuda" if torch.cuda.is_available() else "cpu") if args.device == "auto" else args.device
    side = protocol["representation"]["shape"][1]
    if protocol["representation"]["shape"] != [1, side, side] or protocol["model"]["primary"] != "resnet18":
        raise ValueError("unsupported model or raster shape")
    model = build_model("random", device)
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    if (checkpoint["arch"] != protocol["model"]["primary"] or checkpoint["input"] != [1, side, side]
            or checkpoint["init"] != protocol["model"]["initialization"]
            or checkpoint["seed"] not in protocol["model"]["seeds"]):
        raise ValueError("checkpoint metadata disagrees with frozen model")
    model.load_state_dict(checkpoint["model"])
    model = model.to(device).eval()
    layer = model
    for part in protocol["xai"]["target_layer"].split("."):
        layer = layer[int(part)] if part.isdigit() else getattr(layer, part)
    malicious_label = max(protocol["eligibility"]["labels"])
    rows = rows_for_test(args.rasters_dir / "raster_index.csv",
                         args.rasters_dir / "raster_duplicate_groups.csv", args.split_manifest, malicious_label)
    if args.split_manifest is None and len(rows) != protocol["statistics"]["internal_test_malicious_n"]:
        raise ValueError("main malignant test count disagrees with frozen YAML")
    structures = structure_records(args.structure_ledger, {r["sample_id"] for r in rows})
    rasters = np.load(args.rasters_dir / protocol["representation"]["materialised"]["file"], mmap_mode="r")
    if rasters.ndim != 2 or rasters.shape[1] != side * side:
        raise ValueError("raster array shape mismatch")
    args.outdir.mkdir(parents=True, exist_ok=False)
    counts = {"samples": 0, "rows": 0, "empty_positive_cam_samples": 0, "structure_unattributable_samples": 0}
    with (args.outdir / "gradcam_ledger.jsonl").open("x", encoding="utf-8") as stream:
        for row in rows:
            sid = row["sample_id"]
            record = structures[sid]
            if record["split"] != "test":
                raise ValueError(f"structure/index mismatch for {sid}")
            structure = restored_structure(record, int(row["file_size"]))
            raster = np.asarray(rasters[int(row["row"])], dtype=np.float32).reshape(side, side)
            if raster_sha256(raster) != row["raster_sha256"]:
                raise ValueError(f"raster SHA-256 mismatch for {sid}")
            if build_interval_map(int(row["file_size"]), side=side).map_sha256() != row["map_sha256"]:
                raise ValueError(f"interval map SHA-256 mismatch for {sid}")
            image = preprocess_raster(raster).unsqueeze(0).to(device)
            logits, scores = gradcam(model, layer, image, malicious_label, (side, side), protocol["xai"]["upsampling"])
            sample_rows = list(ledger_rows(sid, row, record, logits, scores, structure, protocol))
            counts["samples"] += 1
            counts["rows"] += len(sample_rows)
            counts["empty_positive_cam_samples"] += int(sample_rows[0]["budget"]["cam_empty"])
            counts["structure_unattributable_samples"] += int(structure is None)
            for entry in sample_rows:
                stream.write(json.dumps(entry, allow_nan=False, ensure_ascii=True) + "\n")
            stream.flush()
    summary = {"protocol_sha256": sha256(FROZEN), "inputs": {str(p): h for p, h in expected.items()},
               "checkpoint_seed": checkpoint.get("seed"), "target_layer": protocol["xai"]["target_layer"],
               "device": device, "counts": counts, "ledger_sha256": sha256(args.outdir / "gradcam_ledger.jsonl")}
    (args.outdir / "gradcam_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
