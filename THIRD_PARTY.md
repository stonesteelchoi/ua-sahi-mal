# Third-party software

This repository integrates third-party projects without relicensing them.

## SAHI

- Upstream: <https://github.com/obss/sahi>
- Pinned release: `0.12.2`
- License: MIT
- Integration: Git submodule at `external/sahi`, installed in editable mode

## Upsample Anything

- Upstream: <https://github.com/seominseok0429/Upsample-Anything_Pytorch>
- Pinned commit: `39251463a8bb352785c063c3c3f941f1dcdf4c51`
- License: no explicit license file was present at the time this integration was created
- Integration: Git submodule at `external/upsample-anything`; the integration code imports the upstream `UPA` entry point without copying or modifying its implementation

Absence of a license does not imply permission to redistribute or modify the upstream source. Obtain permission from the upstream authors before publishing a fork or copied implementation.

## Ultralytics

- Upstream: <https://github.com/ultralytics/ultralytics>
- Pinned package version: `8.4.67`
- License: AGPL-3.0, with enterprise licensing options offered by Ultralytics
- Integration: Python package dependency

Review Ultralytics licensing before network deployment, commercial use, or redistribution.

## Research references not vendored

The DECODE, DexRay, DEYO, and two-stage detector repositories listed in
`docs/SOURCES.md` were consulted as references only. No code, dataset, model,
or notebook cell from them is copied into this repository. Before integrating
one of those projects, record its exact revision and license here and preserve
its notices.

The DECODE and KISA datasets are not bundled. Access, processing, derived-image
redistribution, and publication must follow the corresponding provider terms.

## PyTorch and torchvision

- Upstream: <https://github.com/pytorch/pytorch>
- Tested versions: PyTorch `2.8.0`, torchvision `0.23.0`
- Integration: binary wheels from the official PyTorch package index
