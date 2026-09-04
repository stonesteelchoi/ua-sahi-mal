# Third-party software

This repository integrates third-party projects without relicensing them.

## SAHI

- Upstream: <https://github.com/obss/sahi>
- Pinned release: `0.12.2`
- License: MIT
- Integration: vendored source at `external/sahi`, installed in editable mode; the parent repository currently tracks regular files rather than a Git submodule

## Upsample Anything

- Upstream: <https://github.com/seominseok0429/Upsample-Anything_Pytorch>
- Pinned commit: `39251463a8bb352785c063c3c3f941f1dcdf4c51`
- License: no explicit license file was present at the time this integration was created
- Integration: vendored source and research assets under `external/upsample-anything`; this is not a Git submodule
- Permission record: the repository owner reports that Upsample Anything first author Minseok Seo directly granted permission to commit the complete upstream source in this research repository. The private correspondence itself is not published here.

That direct permission is the basis for this particular vendored copy; it is not
a public license and must not be interpreted as granting downstream users a
general right to redistribute, modify, or relicense the upstream work. Preserve
the upstream authorship and citation. See
`external/upsample-anything/VENDORED_SOURCE.md`.

## Ultralytics

- Upstream: <https://github.com/ultralytics/ultralytics>
- Pinned package version: `8.4.67`
- License: AGPL-3.0, with enterprise licensing options offered by Ultralytics
- Integration: Python package dependency

Review Ultralytics licensing before network deployment, commercial use, or redistribution.

## DeepReflect

- Upstream: <https://github.com/evandowning/deepreflect>
- Paper: <https://www.usenix.org/conference/usenixsecurity21/presentation/downing>
- Pinned research revision: `4358a7e8ef7fc5951360094867dca852ed23712e`
- License: GPL-3.0
- Integration: not vendored; `external/deepreflect/README.md` records the isolated-baseline contract only
- Additional dependency: the faithful upstream workflow documents Binary Ninja 2.3, whose distribution and license are not included

DeepReflect must run in a separate approved environment. Do not copy its GPL
source into this MIT tree without an explicit distribution design, and never
commit the upstream ground-truth malware archives or a Binary Ninja license.

## Research references not vendored

The DECODE, DexRay, DEYO, and two-stage detector repositories listed in
`docs/SOURCES.md` were consulted as references only. No code, dataset, model,
or notebook cell from them is copied into this repository. The current paper
source index is `paper/references/README.md`. Before integrating one of those
projects, record its exact revision and license here and preserve its notices.

The DECODE and KISA datasets are not bundled. Access, processing, derived-image
redistribution, and publication must follow the corresponding provider terms.

## PyTorch and torchvision

- Upstream: <https://github.com/pytorch/pytorch>
- Tested versions: PyTorch `2.8.0`, torchvision `0.23.0`
- Integration: binary wheels from the official PyTorch package index
