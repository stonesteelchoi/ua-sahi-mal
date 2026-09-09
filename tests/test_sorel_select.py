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


def test_read_candidates_path_with_space(iso_dir):
    """meta.db under a directory containing a space must open via a proper file URI."""
    d = iso_dir / "data dir"
    d.mkdir()
    p = d / "meta.db"
    _make_meta_db(str(p), n_per_split=3, benign=1)
    cands = read_candidates(str(p))
    assert len(cands) == 9


# --------------------------------------------------------------------------- #
# Preregistration fidelity (amendment §6.3, §9)
# --------------------------------------------------------------------------- #
def test_count_tertiles_and_strata_coverage(meta_db):
    from ua_sahi_mal.sorel.select import COUNT_STRATA, count_stratum, count_tertiles

    sel = select(meta_db, seed="seed-A", targets={"train": 20})
    tr = sel["train"]
    t1, t2 = tr.count_tertiles
    assert tr.pool_size == 40
    assert t1 <= t2
    # every count stratum is represented among the picks (round-robin covers it)
    covered = {count_stratum(c, (t1, t2)) for c in tr.selected}
    assert covered == set(COUNT_STRATA)
    # boundaries derive from the pool only (seed-independent)
    pool_tertiles = count_tertiles([c for c in read_candidates(meta_db) if c.split == "train"])
    assert pool_tertiles == (t1, t2)
    sel_b = select(meta_db, seed="seed-B", targets={"train": 20})
    assert sel_b["train"].count_tertiles == (t1, t2)


def test_raw_tag_counts_preserved(meta_db):
    cands = read_candidates(meta_db)
    assert all(len(c.tag_counts) == len(TAGS) for c in cands)
    # binarised tags == names with non-zero raw count
    for c in cands:
        assert c.tags == tuple(t for t, v in zip(TAGS, c.tag_counts, strict=True) if v)


def test_manifest_tag_counts_roundtrip(tmp_path, meta_db):
    from ua_sahi_mal.sorel.manifest import format_tag_counts

    sel = select(meta_db, seed="seed-A", targets={"train": 10})
    rows = rows_from_selection(sel, seed="seed-A")
    # tagged rows carry name=count pairs; untagged rows carry ""
    for r in rows:
        if r.tags:
            assert r.tag_counts and all("=" in part for part in r.tag_counts.split(";"))
            names = {part.split("=")[0] for part in r.tag_counts.split(";")}
            assert names == set(r.tags.split(";"))
        else:
            assert r.tag_counts == ""
    out = tmp_path / "m.csv"
    write_manifest(str(out), rows)
    back = read_manifest(str(out))
    assert [b.tag_counts for b in back] == [r.tag_counts for r in rows]
    assert format_tag_counts(("adware", "packed"), (3, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0)) == "adware=3;packed=1"


def test_run_record_written_isolated(iso_dir, meta_db):
    from ua_sahi_mal.sorel.record import build_run_record, file_identity, write_run_record

    rec = build_run_record("sorel_selection", seed="s", targets={"train": 1},
                           meta_db=file_identity(meta_db))
    assert rec["record_kind"] == "sorel_selection"
    assert rec["timestamp_utc"].endswith("+00:00")
    assert isinstance(rec["code_commit"], str) and rec["code_commit"]
    assert rec["meta_db"]["size_bytes"] > 0
    out = write_run_record(iso_dir / "sel_record.json", rec)
    assert out.exists()
    import json
    assert json.loads(out.read_text(encoding="utf-8"))["seed"] == "s"


def test_run_record_refuses_repo(iso_dir):
    from ua_sahi_mal.sorel.record import build_run_record, write_run_record

    (iso_dir / ".git").mkdir()
    with pytest.raises(UnsafeOutputPathError):
        write_run_record(iso_dir / "r.json", build_run_record("x"))
