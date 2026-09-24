"""Verify measured batch capacity and the exact Grad-CAM module path.

This check uses only saved training metadata, a hash-pinned local checkpoint, and a
synthetic tensor.  It never opens a PSA source executable or raster.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import torch
from psa_train import build_model

EXPECTED_CHECKPOINTS = {
    "seed42_imagenet_bs512": "291af0bd0b2133f3c501fe3efdae0f5503b6de7d4e095a5fc2b1c27a7561f48f",
    "seed43_imagenet_bs512": "4156f2b8bf8c7995c8d62e4132102b28430d9fc69de49b293ec561af68bcaf56",
    "seed44_imagenet_bs512": "62c0d8b002586676d61c7488099e362b4c15777a9406424c324c1f4fbec5639c",
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, required=True)
    parser.add_argument("--pilot-path", type=Path, help="pilot_batch_size.json when stored outside --runs-dir")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--target-layer", default="layer4.1")
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(f"refusing to overwrite {args.out}")

    pilot_path = args.pilot_path or args.runs_dir / "pilot_batch_size.json"
    pilot = load_json(pilot_path)
    if pilot.get("recommended_batch_size") != 512 or pilot.get("device") != "cuda":
        raise ValueError("pilot does not pin CUDA batch size 512")
    total = float(pilot["vram_total_mib"])
    batch_row = next(row for row in pilot["results"] if row["batch_size"] == 512)
    pilot_peak = float(batch_row["peak_vram_mib"])
    if not batch_row["ok"] or pilot_peak >= 0.8 * total:
        raise ValueError("batch 512 does not satisfy the measured under-80% rule")

    training_runs = []
    max_training_peak = 0.0
    for tag, expected_sha in EXPECTED_CHECKPOINTS.items():
        run_dir = args.runs_dir / tag
        checkpoint_path = run_dir / "best.pt"
        summary_path = run_dir / "summary.json"
        actual_sha = digest(checkpoint_path)
        summary = load_json(summary_path)
        if actual_sha != expected_sha or summary.get("checkpoint_sha256") != expected_sha:
            raise ValueError(f"checkpoint identity mismatch for {tag}")
        if summary.get("batch_size") != 512 or summary.get("device") != "cuda":
            raise ValueError(f"unexpected batch/device for {tag}")
        peak = max(float(epoch["peak_vram_mib"]) for epoch in summary["history"])
        max_training_peak = max(max_training_peak, peak)
        training_runs.append({"tag": tag, "peak_vram_mib": peak,
                              "checkpoint_sha256": actual_sha})

    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device != "cuda":
        raise RuntimeError("CUDA is required to pin the executed target-layer path")
    reference = args.runs_dir / "seed42_imagenet_bs512" / "best.pt"
    checkpoint = torch.load(reference, map_location="cpu", weights_only=True)
    model = build_model("random", device)
    model.load_state_dict(checkpoint["model"], strict=True)
    model.eval()
    modules = dict(model.named_modules())
    if args.target_layer not in modules:
        raise ValueError(f"module path not found: {args.target_layer}")
    target = modules[args.target_layer]
    captured: dict[str, torch.Tensor] = {}

    def capture(_module, _inputs, output):
        captured["activation"] = output
        output.register_hook(lambda gradient: captured.__setitem__("gradient", gradient))

    handle = target.register_forward_hook(capture)
    try:
        synthetic = torch.linspace(0.0, 1.0, 224 * 224, device=device).reshape(1, 1, 224, 224)
        logits = model(synthetic)
        model.zero_grad(set_to_none=True)
        logits[:, 1].sum().backward()
    finally:
        handle.remove()
    activation = captured.get("activation")
    gradient = captured.get("gradient")
    expected_shape = [1, 512, 7, 7]
    if activation is None or gradient is None:
        raise RuntimeError("target layer did not expose activations and gradients")
    if list(activation.shape) != expected_shape or list(gradient.shape) != expected_shape:
        raise ValueError("unexpected target-layer tensor shape")
    if list(logits.shape) != [1, 2] or not torch.isfinite(logits).all():
        raise ValueError("unexpected classifier output")

    report = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "source_payload_access": False,
        "batch_size": {
            "recommended": 512,
            "pilot_sha256": digest(pilot_path),
            "vram_total_mib": total,
            "pilot_peak_vram_mib": pilot_peak,
            "pilot_peak_fraction": pilot_peak / total,
            "max_training_peak_vram_mib": max_training_peak,
            "max_training_peak_fraction": max_training_peak / total,
            "runs": training_runs,
            "verified": True,
        },
        "target_layer": {
            "module_path": args.target_layer,
            "module_class": type(target).__name__,
            "activation_shape": list(activation.shape),
            "gradient_shape": list(gradient.shape),
            "classifier_output_shape": list(logits.shape),
            "target_logit_index": 1,
            "device": device,
            "verified": True,
        },
        "protocol_freeze_authorized": False,
        "remaining_blocker": "Full-protocol freeze authorization remains pending after the P2 mapping-policy freeze; see paper/v5-kisa-xai/audit/P2_CENSUS_ADJUDICATION_2026-09-24.md",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as handle_out:
        json.dump(report, handle_out, indent=2, allow_nan=False)
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
