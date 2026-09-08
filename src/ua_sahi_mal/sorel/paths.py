"""Output-path safety guards for SOREL selection and acquisition.

The G0-S determination forbids publishing the SHA manifest and forbids letting
sample-linked artefacts leak into shareable locations. These guards make the
"never in Git, never in a sync folder, isolated data path only" rule mechanical
rather than a matter of remembering it.

No network access. Pure path reasoning; nothing here reads file contents.
"""

from __future__ import annotations

from pathlib import Path

# Directory-name fragments that commonly auto-sync to a shared/cloud location.
# Matched case-insensitively against every component of the resolved path.
_SYNC_MARKERS = (
    "onedrive",
    "dropbox",
    "google drive",
    "googledrive",
    "google_drive",
    "icloud",
    "box sync",
    "boxsync",
    "nextcloud",
    "syncthing",
    "creative cloud",
    "pcloud",
    "mega",
)

# Files/dirs that mark a version-control or package root we must never write into.
_REPO_MARKERS = (".git", "pyproject.toml")


class UnsafeOutputPathError(RuntimeError):
    """Raised when a selection/acquisition output would land somewhere unsafe."""


def _resolve(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def find_repo_root(start: str | Path) -> Path | None:
    """Return the nearest ancestor (inclusive) that looks like a repo root, else None."""
    p = _resolve(start)
    for cand in (p, *p.parents):
        for marker in _REPO_MARKERS:
            if (cand / marker).exists():
                return cand
    return None


def is_within_repo(path: str | Path) -> bool:
    """True if ``path`` is inside (or is) a git/python project root."""
    return find_repo_root(path) is not None


def _sync_marker_hit(path: Path) -> str | None:
    for part in path.parts:
        low = part.lower()
        for marker in _SYNC_MARKERS:
            if marker in low:
                return part
    return None


def assert_isolated_output(path: str | Path, *, kind: str = "output") -> Path:
    """Validate a *file* destination for a SHA manifest / selected-SHA list.

    Refuses paths inside a repository tree or a recognised cloud-sync folder.
    Returns the resolved path on success.
    """
    resolved = _resolve(path)
    repo = find_repo_root(resolved.parent if resolved.suffix else resolved)
    if repo is not None:
        raise UnsafeOutputPathError(
            f"refusing to write {kind} inside a repository tree ({repo}); "
            "the SHA manifest is not publishable (G0-S). Choose an isolated path "
            "such as D:\\datasets\\sorel20m-private."
        )
    hit = _sync_marker_hit(resolved)
    if hit is not None:
        raise UnsafeOutputPathError(
            f"refusing to write {kind} into an apparent cloud-sync folder "
            f"(component {hit!r}); use a non-synced isolated path."
        )
    return resolved


def assert_isolated_binary_dir(path: str | Path) -> Path:
    """Validate the *directory* that will hold downloaded (disarmed) binaries.

    Same repo/sync refusal as above, applied to the directory itself.
    Returns the resolved directory path on success.
    """
    resolved = _resolve(path)
    repo = find_repo_root(resolved)
    if repo is not None:
        raise UnsafeOutputPathError(
            f"refusing to place binaries inside a repository tree ({repo}); "
            "malware must live only in an approved isolated data path."
        )
    hit = _sync_marker_hit(resolved)
    if hit is not None:
        raise UnsafeOutputPathError(
            f"refusing to place binaries into an apparent cloud-sync folder "
            f"(component {hit!r}); use a non-synced isolated path."
        )
    return resolved
