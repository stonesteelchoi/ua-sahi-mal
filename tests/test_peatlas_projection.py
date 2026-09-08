"""Tests for the encoding <-> PEAtlas pixel/file-offset projection.

Coordinate correctness only; no training and no analyzer. Correspondence is
proven against the actual encoder output where possible.
"""

from __future__ import annotations

import numpy as np
import pytest
from peatlas_fixtures import simple_two_section

from ua_sahi_mal.encoding import encode_16bit_words, encode_raw_bytes
from ua_sahi_mal.peatlas import (
    IntervalSet,
    PeAtlas,
    PixelProjection,
    UnsupportedProjectionError,
    project_pixels_to_atlas,
)


def _raw_meta(data: bytes, width: int):
    return encode_raw_bytes(data, width=width).metadata


# --- contract construction / unsupported ---------------------------------
def test_from_metadata_supported_modes():
    p = PixelProjection.from_metadata(_raw_meta(bytes(range(10)), 2))
    assert p.mode == "raw-rgb" and p.stride == 3 and p.channels == 3
    assert p.width == 2 and p.height == 2 and p.pixel_count == 4 and p.source_byte_count == 10
    w = PixelProjection.from_metadata(encode_16bit_words(bytes(range(9)), width=2).metadata)
    assert w.mode == "word16-rgb" and w.stride == 2 and w.pixel_count == 5


def test_unsupported_encodings_and_resize_raise():
    # opcode-3gram: source_unit is opcode tokens, not file bytes
    with pytest.raises(UnsupportedProjectionError):
        PixelProjection.from_metadata({"mode": "opcode-3gram-rgb", "source_unit": "opcode_window",
                                       "stride": 1, "width": 4, "pixel_count": 4,
                                       "source_unit_count": 4, "height": 1})
    # existing-image: no source-byte mapping
    with pytest.raises(UnsupportedProjectionError):
        PixelProjection.from_metadata({"mode": "existing-image", "source_unit": "pixel",
                                       "stride": 1, "width": 4, "pixel_count": 4,
                                       "source_unit_count": 4, "height": 1})
    # resized model input is refused even for a supported mode
    with pytest.raises(UnsupportedProjectionError):
        PixelProjection.from_metadata(_raw_meta(bytes(range(10)), 2), resized=True)


# --- byte <-> pixel/channel ----------------------------------------------
def test_byte_to_pixel_channel_and_span_raw():
    p = PixelProjection.from_metadata(_raw_meta(bytes(range(10)), 2))
    assert p.byte_to_pixel_channel(0) == (0, 0)
    assert p.byte_to_pixel_channel(8) == (2, 2)
    assert p.byte_to_pixel_channel(9) == (3, 0)
    with pytest.raises(ValueError):
        p.byte_to_pixel_channel(10)  # padding byte, not in source
    # last pixel span is clamped to the real byte count (channel padding excluded)
    assert p.pixel_to_byte_span(3) == IntervalSet([(9, 10)]).intervals[0]
    assert p.pixel_to_byte_span(4) is None  # padding/out of image


def test_pixel_channel_matches_actual_encoder_raw():
    data = bytes([5, 9, 17, 200, 3, 44, 255, 1])  # 8 bytes -> 3 pixels (width 3 -> 1 row)
    enc = encode_raw_bytes(data, width=3)
    p = PixelProjection.from_metadata(enc.metadata)
    flat = np.asarray(enc.image).reshape(-1)  # RGB channels row-major
    for offset, value in enumerate(data):
        pixel, channel = p.byte_to_pixel_channel(offset)
        assert flat[pixel * 3 + channel] == value


def test_channel_matches_actual_encoder_word16():
    data = bytes([0xA1, 0xB2, 0x10, 0x20, 0x33])  # 5 bytes -> 3 pixels (last odd byte padded)
    enc = encode_16bit_words(data, width=4)
    p = PixelProjection.from_metadata(enc.metadata)
    flat = np.asarray(enc.image).reshape(-1)
    # even offset -> high byte (channel 0), odd offset -> low byte (channel 1)
    for offset, value in enumerate(data):
        pixel, channel = p.byte_to_pixel_channel(offset)
        assert flat[pixel * 3 + channel] == value


