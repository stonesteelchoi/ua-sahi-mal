from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from ua_sahi_mal.upsampling import (
    AnisotropicJBUUpsampler,
    BilinearUpsampler,
    build_upsampler,
    pad_image_to_multiple,
    upa_source_available,
)


def test_padding_uses_edge_values_and_tracks_original_shape() -> None:
    array = np.arange(5 * 7 * 3, dtype=np.uint8).reshape(5, 7, 3)
    padded = pad_image_to_multiple(Image.fromarray(array), multiple=4)
    result = np.asarray(padded.image)

    assert result.shape == (8, 8, 3)
    assert (padded.original_height, padded.original_width) == (5, 7)
    np.testing.assert_array_equal(result[:5, :7], array)
    np.testing.assert_array_equal(result[5:, 7], np.repeat(array[4:5, 6], 3, axis=0))


def test_bilinear_upsampler_restores_guidance_shape() -> None:
    guide = Image.new("RGB", (48, 32))
    low_map = np.arange(24, dtype=np.float32).reshape(4, 6)

    result = BilinearUpsampler().upsample(guide, low_map)

    assert result.shape == (32, 48)
    assert result.dtype == np.float32
    assert np.isfinite(result).all()


def test_auto_uses_safe_cpu_fallback() -> None:
    upsampler = build_upsampler("auto", device="cpu")

    assert isinstance(upsampler, BilinearUpsampler)


def test_jbu_is_deterministic_and_restores_guidance_shape() -> None:
    guide_array = np.zeros((16, 24, 3), dtype=np.uint8)
    guide_array[:, 12:] = 255
    guide = Image.fromarray(guide_array)
    low_map = np.array([[0.0, 0.25, 0.75, 1.0], [0.0, 0.25, 0.75, 1.0]], dtype=np.float32)
    upsampler = AnisotropicJBUUpsampler(radius=2)

    first = upsampler.upsample(guide, low_map)
    second = upsampler.upsample(guide, low_map)

    assert first.shape == (16, 24)
    assert first.dtype == np.float32
    assert np.isfinite(first).all()
    np.testing.assert_array_equal(first, second)
    assert first.min() >= 0.0
    assert first.max() <= 1.0


def test_jbu_guidance_preserves_more_boundary_contrast_than_bilinear() -> None:
    guide_array = np.zeros((16, 32, 3), dtype=np.uint8)
    guide_array[:, 16:] = 255
    guide = Image.fromarray(guide_array)
    low_map = np.array([[0.0, 0.0, 1.0, 1.0], [0.0, 0.0, 1.0, 1.0]], dtype=np.float32)

    bilinear = BilinearUpsampler().upsample(guide, low_map)
    jbu = AnisotropicJBUUpsampler(radius=3, sigma_color=0.05).upsample(guide, low_map)

    bilinear_contrast = float(bilinear[:, 16].mean() - bilinear[:, 15].mean())
    jbu_contrast = float(jbu[:, 16].mean() - jbu[:, 15].mean())
    assert jbu_contrast > bilinear_contrast


def test_jbu_rejects_invalid_inputs_and_is_selectable() -> None:
    with pytest.raises(ValueError, match="radius"):
        AnisotropicJBUUpsampler(radius=0)
    with pytest.raises(ValueError, match="sigmas"):
        AnisotropicJBUUpsampler(sigma_color=0)

    upsampler = build_upsampler("jbu", device="cpu")
    assert isinstance(upsampler, AnisotropicJBUUpsampler)
    with pytest.raises(ValueError, match="non-empty 2D"):
        upsampler.upsample(Image.new("RGB", (4, 4)), np.array([], dtype=np.float32))
    with pytest.raises(ValueError, match="finite"):
        upsampler.upsample(Image.new("RGB", (4, 4)), np.array([[np.nan]], dtype=np.float32))


def test_pinned_upa_submodule_is_present() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    if not (repository_root / "external").exists():
        pytest.skip("external submodules are intentionally excluded from the source distribution")
    assert upa_source_available(repository_root)
