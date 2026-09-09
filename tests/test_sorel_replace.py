"""Tests for deterministic reserve replacement (amendment §6.3 / §8)."""

from __future__ import annotations

import pytest

from ua_sahi_mal.sorel.acquire import HeadResult, read_preflight_csv, write_preflight_csv
from ua_sahi_mal.sorel.manifest import ManifestRow, read_manifest, write_manifest
from ua_sahi_mal.sorel.replace import apply_replacements, effective_rows


def _row(sha_char: str, split: str, role: str, idx: int) -> ManifestRow:
    return ManifestRow(
        sorel_original_sha256=f"{sha_char * 62}{idx:02x}", official_split=split,
        first_seen_timestamp=0.0, tags="", detection_count=20, selection_seed="s",
        selection_role=role,
    )


def _manifest():
    rows = []
    # train: 4 primaries + 2 reserves; test: 2 primaries + 1 reserve (frozen order = list order)
    rows += [_row("a", "train", "primary", i) for i in range(4)]
    rows += [_row("b", "train", "reserve", i) for i in range(2)]
    rows += [_row("c", "test", "primary", i) for i in range(2)]
    rows += [_row("d", "test", "reserve", i) for i in range(1)]
    return rows


def _ok(sha):
    return HeadResult(sha, 100, "e", ok=True)


_NOT_FOUND = ("S3CommandError: aws exit 254: An error occurred (404) when calling the "
              "HeadObject operation: Not Found")


def _fail(sha, reason=_NOT_FOUND):
    return HeadResult(sha, 0, "", ok=False, error=reason)


def test_no_failures_no_change():
    rows = _manifest()
    heads = [_ok(r.sorel_original_sha256) for r in rows if r.selection_role == "primary"]
    new, rep = apply_replacements(rows, heads)
    assert rep.excluded == 0 and rep.promoted == 0
    assert [r.selection_role for r in new] == [r.selection_role for r in rows]
    assert len(effective_rows(new)) == 6


def test_failed_primary_excluded_and_first_reserve_promoted():
    rows = _manifest()
    prim = [r for r in rows if r.selection_role == "primary"]
    heads = [_ok(r.sorel_original_sha256) for r in prim]
    heads[1] = _fail(prim[1].sorel_original_sha256)          # train primary #1 fails
    new, rep = apply_replacements(rows, heads, stage="preflight")
    by = {r.sorel_original_sha256: r for r in new}
    failed = by[prim[1].sorel_original_sha256]
    assert failed.exclusion_reason.startswith("preflight:")
    assert "404" in failed.exclusion_reason
    # first train reserve (frozen order) promoted, pointing at the failed row
    first_reserve = [r for r in rows if r.official_split == "train" and r.selection_role == "reserve"][0]
    promoted = by[first_reserve.sorel_original_sha256]
    assert promoted.selection_role == "replacement"
    assert promoted.replaces_sha256 == prim[1].sorel_original_sha256
    # second train reserve untouched; test split untouched
    second_reserve = [r for r in rows if r.official_split == "train" and r.selection_role == "reserve"][1]
    assert by[second_reserve.sorel_original_sha256].selection_role == "reserve"
    assert rep.per_split["test"]["excluded"] == 0
    # effective count preserved (4 + 2)
    assert len(effective_rows(new)) == 6
    assert rep.reasons  # SHA-free reason bucket recorded
    # input not mutated
    assert rows[1].exclusion_reason == ""


def test_split_isolation_and_exhaustion():
    rows = _manifest()
    test_prim = [r for r in rows if r.official_split == "test" and r.selection_role == "primary"]
    heads = [_fail(r.sorel_original_sha256) for r in test_prim]   # both test primaries fail, 1 reserve
    new, rep = apply_replacements(rows, heads)
    assert rep.per_split["test"]["excluded"] == 2
    assert rep.per_split["test"]["promoted"] == 1
    assert rep.reserve_exhausted == ["test"]
    # train reserves must NOT be used for test failures
    assert all(r.selection_role == "reserve" for r in new
               if r.official_split == "train" and r.sorel_original_sha256.startswith("b"))


def test_iterative_replacement_chain():
    rows = _manifest()
    prim = [r for r in rows if r.selection_role == "primary"]
    # round 1: train primary #0 fails -> reserve b0 promoted
    new1, _ = apply_replacements(rows, [_fail(prim[0].sorel_original_sha256)])
    b0 = [r for r in new1 if r.selection_role == "replacement"][0]
    # round 2: the replacement itself fails -> reserve b1 promoted, chained
    new2, rep2 = apply_replacements(new1, [_fail(b0.sorel_original_sha256)])
    by = {r.sorel_original_sha256: r for r in new2}
    assert by[b0.sorel_original_sha256].exclusion_reason.startswith("preflight:")
    b1 = [r for r in new2 if r.selection_role == "replacement" and not r.exclusion_reason][0]
    assert b1.replaces_sha256 == b0.sorel_original_sha256
    assert rep2.per_split["train"]["reserve_remaining"] == 0
    # previously excluded primary stays excluded and is not double-counted
    assert by[prim[0].sorel_original_sha256].exclusion_reason
    assert rep2.excluded == 1


def test_masks_sha_in_reason():
    rows = _manifest()
    prim = rows[0]
    leaky = f"CalledProcessError: Command ['aws','--key','09-DEC-2020/binaries/{'f' * 64}'] returned 254"
    new, rep = apply_replacements(rows, [_fail(prim.sorel_original_sha256, leaky)])
    assert "f" * 64 not in new[0].exclusion_reason
    assert "<sha>" in new[0].exclusion_reason
    assert all("f" * 64 not in k for k in rep.reasons)


def test_manifest_roundtrip_with_replacement_fields(tmp_path):
    rows = _manifest()
    prim = rows[0]
    new, _ = apply_replacements(rows, [_fail(prim.sorel_original_sha256)])
    p = tmp_path / "eff.csv"
    write_manifest(str(p), new)
    back = read_manifest(str(p))
    rep = [r for r in back if r.selection_role == "replacement"][0]
    assert rep.replaces_sha256 == prim.sorel_original_sha256
    assert [r.exclusion_reason for r in back] == [r.exclusion_reason for r in new]


def test_preflight_csv_roundtrip(tmp_path):
    heads = [_ok("a" * 64), _fail("b" * 64)]
    p = tmp_path / "pf.csv"
    write_preflight_csv(str(p), heads)
    back = read_preflight_csv(str(p))
    assert [(h.sha256, h.ok, h.content_length) for h in back] == [("a" * 64, True, 100), ("b" * 64, False, 0)]
    assert "404" in back[1].error


@pytest.mark.parametrize("stage", ["preflight", "fetch", "static"])
def test_stage_label(stage):
    rows = _manifest()
    new, _ = apply_replacements(rows, [_fail(rows[0].sorel_original_sha256)], stage=stage)
    assert new[0].exclusion_reason.startswith(f"{stage}:")