# --- interval projections ------------------------------------------------
def test_pixels_to_bytes_excludes_padding():
    p = PixelProjection.from_metadata(_raw_meta(bytes(range(10)), 2))
    # all 4 real pixels -> bytes [0,10) (not [0,12); channel padding excluded)
    assert p.pixels_to_bytes(IntervalSet([(0, 4)])) == IntervalSet([(0, 10)])
    # asking beyond pixel_count clamps away padding pixels
    assert p.pixels_to_bytes(IntervalSet([(3, 99)])) == IntervalSet([(9, 10)])


def test_bytes_to_pixels_and_round_trip():
    p = PixelProjection.from_metadata(_raw_meta(bytes(range(10)), 2))
    assert p.bytes_to_pixels(IntervalSet([(0, 10)])) == IntervalSet([(0, 4)])
    assert p.bytes_to_pixels(IntervalSet([(9, 10)])) == IntervalSet([(3, 4)])
    # pixel -> byte -> pixel is exact
    pixels = IntervalSet([(0, 2), (3, 4)])
    assert p.bytes_to_pixels(p.pixels_to_bytes(pixels)) == pixels


def test_bbox_row_and_channel_boundaries_and_noncontiguous():
    # raw, width 2, height 2, 10 bytes
    p = PixelProjection.from_metadata(_raw_meta(bytes(range(10)), 2))
    # single full row -> contiguous bytes
    assert p.bbox_to_bytes(0, 0, 2, 1) == IntervalSet([(0, 6)])
    # whole image -> all real bytes, padding excluded
    assert p.bbox_to_bytes(0, 0, 2, 2) == IntervalSet([(0, 10)])
    # single column across two rows -> NON-contiguous union
    assert p.bbox_to_bytes(1, 0, 1, 2) == IntervalSet([(3, 6), (9, 10)])
    with pytest.raises(ValueError):
        p.bbox_to_bytes(0, 0, 3, 1)  # outside image width


def test_mask_to_bytes():
    p = PixelProjection.from_metadata(_raw_meta(bytes(range(10)), 2))
    # select pixels 0 and 2
    assert p.mask_to_bytes([1, 0, 1, 0]) == IntervalSet([(0, 3), (6, 9)])


def test_word16_padding_excluded():
    p = PixelProjection.from_metadata(encode_16bit_words(bytes(range(9)), width=2).metadata)
    # 9 source bytes, stride 2, pixel_count 5; last real pixel (4) covers [8,10)->[8,9)
    assert p.pixel_to_byte_span(4) == IntervalSet([(8, 9)]).intervals[0]
    assert p.pixel_to_byte_span(5) is None  # image padding pixel
    assert p.pixels_to_bytes(IntervalSet([(0, 5)])) == IntervalSet([(0, 9)])


# --- full encoding -> PEAtlas connection ---------------------------------
def test_project_pixels_through_atlas():
    pe = simple_two_section()
    atlas = PeAtlas.from_bytes(pe)
    p = PixelProjection.from_metadata(encode_raw_bytes(pe, width=256).metadata)
    # pixels covering the .text raw region [0x200, 0x400)
    pixels = p.bytes_to_pixels(IntervalSet([(0x200, 0x400)]))
    offsets, segments = project_pixels_to_atlas(pixels, p, atlas)
    # bytes_to_pixels widens to pixel granularity, so offsets cover >= the request
    assert offsets.contains_point(0x200) and offsets.contains_point(0x3FF)
    # the .text mapped part becomes an OK segment carrying an rva
    ok = [s for s in segments if s.status.name == "OK" and s.mapped is not None]
    assert any(s.mapped.start == 0x1000 for s in ok)
