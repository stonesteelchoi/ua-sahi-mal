"""Reproducibility records for the static DECODE-to-YOLO pipeline."""

from __future__ import annotations

import importlib.metadata
import json
import platform
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from ua_sahi_mal.checkpoint import inspect_checkpoint
from ua_sahi_mal.decode_adapter import annotation_hashes
from ua_sahi_mal.encoding import sha256_file


def _package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for distribution in ("ultralytics", "sahi", "torch", "numpy", "opencv-python", "Pillow"):
        try:
            versions[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[distribution] = "not-installed"
    return versions


def _git_state(repo_root: Path) -> dict[str, Any]:
    if not (repo_root / ".git").exists():
        return {"commit": None, "dirty": None, "reason": ".git metadata not present"}
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_root,
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout.strip()
        )
        return {"commit": commit, "dirty": dirty}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"commit": None, "dirty": None, "reason": str(exc)}


def _accelerator_state() -> dict[str, Any]:
    result: dict[str, Any] = {"cuda_version": None, "gpu_name": None, "cuda_available": False}
    try:
        import torch

        result["cuda_version"] = torch.version.cuda
        result["cuda_available"] = bool(torch.cuda.is_available())
        if torch.cuda.is_available():
            result["gpu_name"] = torch.cuda.get_device_name(0)
    except ImportError:
        result["reason"] = "torch not installed"
    return result


def create_pipeline_record(
    *,
    repo_root: Path,
    base_model: Path,
    annotation_paths: Sequence[Path],
    split_map: Path,
    manifest: Path,
    dataset_revision: str,
    teacher_model: str,
    annotation_version: str,
    class_policy: str,
    epochs: int,
    batch_size: int,
    image_size: int,
    device: str,
    seed: int,
    best_checkpoint: Path | None = None,
    expected_classes: Sequence[str] | None = None,
) -> dict[str, Any]:
    for path, label in (
        (base_model, "base model"),
        (split_map, "split map"),
        (manifest, "manifest"),
    ):
        if not path.is_file():
            raise ValueError(f"{label} does not exist: {path}")
    record: dict[str, Any] = {
        "schema": "ua-sahi-mal-pipeline-inputs-v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_revision": dataset_revision,
        "teacher_model": teacher_model,
        "annotation_version": annotation_version,
        "class_policy": class_policy,
        "inputs": {
            "base_model": {
                "path": str(base_model.resolve()),
                "sha256": sha256_file(base_model.resolve()),
            },
            "annotations": annotation_hashes(annotation_paths),
            "split_map": {
                "name": split_map.name,
                "sha256": sha256_file(split_map.resolve()),
            },
            "manifest": {
                "name": manifest.name,
                "sha256": sha256_file(manifest.resolve()),
            },
        },
        "training": {
            "epochs": epochs,
            "batch_size": batch_size,
            "image_size": image_size,
            "device": device,
            "seed": seed,
            "deterministic": True,
        },
        "runtime": {
            "python": sys.version,
            "platform": platform.platform(),
            "packages": _package_versions(),
            "accelerator": _accelerator_state(),
            "git": _git_state(repo_root.resolve()),
        },
        "best_checkpoint": None,
    }
    if best_checkpoint is not None:
        metadata = inspect_checkpoint(
            best_checkpoint,
            expected_classes=expected_classes,
            dataset_revision=dataset_revision,
        )
        record["best_checkpoint"] = asdict(metadata)
    return record


def write_pipeline_record(record: dict[str, Any], output: Path) -> None:
    output = output.resolve()
    if output.exists():
        raise ValueError(f"refusing to overwrite pipeline record: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
