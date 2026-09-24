r"""ResNet-18 training for PSA-XAI-V1.0-DRAFT: pilot (measure batch size) and full runs.

Faithful to protocol/PSA_XAI_V1_0_DRAFT.yaml:
  input 1x224x224 (conv1 adapted to 1 channel), AdamW, epochs<=30, early stop patience 5,
  selection metric = validation macro-F1, seeds 42/43/44, AMP on, NO augmentation.
  Initialisation is selected on validation then frozen (--init imagenet | random | select).

Reads only the derived rasters + index built by psa_build_rasters.py. No sample byte is
executed, imported or loaded; the .npy is plain float32 arrays.

  # 1) pilot -- find the largest batch that fits 8 GB, record peak VRAM + throughput
  .\.venv\Scripts\python.exe scripts\psa_train.py pilot ^
      --rasters-dir D:\secure-malware-data\psa\rasters ^
      --out-dir     D:\secure-malware-data\psa\runs

  # 2) full run for one seed (repeat for 42, 43, 44)
  .\.venv\Scripts\python.exe scripts\psa_train.py train ^
      --rasters-dir D:\secure-malware-data\psa\rasters ^
      --out-dir     D:\secure-malware-data\psa\runs ^
      --batch-size 256 --init imagenet --seed 42
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import statistics
import sys
import time

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

SIDE = 224
PIXELS = SIDE * SIDE


# --------------------------------------------------------------------------- data
class RasterDataset(Dataset):
    """Rows of a (N, 50176) float32 memmap, addressed by the index's `row` column.

    The memmap is opened lazily per worker (Windows uses spawn), and raster values,
    which are byte means in [0, 255], are scaled to [0, 1]. No augmentation."""

    def __init__(self, npy_path: str, rows: list[int], labels: list[int]):
        self.npy_path = npy_path
        self.rows = np.asarray(rows, dtype=np.int64)
        self.labels = np.asarray(labels, dtype=np.int64)
        self._mm = None

    def __len__(self) -> int:
        return len(self.rows)

    def _mmap(self):
        if self._mm is None:
            self._mm = np.load(self.npy_path, mmap_mode="r")
        return self._mm

    def __getitem__(self, i: int):
        row = int(self.rows[i])
        vec = np.asarray(self._mmap()[row], dtype=np.float32) / 255.0
        x = torch.from_numpy(vec).view(1, SIDE, SIDE)
        return x, int(self.labels[i])


def split_assignments(split_manifest: str | None):
    if split_manifest is None:
        return None
    assignments = {}
    with open(split_manifest, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            sample_id = row["sample_id"]
            if sample_id in assignments or row["split"] not in ("train", "val", "test"):
                raise ValueError("duplicate sample ID or invalid split in manifest")
            assignments[sample_id] = (row["split"], row["label"], row["group"])
    return assignments


def load_index(rasters_dir: str, split: str, assignments=None):
    """Return (rows, labels, groups) for one split, dropping raster duplicates."""
    idx = os.path.join(rasters_dir, "raster_index.csv")
    dup_file = os.path.join(rasters_dir, "raster_duplicate_groups.csv")
    drop = set()
    if os.path.exists(dup_file):
        seen = set()
        with open(dup_file, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                h = r["raster_sha256"]
                if h in seen:
                    drop.add(r["sample_id"])   # keep the first occurrence only
                else:
                    seen.add(h)
    rows, labels, groups = [], [], []
    matched = set()
    with open(idx, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            sample_id = r["sample_id"]
            if assignments is not None:
                assignment = assignments.get(sample_id)
                if assignment is None:
                    continue
                if (r["label"], r["group"]) != assignment[1:]:
                    raise ValueError(f"manifest/index mismatch for {sample_id}")
                matched.add(sample_id)
                selected_split = assignment[0]
            else:
                selected_split = r["split"]
            if selected_split != split or sample_id in drop:
                continue
            rows.append(int(r["row"]))
            labels.append(int(r["label"]))
            groups.append(r["group"])
    if assignments is not None and len(matched) != len(assignments):
        raise ValueError("manifest contains sample IDs absent from raster index")
    return rows, labels, groups


# -------------------------------------------------------------------------- model
def build_model(init: str, device: str) -> nn.Module:
    from torchvision.models import ResNet18_Weights, resnet18
    weights = ResNet18_Weights.IMAGENET1K_V1 if init == "imagenet" else None
    model = resnet18(weights=weights)
    w = model.conv1.weight.data.clone()               # (64, 3, 7, 7)
    model.conv1 = nn.Conv2d(1, 64, 7, 2, 3, bias=False)
    if init == "imagenet":
        model.conv1.weight.data = w.mean(dim=1, keepdim=True)   # 3->1 channel, scale kept
    model.fc = nn.Linear(model.fc.in_features, 2)
    return model.to(device)


# ------------------------------------------------------------------------ metrics
def auroc(scores: np.ndarray, labels: np.ndarray) -> float:
    """Rank AUROC (Mann-Whitney U, average ranks for ties). The metadata-only baseline
    is reported as AUROC (0.95), so the CNN must be scored the same way to answer the
    actual research question: does the byte image beat the metadata shortcut?"""
    order = np.argsort(scores, kind="mergesort")
    s = scores[order]
    ranks = np.empty(len(s), dtype=np.float64)
    i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and s[j + 1] == s[i]:
            j += 1
        ranks[i:j + 1] = (i + j) / 2.0 + 1.0
        i = j + 1
    y = labels[order]
    n1 = float(y.sum())
    n0 = float(len(y) - n1)
    if n1 == 0 or n0 == 0:
        return float("nan")
    return float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def macro_f1(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    f1s = []
    for c in (0, 1):
        tp = int(((y_pred == c) & (y_true == c)).sum())
        fp = int(((y_pred == c) & (y_true != c)).sum())
        fn = int(((y_pred != c) & (y_true == c)).sum())
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * p * r / (p + r) if p + r else 0.0)
    return sum(f1s) / 2


@torch.no_grad()
def evaluate(model, loader, device):
    model.eval()
    ys, ps, probs = [], [], []
    for x, y in loader:
        x = x.to(device, non_blocking=True)
        with torch.amp.autocast("cuda", enabled=device == "cuda"):
            out = model(x)
        pr = torch.softmax(out.float(), dim=1)[:, 1]
        ps.append(out.argmax(1).cpu().numpy())
        probs.append(pr.cpu().numpy())
        ys.append(y.numpy())
    y = np.concatenate(ys)
    p = np.concatenate(ps)
    pr = np.concatenate(probs)
    ba = 0.5 * (((p == 1) & (y == 1)).sum() / max((y == 1).sum(), 1)
                + ((p == 0) & (y == 0)).sum() / max((y == 0).sum(), 1))
    return {"macro_f1": macro_f1(y, p), "auroc": auroc(pr, y), "balanced_acc": float(ba),
            "recall_mal": float(((p == 1) & (y == 1)).sum() / max((y == 1).sum(), 1)),
            "recall_ben": float(((p == 0) & (y == 0)).sum() / max((y == 0).sum(), 1)),
            "n": int(len(y))}


def make_loaders(rasters_dir, batch_size, workers, split_manifest=None):
    npy = os.path.join(rasters_dir, "rasters.npy")
    assignments = split_assignments(split_manifest)
    out = {}
    counts = {}
    for split in ("train", "val", "test"):
        rows, labels, _ = load_index(rasters_dir, split, assignments)
        ds = RasterDataset(npy, rows, labels)
        out[split] = DataLoader(ds, batch_size=batch_size, shuffle=(split == "train"),
                                num_workers=workers, pin_memory=True, drop_last=False,
                                persistent_workers=workers > 0)
        counts[split] = {"n": len(rows), "benign": int((np.array(labels) == 0).sum()),
                         "malicious": int((np.array(labels) == 1).sum())}
    return out, counts


# --------------------------------------------------------------------------- pilot
def cmd_pilot(args):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device != "cuda":
        print("WARNING: CUDA not available; pilot is meaningful only on the GPU", file=sys.stderr)
    model = build_model(args.init, device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    scaler = torch.amp.GradScaler("cuda", enabled=device == "cuda")
    loss_fn = nn.CrossEntropyLoss()
    results = []
    chosen = None
    for bs in [int(x) for x in args.try_batches.split(",")]:
        try:
            if device == "cuda":
                torch.cuda.empty_cache()
                torch.cuda.reset_peak_memory_stats()
            x = torch.randn(bs, 1, SIDE, SIDE, device=device)
            y = torch.randint(0, 2, (bs,), device=device)
            model.train()
            t0 = time.time()
            steps = 5
            for _ in range(steps):
                opt.zero_grad(set_to_none=True)
                with torch.amp.autocast("cuda", enabled=device == "cuda"):
                    loss = loss_fn(model(x), y)
                scaler.scale(loss).backward()
                scaler.step(opt)
                scaler.update()
            if device == "cuda":
                torch.cuda.synchronize()
            dt = (time.time() - t0) / steps
            peak = torch.cuda.max_memory_allocated() / 2**20 if device == "cuda" else 0.0
            imgs = bs / dt
            results.append({"batch_size": bs, "ok": True, "peak_vram_mib": round(peak, 1),
                            "sec_per_step": round(dt, 4), "images_per_sec": round(imgs, 1)})
            print(f"  bs={bs:5} OK  peak {peak:7.1f} MiB  {dt*1000:6.1f} ms/step  {imgs:8.1f} img/s")
            if device == "cuda" and peak < 0.80 * (torch.cuda.get_device_properties(0).total_memory / 2**20):
                chosen = bs
        except torch.cuda.OutOfMemoryError:
            results.append({"batch_size": bs, "ok": False, "error": "OOM"})
            print(f"  bs={bs:5} OOM")
            break
        finally:
            if device == "cuda":
                torch.cuda.empty_cache()
    os.makedirs(args.out_dir, exist_ok=True)
    total = torch.cuda.get_device_properties(0).total_memory / 2**20 if device == "cuda" else 0
    rec = {"check": "psa_train_pilot", "device": device,
           "gpu": torch.cuda.get_device_name(0) if device == "cuda" else "cpu",
           "vram_total_mib": round(total, 1), "init": args.init,
           "results": results, "recommended_batch_size": chosen,
           "note": "recommended = largest tried batch that peaked under 80% of total VRAM"}
    p = os.path.join(args.out_dir, "pilot_batch_size.json")
    json.dump(rec, open(p, "w"), indent=2)
    print(f"\nrecommended batch size: {chosen}   -> {p}")
    return 0


# --------------------------------------------------------------------------- train
def set_seed(seed: int):
    import random
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def cmd_train(args):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    set_seed(args.seed)
    loaders, counts = make_loaders(args.rasters_dir, args.batch_size, args.workers, args.split_manifest)
    print(f"splits: {counts}")
    # class weights from train (protocol lists a balanced baseline; imbalance ~1:1.35)
    nb = counts["train"]["benign"]
    nm = counts["train"]["malicious"]
    tot = nb + nm
    cw = torch.tensor([tot / (2 * nb), tot / (2 * nm)], dtype=torch.float32, device=device)
    print(f"class weights benign/malicious: {cw.tolist()}")

    model = build_model(args.init, device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    scaler = torch.amp.GradScaler("cuda", enabled=device == "cuda")
    loss_fn = nn.CrossEntropyLoss(weight=cw)

    tag = f"seed{args.seed}_{args.init}_bs{args.batch_size}"
    run_dir = os.path.join(args.out_dir, tag)
    os.makedirs(run_dir, exist_ok=True)
    best = {"val_macro_f1": -1.0, "epoch": -1}
    history = []
    patience = 0
    for epoch in range(args.epochs_max):
        model.train()
        t0 = time.time()
        seen = 0
        for x, y in loaders["train"]:
            x = x.to(device, non_blocking=True)
            y = y.to(device, non_blocking=True)
            opt.zero_grad(set_to_none=True)
            with torch.amp.autocast("cuda", enabled=device == "cuda"):
                loss = loss_fn(model(x), y)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            seen += x.size(0)
        val = evaluate(model, loaders["val"], device)
        peak = torch.cuda.max_memory_allocated() / 2**20 if device == "cuda" else 0.0
        dt = time.time() - t0
        history.append({"epoch": epoch, "val": val, "train_sec": round(dt, 1),
                        "images_per_sec": round(seen / dt, 1), "peak_vram_mib": round(peak, 1)})
        print(f"  epoch {epoch:2}  val_macroF1 {val['macro_f1']:.4f}  val_AUROC {val['auroc']:.4f}  "
              f"bal_acc {val['balanced_acc']:.4f}  recall b/m {val['recall_ben']:.3f}/{val['recall_mal']:.3f}  "
              f"{dt:.0f}s  {seen/dt:.0f} img/s")
        if val["macro_f1"] > best["val_macro_f1"] + 1e-4:
            best = {"val_macro_f1": val["macro_f1"], "epoch": epoch, **val}
            patience = 0
            ckpt = os.path.join(run_dir, "best.pt")
            torch.save({"model": model.state_dict(), "epoch": epoch, "val": val,
                        "init": args.init, "seed": args.seed, "batch_size": args.batch_size,
                        "arch": "resnet18", "input": [1, SIDE, SIDE]}, ckpt)
        else:
            patience += 1
            if patience >= args.patience:
                print(f"  early stop at epoch {epoch} (patience {args.patience})")
                break

    ckpt = os.path.join(run_dir, "best.pt")
    sha = hashlib.sha256(open(ckpt, "rb").read()).hexdigest()
    # sanity gate (protocol) -- reported, not enforced here
    gate = {
        "macro_f1_margin_over_majority": best["val_macro_f1"] - _majority_macro_f1(counts["val"]),
        "balanced_acc_ge_0.70": best["balanced_acc"] >= 0.70,
        "recall_both_ge_0.60": best["recall_ben"] >= 0.60 and best["recall_mal"] >= 0.60,
    }
    summary = {"tag": tag, "device": device, "seed": args.seed, "init": args.init,
               "batch_size": args.batch_size, "epochs_ran": len(history),
               "best": best, "checkpoint_sha256": sha, "sanity_gate": gate,
               "counts": counts, "history": history,
               "metadata_only_auroc_baseline": 0.95,
               "cnn_val_auroc_over_baseline": round(best.get("auroc", float("nan")) - 0.95, 4),
               "target_layer_candidate": "layer4.1"}
    json.dump(summary, open(os.path.join(run_dir, "summary.json"), "w"), indent=2)
    print(f"\nbest val macro-F1 {best['val_macro_f1']:.4f} @ epoch {best['epoch']}")
    print(f"sanity gate: {gate}")
    print(f"checkpoint {ckpt}\n  sha256 {sha}")
    return 0


def _majority_macro_f1(c):
    # predicting the majority class only -> macro-F1 of that degenerate classifier
    nb, nm = c["benign"], c["malicious"]
    maj = 1 if nm >= nb else 0
    y = np.array([1] * nm + [0] * nb)
    p = np.full_like(y, maj)
    return macro_f1(y, p)


def cmd_eval(args):
    """Score saved checkpoints on a split (AUROC + macro-F1). No training.

    The whole study hinges on CNN val AUROC vs the metadata-only baseline (0.95); the
    early runs were trained before AUROC was reported, so this recomputes it from best.pt."""
    device = "cuda" if torch.cuda.is_available() else "cpu"
    loaders, counts = make_loaders(args.rasters_dir, args.batch_size, args.workers, args.split_manifest)
    loader = loaders[args.split]
    ckpts = []
    if args.checkpoint:
        ckpts = [args.checkpoint]
    else:
        for name in sorted(os.listdir(args.runs_dir)):
            c = os.path.join(args.runs_dir, name, "best.pt")
            if os.path.isfile(c):
                ckpts.append(c)
    if not ckpts:
        print("no checkpoints found", file=sys.stderr)
        return 1
    rows = []
    for c in ckpts:
        ck = torch.load(c, map_location=device, weights_only=True)
        model = build_model("random", device)          # weights overwritten; no imagenet download
        model.load_state_dict(ck["model"])
        m = evaluate(model, loader, device)
        tag = os.path.basename(os.path.dirname(c))
        m.update({"tag": tag, "seed": ck.get("seed"), "init": ck.get("init"),
                  "train_best_epoch": ck.get("epoch")})
        rows.append(m)
        print(f"  {tag:28} {args.split}  AUROC {m['auroc']:.4f}  macroF1 {m['macro_f1']:.4f}  "
              f"balAcc {m['balanced_acc']:.4f}  recall b/m {m['recall_ben']:.3f}/{m['recall_mal']:.3f}  n={m['n']}")
    if len(rows) > 1:
        au = [r["auroc"] for r in rows if r["init"] == "imagenet"] or [r["auroc"] for r in rows]
        print(f"\n  imagenet AUROC: mean {statistics.mean(au):.4f}  "
              f"min {min(au):.4f}  max {max(au):.4f}  vs metadata baseline 0.95 "
              f"(delta {statistics.mean(au)-0.95:+.4f})")
    out = {"split": args.split, "metadata_baseline_auroc": 0.95, "results": rows}
    dst = args.out or os.path.join(args.runs_dir if not args.checkpoint else ".", f"auroc_{args.split}.json")
    json.dump(out, open(dst, "w"), indent=2)
    print(f"\nwrote {dst}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    pp = sub.add_parser("pilot")
    pp.add_argument("--rasters-dir", required=True)
    pp.add_argument("--out-dir", required=True)
    pp.add_argument("--init", choices=("imagenet", "random"), default="imagenet")
    pp.add_argument("--try-batches", default="64,128,256,512,768,1024")
    pp.set_defaults(func=cmd_pilot)

    tp = sub.add_parser("train")
    tp.add_argument("--rasters-dir", required=True)
    tp.add_argument("--split-manifest", default=None, help="optional split assignment CSV; default uses raster_index.csv")
    tp.add_argument("--out-dir", required=True)
    tp.add_argument("--batch-size", type=int, required=True)
    tp.add_argument("--init", choices=("imagenet", "random"), default="imagenet")
    tp.add_argument("--seed", type=int, default=42)
    tp.add_argument("--epochs-max", type=int, default=30)
    tp.add_argument("--patience", type=int, default=5)
    tp.add_argument("--lr", type=float, default=1e-3)
    tp.add_argument("--weight-decay", type=float, default=1e-2)
    tp.add_argument("--workers", type=int, default=4)
    tp.set_defaults(func=cmd_train)

    ep = sub.add_parser("eval")
    ep.add_argument("--rasters-dir", required=True)
    ep.add_argument("--split-manifest", default=None, help="optional split assignment CSV; default uses raster_index.csv")
    ep.add_argument("--runs-dir", help="scan every <run>/best.pt under here")
    ep.add_argument("--checkpoint", help="score a single best.pt instead")
    ep.add_argument("--split", choices=("val", "test", "train"), default="val")
    ep.add_argument("--batch-size", type=int, default=512)
    ep.add_argument("--workers", type=int, default=4)
    ep.add_argument("--out", default=None)
    ep.set_defaults(func=cmd_eval)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
