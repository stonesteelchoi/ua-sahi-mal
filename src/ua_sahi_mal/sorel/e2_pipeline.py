"""E2 per-file pipeline (frozen: ``E2_prereg_v1``).

Runs entirely static and in memory: decompress the isolated ``<sha>.zlib``,
verify it is disarmed (Machine=0, Subsystem=0) and refuse otherwise, parse the
PE header, derive the overlay stratum, extract silver evidence, score every
selector, and scrub the decompressed buffer. The decompressed sample is never
written to disk. SHA appears only in the isolated per-file record; console
summaries are SHA-free.

The capa run (when enabled) is executed in a killable worker process with a hard
per-file timeout, so a pathological disassembly cannot stall the run.
"""

from __future__ import annotations

import multiprocessing as mp
import zlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

import numpy as np

from ua_sahi_mal.peatlas import PeAtlas, PeFormatError, parse_pe
from ua_sahi_mal.sorel.e2_select import evaluate_file
from ua_sahi_mal.sorel.e2_silver import CapaUnavailable, _default_capa_runner, build_silver
from ua_sahi_mal.sorel.e2_tiles import BUDGETS, DEFAULT_GEOMETRY, Geometry, per_tile_entropy
from ua_sahi_mal.sorel.paths import assert_isolated_binary_dir
from ua_sahi_mal.sorel.static_stage import StaticOnlyNotAcknowledgedError, verify_disarmed

OVERLAY_DOMINANT_THRESHOLD = 0.50


# --------------------------------------------------------------------------
# hard per-file capa timeout (killable worker process)
# --------------------------------------------------------------------------


def _capa_worker(queue, data: bytes, image_base: int, rules_path: str | None,
                 work_dir: str | None) -> None:  # pragma: no cover - child proc
    try:
        matches = _default_capa_runner(data, timeout=0, image_base=image_base,
                                       rules_path=rules_path, work_dir=work_dir)
        queue.put(("ok", matches))
    except BaseException as exc:  # noqa: BLE001 - report everything to the parent
        queue.put(("err", f"{type(exc).__name__}: {exc}"))


def make_capa_runner(*, timeout: int, rules_path: str | None = None, work_dir: str | None = None):
    """A capa runner that enforces ``timeout`` seconds per file by running the
    capa analysis in a spawned process and terminating it on overrun. capa writes
    the sample to disk (vivisect backend), so it is confined to the isolated
    ``work_dir`` and refuses without one. Raises :class:`CapaUnavailable` on
    timeout/refusal/worker error, recorded as a per-file status without failing
    the run."""
    context = mp.get_context("spawn")

    def runner(data: bytes, *, timeout: int = timeout, image_base: int,
               work_dir: str | None = work_dir):  # noqa: A002
        queue = context.Queue()
        process = context.Process(target=_capa_worker, args=(queue, data, image_base, rules_path, work_dir))
        process.start()
        process.join(timeout)
        if process.is_alive():  # pragma: no cover - timing dependent
            process.terminate()
            process.join()
            raise CapaUnavailable(f"timeout>{timeout}s")
        if queue.empty():  # pragma: no cover - worker died silently
            raise CapaUnavailable("capa worker produced no result")
        status, payload = queue.get()
        if status == "ok":
            return payload
        raise CapaUnavailable(str(payload))

    return runner


# --------------------------------------------------------------------------
# per-file record
# --------------------------------------------------------------------------


@dataclass
class E2FileResult:
    sorel_original_sha256: str         # private; only in the isolated record
    ok: bool = False
    exclusion_reason: str = ""
    file_size: int = 0
    is_pe32_plus: bool = False
    overlay_offset: int = 0
    overlay_share: float = 0.0
    stratum: str = ""                  # overlay_dominant | non_dominant
    silver: dict[str, object] = field(default_factory=dict)
    evaluation: dict[str, object] = field(default_factory=dict)

    def public_summary(self, case_id: str) -> str:
        if not self.ok:
            return f"{case_id}: EXCLUDED {self.exclusion_reason}"
        silver_bytes = self.evaluation.get("silver_bytes", 0)
        capa = self.silver.get("capa_status", "?")
        yara = self.silver.get("yara_status", "?")
        return (f"{case_id}: {self.stratum} pe32+={self.is_pe32_plus} "
                f"overlay_share={self.overlay_share:.3f} silver_bytes={silver_bytes} "
                f"embedded={self.silver.get('embedded_count', 0)} yara={yara} capa={capa}")


