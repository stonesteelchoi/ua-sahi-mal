"""Fail CI when tracked files cross the malware-data safety boundary."""

from __future__ import annotations

import fnmatch
import os
import re
import subprocess
import sys
from pathlib import Path

FORBIDDEN_SUFFIXES = {
    ".7z",
    ".apk",
    ".bin",
    ".bytes",
    ".com",
    ".dex",
    ".dll",
    ".dylib",
    ".elf",
    ".engine",
    ".exe",
    ".hex",
    ".msi",
    ".onnx",
    ".pt",
    ".rar",
    ".scr",
    ".so",
    ".sys",
    ".torchscript",
    ".zip",
}
FORBIDDEN_PREFIXES = ("data/raw/", "datasets/raw/", "samples/", "quarantine/")
SECRET_PATTERNS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(rb"ghp_[A-Za-z0-9]{30,}"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
)
SENSITIVE_PNG_MARKER = b"ua_sahi_mal_sensitive"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
FALLBACK_IGNORED_DIRECTORIES = {
    ".codex-review",
    ".git",
    ".idea",
    ".ipynb_checkpoints",
    ".pytest_cache",
    ".pytest_tmp",
    ".ruff_cache",
    ".venv",
    ".vscode",
    "__pycache__",
    "artifacts",
    "build",
    "data",
    "datasets",
    "dist",
    "htmlcov",
    "quarantine",
    "runs",
    "samples",
    "weights",
}
FALLBACK_IGNORED_FILE_PATTERNS = (
    "*.7z",
    "*.apk",
    "*.bin",
    "*.bytes",
    "*.com",
    "*.dex",
    "*.dll",
    "*.dylib",
    "*.elf",
    "*.engine",
    "*.exe",
    "*.hex",
    "*.log",
    "*.msi",
    "*.onnx",
    "*.pt",
    "*.pyc",
    "*.pyd",
    "*.pyo",
    "*.rar",
    "*.scr",
    "*.so",
    "*.sys",
    "*.torchscript",
    "*.zip",
    ".coverage",
    ".DS_Store",
    "Thumbs.db",
)


def is_sensitive_png(header_probe: bytes) -> bool:
    """Recognize marked PNG content even when its filename was disguised."""

    return header_probe.startswith(PNG_SIGNATURE) and SENSITIVE_PNG_MARKER in header_probe


def _fallback_ignored_file(name: str) -> bool:
    if name == ".env.example":
        return False
    if name == ".env" or name.startswith(".env."):
        return True
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in FALLBACK_IGNORED_FILE_PATTERNS)


def filesystem_paths(root: Path) -> tuple[Path, ...]:
    """List non-ignored files when a source archive has no Git metadata.

    The exclusions mirror this repository's .gitignore. This fallback cannot
    identify a force-added ignored file, so CI must continue to use Git mode.
    """

    paths: list[Path] = []
    for current, directory_names, file_names in os.walk(root):
        directory_names[:] = sorted(
            name
            for name in directory_names
            if name not in FALLBACK_IGNORED_DIRECTORIES
            and not fnmatch.fnmatchcase(name, "*.egg-info")
        )
        current_path = Path(current)
        paths.extend(
            current_path / name
            for name in sorted(file_names)
            if not _fallback_ignored_file(name)
        )
    return tuple(paths)


def repository_paths(root: Path) -> tuple[tuple[Path, ...], str]:
    """Prefer Git's exact tracked set and fall back for unpacked source trees."""

    try:
        completed = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root,
            check=False,
            capture_output=True,
        )
    except OSError:
        completed = None
    if completed is not None and completed.returncode == 0:
        names = [name for name in completed.stdout.decode("utf-8").split("\0") if name]
        return tuple(root / Path(name) for name in names), "Git-tracked files"
    return filesystem_paths(root), "non-ignored files (Git metadata unavailable)"


def tracked_paths(root: Path) -> tuple[Path, ...]:
    """Compatibility wrapper returning the safety-scan path set."""

    return repository_paths(root)[0]


def scan_repository(root: Path, *, paths: tuple[Path, ...] | None = None) -> list[str]:
    problems: list[str] = []
    for path in paths if paths is not None else tracked_paths(root):
        relative = path.relative_to(root).as_posix()
        lower_relative = relative.lower()
        if lower_relative.startswith(FORBIDDEN_PREFIXES):
            problems.append(f"tracked raw-data path: {relative}")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            problems.append(f"tracked forbidden artifact type: {relative}")
        if path.name == ".env" or path.name.startswith(".env.") and path.name != ".env.example":
            problems.append(f"tracked environment secret file: {relative}")
        if not path.is_file():
            continue
        with path.open("rb") as stream:
            marker_probe = stream.read(1024 * 1024)
        head = marker_probe[:4]
        if head[:2] == b"MZ" or head == b"\x7fELF" or head.startswith(b"dex\n"):
            problems.append(f"tracked executable magic bytes: {relative}")
        if is_sensitive_png(marker_probe):
            problems.append(f"tracked reversible malware visualization: {relative}")
        if path.stat().st_size <= 2 * 1024 * 1024:
            payload = path.read_bytes()
            if any(pattern.search(payload) for pattern in SECRET_PATTERNS):
                problems.append(f"tracked high-confidence credential pattern: {relative}")
    return problems


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    paths, scope = repository_paths(root)
    problems = scan_repository(root, paths=paths)
    if problems:
        print("Repository safety check failed:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1
    print(
        "Repository safety check passed: "
        f"no malware payloads or high-confidence secrets in {scope}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
