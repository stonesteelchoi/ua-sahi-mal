from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np
from PIL import Image


@dataclass(frozen=True)
class PaddedImage:
    image: Image.Image
    original_height: int
    original_width: int
    padded_height: int
    padded_width: int

    def crop_map(self, array: np.ndarray) -> np.ndarray:
        return array[: self.original_height, : self.original_width]


def pad_image_to_multiple(image: Image.Image, multiple: int) -> PaddedImage:
    if multiple < 1:
        raise ValueError("multiple must be positive")

    rgb = np.asarray(image.convert("RGB"))
    height, width = rgb.shape[:2]
    padded_height = ((height + multiple - 1) // multiple) * multiple
    padded_width = ((width + multiple - 1) // multiple) * multiple
    pad_bottom = padded_height - height
    pad_right = padded_width - width
    padded = np.pad(rgb, ((0, pad_bottom), (0, pad_right), (0, 0)), mode="edge")
    return PaddedImage(
        image=Image.fromarray(padded),
        original_height=height,
        original_width=width,
        padded_height=padded_height,
        padded_width=padded_width,
    )


class RoutingUpsampler(Protocol):
    name: str

    def upsample(self, guidance_image: Image.Image, low_map: np.ndarray) -> np.ndarray:
        """Upsample a single-channel map to the guidance image size."""


class BilinearUpsampler:
    name = "bilinear"

    def upsample(self, guidance_image: Image.Image, low_map: np.ndarray) -> np.ndarray:
        width, height = guidance_image.size
        result = cv2.resize(low_map.astype(np.float32), (width, height), interpolation=cv2.INTER_LINEAR)
        return np.nan_to_num(result, nan=0.0, posinf=1.0, neginf=0.0).astype(np.float32)


class AnisotropicJBUUpsampler:
    """Deterministic CPU joint-bilateral upsampling baseline.

    The spatial kernel is elongated along local guidance-image edges and narrow
    across them. This is a research baseline, not the official Upsample Anything
    test-time optimization implementation.
    """

    name = "jbu"

    def __init__(
        self,
        *,
        radius: int = 3,
        sigma_normal: float = 1.0,
        sigma_tangent: float = 2.5,
        sigma_color: float = 0.12,
    ) -> None:
        if radius < 1:
            raise ValueError("JBU radius must be positive")
        if sigma_normal <= 0 or sigma_tangent <= 0 or sigma_color <= 0:
            raise ValueError("JBU sigmas must be positive")
        self.radius = radius
        self.sigma_normal = float(sigma_normal)
        self.sigma_tangent = float(sigma_tangent)
        self.sigma_color = float(sigma_color)

    def upsample(self, guidance_image: Image.Image, low_map: np.ndarray) -> np.ndarray:
        width, height = guidance_image.size
        source = np.asarray(low_map, dtype=np.float32)
        if source.ndim != 2 or source.shape[0] < 1 or source.shape[1] < 1:
            raise ValueError("JBU low_map must be a non-empty 2D array")
        if not np.isfinite(source).all():
            raise ValueError("JBU low_map must contain only finite values")
        initial = cv2.resize(source, (width, height), interpolation=cv2.INTER_LINEAR)
        guidance = np.asarray(guidance_image.convert("RGB"), dtype=np.float32) / 255.0
        gray = cv2.cvtColor(guidance, cv2.COLOR_RGB2GRAY)
        gradient_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        gradient_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        magnitude = np.sqrt(gradient_x * gradient_x + gradient_y * gradient_y)
        normal_x = np.divide(
            gradient_x,
            magnitude,
            out=np.ones_like(gradient_x),
            where=magnitude > 1e-6,
        )
        normal_y = np.divide(
            gradient_y,
            magnitude,
            out=np.zeros_like(gradient_y),
            where=magnitude > 1e-6,
        )

        radius = self.radius
        padded_map = np.pad(initial, radius, mode="edge")
        padded_guidance = np.pad(guidance, ((radius, radius), (radius, radius), (0, 0)), mode="edge")
        weighted_sum = np.zeros_like(initial, dtype=np.float32)
        weight_sum = np.zeros_like(initial, dtype=np.float32)
        for offset_y in range(-radius, radius + 1):
            for offset_x in range(-radius, radius + 1):
                map_neighbor = padded_map[
                    radius + offset_y : radius + offset_y + height,
                    radius + offset_x : radius + offset_x + width,
                ]
                guide_neighbor = padded_guidance[
                    radius + offset_y : radius + offset_y + height,
                    radius + offset_x : radius + offset_x + width,
                ]
                normal_distance = offset_x * normal_x + offset_y * normal_y
                tangent_distance = -offset_x * normal_y + offset_y * normal_x
                spatial_weight = np.exp(
                    -0.5
                    * (
                        (normal_distance / self.sigma_normal) ** 2
                        + (tangent_distance / self.sigma_tangent) ** 2
                    )
                )
                color_distance = np.sum((guide_neighbor - guidance) ** 2, axis=2)
                range_weight = np.exp(
                    -0.5 * color_distance / (self.sigma_color * self.sigma_color)
                )
                weight = (spatial_weight * range_weight).astype(np.float32)
                weighted_sum += weight * map_neighbor
                weight_sum += weight
        result = np.divide(
            weighted_sum,
            weight_sum,
            out=initial.astype(np.float32, copy=True),
            where=weight_sum > 1e-8,
        )
        return np.nan_to_num(result, nan=0.0, posinf=1.0, neginf=0.0).astype(np.float32)


class OfficialUPAUpsampler:
    name = "upa"

    def __init__(self, repo_root: Path, device: str) -> None:
        if not device.startswith("cuda"):
            raise RuntimeError("the official Upsample Anything implementation requires CUDA")

        try:
            import torch
        except ImportError as exc:
            raise RuntimeError("PyTorch is required for Upsample Anything") from exc

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is not available to PyTorch")

        source_dir = repo_root / "external" / "upsample-anything" / "src"
        source_file = source_dir / "upsample_anything.py"
        if not source_file.is_file():
            raise RuntimeError(
                "Upsample Anything submodule is missing; run git submodule update --init --recursive"
            )

        source_text = str(source_dir)
        if source_text not in sys.path:
            sys.path.insert(0, source_text)
        module = importlib.import_module("upsample_anything")
        self._upa = module.UPA

    def upsample(self, guidance_image: Image.Image, low_map: np.ndarray) -> np.ndarray:
        import torch

        width, height = guidance_image.size
        low_height, low_width = low_map.shape
        if height % low_height or width % low_width:
            raise ValueError("UPA requires integer and equal spatial scale factors")
        if height // low_height != width // low_width:
            raise ValueError("UPA requires the same integer scale factor for height and width")

        low_tensor = torch.from_numpy(low_map.astype(np.float32)).unsqueeze(0).unsqueeze(0).cuda()
        high_tensor = self._upa(guidance_image, low_tensor)
        result = high_tensor.detach().float().cpu().numpy()[0, 0]
        return np.nan_to_num(result, nan=0.0, posinf=1.0, neginf=0.0).astype(np.float32)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def upa_source_available(repo_root: Path | None = None) -> bool:
    root = repo_root or repository_root()
    return (root / "external" / "upsample-anything" / "src" / "upsample_anything.py").is_file()


def build_upsampler(choice: str, device: str, repo_root: Path | None = None) -> RoutingUpsampler:
    root = repo_root or repository_root()
    if choice == "bilinear":
        return BilinearUpsampler()
    if choice == "jbu":
        return AnisotropicJBUUpsampler()
    if choice == "upa":
        return OfficialUPAUpsampler(root, device)
    if choice != "auto":
        raise ValueError(f"unsupported upsampler: {choice}")

    try:
        import torch

        if device.startswith("cuda") and torch.cuda.is_available() and upa_source_available(root):
            return OfficialUPAUpsampler(root, device)
    except (ImportError, RuntimeError):
        pass
    return BilinearUpsampler()