def _silver_public(silver) -> dict[str, object]:
    return {
        "embedded_count": silver.embedded_count,
        "yara_status": silver.yara_status,
        "yara_meta": silver.yara_meta,
        "capa_status": silver.capa_status,
        "capa_meta": silver.capa_meta,
        "silver_bytes": silver.silver_bytes,
        "n_union_regions": len(silver.union_intervals),
        # offsets are structural, sample-linked -> isolated record only
        "embedded_intervals": silver.embedded_intervals,
        "yara_intervals": silver.yara_intervals,
        "capa_intervals": silver.capa_intervals,
        "union_intervals": silver.union_intervals,
    }


def process_compressed(
    compressed: bytes,
    *,
    sha256: str,
    static_only: bool,
    enable_capa: bool = False,
    enable_yara: bool = False,
    capa_timeout: int = 300,
    capa_rules_path: str | None = None,
    capa_work_dir: str | None = None,
    capa_version: str = "",
    yara_rules_path: str | None = None,
    yara_matcher=None,
    geom: Geometry = DEFAULT_GEOMETRY,
    budgets: tuple[float, ...] = BUDGETS,
    seed: int = 0,
    overlay_threshold: float = OVERLAY_DOMINANT_THRESHOLD,
    capa_runner=None,
) -> E2FileResult:
    """Static-only E2 analysis of one zlib artefact (in memory)."""
    if not static_only:
        raise StaticOnlyNotAcknowledgedError(
            "refusing to decompress without static_only=True; run only in an isolated static context"
        )
    result = E2FileResult(sorel_original_sha256=sha256)
    try:
        data = zlib.decompress(compressed)
    except zlib.error as exc:
        result.exclusion_reason = f"decompress_error:{exc}"
        return result
    try:
        result.file_size = len(data)
        if not verify_disarmed(data):
            result.exclusion_reason = "armed:refused"     # never analyze a re-armed sample
            return result
        try:
            layout = parse_pe(data)
        except PeFormatError as exc:
            result.exclusion_reason = f"peatlas_error:{exc}"
            return result

        atlas = PeAtlas(layout)
        result.is_pe32_plus = layout.is_pe32_plus
        result.overlay_offset = layout.overlay_offset
        overlay_bytes = max(0, result.file_size - layout.overlay_offset) if layout.overlay_offset else 0
        result.overlay_share = overlay_bytes / result.file_size if result.file_size else 0.0
        result.stratum = "overlay_dominant" if result.overlay_share > overlay_threshold else "non_dominant"

        if enable_capa and capa_runner is None:
            capa_runner = make_capa_runner(timeout=capa_timeout, rules_path=capa_rules_path,
                                           work_dir=capa_work_dir)
        silver = build_silver(
            data, atlas, image_base=layout.image_base,
            enable_capa=enable_capa, enable_yara=enable_yara,
            capa_timeout=capa_timeout, capa_work_dir=capa_work_dir, capa_version=capa_version,
            capa_runner=capa_runner, yara_rules_path=yara_rules_path, yara_matcher=yara_matcher,
        )
        result.silver = _silver_public(silver)

        entropy = per_tile_entropy(np.frombuffer(data, dtype=np.uint8), geom)
        result.evaluation = evaluate_file(
            result.file_size, silver.union_intervals, entropy, geom=geom, budgets=budgets, seed=seed
        )
        result.ok = True
        return result
    finally:
        del data  # scrub the decompressed buffer reference


def process_dir(
    compressed_dir: str | Path,
    shas: Iterable[str],
    *,
    static_only: bool,
    enable_capa: bool,
    **kwargs,
) -> list[E2FileResult]:
    """Process ``<sha>.zlib`` files under an isolated directory."""
    root = assert_isolated_binary_dir(compressed_dir)
    out: list[E2FileResult] = []
    for sha in shas:
        path = root / f"{sha}.zlib"
        if not path.exists():
            res = E2FileResult(sorel_original_sha256=sha, exclusion_reason="missing:zlib_not_found")
            out.append(res)
            continue
        res = process_compressed(
            path.read_bytes(), sha256=sha, static_only=static_only, enable_capa=enable_capa, **kwargs
        )
        out.append(res)
    return out


def result_to_dict(result: E2FileResult) -> dict[str, object]:
    return asdict(result)
