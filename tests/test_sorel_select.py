"""Network-free tests for deterministic SOREL-20M selection and manifest I/O."""

from __future__ import annotations

import sqlite3

import pytest

from ua_sahi_mal.sorel.manifest import read_manifest, rows_from_selection, write_manifest
from ua_sahi_mal.sorel.paths import UnsafeOutputPathError, assert_isolated_output
from ua_sahi_mal.sorel.select import (
    TAGS,
    TRAIN_VALIDATION_SPLIT,
    VALIDATION_TEST_SPLIT,
    official_split,
    read_candidates,
    select,
)


def _make_meta_db(path, n_per_split=40, benign=10):
    """Create a synthetic meta.db mimicking the SOREL 'meta' table."""
    conn = sqlite3.connect(path)
    cols = ["sha256 TEXT", "is_malware INTEGER", "rl_fs_t REAL",
            "rl_ls_const_positives INTEGER", *[f"{t} INTEGER" for t in TAGS]]
    conn.execute(f"CREATE TABLE meta ({', '.join(cols)})")

    # deterministic timestamps inside each official split window
    windows = {
        "train": TRAIN_VALIDATION_SPLIT - 1_000_000,
        "validation": (TRAIN_VALIDATION_SPLIT + VALIDATION_TEST_SPLIT) / 2,
        "test": VALIDATION_TEST_SPLIT + 1_000_000,
    }
    rows = []
    idx = 0
    for _split, base_t in windows.items():
        for i in range(n_per_split):
            sha = f"{idx:064x}"
            tagvals = [0] * len(TAGS)
            # give each row 0..2 tags in a rotating pattern (some rows have none)
            if i % 5 != 0:
                tagvals[i % len(TAGS)] = 1
            if i % 7 == 0:
                tagvals[(i + 3) % len(TAGS)] = 1
            rows.append((sha, 1, float(base_t + i), i % 60, *tagvals))
            idx += 1
        # benign rows in the same window that must be excluded
        for _ in range(benign):
            sha = f"{idx:064x}"
            rows.append((sha, 0, float(base_t), 0, *([0] * len(TAGS))))
            idx += 1

    placeholders = ", ".join(["?"] * (4 + len(TAGS)))
    conn.executemany(f"INSERT INTO meta VALUES ({placeholders})", rows)
    conn.commit()
    conn.close()


@pytest.fixture()
def meta_db(tmp_path):
    p = tmp_path / "meta.db"
    _make_meta_db(str(p))
    return str(p)


def test_official_split_boundaries():
    assert official_split(TRAIN_VALIDATION_SPLIT - 1) == "train"
    assert official_split(TRAIN_VALIDATION_SPLIT) == "validation"
    assert official_split(VALIDATION_TEST_SPLIT - 1) == "validation"
    assert official_split(VALIDATION_TEST_SPLIT) == "test"


def test_read_candidates_malware_only(meta_db):
    cands = read_candidates(meta_db)
    assert cands, "expected some candidates"
    # 40 malware per split * 3 splits = 120 (benign excluded)
    assert len(cands) == 120
    assert all(len(c.sha256) == 64 for c in cands)


def test_read_candidates_missing_column(tmp_path):
    p = tmp_path / "bad.db"
    conn = sqlite3.connect(str(p))
    conn.execute("CREATE TABLE meta (sha256 TEXT, is_malware INTEGER)")
    conn.commit()
    conn.close()
    with pytest.raises(ValueError, match="missing expected columns"):
        read_candidates(str(p))


def test_selection_deterministic(meta_db):
    t = {"train": 20, "validation": 10, "test": 10}
    a = select(meta_db, seed="seed-A", targets=t)
    b = select(meta_db, seed="seed-A", targets=t)
    for s in ("train", "validation", "test"):
        assert [c.sha256 for c in a[s].selected] == [c.sha256 for c in b[s].selected]
        assert [c.sha256 for c in a[s].reserve] == [c.sha256 for c in b[s].reserve]


def test_selection_seed_sensitive(meta_db):
    t = {"train": 20, "validation": 10, "test": 10}
    a = select(meta_db, seed="seed-A", targets=t)
    b = select(meta_db, seed="seed-B", targets=t)
    # different seed should reorder/repick at least one split's primary set
    same = all(
        [c.sha256 for c in a[s].selected] == [c.sha256 for c in b[s].selected]
        for s in ("train", "validation", "test")
    )
    assert not same


def test_counts_reserve_and_no_dup(meta_db):
    t = {"train": 20, "validation": 10, "test": 10}
    sel = select(meta_db, seed="seed-A", targets=t)
    for s, target in t.items():
        chosen = sel[s].selected
        reserve = sel[s].reserve
        assert len(chosen) == target
        # reserve is ceil(0.2 * target)
        assert len(reserve) == (target + 4) // 5
        ids = [c.sha256 for c in (*chosen, *reserve)]
        assert len(ids) == len(set(ids)), "primary and reserve must be disjoint, no dups"
        # every selected row belongs to its official split
        assert all(c.split == s for c in (*chosen, *reserve))


def test_selection_all_malware(meta_db):
    sel = select(meta_db, seed="seed-A", targets={"train": 30})
    # every candidate came from is_malware=1 rows (read_candidates enforces this)
    assert len(sel["train"].selected) == 30


def test_stratification_spreads_tags(meta_db):
    sel = select(meta_db, seed="seed-A", targets={"train": 20})
    covered = set()
    for c in sel["train"].selected:
        covered.update(c.tags)
    # round-robin should touch several distinct tag strata, not collapse to one
    assert len(covered) >= 5


def test_manifest_roundtrip(tmp_path, meta_db):
    sel = select(meta_db, seed="seed-A", targets={"train": 10, "validation": 5, "test": 5})
    rows = rows_from_selection(sel, seed="seed-A")
    assert rows
    # roles present
    roles = {r.selection_role for r in rows}
    assert roles == {"primary", "reserve"}
    out = tmp_path / "manifest.csv"
    write_manifest(str(out), rows)
    back = read_manifest(str(out))
    assert len(back) == len(rows)
    assert back[0].sorel_original_sha256 == rows[0].sorel_original_sha256
    assert back[0].official_split == rows[0].official_split
    # acquisition columns start empty
    assert back[0].download_status == ""
    assert back[0].stored_artifact_sha256 == ""


def test_isolated_output_refuses_repo(iso_dir):
    # simulate a repo root
    (iso_dir / ".git").mkdir()
    with pytest.raises(UnsafeOutputPathError, match="repository tree"):
        assert_isolated_output(iso_dir / "sub" / "selected_sha256.txt")


def test_isolated_output_refuses_sync_folder(iso_dir):
    d = iso_dir / "OneDrive" / "data"
    d.mkdir(parents=True)
    with pytest.raises(UnsafeOutputPathError, match="cloud-sync"):
        assert_isolated_output(d / "manifest.csv")


def test_isolated_output_accepts_plain_path(iso_dir):
    d = iso_dir / "sorel20m-private"
    d.mkdir()
    resolved = assert_isolated_output(d / "manifest.csv")
    assert resolved.name == "manifest.csv"
