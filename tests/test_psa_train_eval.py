"""Synthetic evaluation checks; no held-out data is opened."""

import argparse
import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


class Tensor:
    def __init__(self, value):
        self.value = np.asarray(value)

    def to(self, *args, **kwargs):
        return self

    def float(self):
        return self

    def argmax(self, axis):
        return Tensor(self.value.argmax(axis))

    def cpu(self):
        return self

    def numpy(self):
        return self.value

    def __getitem__(self, key):
        return Tensor(self.value[key])


class Autocast:
    def __enter__(self):
        pass

    def __exit__(self, *args):
        pass


def no_grad():
    return lambda func: func


def softmax(tensor, dim):
    axis = dim
    values = np.exp(tensor.value - tensor.value.max(axis=axis, keepdims=True))
    return Tensor(values / values.sum(axis=axis, keepdims=True))


source = (Path(__file__).resolve().parents[1] / "scripts/psa_train.py").read_text(encoding="utf-8")
tree = ast.parse(source)
names = {"auroc", "macro_f1", "evaluate", "file_sha256", "cmd_eval"}
selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
train = SimpleNamespace()
scope = {"__file__": str(Path(__file__).resolve().parents[1] / "scripts/psa_train.py"),
         "np": np, "hashlib": hashlib, "json": json, "os": __import__("os"),
         "sys": __import__("sys"), "statistics": __import__("statistics"),
         "torch": SimpleNamespace(no_grad=no_grad, softmax=softmax,
                                  amp=SimpleNamespace(autocast=lambda *a, **kw: Autocast()),
                                  cuda=SimpleNamespace(is_available=lambda: False))}
exec(compile(ast.Module(body=selected, type_ignores=[]), "psa_train.py", "exec"), scope)
for name in names:
    setattr(train, name, scope[name])


class Model:
    def eval(self):
        return self

    def __call__(self, x):
        return x

    def load_state_dict(self, state):
        pass


def test_eval_metrics_and_provenance(tmp_path, monkeypatch):
    rasters = tmp_path / "rasters"
    rasters.mkdir()
    for name in ("raster_index.csv", "rasters.npy", "raster_duplicate_groups.csv"):
        (rasters / name).write_bytes(name.encode())
    manifest = tmp_path / "era.csv"
    manifest.write_bytes(b"synthetic era manifest")
    checkpoint = tmp_path / "best.pt"
    checkpoint.write_bytes(b"synthetic checkpoint")
    expected = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    output = tmp_path / "test.json"
    logits = Tensor([[3., 1.], [1., 3.], [3., 1.], [1., 3.]])
    labels = Tensor([0, 1, 1, 0])
    scope["make_loaders"] = lambda *a: (
        {"test": [(logits, labels)]}, {"test": {"n": 4, "benign": 2, "malicious": 2}})
    scope["build_model"] = lambda *a: Model()
    scope["torch"].load = lambda *a, **kw: {"model": {}, "seed": 42, "init": "imagenet", "epoch": 2}
    args = argparse.Namespace(rasters_dir=str(rasters), split_manifest=str(manifest),
        runs_dir=None, checkpoint=str(checkpoint), checkpoint_sha256=expected,
        split="test", batch_size=4, workers=0, out=str(output))
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        train.cmd_eval(argparse.Namespace(**{**vars(args), "checkpoint_sha256": "0" * 64}))
    assert not output.exists()
    assert train.cmd_eval(args) == 0
    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["split"] == "test"
    assert record["results"][0]["confusion_matrix"] == [[1, 1], [1, 1]]
    assert record["results"][0]["recall_ben"] == record["results"][0]["recall_mal"] == 0.5
    assert record["results"][0]["checkpoint_sha256"] == expected
    assert record["input_sha256"]["split_manifest"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert record["protocol_sha256"] == "c0c7b79775b3aa36d3dc59f5a8544e5248e9517ca218319cb8ee83d88c70e709"
    with pytest.raises(FileExistsError):
        train.cmd_eval(args)
