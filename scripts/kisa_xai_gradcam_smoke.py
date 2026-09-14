"""KISA-XAI-v5 Grad-CAM smoke: verify the `xai` extras on CPU or CUDA with synthetic input.

Runs `grad-cam` on a randomly initialised 1-channel ResNet-18 (2 classes) with a
synthetic 2x1x224x224 batch, compares the library CAM with a plain forward/backward
hook Grad-CAM (bilinear upsampling, ``align_corners=False``), and records device,
versions, timings, peak VRAM and the empty-positive-CAM flag. No sample data is
read; this is an environment check, not a KISA-XAI-v5 result.

Usage::

    python scripts/kisa_xai_gradcam_smoke.py --out runs/kisa-xai-env-<tag>/gradcam_smoke.json
    python scripts/kisa_xai_gradcam_smoke.py --device cpu --seed 43
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=None, help="JSON report path (default: print only)")
    parser.add_argument("--seed", type=int, default=43, help="torch/numpy seed (42 reproduces an empty positive CAM)")
    parser.add_argument("--device", default="auto", help="auto | cpu | cuda | cuda:N")
    parser.add_argument("--batch", type=int, default=2)
    args = parser.parse_args()

    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    import torchvision

    try:
        import pytorch_grad_cam
        from pytorch_grad_cam import GradCAM
        from pytorch_grad_cam.utils.model_targets import ClassifierOutputTarget
    except ImportError as exc:  # pragma: no cover - environment-dependent
        print(f"grad-cam is not installed ({exc}). Install the extras: pip install -e '.[dev,xai]'", file=sys.stderr)
        return 2
    import cv2
    import scipy
    import sklearn
    from scipy.stats import spearmanr

    device = ("cuda" if torch.cuda.is_available() else "cpu") if args.device == "auto" else args.device
    if device.startswith("cuda") and not torch.cuda.is_available():
        print("CUDA requested but torch.cuda.is_available() is False", file=sys.stderr)
        return 3

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    model = torchvision.models.resnet18(weights=None, num_classes=2)
    model.conv1 = nn.Conv2d(1, 64, kernel_size=7, stride=2, padding=3, bias=False)
    model = model.to(device)
    model.train()  # BN uses batch statistics; random-init eval-mode BN can saturate (smoke only)
    x = torch.rand(args.batch, 1, 224, 224, device=device)  # synthetic, not malware-derived

    if device.startswith("cuda"):
        torch.cuda.reset_peak_memory_stats(device)
        torch.cuda.synchronize(device)
    t0 = time.perf_counter()
    cam = GradCAM(model=model, target_layers=[model.layer4[-1]])
    lib = cam(input_tensor=x, targets=[ClassifierOutputTarget(1) for _ in range(x.shape[0])])
    if device.startswith("cuda"):
        torch.cuda.synchronize(device)
    lib_seconds = time.perf_counter() - t0

    acts: dict[str, torch.Tensor] = {}
    grads: dict[str, torch.Tensor] = {}
    h1 = model.layer4[-1].register_forward_hook(lambda m, i, o: acts.__setitem__("a", o))
    h2 = model.layer4[-1].register_full_backward_hook(lambda m, gi, go: grads.__setitem__("g", go[0]))
    model.zero_grad()
    out = model(x)
    out[:, 1].sum().backward()
    h1.remove()
    h2.remove()
    w = grads["g"].mean(dim=(2, 3), keepdim=True)
    native = F.relu((w * acts["a"]).sum(dim=1, keepdim=True))
    native = F.interpolate(native, size=(224, 224), mode="bilinear", align_corners=False)[:, 0]
    native = native / (native.amax(dim=(1, 2), keepdim=True) + 1e-12)
    native_np = native.detach().cpu().numpy()

    rho = [
        None if lib[i].max() <= 0 else float(spearmanr(lib[i].ravel(), native_np[i].ravel()).statistic)
        for i in range(lib.shape[0])
    ]
    report = {
        "check": "kisa_xai_gradcam_smoke",
        "device": device,
        "device_name": torch.cuda.get_device_name(device) if device.startswith("cuda") else platform.processor(),
        "seed": args.seed,
        "python": platform.python_version(),
        "torch": torch.__version__,
        "torchvision": torchvision.__version__,
        "cuda_runtime": torch.version.cuda,
        "grad_cam": getattr(pytorch_grad_cam, "__version__", "unknown"),
        "scikit_learn": sklearn.__version__,
        "scipy": scipy.__version__,
        "cv2": cv2.__version__,
        "target_layer_module_path": "layer4.1",
        "feature_map_shape": list(acts["a"].shape),
        "cam_shape": list(lib.shape),
        "cam_finite": bool(np.isfinite(lib).all()),
        "cam_max": float(lib.max()),
        "empty_positive_cam_any": bool((lib.max(axis=(1, 2)) <= 0).any()),
        "spearman_lib_vs_native_hook": rho,
        "library_cam_seconds": round(lib_seconds, 4),
        "peak_vram_mib": (
            round(torch.cuda.max_memory_allocated(device) / 2**20, 1) if device.startswith("cuda") else None
        ),
        "note": "synthetic random-weight smoke: import, device, shapes and library/native agreement only",
    }
    text = json.dumps(report, indent=2)
    print(text)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    ok = report["cam_finite"] and (report["empty_positive_cam_any"] or all(r is not None and r > 0.99 for r in rho))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
