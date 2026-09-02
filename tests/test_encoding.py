from pathlib import Path

import pytest
from PIL import Image

from ua_sahi_mal.encoding import (
    ENCODING_EXISTING_IMAGE,
    encode_16bit_words,
    encode_opcode_3grams,
    encode_path,
    encode_raw_bytes,
    parse_opcode_stream,
    pixel_interval_to_boxes,
    save_encoded_png,
    source_range_to_boxes,
)


def test_raw_rgb_maps_non_overlapping_byte_triples() -> None:
    encoded = encode_raw_bytes(bytes([1, 2, 3, 4]), width=2)

    assert encoded.image.size == (2, 1)
    assert encoded.image.tobytes() == bytes([1, 2, 3, 4, 0, 0])
    assert encoded.metadata.source_unit == "byte_offset"
    assert encoded.metadata.stride == 3
    assert encoded.metadata.pixel_count == 2


def test_word16_rgb_maps_big_endian_words_and_pads_odd_tail() -> None:
    encoded = encode_16bit_words(bytes([0xA1, 0xB2, 0xC3]), width=2)

    assert encoded.image.size == (2, 1)
    assert encoded.image.tobytes() == bytes([0xA1, 0xB2, 0x13, 0xC3, 0x00, 0xC3])
    assert encoded.metadata.version == "word16-rgb-v1"
    assert encoded.metadata.source_unit_count == 3
    assert encoded.metadata.window_size == 2
    assert encoded.metadata.stride == 2


def test_word16_source_range_maps_two_bytes_per_pixel() -> None:
    encoded = encode_16bit_words(bytes(range(10)), width=3)

    assert source_range_to_boxes(2, 10, encoded.metadata) == (
        (1, 0, 2, 1),
        (0, 1, 2, 1),
    )


def test_opcode_encoder_uses_sliding_three_grams() -> None:
    encoded = encode_opcode_3grams([0x10, 0x20, 0x30, 0x40], width=2)

    assert encoded.image.tobytes() == bytes([0x10, 0x20, 0x30, 0x20, 0x30, 0x40])
    assert encoded.metadata.version == "opcode-3gram-rgb-v1"
    assert encoded.metadata.window_size == 3
    assert encoded.metadata.stride == 1


def test_opcode_parser_is_strict_but_accepts_comments() -> None:
    assert parse_opcode_stream("48 8B 05 # load\n0xFF,10,20 // tail") == bytes(
        [0x48, 0x8B, 0x05, 0xFF, 0x10, 0x20]
    )

    with pytest.raises(ValueError, match="invalid opcode token"):
        parse_opcode_stream("00401000: mov eax, ebx")


def test_pixel_interval_splits_exactly_at_row_boundaries() -> None:
    assert pixel_interval_to_boxes(2, 6, width=4, height=2) == (
        (2, 0, 2, 1),
        (0, 1, 2, 1),
    )
    assert pixel_interval_to_boxes(0, 8, width=4, height=2) == ((0, 0, 4, 2),)


def test_raw_source_range_maps_to_exact_row_spans() -> None:
    encoded = encode_raw_bytes(bytes(range(18)), width=4)

    assert source_range_to_boxes(6, 18, encoded.metadata) == (
        (2, 0, 2, 1),
        (0, 1, 2, 1),
    )


def test_opcode_range_includes_all_overlapping_windows() -> None:
    encoded = encode_opcode_3grams([0, 1, 2, 3, 4, 5], width=4)

    assert source_range_to_boxes(2, 4, encoded.metadata) == ((0, 0, 4, 1),)


def test_existing_image_is_loaded_without_resize(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    Image.new("L", (7, 5), color=64).save(source)

    encoded = encode_path(source, mode=ENCODING_EXISTING_IMAGE, width=999)

    assert encoded.image.mode == "RGB"
    assert encoded.image.size == (7, 5)
    assert encoded.metadata.width == 7
    assert encoded.metadata.height == 5


def test_encode_path_enforces_input_size_limit(tmp_path: Path) -> None:
    source = tmp_path / "large.dat"
    source.write_bytes(b"1234")

    with pytest.raises(ValueError, match="max_input_bytes"):
        encode_path(source, mode="raw-rgb", max_input_bytes=3)


def test_saved_encoded_png_carries_sensitive_marker(tmp_path: Path) -> None:
    encoded = encode_raw_bytes(b"abcdef", width=2)
    output = tmp_path / "encoded.png"

    save_encoded_png(encoded, output)

    assert b"ua_sahi_mal_sensitive" in output.read_bytes()
