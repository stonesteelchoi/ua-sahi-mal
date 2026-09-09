"""Run records for SOREL selection / acquisition (amendment §9).

The amendment requires recording access date-time, Terms revision, code commit,
seed and exclusion reasons alongside the private manifest. This module builds a
small, non-executable JSON record with that provenance so a frozen selection or an
acquisition run can be audited and reproduced later.

Records contain hashes/paths/counts only — never binary content — and are written
only to isolated (non-repo, non-sync) destinations via the path guards.
"""

from __future__ import annotations

import datetime as _dt
import json
import subprocess
from pathlib import Path

from .paths import assert_isolated_output


def utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def code_commit(repo_root: str | Path | None = None) -> str:
    """Return the current git commit (short + dirty flag) or 'unknown'. Never raises."""
    try:
        cwd = str(repo_root) if repo_root else None
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"],  # noqa: S603,S607
                             capture_output=True, text=True, check=True, cwd=cwd).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"],  # noqa: S603,S607
                               capture_output=True, text=True, check=True, cwd=cwd).stdout.strip()
        return f"{sha}{'-dirty' if dirty else ''}"
    except Exception:  # noqa: BLE001 - provenance is best-effort
        return "unknown"


def file_identity(path: str | Path) -> dict[str, object]:
    """Cheap identity for a large input file (no full hash): path, size, mtime."""
    p = Path(path)
    try:
        st = p.stat()
        return {"path": str(p), "size_bytes": st.st_size,
                "mtime_utc": _dt.datetime.fromtimestamp(st.st_mtime, _dt.timezone.utc)
                .replace(microsecond=0).isoformat()}
    except OSError:
        return {"path": str(p), "size_bytes": None, "mtime_utc": None}


def build_run_record(kind: str, *, repo_root: str | Path | None = None,
                     **fields: object) -> dict[str, object]:
    """Assemble a run record: kind, UTC timestamp, code commit, then caller fields."""
    rec: dict[str, object] = {
        "record_kind": kind,
        "timestamp_utc": utc_now_iso(),
        "code_commit": code_commit(repo_root),
        "tool": "ua_sahi_mal.sorel",
    }
    rec.update(fields)
    return rec


def write_run_record(path: str | Path, record: dict[str, object]) -> Path:
    """Write the record as JSON to an isolated path (guarded). Returns resolved path."""
    out = assert_isolated_output(path, kind="run record")
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
