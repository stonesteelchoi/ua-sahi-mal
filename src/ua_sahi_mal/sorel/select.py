"""Deterministic, stratified sample selection from the SOREL-20M ``meta.db``.

This module never downloads a binary. It reads only the metadata sqlite
(``processed-data/meta.db``) and produces a **frozen, deterministic** selection
manifest per the SOREL amendment (§5/§6). Actual acquisition is a separate,
gated step (see ``acquire.py``).

Schema assumptions (SOREL ``meta`` table; verified against the official
dataset.py): columns ``sha256``, ``is_malware``, ``rl_fs_t`` (first-seen time),
``rl_ls_const_positives`` (detection count), and one integer column per tag. The
code introspects the table and fails loudly if an expected column is missing.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, field

# Official temporal split boundaries (SOREL config.py). Do not change: altering
# them makes results incomparable to official SOREL.
TRAIN_VALIDATION_SPLIT = 1543542570.0
VALIDATION_TEST_SPLIT = 1547279640.0

TAGS = (
    "adware", "flooder", "ransomware", "dropper", "spyware", "packed",
    "crypto_miner", "file_infector", "installer", "worm", "downloader",
)
SPLITS = ("train", "validation", "test")


def official_split(first_seen_t: float) -> str:
    if first_seen_t < TRAIN_VALIDATION_SPLIT:
        return "train"
    if first_seen_t < VALIDATION_TEST_SPLIT:
        return "validation"
    return "test"


@dataclass(frozen=True)
class Candidate:
    sha256: str
    first_seen_t: float
    split: str
    detection_count: int
    tags: tuple[str, ...]  # tags with non-zero count

    def det_key(self, seed: str) -> str:
        return hashlib.sha256(f"{seed}||{self.sha256}".encode()).hexdigest()


@dataclass
class SplitSelection:
    split: str
    target: int
    selected: list[Candidate] = field(default_factory=list)
    reserve: list[Candidate] = field(default_factory=list)


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def read_candidates(db_path: str, *, table: str = "meta",
                    tags: tuple[str, ...] = TAGS) -> list[Candidate]:
    """Read malware candidates from meta.db (read-only). No network, no binaries."""
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        cols = _table_columns(conn, table)
        required = {"sha256", "is_malware", "rl_fs_t", "rl_ls_const_positives", *tags}
        missing = required - cols
        if missing:
            raise ValueError(f"meta.db table {table!r} missing expected columns: {sorted(missing)}")
        select_cols = ["sha256", "rl_fs_t", "rl_ls_const_positives", *tags]
        query = f"SELECT {', '.join(select_cols)} FROM {table} WHERE is_malware = 1"  # noqa: S608 (fixed names)
        out: list[Candidate] = []
        for row in conn.execute(query):
            sha, fst, det = row[0], float(row[1]), int(row[2] or 0)
            row_tags = tuple(t for t, v in zip(tags, row[3:], strict=True) if v)
            out.append(Candidate(sha, fst, official_split(fst), det, row_tags))
        return out
    finally:
        conn.close()


def _stratified_pick(pool: list[Candidate], target: int, seed: str,
                     tags: tuple[str, ...]) -> tuple[list[Candidate], list[Candidate]]:
    """Deterministic tag-round-robin pick + deterministic reserve.

    Ordered by det_key. A round-robin over tags (and a no-tag stratum) fills slots
    to spread coverage; remaining slots and a 20% reserve are taken in det order.
    Fully deterministic in ``seed``.
    """
    ordered = sorted(pool, key=lambda c: c.det_key(seed))
    used: set[str] = set()
    picked: list[Candidate] = []

    strata: list[str] = [*tags, "__no_tag__"]
    # round-robin coverage pass
    progressed = True
    while len(picked) < target and progressed:
        progressed = False
        for stratum in strata:
            if len(picked) >= target:
                break
            for c in ordered:
                if c.sha256 in used:
                    continue
                match = (not c.tags) if stratum == "__no_tag__" else (stratum in c.tags)
                if match:
                    used.add(c.sha256)
                    picked.append(c)
                    progressed = True
                    break
    # fill remaining in det order
    for c in ordered:
        if len(picked) >= target:
            break
        if c.sha256 not in used:
            used.add(c.sha256)
            picked.append(c)
    # reserve: next 20% in det order
    reserve_target = (target + 4) // 5
    reserve: list[Candidate] = []
    for c in ordered:
        if len(reserve) >= reserve_target:
            break
        if c.sha256 not in used:
            used.add(c.sha256)
            reserve.append(c)
    # deterministic output order = det_key
    picked.sort(key=lambda c: c.det_key(seed))
    reserve.sort(key=lambda c: c.det_key(seed))
    return picked, reserve


def select(db_path: str, *, seed: str, targets: dict[str, int],
           tags: tuple[str, ...] = TAGS, table: str = "meta") -> dict[str, SplitSelection]:
    """Produce a frozen deterministic selection per official split.

    ``targets`` maps split -> desired count (e.g. {"train":180,"validation":60,"test":60}).
    Selection and reserve are deterministic in ``seed``; no binaries are fetched.
    """
    candidates = read_candidates(db_path, table=table, tags=tags)
    by_split: dict[str, list[Candidate]] = {s: [] for s in SPLITS}
    for c in candidates:
        by_split[c.split].append(c)

    result: dict[str, SplitSelection] = {}
    for split in SPLITS:
        target = int(targets.get(split, 0))
        sel = SplitSelection(split=split, target=target)
        if target > 0:
            sel.selected, sel.reserve = _stratified_pick(by_split[split], target, seed, tags)
        result[split] = sel
    return result
