import json
from pathlib import Path

from ua_sahi_mal.smoke import run_smoke


def test_synthetic_smoke_runs_end_to_end(tmp_path: Path) -> None:
    summary = run_smoke(tmp_path / "smoke")

    assert summary.prepared_samples == 2
    assert summary.full_sahi_detections == summary.budgeted_detections == 1
    assert summary.detector_call_reduction == 0.5
    assert summary.tile_recall == 1.0
    saved = json.loads((tmp_path / "smoke/smoke_summary.json").read_text(encoding="utf-8"))
    assert saved["budgeted_detector_images"] == 2
