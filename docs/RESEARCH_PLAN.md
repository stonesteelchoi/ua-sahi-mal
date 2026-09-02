# UA-SAHI-MAL implementation and experiment plan

## Scope decision

The first milestone is not “prove UA is better.” It is a reproducible path from malware evidence to detector labels and comparable baselines. The final FPN-logit/entropy/UA router cannot be evaluated honestly until boxes, splits, metrics, and timing are fixed.

## Primary question

At a fixed 50% slice budget, can a structure-preserving, recall-guarded router retain Full SAHI small-evidence localization while materially reducing detector work and p95 end-to-end latency?

Primary gates:

```text
AP_S(UA-SAHI-MAL, B=0.5) - AP_S(Full SAHI) >= -1.5 AP point
detector image reduction >= 40%
p95 end-to-end latency reduction >= 25%
```

The result passes only if all three gates pass. AP50, mAP50:95, Tile Recall, peak VRAM, and class-level false negatives remain required secondary diagnostics.

## Work order

### M0 — Repository and safety baseline (implemented in v0.2 scaffold)

- rename package and CLI to `ua_sahi_mal` / `ua-sahi-mal`
- preserve the prior main branch and third-party submodule boundaries
- reject tracked executable/archive/model artifacts and high-confidence secrets
- add the manifest, coordinate map, provenance, split leakage validation, and synthetic smoke path
- separate “implemented” from “planned” claims

Exit: repository safety check, tests, smoke, strict doctor, and package build pass in CI.

### M1 — Real data contract validation (adapter implemented; real data pending)

- confirm the exact DECODE category names, download terms, split fields, images, and annotations
- confirm whether official COCO boxes exist; do not assume that file categories are boxes
- confirm KISA PE access, redistribution terms, and whether opcode/source ranges are available
- select one primary modality; use DECODE first, KISA only as a portability experiment
- create immutable SHA-256 manifests outside Git
- manually inspect at least a pilot subset for encoding and coordinate reversibility

Exit: dataset card, category map, group-aware splits, and validated COCO/pseudo-label provenance.

### M2 — Honest localization labels

- train the classification teacher on train only
- implement Bayesian Grad-CAM with frozen settings
- heatmap threshold, connected components, min/max area, and overlap filtering become versioned config
- store teacher checkpoint hash and per-box uncertainty/score
- create a human review set before detector tuning
- measure inter-reviewer or reviewer-versus-pseudo agreement

Exit: detector train/val pseudo-boxes and an independently reviewed test subset.

### M3 — Fixed baselines and evaluation harness (partial)

- YOLO11 primary detector; defer EfficientDet until the primary path works
- Full Image and Full SAHI-100
- Uniform/Random budget, Bilinear-50, JBU-50
- dataset-level COCO metrics, Tile Recall, per-stage timings, detector invocations/images, and peak VRAM (single-image timing and detector-only metrics exist; aggregate AP_S/VRAM runner remains)
- warm-up plus repeated p50/p95 timing on a named device
- record root commit, dirty state, data/config/model hashes, seed, Python/CUDA/package versions

Exit: one command regenerates baseline predictions and aggregate tables.

### M4 — Dense probability and routing (core adapter implemented; calibration ablation pending)

- isolate the Ultralytics-version-specific P3/P4/P5 pre-NMS hook behind an adapter
- define class aggregation (`max`, sum, or log-sum-exp) and probability calibration
- generate class-agnostic `P_lr` and entropy with explicit tensor/stride tests
- compare raw probability, guard, coverage, entropy additions in that order
- implement Low-confidence Guard fail-open behavior when guard tiles exceed a strict budget
- keep deterministic tie-breaking and Farthest-Point coverage

Exit: the router never reads ground truth at inference time and exactly reports any elastic budget overrun.

### M5 — JBU and Upsample Anything (JBU implemented; official UPA experiment pending)

- compare nearest/bilinear/JBU before UPA
- keep UPA as an unmodified submodule adapter until licensing permission is clear
- measure 0/10/25/50 TTO steps, guidance resolution, early stopping, AMP, VRAM, and OOM fallback
- include routing-map generation in end-to-end latency
- do not infer that fewer detector tiles means lower total latency

Exit: accuracy/cost ablation shows whether UPA is worth its test-time optimization.

### M6 — Final experiment and paper

- freeze one primary dataset, budget, hardware, checkpoint, and config before test evaluation
- run at least three detector-training seeds where stochastic training is involved
- use image-level paired bootstrap confidence intervals
- publish effect sizes and failures, not only point estimates
- run EfficientDet and KISA only after the primary YOLO11/DECODE claim is complete
- generate Pareto plots and paper tables from saved per-image records

Exit: all primary claims map to a frozen artifact and can be reproduced from the tagged commit.

## Known risks

| Risk | Consequence | Required mitigation |
|---|---|---|
| File-level class labels mistaken for boxes | invalid detector target | explicit direct bbox/source range only |
| Grad-CAM circular evaluation | measures teacher imitation | independent human/tool test labels |
| Family/variant leakage | inflated AP | SHA-256 and group-aware split checks |
| 2D artificial locality | misleading convolution patterns | preserve reverse mapping; compare 1D baseline |
| Fixed resize destroys offsets | boxes no longer map to code | no resize in encoder; record mapping version |
| Coarse map misses a tiny target | router cannot recover it | exploration/coverage and fail-open guard |
| UPA TTO dominates latency | efficiency claim fails | full stage timing and bilinear/JBU baselines |
| UPA source has no explicit license | redistribution risk | adapter/submodule only; obtain permission |
| Raw malware enters Git/CI | operational security incident | ignore rules, safety scan, staged-file review |
| Deadline compression | incomplete claims | finish DECODE+YOLO11 primary path before portability |

## Immediate next actions

1. Obtain approved static DECODE PNG/ROI JSON and provider terms without copying raw samples into the repository.
2. Freeze class-agnostic `malicious_evidence` as the primary localization target; keep `roi-family` as a baseline and add feature-cluster IDs only for strict DECODE reproduction.
3. Build a 20–100 image pilot with a source-group split map and run `run_decode_pipeline.ps1 -SkipTraining`.
4. Create and review a small independent localization test subset before detector tuning.
5. Implement the dataset-level strategy runner for Full Image, Full SAHI-100, Bilinear-50, JBU-50, and official UPA-50; populate only actually measured paper-table cells.
