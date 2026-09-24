"""Synthetic-only regression for frozen Grad-CAM projection and structure ledger."""

import numpy as np
import pytest

from scripts.psa_gradcam import gradcam, ledger_rows
from ua_sahi_mal.kisa_xai.structure import RegionSpan, StructureMap


def protocol():
    return {
        "eligibility": {"labels": [0, 1]},
        "representation": {"shape": [1, 4, 4],
                           "long_file_policy": "contiguous_interval_mean_pool",
                           "short_file_policy": "nearest_byte_repetition"},
        "xai": {"budgets": [0.05, 0.10, 0.20, 0.40],
                "empty_positive_cam_policy": "retain_and_flag"},
    }


def test_unique_byte_overshoot_and_structure_mass():
    scores = np.ones((4, 4), dtype=np.float32)
    structure = StructureMap(64, (RegionSpan(0, 8, "dos_and_pe_headers"),
                                  RegionSpan(8, 40, "executable_sections"),
                                  RegionSpan(40, 64, "unknown")), ())
    row = {"group": "synthetic", "row": "0", "file_size": "64"}
    record = {"status": "agreement"}
    entries = list(ledger_rows("synthetic", row, record, [0.1, 0.9], scores, structure, protocol()))
    assert [e["budget"]["requested_bytes"] for e in entries] == [4, 7, 13, 26]
    assert [e["budget"]["achieved_bytes"] for e in entries] == [4, 8, 16, 28]
    assert entries[1]["budget"]["overshoot_bytes"] == 1
    assert entries[1]["budget"]["intervals"] == [[0, 8]]
    assert entries[0]["structure_cam_mass"] == {
        "dos_and_pe_headers": 2.0, "executable_sections": 8.0,
        "non_executable_sections": 0.0, "resource_like_sections": 0.0,
        "certificate_table": 0.0, "overlay": 0.0, "unknown": 6.0,
    }


def test_empty_positive_cam_is_retained_for_every_budget():
    row = {"group": "synthetic", "row": "0", "file_size": "3"}
    record = {"status": "error", "structure_attribution_reason": "unclassified_parse_error"}
    entries = list(ledger_rows("synthetic", row, record, [0.1, 0.9],
                               np.zeros((4, 4), dtype=np.float32), None, protocol()))
    assert len(entries) == 4
    assert all(e["budget"]["cam_empty"] and e["budget"]["achieved_bytes"] == 0 for e in entries)
    assert all(e["empty_positive_cam_policy"] == "retain_and_flag" for e in entries)
    assert all(e["structure_cam_mass"] is None for e in entries)


def test_hook_targets_malicious_logit_and_aligns_synthetic_raster():
    torch = pytest.importorskip("torch")
    from torch import nn

    model = nn.Sequential(nn.Conv2d(1, 1, 1, bias=False), nn.Flatten(), nn.Linear(16, 2, bias=False))
    with torch.no_grad():
        model[0].weight.fill_(1)
        model[2].weight[0].fill_(-1)
        model[2].weight[1].fill_(1)
    logits, scores = gradcam(model.eval(), model[0], torch.ones(1, 1, 4, 4), 1, (4, 4),
                             {"method": "bilinear", "align_corners": False})
    assert logits[1] > logits[0]
    assert scores.shape == (4, 4)
    assert np.isfinite(scores).all() and np.all(scores > 0)
    assert scores.max() == pytest.approx(1.0)
