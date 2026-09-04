# ADR-001: Use DeepReflect, not DECODE, as the direct prior-system baseline

- **Status:** Accepted
- **Date:** 2026-09-04
- **Deciders:** UA-SAHI-Mal research team
- **Applies to:** v3 static-PE malicious-component retrieval paper

## Context

The v3 paper asks whether a method trained primarily from file labels can rank and refine analyst-verifiable malicious functions, basic blocks, and byte intervals in statically analyzable Windows PE files under an explicit review budget.

DECODE and DeepReflect both discuss localization, but they do not solve the same task:

- [DECODE](https://doi.org/10.1038/s41598-025-21848-z) transforms dynamic API-call behavior into images, creates Bayesian Grad-CAM pseudo-regions, groups those regions, and trains an object detector for proportional multi-label behavior classification. Its code and paper use process, file-system, network, and registry API-call sequences rather than raw static PE coordinates.
- [DeepReflect](https://www.usenix.org/conference/usenixsecurity21/presentation/downing) analyzes unpacked static PE binaries, scores basic blocks with a benign-trained reconstruction model, aggregates suspicious regions to functions, and prioritizes components for reverse engineering. Its output and analyst-facing purpose are directly comparable to the v3 task.

The official DeepReflect artifact is available at [evandowning/deepreflect](https://github.com/evandowning/deepreflect), currently pinned for this plan at commit `4358a7e8ef7fc5951360094867dca852ed23712e`. The upstream code is GPL-3.0 and its documented reproduction environment includes Binary Ninja 2.3, Python 3.7.3, and PostgreSQL 11.10. The artifact also exposes ground-truth archives for rbot, pegasus, and carbanak, but those real-malware artifacts are not safe or appropriate to commit to this repository.

## Decision

1. Remove DECODE from every direct numeric baseline table for v3.
2. Keep DECODE in related work and explain why a cross-task accuracy or localization comparison would be invalid.
3. Make DeepReflect the primary prior-system localization baseline.
4. Do not make DeepReflect the only baseline. Compare it with matched lower bounds, attribution, MIL, rule systems, an exhaustive upper bound, and a supervised-gold baseline when gold training data exist.
5. Evaluate every localizer in a shared output contract: ranked `file_offset_intervals`, mapped functions/basic blocks, confidence/rank, reviewed-byte/function cost, and end-to-end latency.
6. Run the upstream DeepReflect implementation without semantic modification in an isolated environment. If an adapter or reimplementation changes the feature extractor, disassembler, reconstruction model, or ranking rule, label it `DeepReflect-inspired` and never report it as a faithful reproduction.
7. Use validation data, not test gold, to choose a DeepReflect threshold. Also report threshold-free ranking curves because the original paper selected thresholds from its ground-truth samples.
8. Report two scopes:
   - the intersection set on which all compared methods can run, for paired comparisons;
   - the full eligible test set, with method coverage/failure rate, so a dependency or disassembly failure is not silently discarded.

## Options considered

### Option A: Keep DECODE as the direct baseline

| Dimension | Assessment |
|---|---|
| Task alignment | Low |
| Input alignment | Low |
| Coordinate compatibility | Low |
| Reproduction cost | Medium–high |
| Reviewer defensibility | Low |

**Pros**

- Reuses substantial historical code in this repository.
- Provides a recent malware-visualization comparison.

**Cons**

- Compares dynamic API behavior with static PE bytes/functions.
- Compares pseudo-box multi-label classification with externally evaluated component retrieval.
- Any accuracy or AP ranking would be scientifically uninterpretable.

### Option B: Use DeepReflect as the direct prior-system baseline

| Dimension | Assessment |
|---|---|
| Task alignment | High |
| Input alignment | High for unpacked native PE |
| Coordinate compatibility | Medium; requires verified address-to-file mapping |
| Reproduction cost | High |
| Reviewer defensibility | High if faithfully reproduced |

**Pros**

- Directly localizes and ranks static malware functionality for analysts.
- Provides public code, extracted data, paper-reproduction material, and small source-grounded artifacts.
- Forces the paper to acknowledge the closest prior art and narrows novelty claims correctly.

**Cons**

- Depends on an old, proprietary Binary Ninja environment and a database service.
- The original gold set contains only three malware projects and has incomplete function recovery.
- Threshold calibration, function-boundary disagreement, and coverage failures require explicit handling.
- GPL-3.0 code cannot be silently vendored or relicensed inside this MIT repository.

### Option C: Put both DECODE and DeepReflect in the same numeric table

| Dimension | Assessment |
|---|---|
| Coverage of prior work | High |
| Scientific comparability | Low |
| Table clarity | Low |
| Reviewer defensibility | Low |

**Pros**

- Appears comprehensive.

**Cons**

- Encourages invalid cross-task conclusions.
- Adds substantial implementation cost without a shared estimand.

### Option D: Use only generic attribution/MIL baselines

| Dimension | Assessment |
|---|---|
| Implementation complexity | Medium |
| Closest-prior-art coverage | Low |
| Reviewer defensibility | Low |

**Pros**

- Avoids DeepReflect's legacy dependencies.

**Cons**

- Omits the most relevant static malware-component localization system.
- Makes novelty claims vulnerable to an immediate prior-art objection.

## Trade-off analysis

DeepReflect costs more to reproduce, but it measures the same analyst-facing object: suspicious static functions/basic blocks. DECODE is easier to connect to the historical codebase, yet the shared word “localization” hides different data and labels. Scientific comparability therefore outweighs reuse convenience.

The decision is not “replace one baseline row with another.” DeepReflect occupies the closest-prior-system role; lower bounds, attribution/MIL methods, rules, exhaustive search, and supervised gold answer different failure modes and remain necessary.

## Consequences

- The v3 manuscript can make a defensible matched-task comparison and must narrow any “first” claim around DeepReflect.
- The repository retains DECODE code and documents for reproduction, but the root README labels them historical.
- A separate legacy environment and a licensed Binary Ninja installation are required for faithful DeepReflect execution.
- The main method must export function/basic-block mappings in addition to byte intervals; a byte-only score is not sufficient for matched DeepReflect evaluation.
- DeepReflect ground-truth artifacts may seed Tier 3, but the same labels cannot be used both to tune a threshold and to report final test performance.
- A reproduction failure is itself reported as coverage/status; it does not authorize substituting an unlabelled proxy.

## Action items

1. [ ] Freeze the upstream commit and record Binary Ninja, Python, PostgreSQL, capa-rule, and OS versions.
2. [ ] Implement the PEAtlas address-to-file-offset mapper and round-trip tests before importing scores.
3. [ ] Define a versioned DeepReflect output adapter with sample hash, function/range, score, rank, timing, and failure reason.
4. [ ] Build validation/test group splits that keep source projects and near-duplicate functions together.
5. [ ] Run the authors' configuration and a threshold-free ranking evaluation.
6. [ ] Compare at matched top-K functions, reviewed-byte fractions, and wall-clock budgets.
7. [ ] Report analyzer coverage and disassembler disagreements.
8. [ ] Keep DECODE in related work with an explicit non-comparability sentence.
