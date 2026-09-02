"""Static CAPE-shaped behavior JSON to a DECODE-like 2x2 visualization."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image, PngImagePlugin

from ua_sahi_mal.encoding import SENSITIVE_PNG_MARKER, sha256_file

BEHAVIOR_CATEGORIES = ("process", "registry", "network", "filesystem")
LOW_SIZE = 128
QUADRANT_SIZE = 256
OUTPUT_SIZE = 512
PIXELS_PER_CATEGORY = LOW_SIZE * LOW_SIZE


class BehaviorEncodingError(ValueError):
    """Raised when an approved static behavior report violates the input contract."""


@dataclass(frozen=True)
class BehaviorEncodingMetadata:
    version: str
    source_name: str
    source_sha256: str
    output_width: int
    output_height: int
    quadrant_order: tuple[str, ...]
    api_call_counts: dict[str, int]
    ignored_call_count: int
    truncated_character_counts: dict[str, int]
    repeated_character_counts: dict[str, int]


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BehaviorEncodingError(f"JSON contains duplicate key: {key}")
        result[key] = value
    return result


def _load_report(path: Path, *, max_input_bytes: int) -> dict[str, Any]:
    if not path.is_file():
        raise BehaviorEncodingError(f"behavior report does not exist: {path}")
    size = path.stat().st_size
    if size > max_input_bytes:
        raise BehaviorEncodingError(
            f"behavior report exceeds max_input_bytes ({size} > {max_input_bytes})"
        )
    try:
        document = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
        )
    except BehaviorEncodingError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BehaviorEncodingError(f"cannot read behavior report JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise BehaviorEncodingError("behavior report root must be an object")
    return document


def extract_api_sequences(
    report: dict[str, Any],
) -> tuple[dict[str, list[str]], int]:
    """Extract only category and API name; arguments and payloads are never rendered."""

    behavior = report.get("behavior")
    if not isinstance(behavior, dict) or not isinstance(behavior.get("processes"), list):
        raise BehaviorEncodingError("report requires behavior.processes array")
    sequences = {category: [] for category in BEHAVIOR_CATEGORIES}
    ignored = 0
    seen_process_sequences: set[tuple[tuple[str, str], ...]] = set()
    for process_index, process in enumerate(behavior["processes"]):
        if not isinstance(process, dict) or not isinstance(process.get("calls"), list):
            raise BehaviorEncodingError(
                f"behavior.processes[{process_index}].calls must be an array"
            )
        cleaned_process: list[tuple[str, str]] = []
        previous: tuple[str, str] | None = None
        for call_index, call in enumerate(process["calls"]):
            context = f"behavior.processes[{process_index}].calls[{call_index}]"
            if not isinstance(call, dict):
                raise BehaviorEncodingError(f"{context} must be an object")
            category = call.get("category")
            api = call.get("api")
            if category not in BEHAVIOR_CATEGORIES:
                ignored += 1
                continue
            if not isinstance(api, str) or not api.strip():
                raise BehaviorEncodingError(f"{context}.api must be a non-empty string")
            api = api.strip()
            if len(api) > 512:
                raise BehaviorEncodingError(f"{context}.api exceeds 512 characters")
            if any(ord(character) > 127 for character in api):
                raise BehaviorEncodingError(f"{context}.api must contain ASCII characters only")
            current = (category, api)
            # Mirror the useful part of DECODE's sequential duplicate removal.
            if current != previous:
                cleaned_process.append(current)
            previous = current
        process_key = tuple(cleaned_process)
        if process_key in seen_process_sequences:
            continue
        seen_process_sequences.add(process_key)
        for category, api in cleaned_process:
            sequences[category].append(api)
    return sequences, ignored


def _category_pixels(api_names: list[str]) -> tuple[list[tuple[int, int, int]], int, int]:
    text = "".join(api_names)
    values = [max(0, min(255, int(256 * ord(character) / 128))) for character in text]
    truncated = max(0, len(values) - PIXELS_PER_CATEGORY)
    repeated = max(0, PIXELS_PER_CATEGORY - len(values)) if values else 0
    if not values:
        values = [0] * PIXELS_PER_CATEGORY
    elif len(values) < PIXELS_PER_CATEGORY:
        repeats = (PIXELS_PER_CATEGORY + len(values) - 1) // len(values)
        values = (values * repeats)[:PIXELS_PER_CATEGORY]
    else:
        values = values[:PIXELS_PER_CATEGORY]
    return [(value, value, value) for value in values], truncated, repeated


def encode_behavior_report(
    source: Path,
    *,
    max_input_bytes: int = 64 * 1024 * 1024,
) -> tuple[Image.Image, BehaviorEncodingMetadata]:
    """Read one already-produced static JSON report and create a 512x512 RGB image."""

    source = source.resolve()
    sequences, ignored = extract_api_sequences(_load_report(source, max_input_bytes=max_input_bytes))
    combined = Image.new("RGB", (OUTPUT_SIZE, OUTPUT_SIZE))
    truncated: dict[str, int] = {}
    repeated: dict[str, int] = {}
    for index, category in enumerate(BEHAVIOR_CATEGORIES):
        pixels, truncated[category], repeated[category] = _category_pixels(sequences[category])
        quadrant = Image.new("RGB", (LOW_SIZE, LOW_SIZE))
        quadrant.putdata(pixels)
        quadrant = quadrant.resize((QUADRANT_SIZE, QUADRANT_SIZE), Image.Resampling.NEAREST)
        combined.paste(quadrant, ((index % 2) * QUADRANT_SIZE, (index // 2) * QUADRANT_SIZE))
    metadata = BehaviorEncodingMetadata(
        version="decode-static-behavior-v1",
        source_name=source.name,
        source_sha256=sha256_file(source),
        output_width=OUTPUT_SIZE,
        output_height=OUTPUT_SIZE,
        quadrant_order=BEHAVIOR_CATEGORIES,
        api_call_counts={category: len(sequences[category]) for category in BEHAVIOR_CATEGORIES},
        ignored_call_count=ignored,
        truncated_character_counts=truncated,
        repeated_character_counts=repeated,
    )
    return combined, metadata


def save_behavior_visualization(
    image: Image.Image,
    metadata: BehaviorEncodingMetadata,
    *,
    output: Path,
    metadata_output: Path,
) -> None:
    for path in (output, metadata_output):
        if path.exists():
            raise BehaviorEncodingError(f"refusing to overwrite behavior output: {path}")
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata_output.parent.mkdir(parents=True, exist_ok=True)
    png_info = PngImagePlugin.PngInfo()
    png_info.add_text(SENSITIVE_PNG_MARKER, "true")
    png_info.add_text("ua_sahi_mal_encoding", metadata.version)
    png_info.add_text(
        "ua_sahi_mal_notice",
        "Sensitive static behavior visualization; no call arguments are rendered.",
    )
    image.save(output, format="PNG", optimize=False, pnginfo=png_info)
    metadata_output.write_text(
        json.dumps(asdict(metadata), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
