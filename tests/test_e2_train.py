"""E2 v3 training recipe: class weights / majority baseline (torch-free) + a tiny CPU
training run and checkpoint round-trip (torch; runs in CI and on cau)."""

from __future__ import annotations

import zlib

import numpy as np
import pytest

from ua_sahi_mal.peatlas import SectionSpec, build_pe
from ua_sahi_mal.sorel.e2_dataset import LabeledSample, SorelTileStore
from ua_sahi_mal.sorel.e2_train import TrainConfig, class_weights, majority_baseline, sanity_gate


def test_class_weights_inverse_frequency():
    w = class_weights([0, 0, 0, 1], class_count=2)
    assert w[1] > w[0] > 0 and np.isclose(w[0] * 3 + w[1] * 1, 4.0)   # sum(weight*count) == n


def test_majority_baseline_and_sanity_gate():
    labels = [0, 0, 0, 1, 2]
    base = majority_baseline(labels, class_count=3)
    assert base["majority_class"] == 0 and np.isclose(base["accuracy"], 0.6)
    weak = sanity_gate({"accuracy": 0.62, "macro_f1": base["macro_f1"]}, labels, 3)
    strong = sanity_gate({"accuracy": 0.95, "macro_f1": 0.9}, labels, 3)
    assert weak["pass"] is False and strong["pass"] is True


def _sample_pe(fill: int, overlay: int) -> bytes:
    return build_pe(sections=[SectionSpec(".text", rva=0x1000, virtual_size=0x400, raw_offset=0x400,
                                          raw_size=0x400, fill=fill)],
                    overlay=bytes([fill]) * overlay, disarm=True)


def test_tiny_training_run_and_checkpoint_roundtrip(iso_dir):
    pytest.importorskip("torch")
    from ua_sahi_mal.sorel.e2_models import load_checkpoint, resolve_device
    from ua_sahi_mal.sorel.e2_train import log_probabilities, train_model

    samples = []
    for i in range(6):
        label = i % 2
        sha = f"{label}{i:063d}"
        (iso_dir / f"{sha}.zlib").write_bytes(zlib.compress(_sample_pe(0x11 if label == 0 else 0xEE, 70000 + i)))
        samples.append(LabeledSample(sha, "train", "primary", "adware" if label == 0 else "packed", label))
    store = SorelTileStore(iso_dir, static_only=True, cache_bytes=64 << 20)

    for pooling in ("meanmax", "attention"):
        config = TrainConfig(pooling=pooling, epochs=1, accumulate=2, max_train_tiles=2, device="cpu", seed=3)
        model, report = train_model(samples, store, class_count=2, config=config, validation=samples)
        assert len(report.epochs) == 1 and np.isfinite(report.epochs[0]["loss"])
        assert report.validation["n"] == 6 and "pass" in report.sanity
        rows = log_probabilities(model, store.get(samples[0].sorel_original_sha256).tiles, resolve_device("cpu"))
        assert rows.shape == (2,) and np.isclose(np.exp(rows).sum(), 1.0, atol=1e-5)

    from ua_sahi_mal.sorel.e2_models import save_checkpoint
    ckpt = iso_dir / "m.pt"
    save_checkpoint(model, ckpt, meta={"class_names": ["adware", "packed"]})
    loaded, meta = load_checkpoint(ckpt, device=resolve_device("cpu"))
    assert loaded.pooling == "attention" and meta["class_names"] == ["adware", "packed"]
