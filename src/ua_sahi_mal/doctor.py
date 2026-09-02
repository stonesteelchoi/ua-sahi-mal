from __future__ import annotations

import importlib.metadata
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict

import numpy as np
from PIL import Image

from ua_sahi_mal.upsampling import BilinearUpsampler, repository_root, upa_source_available


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "missing"


def _git_head(path: Path) -> str:
    if not path.is_dir():
        return "missing"
    completed = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def collect_versions() -> Dict[str, str]:
    root = repository_root()
    source_checkout = (root / ".gitmodules").is_file()
    return {
        "ua_sahi_mal": _package_version("ua-sahi-mal"),
        "sahi": _package_version("sahi"),
        "ultralytics": _package_version("ultralytics"),
        "torch": _package_version("torch"),
        "torchvision": _package_version("torchvision"),
        "sahi_commit": _git_head(root / "external" / "sahi") if source_checkout else "not-applicable",
        "upa_commit": (
            _git_head(root / "external" / "upsample-anything")
            if source_checkout
            else "not-applicable"
        ),
    }


def run_doctor(skip_upsample_smoke: bool = False) -> Dict[str, object]:
    try:
        import torch

        cuda_available = torch.cuda.is_available()
        cuda_name = torch.cuda.get_device_name(0) if cuda_available else None
        cuda_runtime = torch.version.cuda
    except ImportError:
        cuda_available = False
        cuda_name = None
        cuda_runtime = None

    smoke_ok = None
    if not skip_upsample_smoke:
        guide = Image.fromarray(np.zeros((32, 48, 3), dtype=np.uint8))
        low_map = np.arange(24, dtype=np.float32).reshape(4, 6)
        smoke = BilinearUpsampler().upsample(guide, low_map)
        smoke_ok = smoke.shape == (32, 48) and bool(np.isfinite(smoke).all())

    root = repository_root()
    report: Dict[str, object] = {
        "python": sys.version.split()[0],
        "source_checkout": (root / ".gitmodules").is_file(),
        "versions": collect_versions(),
        "cuda_available": cuda_available,
        "cuda_device": cuda_name,
        "cuda_runtime": cuda_runtime,
        "upa_source_available": upa_source_available(),
        "bilinear_smoke_ok": smoke_ok,
    }
    return report


def doctor_issues(report: Dict[str, object]) -> tuple[str, ...]:
    """Return strict environment failures without hiding missing dependencies."""

    versions = report.get("versions", {})
    issues: list[str] = []
    if isinstance(versions, dict):
        for package in ("ua_sahi_mal", "sahi", "ultralytics", "torch", "torchvision"):
            if versions.get(package) in {None, "missing", "unknown"}:
                issues.append(f"required package is unavailable: {package}")
        if report.get("source_checkout"):
            for submodule in ("sahi_commit", "upa_commit"):
                if versions.get(submodule) in {None, "missing", "unknown"}:
                    issues.append(f"submodule is unavailable: {submodule}")
    if report.get("bilinear_smoke_ok") is False:
        issues.append("bilinear upsampling smoke failed")
    return tuple(issues)


def print_doctor(skip_upsample_smoke: bool = False) -> tuple[str, ...]:
    report = run_doctor(skip_upsample_smoke)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return doctor_issues(report)
