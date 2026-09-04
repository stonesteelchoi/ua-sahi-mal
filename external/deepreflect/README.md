# DeepReflect integration record

This directory intentionally contains **no vendored DeepReflect source and no malware artifact**. It records the v3 baseline contract without mixing GPL-3.0 code, proprietary tooling, or real malware into the MIT-licensed UA-SAHI-Mal tree.

## Upstream

- Project: DeepReflect — Discovering Malicious Functionality through Binary Reconstruction
- Paper: <https://www.usenix.org/conference/usenixsecurity21/presentation/downing>
- Repository: <https://github.com/evandowning/deepreflect>
- Pinned revision: `4358a7e8ef7fc5951360094867dca852ed23712e`
- Upstream license: GPL-3.0
- Documented legacy environment: Debian 10, Python 3.7.3, Binary Ninja 2.3, PostgreSQL 11.10

## Integration mode

Run the faithful baseline in an isolated checkout outside this repository and export only versioned, nonexecutable result records. Do not copy or relicense upstream code here. Any compatibility patch must be preserved as a patch artifact, and any semantic change to feature extraction, disassembly, the autoencoder, thresholding, or ranking changes the table label to `DeepReflect-inspired`.

The expected adapter schema is defined in [`../../paper/plan/RESEARCH_PLAN_v3.md`](../../paper/plan/RESEARCH_PLAN_v3.md). At minimum it records the sample hash, upstream/environment revision, native addresses, mapped file-offset interval unions, reconstruction score/rank, threshold calibration split, timing, and failure code.

## Safety boundary

The upstream `grader` workflow exposes password-protected real-malware archives. Do not download, extract, execute, or commit those artifacts in this workspace. Use an institutionally approved isolated malware environment and export only the minimum nonexecutable measurements allowed by the data agreement.

Do not commit:

- PE/DLL/SYS malware or benign copyrighted binaries;
- password-protected malware archives;
- Binary Ninja distributions or `license.dat`;
- database dumps containing restricted sample content;
- reversible malware byte images;
- API keys, access tokens, or private dataset URLs.

## Reproduction status

`NOT_RUN` — the repository currently records the decision and interface only. A result row may be labelled `DeepReflect` only after the v3 plan assigns a declared reproduction exit state and the environment, coverage, mapping, and threshold protocol have been captured.
