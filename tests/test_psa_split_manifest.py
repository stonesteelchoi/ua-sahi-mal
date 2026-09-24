"""Synthetic split assignment checks; no PE bytes or held-out raster data."""

import csv
import importlib.util
from pathlib import Path


def _load(name, filename):
    path = Path(__file__).resolve().parents[1] / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _csv(path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


def test_default_split_unchanged_and_era_assignment(tmp_path):
    train = _load("psa_train", "psa_train.py")
    verify = _load("psa_verify_training", "psa_verify_training.py")
    _csv(tmp_path / "raster_index.csv", ["sample_id", "row", "label", "group", "split"],
         [["a", 0, 0, "ga", "train"], ["b", 1, 1, "gb", "val"],
          ["c", 2, 1, "gc", "test"], ["d", 3, 0, "gd", "train"]])
    _csv(tmp_path / "raster_duplicate_groups.csv", ["sample_id", "raster_sha256"], [])
    manifest = tmp_path / "era.csv"
    _csv(manifest, ["sample_id", "label", "group", "split"],
         [["a", 0, "ga", "val"], ["b", 1, "gb", "train"], ["c", 1, "gc", "test"]])

    expected_main = {"train": {"n": 2, "benign": 2, "malicious": 0},
                     "val": {"n": 1, "benign": 0, "malicious": 1},
                     "test": {"n": 1, "benign": 0, "malicious": 1}}
    expected_era = {"train": {"n": 1, "benign": 0, "malicious": 1},
                    "val": {"n": 1, "benign": 1, "malicious": 0},
                    "test": {"n": 1, "benign": 0, "malicious": 1}}
    assert verify.dataset_counts(tmp_path) == expected_main
    assert verify.dataset_counts(tmp_path, manifest) == expected_era
    assert train.load_index(str(tmp_path), "train") == ([0, 3], [0, 0], ["ga", "gd"])
    assignments = train.split_assignments(str(manifest))
    assert train.load_index(str(tmp_path), "train", assignments) == ([1], [1], ["gb"])
