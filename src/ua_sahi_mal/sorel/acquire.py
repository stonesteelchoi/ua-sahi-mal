"""Gated acquisition of SOREL-20M disarmed binaries (amendment §6).

This module NEVER downloads by importing it. Acquisition is explicitly gated:

  1. Terms acknowledgement is required (``terms_accepted=True``). The caller must
     have accepted the SOREL Terms; without the flag, ``fetch`` refuses.
  2. The destination directory must be an approved isolated data path — not a
     repository tree and not a cloud-sync folder (see ``paths``).
  3. A byte budget cap is enforced against the preflight ``ContentLength`` sum;
     the download refuses to exceed it.
  4. Binaries are kept **zlib-compressed** exactly as served. This module never
     decompresses and never re-arms (Machine/Subsystem stay zeroed). Decompression
     happens only later, in an approved static-only isolated environment, by other
     code — never here.

The S3 access itself is abstracted behind a small client protocol so the logic is
fully unit-testable without any network. The default ``AwsCliClient`` shells out
to the AWS CLI with ``--no-sign-request`` and is only exercised on the operator's
isolated machine (cau), never in the ephemeral cloud session.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .paths import assert_isolated_binary_dir

BUCKET = "sorel-20m"
KEY_PREFIX = "09-DEC-2020/binaries"
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class AwsCliNotFoundError(RuntimeError):
    """Raised when the AWS CLI executable cannot be resolved on PATH (or via --aws-bin)."""


class TermsNotAcceptedError(RuntimeError):
    """Raised when acquisition is attempted without an explicit Terms acknowledgement."""


class BudgetExceededError(RuntimeError):
    """Raised when the preflighted byte total would exceed the configured cap."""


def validate_sha(sha: str) -> str:
    s = sha.strip().lower()
    if not _SHA_RE.match(s):
        raise ValueError(f"not a 64-hex sha256: {sha!r}")
    return s


def s3_key(sha: str, *, key_prefix: str = KEY_PREFIX) -> str:
    return f"{key_prefix}/{validate_sha(sha)}"


@dataclass(frozen=True)
class HeadResult:
    sha256: str
    content_length: int
    etag: str
    ok: bool
    error: str = ""


@dataclass(frozen=True)
class FetchResult:
    sha256: str
    dest: str
    content_length: int
    stored_artifact_sha256: str
    download_status: str          # "ok" | "skipped:exists" | "error:<msg>"
    zlib_status: str = "ok"       # kept compressed; "ok" means stored as served


class S3Client(Protocol):
    """Minimal S3 surface needed for preflight + fetch. Injectable for tests."""

    def head_object(self, key: str) -> tuple[int, str]:
        """Return (content_length, etag) for ``key`` or raise on failure."""
        ...

    def download(self, key: str, dest: Path) -> None:
        """Download ``key`` to ``dest`` verbatim (no decompression)."""
        ...


# --------------------------------------------------------------------------- #
# Preflight + budget
# --------------------------------------------------------------------------- #
def preflight(shas: Iterable[str], client: S3Client, *,
              key_prefix: str = KEY_PREFIX) -> list[HeadResult]:
    """HEAD every sha; collect ContentLength + ETag. No bytes are downloaded."""
    results: list[HeadResult] = []
    for raw in shas:
        try:
            sha = validate_sha(raw)
        except ValueError as exc:
            results.append(HeadResult(str(raw), 0, "", ok=False, error=str(exc)))
            continue
        try:
            length, etag = client.head_object(f"{key_prefix}/{sha}")
            results.append(HeadResult(sha, int(length), str(etag), ok=True))
        except Exception as exc:  # noqa: BLE001 - surfaced to caller as a status
            results.append(HeadResult(sha, 0, "", ok=False, error=f"{type(exc).__name__}: {exc}"))
    return results


def budget_total(results: Iterable[HeadResult]) -> int:
    return sum(r.content_length for r in results if r.ok)


def assert_within_budget(results: Iterable[HeadResult], *, max_bytes: int) -> int:
    total = budget_total(results)
    if total > max_bytes:
        raise BudgetExceededError(
            f"preflighted total {total} bytes exceeds budget {max_bytes} bytes; "
            "reduce the selection or raise the cap deliberately."
        )
    return total


# --------------------------------------------------------------------------- #
# Gated fetch
# --------------------------------------------------------------------------- #
def _sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(shas: Iterable[str], client: S3Client, dest_dir: str | Path, *,
          terms_accepted: bool,
          max_bytes: int,
          preflighted: list[HeadResult] | None = None,
          key_prefix: str = KEY_PREFIX,
          overwrite: bool = False) -> list[FetchResult]:
    """Download the selected shas into an isolated directory, kept zlib-compressed.

    Gates (all enforced before any byte is fetched):
      * ``terms_accepted`` must be True.
      * ``dest_dir`` must pass the isolated-path guard.
      * the preflighted byte total must be within ``max_bytes``.

    Files are written as ``<dest_dir>/<sha>.zlib`` exactly as served. This function
    never decompresses and never modifies bytes.
    """
    if not terms_accepted:
        raise TermsNotAcceptedError(
            "SOREL Terms not acknowledged; pass terms_accepted=True only after "
            "accepting the Terms. Acquisition refused."
        )
    dest = assert_isolated_binary_dir(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    sha_list = [validate_sha(s) for s in shas]

    heads = preflighted if preflighted is not None else preflight(sha_list, client, key_prefix=key_prefix)
    head_by_sha = {h.sha256: h for h in heads}
    assert_within_budget([head_by_sha[s] for s in sha_list if s in head_by_sha and head_by_sha[s].ok],
                         max_bytes=max_bytes)

    results: list[FetchResult] = []
    for sha in sha_list:
        target = dest / f"{sha}.zlib"
        head = head_by_sha.get(sha)
        clen = head.content_length if head and head.ok else 0
        if target.exists() and not overwrite:
            results.append(FetchResult(
                sha256=sha, dest=str(target), content_length=clen,
                stored_artifact_sha256=_sha256_of_file(target),
                download_status="skipped:exists",
            ))
            continue
        try:
            client.download(f"{key_prefix}/{sha}", target)
            results.append(FetchResult(
                sha256=sha, dest=str(target),
                content_length=clen or (target.stat().st_size if target.exists() else 0),
                stored_artifact_sha256=_sha256_of_file(target),
                download_status="ok",
            ))
        except Exception as exc:  # noqa: BLE001 - recorded as a status, not fatal
            results.append(FetchResult(
                sha256=sha, dest=str(target), content_length=clen,
                stored_artifact_sha256="",
                download_status=f"error:{type(exc).__name__}: {exc}",
                zlib_status="",
            ))
    return results


# --------------------------------------------------------------------------- #
# Default client: AWS CLI, --no-sign-request. Only runs on the operator machine.
# --------------------------------------------------------------------------- #
def resolve_aws_binary(aws: str = "aws") -> str:
    """Resolve the AWS CLI executable once, up front, with an actionable error.

    Without this, a missing/unreachable ``aws`` surfaces as one identical
    ``FileNotFoundError: [WinError 2]`` per SHA (300 times on the pilot) — e.g. when the
    shell was opened before the CLI was installed and its PATH is stale.
    """
    found = shutil.which(aws)
    if found is None:
        raise AwsCliNotFoundError(
            f"AWS CLI executable {aws!r} not found on PATH. Install AWS CLI v2, open a NEW shell "
            "(or refresh PATH: $env:Path += ';C:\\Program Files\\Amazon\\AWSCLIV2'), or pass "
            "--aws-bin with the full path to aws.exe."
        )
    return found


def parse_head_object_json(stdout: str) -> tuple[int, str]:
    """Parse ``aws s3api head-object --output json`` into (content_length, etag).

    Kept as a pure function so the real CLI output shape is unit-testable without
    any network or subprocess. ETag is returned without its surrounding quotes.
    """
    doc = json.loads(stdout)
    try:
        length = int(doc["ContentLength"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"head-object JSON missing/invalid ContentLength: {exc}") from exc
    etag = str(doc.get("ETag", "")).strip().strip('"')
    return length, etag


class AwsCliClient:
    """S3 access via the AWS CLI with anonymous (``--no-sign-request``) reads.

    Instantiating this does nothing; network happens only on method calls, which
    are made solely on the operator's isolated machine.
    """

    def __init__(self, bucket: str = BUCKET, *, aws: str = "aws") -> None:
        self.bucket = bucket
        self.aws = resolve_aws_binary(aws)

    def head_object(self, key: str) -> tuple[int, str]:
        # Ask for JSON and parse it here rather than shaping output with a JMESPath
        # --query: a backtick tab literal (`\t`) is not valid JMESPath JSON and
        # silently drops the separator, which broke ContentLength parsing.
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [self.aws, "s3api", "head-object", "--bucket", self.bucket, "--key", key,
             "--no-sign-request", "--output", "json"],
            capture_output=True, text=True, check=True,
        )
        return parse_head_object_json(proc.stdout)

    def download(self, key: str, dest: Path) -> None:
        subprocess.run(  # noqa: S603 - fixed argv, no shell
            [self.aws, "s3", "cp", f"s3://{self.bucket}/{key}", str(dest),
             "--no-sign-request", "--only-show-errors"],
            check=True,
        )
