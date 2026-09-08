"""Shared pytest fixtures."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture()
def iso_dir() -> Iterator[Path]:
    """A temp directory OUTSIDE any repo/sync tree, for isolated-path guard tests.

    The repo's pytest config sets ``--basetemp=.pytest_tmp`` (inside the repo), so
    the built-in ``tmp_path`` lives inside the repository tree and would trip the
    SOREL isolated-path guards (``ua_sahi_mal.sorel.paths``). This fixture yields an
    OS-temp directory (outside the repo and any sync folder) so those guards behave
    as they would in real operator use.
    """
    d = Path(tempfile.mkdtemp(prefix="sorel-iso-"))
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)
