"""Network-free tests for gated SOREL-20M acquisition (fake S3 client)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ua_sahi_mal.sorel.acquire import (
    BudgetExceededError,
    HeadResult,
    TermsNotAcceptedError,
    assert_within_budget,
    budget_total,
    fetch,
    preflight,
    s3_key,
    validate_sha,
)
from ua_sahi_mal.sorel.paths import UnsafeOutputPathError

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_BAD = "notahash"


class FakeS3:
    """In-memory S3: maps key -> bytes. Records calls; no network."""

    def __init__(self, objects: dict[str, bytes]):
        self.objects = objects
        self.head_calls: list[str] = []
        self.download_calls: list[str] = []

    def head_object(self, key: str) -> tuple[int, str]:
        self.head_calls.append(key)
        if key not in self.objects:
            raise KeyError(f"no such key: {key}")
        data = self.objects[key]
        etag = hashlib.md5(data).hexdigest()  # noqa: S324 - test-only etag stand-in
        return len(data), etag

    def download(self, key: str, dest: Path) -> None:
        self.download_calls.append(key)
        dest.write_bytes(self.objects[key])


def _client():
    return FakeS3({
        s3_key(SHA_A): b"zlib-compressed-disarmed-A" * 4,
        s3_key(SHA_B): b"zlib-compressed-disarmed-B" * 8,
    })


def test_validate_sha():
    assert validate_sha("A" * 64) == "a" * 64
    with pytest.raises(ValueError, match="64-hex"):
        validate_sha(SHA_BAD)


def test_s3_key_shape():
    assert s3_key(SHA_A) == f"09-DEC-2020/binaries/{SHA_A}"


def test_preflight_reports_lengths_and_bad():
    c = _client()
    res = preflight([SHA_A, SHA_B, SHA_BAD], c)
    by = {r.sha256: r for r in res}
    assert by[SHA_A].ok and by[SHA_A].content_length > 0
    assert by[SHA_B].ok and by[SHA_B].content_length > 0
    # bad sha recorded as not-ok, and never HEADed
    assert not by[SHA_BAD].ok
    assert all(SHA_BAD not in k for k in c.head_calls)


def test_preflight_missing_object():
    c = FakeS3({})
    res = preflight([SHA_A], c)
    assert not res[0].ok
    assert "KeyError" in res[0].error


def test_budget_helpers():
    heads = [HeadResult(SHA_A, 100, "e", ok=True), HeadResult(SHA_B, 250, "e", ok=True),
             HeadResult(SHA_BAD, 0, "", ok=False, error="x")]
    assert budget_total(heads) == 350
    assert assert_within_budget(heads, max_bytes=350) == 350
    with pytest.raises(BudgetExceededError):
        assert_within_budget(heads, max_bytes=349)


def test_fetch_requires_terms(tmp_path):
    c = _client()
    with pytest.raises(TermsNotAcceptedError):
        fetch([SHA_A], c, tmp_path / "iso", terms_accepted=False, max_bytes=10**9)
    assert c.download_calls == []


def test_fetch_refuses_repo_dest(tmp_path):
    (tmp_path / ".git").mkdir()
    c = _client()
    with pytest.raises(UnsafeOutputPathError, match="repository tree"):
        fetch([SHA_A], c, tmp_path / "compressed", terms_accepted=True, max_bytes=10**9)
    assert c.download_calls == []


def test_fetch_refuses_sync_dest(tmp_path):
    c = _client()
    dest = tmp_path / "Dropbox" / "compressed"
    with pytest.raises(UnsafeOutputPathError, match="cloud-sync"):
        fetch([SHA_A], c, dest, terms_accepted=True, max_bytes=10**9)
    assert c.download_calls == []


def test_fetch_enforces_budget_before_download(tmp_path):
    c = _client()
    dest = tmp_path / "sorel-private" / "compressed"
    with pytest.raises(BudgetExceededError):
        fetch([SHA_A, SHA_B], c, dest, terms_accepted=True, max_bytes=1)
    # budget checked before any byte is fetched
    assert c.download_calls == []
    assert not dest.exists() or not any(dest.iterdir())


def test_fetch_stores_compressed_verbatim(tmp_path):
    c = _client()
    dest = tmp_path / "sorel-private" / "compressed"
    res = fetch([SHA_A, SHA_B], c, dest, terms_accepted=True, max_bytes=10**9)
    assert {r.download_status for r in res} == {"ok"}
    for r in res:
        p = Path(r.dest)
        assert p.exists()
        assert p.suffix == ".zlib"
        # stored exactly as served (byte-identical, no decompression / re-arming)
        original = c.objects[s3_key(r.sha256)]
        assert p.read_bytes() == original
        # stored-artifact hash matches the on-disk bytes
        assert r.stored_artifact_sha256 == hashlib.sha256(original).hexdigest()


def test_fetch_skips_existing(tmp_path):
    c = _client()
    dest = tmp_path / "sorel-private" / "compressed"
    fetch([SHA_A], c, dest, terms_accepted=True, max_bytes=10**9)
    calls_after_first = list(c.download_calls)
    res = fetch([SHA_A], c, dest, terms_accepted=True, max_bytes=10**9)
    assert res[0].download_status == "skipped:exists"
    # no second download issued
    assert c.download_calls == calls_after_first


def test_fetch_records_error_status(tmp_path):
    c = FakeS3({s3_key(SHA_A): b"ok-bytes"})  # SHA_B absent
    dest = tmp_path / "sorel-private" / "compressed"
    # preflight will mark B not-ok, so budget uses only A; fetch of B errors on download
    res = fetch([SHA_A, SHA_B], c, dest, terms_accepted=True, max_bytes=10**9)
    by = {r.sha256: r for r in res}
    assert by[SHA_A].download_status == "ok"
    assert by[SHA_B].download_status.startswith("error:")
