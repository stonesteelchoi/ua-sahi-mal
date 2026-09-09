"""Frozen selection/acquisition manifest for SOREL-20M (amendment §9).

Only non-executable metadata lives here: hashes, split, tags, sizes, and status
fields. Binaries are never referenced by a repository-relative path; the
acquisition step writes them to an approved isolated directory only.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .select import TAGS, SplitSelection


@dataclass
class ManifestRow:
    # selection (frozen before download)
    sorel_original_sha256: str
    official_split: str
    first_seen_timestamp: float
    tags: str                 # ";"-joined tag names with non-zero count ("" if none)
    detection_count: int
    selection_seed: str
    selection_role: str       # "primary" | "reserve" | "replacement"
    # raw per-tag count values preserved alongside the binarised ``tags`` view
    # (amendment §6.3), e.g. "adware=3;packed=1" (non-zero tags only; "" if none)
    tag_counts: str = ""
    # replacement bookkeeping (replace.py): for selection_role == "replacement", the sha of
    # the excluded effective row this reserve candidate was promoted to replace
    replaces_sha256: str = ""
    # acquisition (filled by acquire.py; empty until then)
    stored_artifact_sha256: str = ""   # sha256 of the on-disk .zlib as stored (compressed)
    disarmed_local_sha256: str = ""    # sha256 of the DECOMPRESSED disarmed binary; only
                                       # fillable in an approved static-only isolated env
    s3_etag: str = ""
    content_length: int = 0
    download_status: str = ""      # "ok" | "missing" | "error:<msg>" | ""
    zlib_status: str = ""          # "ok" | "error:<msg>" | ""
    # downstream (filled by later stages)
    peatlas_status: str = ""
    independent_parser_status: str = ""
    evidence_status: str = ""
    exclusion_reason: str = ""


FIELDNAMES = [f.name for f in fields(ManifestRow)]


def format_tag_counts(tags: tuple[str, ...], counts: tuple[int, ...],
                      tag_names: tuple[str, ...] = TAGS) -> str:
    """Render raw per-tag counts as "name=count;..." for tags with a non-zero count.

    ``counts`` is aligned with ``tag_names`` (the order passed to read_candidates); the
    binarised ``tags`` tuple is used only to keep output limited to present tags.
    """
    if not counts:
        return ""
    present = set(tags)
    parts = [f"{n}={v}" for n, v in zip(tag_names, counts, strict=False) if v and n in present]
    return ";".join(parts)


def rows_from_selection(selection: dict[str, SplitSelection], *, seed: str,
                        tag_names: tuple[str, ...] = TAGS) -> list[ManifestRow]:
    rows: list[ManifestRow] = []
    for split in ("train", "validation", "test"):
        sel = selection.get(split)
        if sel is None:
            continue
        for role, group in (("primary", sel.selected), ("reserve", sel.reserve)):
            for c in group:
                rows.append(ManifestRow(
                    sorel_original_sha256=c.sha256,
                    official_split=c.split,
                    first_seen_timestamp=c.first_seen_t,
                    tags=";".join(c.tags),
                    detection_count=c.detection_count,
                    tag_counts=format_tag_counts(c.tags, c.tag_counts, tag_names),
                    selection_seed=seed,
                    selection_role=role,
                ))
    return rows


def write_manifest(path: str | Path, rows: list[ManifestRow]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        for r in rows:
            writer.writerow(asdict(r))


def read_manifest(path: str | Path) -> list[ManifestRow]:
    out: list[ManifestRow] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for d in csv.DictReader(fh):
            out.append(ManifestRow(
                sorel_original_sha256=d["sorel_original_sha256"],
                official_split=d["official_split"],
                first_seen_timestamp=float(d["first_seen_timestamp"]),
                tags=d.get("tags", ""),
                detection_count=int(d.get("detection_count") or 0),
                tag_counts=d.get("tag_counts", ""),
                replaces_sha256=d.get("replaces_sha256", ""),
                selection_seed=d.get("selection_seed", ""),
                selection_role=d.get("selection_role", ""),
                stored_artifact_sha256=d.get("stored_artifact_sha256", ""),
                disarmed_local_sha256=d.get("disarmed_local_sha256", ""),
                s3_etag=d.get("s3_etag", ""),
                content_length=int(d.get("content_length") or 0),
                download_status=d.get("download_status", ""),
                zlib_status=d.get("zlib_status", ""),
                peatlas_status=d.get("peatlas_status", ""),
                independent_parser_status=d.get("independent_parser_status", ""),
                evidence_status=d.get("evidence_status", ""),
                exclusion_reason=d.get("exclusion_reason", ""),
            ))
    return out
