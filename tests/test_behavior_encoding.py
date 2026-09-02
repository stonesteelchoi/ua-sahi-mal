import json
from pathlib import Path

import pytest
from PIL import Image

from ua_sahi_mal.behavior_encoding import (
    BEHAVIOR_CATEGORIES,
    BehaviorEncodingError,
    encode_behavior_report,
    save_behavior_visualization,
)
from ua_sahi_mal.encoding import SENSITIVE_PNG_MARKER, sha256_file

FIXTURE = Path(__file__).parent / "fixtures" / "safe_behavior_report.json"


def _write_report(path: Path, *, argument_value: str = "FIRST") -> None:
    path.write_text(
        json.dumps(
            {
                "behavior": {
                    "processes": [
                        {
                            "calls": [
                                {
                                    "category": "process",
                                    "api": "CreateProcessW",
                                    "arguments": {"ignored": argument_value},
                                },
                                {"category": "registry", "api": "RegOpenKeyExW"},
                                {"category": "network", "api": "InternetOpenW"},
                                {"category": "filesystem", "api": "CreateFileW"},
                            ]
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )


def test_static_behavior_fixture_maps_fixed_quadrants_and_deduplicates() -> None:
    image, metadata = encode_behavior_report(FIXTURE)

    assert image.mode == "RGB"
    assert image.size == (512, 512)
    assert metadata.version == "decode-static-behavior-v1"
    assert metadata.source_sha256 == sha256_file(FIXTURE)
    assert metadata.quadrant_order == BEHAVIOR_CATEGORIES
    assert metadata.api_call_counts == {
        "process": 1,
        "registry": 1,
        "network": 1,
        "filesystem": 1,
    }
    assert metadata.ignored_call_count == 2

    # DECODE-like ASCII scaling is 256 * ord(character) / 128 = 2 * ord(character).
    assert image.getpixel((0, 0)) == (2 * ord("C"),) * 3
    assert image.getpixel((256, 0)) == (2 * ord("R"),) * 3
    assert image.getpixel((0, 256)) == (2 * ord("I"),) * 3
    assert image.getpixel((256, 256)) == (2 * ord("C"),) * 3


def test_call_arguments_and_payload_values_never_affect_pixels(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    _write_report(first, argument_value="SECRET_ONE")
    _write_report(second, argument_value="COMPLETELY_DIFFERENT_SECRET_TWO")

    first_image, first_metadata = encode_behavior_report(first)
    second_image, second_metadata = encode_behavior_report(second)

    assert first_image.tobytes() == second_image.tobytes()
    assert first_metadata.api_call_counts == second_metadata.api_call_counts
    assert first_metadata.source_sha256 != second_metadata.source_sha256


def test_saved_behavior_image_has_sensitive_marker_and_metadata(tmp_path: Path) -> None:
    image, metadata = encode_behavior_report(FIXTURE)
    output = tmp_path / "behavior.png"
    metadata_output = tmp_path / "behavior.metadata.json"

    save_behavior_visualization(
        image,
        metadata,
        output=output,
        metadata_output=metadata_output,
    )

    with Image.open(output) as saved:
        assert saved.info[SENSITIVE_PNG_MARKER] == "true"
        assert saved.info["ua_sahi_mal_encoding"] == "decode-static-behavior-v1"
    document = json.loads(metadata_output.read_text(encoding="utf-8"))
    assert document["source_name"] == FIXTURE.name
    assert document["quadrant_order"] == list(BEHAVIOR_CATEGORIES)

    with pytest.raises(BehaviorEncodingError, match="refusing to overwrite"):
        save_behavior_visualization(
            image,
            metadata,
            output=output,
            metadata_output=metadata_output,
        )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ('{"behavior": {}, "behavior": {}}', "duplicate key"),
        ('{"behavior": {"processes": "not-an-array"}}', "processes array"),
        (
            '{"behavior":{"processes":[{"calls":[{"category":"process","api":"비ASCII"}]}]}}',
            "ASCII",
        ),
    ],
)
def test_behavior_report_rejects_ambiguous_or_malformed_json(
    tmp_path: Path,
    payload: str,
    message: str,
) -> None:
    source = tmp_path / "bad.json"
    source.write_text(payload, encoding="utf-8")

    with pytest.raises(BehaviorEncodingError, match=message):
        encode_behavior_report(source)


def test_behavior_report_enforces_size_limit(tmp_path: Path) -> None:
    source = tmp_path / "report.json"
    _write_report(source)

    with pytest.raises(BehaviorEncodingError, match="max_input_bytes"):
        encode_behavior_report(source, max_input_bytes=8)
