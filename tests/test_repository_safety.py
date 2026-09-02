from pathlib import Path

from scripts.check_repository_safety import (
    PNG_SIGNATURE,
    SENSITIVE_PNG_MARKER,
    filesystem_paths,
    is_sensitive_png,
    scan_repository,
)


def test_sensitive_png_marker_requires_png_content() -> None:
    source_text = b'SENSITIVE_PNG_MARKER = b"ua_sahi_mal_sensitive"'

    assert not is_sensitive_png(source_text)


def test_sensitive_png_is_detected_even_with_disguised_filename() -> None:
    payload = PNG_SIGNATURE + b"metadata:" + SENSITIVE_PNG_MARKER

    assert is_sensitive_png(payload)


def test_filesystem_fallback_ignores_generated_roots_and_model_files(tmp_path: Path) -> None:
    source = tmp_path / "src" / "package"
    source.mkdir(parents=True)
    checked = source / "module.py"
    checked.write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "model.pt").write_bytes(b"ignored local checkpoint")
    generated = tmp_path / ".codex-review"
    generated.mkdir()
    (generated / "result.json").write_text("{}", encoding="utf-8")

    assert filesystem_paths(tmp_path) == (checked,)


def test_filesystem_fallback_still_catches_disguised_executable(tmp_path: Path) -> None:
    disguised = tmp_path / "docs" / "notes.txt"
    disguised.parent.mkdir()
    disguised.write_bytes(b"MZ" + b"synthetic-header-only")

    problems = scan_repository(tmp_path, paths=filesystem_paths(tmp_path))

    assert problems == ["tracked executable magic bytes: docs/notes.txt"]
