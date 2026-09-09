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
from pathlib import Path

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


COUNT_STRATA = ("__count_low__", "__count_mid__", "__count_high__")


@dataclass(frozen=True)
class Candidate:
    sha256: str
    first_seen_t: float
    split: str
    detection_count: int
    tags: tuple[str, ...]  # tags with non-zero count (binarised view, per SOREL guidance)
    # Original per-tag count values, aligned with the ``tags`` argument order given to
    # read_candidates (amendment §6.3: binarise for stratification, preserve raw values).
    tag_counts: tuple[int, ...] = ()

    def det_key(self, seed: str) -> str:
        return hashlib.sha256(f"{seed}||{self.sha256}".encode()).hexdigest()


@dataclass
class SplitSelection:
    split: str
    target: int
    selected: list[Candidate] = field(default_factory=list)
    reserve: list[Candidate] = field(default_factory=list)
    # detection-count tertile boundaries used for the count strata (low <= t1 < mid <= t2 < high),
    # derived deterministically from this split's candidate pool; recorded for preregistration.
    count_tertiles: tuple[int, int] = (0, 0)
    pool_size: int = 0


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def read_candidates(db_path: str, *, table: str = "meta",
                    tags: tuple[str, ...] = TAGS) -> list[Candidate]:
    """Read malware candidates from meta.db (read-only). No network, no binaries."""
    # Build a proper file:// URI (as_uri handles Windows drive letters / backslashes
    # and percent-encoding) so read-only mode works identically on cau and Linux.
    uri = Path(db_path).expanduser().resolve().as_uri() + "?mode=ro"
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
            raw_counts = tuple(int(v or 0) for v in row[3:])
            row_tags = tuple(t for t, v in zip(tags, raw_counts, strict=True) if v)
            out.append(Candidate(sha, fst, official_split(fst), det, row_tags, raw_counts))
        return out
    finally:
        conn.close()


def count_tertiles(pool: list[Candidate]) -> tuple[int, int]:
    """Deterministic detection-count tertile boundaries (t1, t2) for a candidate pool.

    ``low``: count <= t1, ``mid``: t1 < count <= t2, ``high``: count > t2. Boundaries are
    the 1/3 and 2/3 order statistics of the pool's detection counts, so they depend only
    on meta.db content (reproducible), not on the seed.
    """
    counts = sorted(c.detection_count for c in pool)
    if not counts:
        return (0, 0)
    n = len(counts)
    t1 = counts[min(n - 1, n // 3)]
    t2 = counts[min(n - 1, (2 * n) // 3)]
    return (t1, t2)


def count_stratum(c: Candidate, tertiles: tuple[int, int]) -> str:
    t1, t2 = tertiles
    if c.detection_count <= t1:
        return "__count_low__"
    if c.detection_count <= t2:
        return "__count_mid__"
    return "__count_high__"


def _stratified_pick(pool: list[Candidate], target: int, seed: str,
                     tags: tuple[str, ...]) -> tuple[list[Candidate], list[Candidate], tuple[int, int]]:
    """Deterministic multi-stratum round-robin pick + deterministic reserve.

    Ordered by det_key = SHA256(seed || sha). A round-robin over strata fills slots to
    spread coverage; strata are the behavioural tags, a no-tag stratum, and the
    detection-count tertiles (amendment §6.3: consider tags and detection-count
    low/mid/high together). Remaining slots and a 20% reserve are taken in det order.
    Fully deterministic in ``seed`` (tertile boundaries depend only on the pool).
    """
    ordered = sorted(pool, key=lambda c: c.det_key(seed))
    used: set[str] = set()
    picked: list[Candidate] = []
    tertiles = count_tertiles(pool)

    strata: list[str] = [*tags, "__no_tag__", *COUNT_STRATA]

    def _match(c: Candidate, stratum: str) -> bool:
        if stratum == "__no_tag__":
            return not c.tags
        if stratum in COUNT_STRATA:
            return count_stratum(c, tertiles) == stratum
        return stratum in c.tags

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
                if _match(c, stratum):
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
    return picked, reserve, tertiles


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
        sel = SplitSelection(split=split, target=target, pool_size=len(by_split[split]))
        if target > 0:
            sel.selected, sel.reserve, sel.count_tertiles = _stratified_pick(
                by_split[split], target, seed, tags)
        result[split] = sel
    return result
