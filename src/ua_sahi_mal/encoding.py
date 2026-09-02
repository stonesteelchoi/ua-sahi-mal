"""Deterministic, non-executing malware-to-image encoders.

The functions in this module only read bytes or a sanitized hexadecimal token
stream. They never import, load, disassemble, or execute the input artifact.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

from PIL import Image, PngImagePlugin

ENCODING_RAW_RGB = "raw-rgb"
ENCODING_WORD16_RGB = "word16-rgb"
ENCODING_OPCODE_3GRAM = "opcode-3gram-rgb"
ENCODING_EXISTING_IMAGE = "existing-image"
SUPPORTED_ENCODINGS = frozenset(
    {
        ENCODING_EXISTING_IMAGE,
        ENCODING_RAW_RGB,
        ENCODING_WORD16_RGB,
        ENCODING_OPCODE_3GRAM,
    }
)
SENSITIVE_PNG_MARKER = "ua_sahi_mal_sensitive"
MAX_ENCODED_PIXELS = 100_000_000

_HEX_TOKEN = re.compile(r"^(?:0x)?([0-9a-fA-F]{2})$")


@dataclass(frozen=True)
class EncodingMetadata:
    """Coordinate contract for an encoded image."""

    version: str
    mode: str
    width: int
    height: int
    source_unit: str
    source_unit_count: int
    pixel_count: int
    padded_pixel_count: int
    window_size: int
    stride: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EncodedImage:
    image: Image.Image
    metadata: EncodingMetadata


def save_encoded_png(encoded: EncodedImage, path: Path) -> None:
    """Save an encoded image with a machine-detectable sensitivity marker.

    RGB and sliding n-gram images can preserve enough information to reconstruct
    the source stream. The marker lets the repository safety check reject a
    generated image if someone force-adds it to Git.
    """

    png_info = PngImagePlugin.PngInfo()
    png_info.add_text(SENSITIVE_PNG_MARKER, "true")
    png_info.add_text("ua_sahi_mal_encoding", encoded.metadata.version)
    png_info.add_text(
        "ua_sahi_mal_notice",
        "Sensitive derived artifact; do not commit or redistribute without review.",
    )
    encoded.image.save(path, format="PNG", optimize=False, pnginfo=png_info)


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Return a source fingerprint without loading the whole artifact."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_width(width: int) -> None:
    if not 1 <= width <= 8192:
        raise ValueError("width must be between 1 and 8192 pixels")


def _rgb_image(pixel_bytes: bytes, width: int, pixel_count: int) -> tuple[Image.Image, int]:
    if pixel_count < 1:
        raise ValueError("the source does not contain enough data to encode one pixel")
    height = math.ceil(pixel_count / width)
    padded_size = width * height * 3
    padded = pixel_bytes + bytes(padded_size - len(pixel_bytes))
    return Image.frombytes("RGB", (width, height), padded), width * height - pixel_count


def encode_raw_bytes(data: bytes, *, width: int = 256) -> EncodedImage:
    """Encode non-overlapping byte triples directly as RGB pixels."""

    _validate_width(width)
    if not data:
        raise ValueError("raw-rgb encoding requires at least one input byte")
    pixel_count = math.ceil(len(data) / 3)
    if pixel_count > MAX_ENCODED_PIXELS:
        raise ValueError("raw-rgb image exceeds the 100-megapixel safety limit")
    channel_padding = pixel_count * 3 - len(data)
    image, image_padding = _rgb_image(data + bytes(channel_padding), width, pixel_count)
    metadata = EncodingMetadata(
        version="raw-rgb-v1",
        mode=ENCODING_RAW_RGB,
        width=width,
        height=image.height,
        source_unit="byte_offset",
        source_unit_count=len(data),
        pixel_count=pixel_count,
        padded_pixel_count=image_padding,
        window_size=3,
        stride=3,
    )
    return EncodedImage(image=image, metadata=metadata)


def encode_16bit_words(data: bytes, *, width: int = 256) -> EncodedImage:
    """Map non-overlapping big-endian 16-bit words to lossless RGB pixels.

    A word ``0xA1B2`` becomes ``(0xA1, 0xB2, 0x13)`` where the third channel is
    the XOR of the first two. An odd final source byte is padded on the right
    with zero. This representation is an optional ablation and is not DECODE's
    ASCII behavior-image algorithm.
    """

    _validate_width(width)
    if not data:
        raise ValueError("word16-rgb encoding requires at least one input byte")
    source_length = len(data)
    padded_source = data if source_length % 2 == 0 else data + b"\x00"
    word_count = len(padded_source) // 2
    if word_count > MAX_ENCODED_PIXELS:
        raise ValueError("word16-rgb image exceeds the 100-megapixel safety limit")
    pixels = bytearray()
    for index in range(0, len(padded_source), 2):
        high = padded_source[index]
        low = padded_source[index + 1]
        pixels.extend((high, low, high ^ low))
    image, image_padding = _rgb_image(bytes(pixels), width, word_count)
    metadata = EncodingMetadata(
        version="word16-rgb-v1",
        mode=ENCODING_WORD16_RGB,
        width=width,
        height=image.height,
        source_unit="byte_offset",
        source_unit_count=source_length,
        pixel_count=word_count,
        padded_pixel_count=image_padding,
        window_size=2,
        stride=2,
    )
    return EncodedImage(image=image, metadata=metadata)


def parse_opcode_stream(text: str) -> bytes:
    """Parse a strict text stream containing only two-digit hexadecimal tokens.

    Lines may contain ``#`` or ``//`` comments. Disassembler output is rejected
    deliberately: callers must sanitize opcode extraction in an isolated step.
    """

    values = bytearray()
    for line_number, original_line in enumerate(text.splitlines(), start=1):
        line = original_line.split("#", 1)[0].split("//", 1)[0].strip()
        if not line:
            continue
        for raw_token in re.split(r"[\s,;]+", line):
            if not raw_token:
                continue
            matched = _HEX_TOKEN.fullmatch(raw_token)
            if matched is None:
                raise ValueError(
                    f"invalid opcode token on line {line_number}: {raw_token!r}; "
                    "expected sanitized values such as '48 8B 05'"
                )
            values.append(int(matched.group(1), 16))
    if len(values) < 3:
        raise ValueError("opcode-3gram-rgb encoding requires at least three opcode bytes")
    return bytes(values)


def encode_opcode_3grams(opcodes: Sequence[int], *, width: int = 256) -> EncodedImage:
    """Encode each sliding opcode 3-gram as one RGB pixel."""

    _validate_width(width)
    if len(opcodes) < 3:
        raise ValueError("opcode-3gram-rgb encoding requires at least three opcode bytes")
    if any(not 0 <= value <= 255 for value in opcodes):
        raise ValueError("opcode values must be in [0, 255]")
    if len(opcodes) - 2 > MAX_ENCODED_PIXELS:
        raise ValueError("opcode-3gram-rgb image exceeds the 100-megapixel safety limit")

    pixels = bytearray()
    for index in range(len(opcodes) - 2):
        pixels.extend((opcodes[index], opcodes[index + 1], opcodes[index + 2]))
    pixel_count = len(opcodes) - 2
    image, image_padding = _rgb_image(bytes(pixels), width, pixel_count)
    metadata = EncodingMetadata(
        version="opcode-3gram-rgb-v1",
        mode=ENCODING_OPCODE_3GRAM,
        width=width,
        height=image.height,
        source_unit="opcode_offset",
        source_unit_count=len(opcodes),
        pixel_count=pixel_count,
        padded_pixel_count=image_padding,
        window_size=3,
        stride=1,
    )
    return EncodedImage(image=image, metadata=metadata)


def encode_existing_image(path: Path) -> EncodedImage:
    """Load an already-sanitized visualization without resizing it."""

    with Image.open(path) as opened:
        if opened.width * opened.height > MAX_ENCODED_PIXELS:
            raise ValueError("existing image exceeds the 100-megapixel safety limit")
        image = opened.convert("RGB")
        image.load()
    metadata = EncodingMetadata(
        version="existing-image-v1",
        mode=ENCODING_EXISTING_IMAGE,
        width=image.width,
        height=image.height,
        source_unit="pixel_index",
        source_unit_count=image.width * image.height,
        pixel_count=image.width * image.height,
        padded_pixel_count=0,
        window_size=1,
        stride=1,
    )
    return EncodedImage(image=image, metadata=metadata)


def encode_path(
    path: Path,
    *,
    mode: str,
    width: int = 256,
    max_input_bytes: int = 64 * 1024 * 1024,
) -> EncodedImage:
    """Read and encode a local artifact without executing or loading it."""

    if mode not in SUPPORTED_ENCODINGS:
        supported = ", ".join(sorted(SUPPORTED_ENCODINGS))
        raise ValueError(f"unsupported encoding {mode!r}; choose one of: {supported}")
    if not path.is_file():
        raise ValueError(f"source file does not exist: {path}")
    size = path.stat().st_size
    if size > max_input_bytes:
        raise ValueError(f"source exceeds max_input_bytes ({size} > {max_input_bytes})")

    if mode == ENCODING_EXISTING_IMAGE:
        return encode_existing_image(path)
    if mode == ENCODING_RAW_RGB:
        return encode_raw_bytes(path.read_bytes(), width=width)
    if mode == ENCODING_WORD16_RGB:
        return encode_16bit_words(path.read_bytes(), width=width)
    text = path.read_text(encoding="utf-8")
    return encode_opcode_3grams(parse_opcode_stream(text), width=width)


def source_range_to_pixel_interval(
    start: int,
    end: int,
    metadata: EncodingMetadata,
) -> tuple[int, int]:
    """Map a half-open source interval to overlapping encoded pixels."""

    if not 0 <= start < end <= metadata.source_unit_count:
        raise ValueError(
            f"source range [{start}, {end}) is outside [0, {metadata.source_unit_count})"
        )

    if metadata.mode in {
        ENCODING_EXISTING_IMAGE,
        ENCODING_RAW_RGB,
        ENCODING_WORD16_RGB,
    }:
        pixel_start = start // metadata.stride
        pixel_end = math.ceil(end / metadata.stride)
    elif metadata.mode == ENCODING_OPCODE_3GRAM:
        # Pixel i contains opcode window [i, i + 3). Keep every window that
        # overlaps the requested source interval.
        pixel_start = max(0, start - metadata.window_size + 1)
        pixel_end = min(metadata.pixel_count, end)
    else:  # Defensive guard for hand-authored manifests.
        raise ValueError(f"unsupported metadata mode: {metadata.mode}")

    if pixel_start >= pixel_end:
        raise ValueError("source range does not map to any encoded pixel")
    return pixel_start, pixel_end


def pixel_interval_to_boxes(
    start: int,
    end: int,
    *,
    width: int,
    height: int,
) -> tuple[tuple[int, int, int, int], ...]:
    """Convert a row-major pixel interval to exact COCO ``xywh`` rectangles.

    A range that wraps across a row becomes up to three rectangles: the first
    partial row, all complete middle rows, and the last partial row. This avoids
    labeling unrelated pixels inside one oversized bounding rectangle.
    """

    if width < 1 or height < 1:
        raise ValueError("image dimensions must be positive")
    if not 0 <= start < end <= width * height:
        raise ValueError("pixel interval is outside the encoded image")

    first_row, first_col = divmod(start, width)
    last_row, last_col = divmod(end - 1, width)
    if first_row == last_row:
        return ((first_col, first_row, last_col - first_col + 1, 1),)

    boxes: list[tuple[int, int, int, int]] = []
    full_row_start = first_row
    if first_col:
        boxes.append((first_col, first_row, width - first_col, 1))
        full_row_start += 1

    full_row_end = last_row + 1
    if last_col != width - 1:
        full_row_end = last_row

    if full_row_start < full_row_end:
        boxes.append((0, full_row_start, width, full_row_end - full_row_start))
    if last_col != width - 1:
        boxes.append((0, last_row, last_col + 1, 1))
    return tuple(boxes)


def source_range_to_boxes(
    start: int,
    end: int,
    metadata: EncodingMetadata,
) -> tuple[tuple[int, int, int, int], ...]:
    """Map a source range directly to exact COCO ``xywh`` rectangles."""

    pixel_start, pixel_end = source_range_to_pixel_interval(start, end, metadata)
    return pixel_interval_to_boxes(
        pixel_start,
        pixel_end,
        width=metadata.width,
        height=metadata.height,
    )
