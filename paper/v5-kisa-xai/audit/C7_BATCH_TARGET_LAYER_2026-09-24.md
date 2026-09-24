# C7 — batch size and Grad-CAM target layer

## Decision

For the existing PSA raster training configuration, retain `model.batch_size: 512` and `xai.target_layer: layer4.1` (`torchvision` ResNet-18 `BasicBlock`). Both values are already recorded in `protocol/PSA_XAI_V1_0_DRAFT.yaml`; no setting or code was changed in C7. This decision covers the train/validation workflow only. The P2 structure policy remains `conservative_unknown_v1`, and full protocol freeze and held-out test payload access remain unauthorized.

## Basis and scope

- `TRAINING_HANDOFF_KO.md` records a 2026-09-21 prerequisite check using the earlier pilot and completed training runs: batch 512 pilot peak 6,070.7 MiB of 8,123.4 MiB (74.73%); maximum observed training peak 6,072.7 MiB (74.76%). Both are below the documented 80% VRAM ceiling.
- The same check records the exact `named_modules()` path `layer4.1`, class `BasicBlock`, with CUDA synthetic forward/backward activation and gradient shapes `[1, 512, 7, 7]`, output shape `[1, 2]`, and malicious logit index 1. The synthetic layer check uses no payload.
- Evidence artifacts are present: `runs/psa-orchestration/freeze_prereqs_20260921.json` (SHA-256 `ff0dedc7d551efcb593d122d1eac0315a2f516f908ee007e2aa718521807265c`) and `D:\secure-malware-data\psa\runs\pilot_batch_size.json` (SHA-256 `a440898c124f8bc740e0978fe5c758e711f80e9c6f65ded3183ba98dc990adcd`). C7 checked their existence and hashes; the numerical assessment uses the prior handoff record rather than reopening the artifacts.
- C7 performed no pilot or training run, no raster or PE read, and no held-out test access. A new pilot is unnecessary for the recorded hardware and configuration. If the hardware, model, input shape, precision, or training implementation changes, measure batch size again before using the new setup. A required run belongs in the user's separate `.venv` window.

## Completion

The batch and target-layer prerequisites are documented and pinned for C8. C8 must still check the train/validation-only training command and its resulting artifacts and sanity gate. This C7 decision does not approve C9 or full protocol freeze.
