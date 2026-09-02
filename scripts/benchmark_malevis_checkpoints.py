from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import time
from pathlib import Path
from typing import Any

from PIL import Image

from ua_sahi_mal.malevis_experiment import (
    SCHEMA,
    MaleVisExperimentError,
    _benchmark_model,
    _build_model,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark trained MaleVis seed-42 checkpoints sequentially in one process."
    )
    parser.add_argument("--run-dir", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cpu")
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _benchmark_one(run_dir: Path, *, device_name: str) -> dict[str, Any]:
    try:
        import torch
        import torchvision
        from torch.utils.data import DataLoader, Dataset
        from torchvision import transforms
    except ImportError as exc:
        raise MaleVisExperimentError("PyTorch and torchvision are required") from exc

    summary_path = run_dir / "summary.json"
    summary = _load_json(summary_path)
    if summary.get("schema") != SCHEMA:
        raise MaleVisExperimentError(f"unexpected summary schema: {summary_path}")
    if int(summary["seed"]) != 42:
        raise MaleVisExperimentError("isolated timing is restricted to the designated seed 42")
    checkpoint_path = Path(summary["model"]["checkpoint"])
    if _sha256(checkpoint_path) != summary["model"]["checkpoint_sha256"]:
        raise MaleVisExperimentError(f"checkpoint hash mismatch: {checkpoint_path}")
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    if checkpoint.get("schema") != SCHEMA:
        raise MaleVisExperimentError(f"unexpected checkpoint schema: {checkpoint_path}")
    if checkpoint["class_names"] != summary["dataset"]["class_names"]:
        raise MaleVisExperimentError("checkpoint and summary class order differ")

    settings = checkpoint["settings"]
    image_size = int(checkpoint["image_size"])
    torch.set_num_threads(int(settings["torch_threads"]))
    device = torch.device(device_name)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise MaleVisExperimentError(f"requested CUDA device is unavailable: {device}")
    model, _ = _build_model(
        num_classes=len(checkpoint["class_names"]),
        embedding_dim=int(settings["embedding_dim"]),
        dropout=float(settings["dropout"]),
        torch=torch,
    )
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    model.to(device)

    transform = transforms.Compose(
        [
            transforms.Resize((image_size, image_size), antialias=True),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=(0.485, 0.456, 0.406),
                std=(0.229, 0.224, 0.225),
            ),
        ]
    )
    manifest_path = Path(summary["dataset"]["paired_manifest"])
    manifest = _load_json(manifest_path)
    if _sha256(manifest_path) != summary["dataset"]["paired_manifest_sha256"]:
        raise MaleVisExperimentError(f"paired manifest hash mismatch: {manifest_path}")
    root = Path(summary["dataset"]["root"])
    class_to_index = {
        class_name: index for index, class_name in enumerate(checkpoint["class_names"])
    }
    samples = [
        (
            root / row["relative_paths"][str(image_size)],
            class_to_index[row["class_name"]],
        )
        for row in manifest["samples"]
        if row["split"] == "val"
    ]
    if len(samples) != int(summary["dataset"]["deduplicated_val_as_final_test_images"]):
        raise MaleVisExperimentError("benchmark sample count differs from the final-test protocol")

    class ManifestDataset(Dataset):
        def __len__(self) -> int:
            return len(samples)

        def __getitem__(self, index: int):
            path, target = samples[index]
            with Image.open(path) as opened:
                image = opened.convert("RGB")
            return transform(image), target

    loader = DataLoader(
        ManifestDataset(),
        batch_size=int(settings["batch_size"]),
        shuffle=False,
        num_workers=0,
        pin_memory=device.type == "cuda",
    )
    modes = {}
    for mode, passes in (
        ("deterministic", 1),
        ("mc_dropout", int(settings["mc_dropout_passes"])),
    ):
        modes[mode] = _benchmark_model(
            model,
            loader,
            torch=torch,
            device=device,
            mc_passes=passes,
            warmup_batches=int(settings["timing_warmup_batches"]),
            repeats=int(settings["timing_repeats"]),
        )
    return {
        "image_size": image_size,
        "seed": int(summary["seed"]),
        "run_dir": str(run_dir.resolve()),
        "checkpoint_sha256": summary["model"]["checkpoint_sha256"],
        "dataset_fingerprint_sha256": summary["dataset"]["dataset_fingerprint_sha256"],
        "paired_manifest_sha256": summary["dataset"]["paired_manifest_sha256"],
        "device": str(device),
        "torch": torch.__version__,
        "torchvision": torchvision.__version__,
        "torch_threads": torch.get_num_threads(),
        "modes": modes,
    }


def main() -> int:
    args = parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite existing output: {args.output}")
    if len(args.run_dir) != 2:
        raise SystemExit("provide exactly two seed-42 run directories (224 and 300)")
    started = time.perf_counter()
    try:
        runs = [_benchmark_one(path.resolve(), device_name=args.device) for path in args.run_dir]
    except (MaleVisExperimentError, OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    if {run["image_size"] for run in runs} != {224, 300}:
        raise SystemExit("run directories must contain one 224 and one 300 checkpoint")
    result = {
        "schema": "ua-sahi-mal-malevis-isolated-timing-v1",
        "protocol": (
            "Seed-42 checkpoints are benchmarked sequentially in one fresh process after all "
            "training jobs finish; no other project training job may run concurrently."
        ),
        "host": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "logical_cpu_count": os.cpu_count(),
        },
        "runs": sorted(runs, key=lambda item: item["image_size"]),
        "wall_time_seconds": time.perf_counter() - started,
        "interpretation": (
            "Per-image p50/p95 divides batch model-forward time after loading by batch size. "
            "Throughput includes data loading and transfer. Neither is single-request end-to-end latency."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
