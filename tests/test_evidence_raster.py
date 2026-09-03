"""Raster parsing and the coordinate contract that everything downstream assumes."""

from __future__ import annotations

import numpy as np
import pytest

from ua_sahi_mal.evidence import raster


def write_dump(path, lines):
    path.write_text("\r\n".join(lines) + "\r\n", encoding="latin-1")
    return path


def test_parses_a_well_formed_dump(tmp_path):
    dump_path = write_dump(
        tmp_path / "sample.bytes",
        [
            "00401000 " + " ".join(f"{value:02X}" for value in range(16)),
            "00401010 " + " ".join(f"{value:02X}" for value in range(16, 32)),
        ],
    )
    dump = raster.parse_bytes_dump(dump_path)

    assert dump.size == 32
    assert dump.base_address == 0x401000
    assert dump.valid.all()
    np.testing.assert_array_equal(dump.data, np.arange(32, dtype=np.uint8))


def test_question_marks_are_recorded_as_invalid_not_as_zero_bytes(tmp_path):
    dump_path = write_dump(
        tmp_path / "sample.bytes",
        ["00401000 AA ?? BB ??"],
    )
    dump = raster.parse_bytes_dump(dump_path)

    np.testing.assert_array_equal(dump.data, np.array([0xAA, 0, 0xBB, 0], dtype=np.uint8))
    np.testing.assert_array_equal(dump.valid, np.array([True, False, True, False]))
    assert dump.valid_fraction == 0.5


def test_address_gaps_are_filled_and_marked_invalid(tmp_path):
    dump_path = write_dump(
        tmp_path / "sample.bytes",
        ["00401000 01 02", "00401010 03 04"],  # 14-byte gap
    )
    dump = raster.parse_bytes_dump(dump_path)

    assert dump.size == 18
    np.testing.assert_array_equal(dump.data[:2], np.array([1, 2], dtype=np.uint8))
    np.testing.assert_array_equal(dump.data[16:], np.array([3, 4], dtype=np.uint8))
    assert not dump.valid[2:16].any()


def test_lowercase_hexadecimal_is_accepted(tmp_path):
    dump_path = write_dump(tmp_path / "sample.bytes", ["00401000 de ad be ef"])
    dump = raster.parse_bytes_dump(dump_path)
    np.testing.assert_array_equal(dump.data, np.array([0xDE, 0xAD, 0xBE, 0xEF], dtype=np.uint8))


def test_binary_input_is_rejected_rather_than_silently_misparsed(tmp_path):
    path = tmp_path / "sample.bytes"
    path.write_bytes(b"MZ\x00\x00\x90" * 100)
    with pytest.raises(raster.DumpParseError, match="binary"):
        raster.parse_bytes_dump(path)


def test_empty_input_is_rejected(tmp_path):
    path = tmp_path / "sample.bytes"
    path.write_bytes(b"")
    with pytest.raises(raster.DumpParseError, match="empty"):
        raster.parse_bytes_dump(path)


def test_dump_over_the_size_limit_is_rejected(tmp_path):
    dump_path = write_dump(tmp_path / "sample.bytes", ["00401000 " + " ".join(["AA"] * 16)])
    with pytest.raises(raster.DumpParseError, match="over the"):
        raster.parse_bytes_dump(dump_path, max_bytes=8)


def test_row_maps_to_a_fixed_byte_range_regardless_of_sample_size():
    small = raster.rasterize(_dump(1000))
    large = raster.rasterize(_dump(100_000))
    assert small.row_byte_range(1) == (512, 1000)
    assert large.row_byte_range(1) == (512, 1024)


def test_rasterizing_pads_the_last_row_and_marks_the_padding_invalid():
    image = raster.rasterize(_dump(600))
    assert image.image.shape == (2, 512)
    assert image.byte_count == 600
    assert image.valid[1, 88:].sum() == 0
    assert image.flat_bytes().size == 600


def test_raster_survives_a_png_round_trip_exactly(tmp_path):
    original = raster.rasterize(_dump(5000, seed=7))
    path = raster.save_raster(original, tmp_path / "r.png")
    restored = raster.load_raster(path)

    np.testing.assert_array_equal(original.image, restored.image)
    np.testing.assert_array_equal(original.valid, restored.valid)
    assert restored.byte_count == original.byte_count
    assert restored.base_address == original.base_address
    assert restored.source_name == original.source_name


def test_block_ranges_cover_every_byte_once_and_clip_the_tail():
    ranges = raster.block_ranges(10_000, 4096)
    assert ranges.shape == (3, 2)
    assert ranges[0].tolist() == [0, 4096]
    assert ranges[-1].tolist() == [8192, 10_000]
    assert int((ranges[:, 1] - ranges[:, 0]).sum()) == 10_000


def test_zero_width_and_empty_dumps_are_refused():
    with pytest.raises(ValueError):
        raster.rasterize(_dump(100), width=0)
    empty = raster.ByteDump(
        data=np.zeros(0, np.uint8), valid=np.zeros(0, bool), base_address=0, source_name="e"
    )
    with pytest.raises(ValueError, match="empty"):
        raster.rasterize(empty)


def _dump(size: int, seed: int = 0) -> raster.ByteDump:
    rng = np.random.default_rng(seed)
    data = rng.integers(0, 256, size=size, dtype=np.uint8)
    return raster.ByteDump(
        data=data, valid=np.ones(size, dtype=bool), base_address=0x401000, source_name="synthetic"
    )
