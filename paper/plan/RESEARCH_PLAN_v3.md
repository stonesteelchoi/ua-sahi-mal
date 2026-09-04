# UA-SAHI-Mal research plan v3

- **Status:** pre-results design and execution plan
- **Frozen for review:** 2026-09-04
- **Primary task:** budget-aware retrieval of analyst-verifiable malicious components in static Windows PE files
- **Supersedes as the active paper direction:** `docs/RESEARCH_PLAN.md` and `docs/RESEARCH_PLAN_v2.md`
- **Does not supersede:** historical code, raw result records, or the audit trail of v1/v2

## 0. Executive decision

The defensible paper is not a DECODE reproduction and not a BIG2015 family-attribution paper. It is a static-PE component-retrieval study with a new byte-interval benchmark and explicit analyst/compute budgets.

The baseline decision is:

- **DECODE is removed from direct numeric baselines.** It uses dynamic API-call imagery, Bayesian Grad-CAM pseudo-regions, and proportional multi-label behavior classification. Its inputs, labels, coordinates, and estimand do not match this study.
- **DeepReflect becomes the primary prior-system baseline.** It ranks static PE basic blocks/functions through reconstruction error and was designed to reduce reverse-engineering workload.
- **DeepReflect is not the entire baseline suite.** Random, uniform, entropy, attribution, MIL, capa/YARA, exhaustive search, and supervised-gold methods remain necessary controls.
- **The canonical unit is a union of half-open file-offset intervals.** Functions, basic blocks, masks, and bounding boxes are mapped views. A bbox is never the authoritative label.
- **v1/v2 are archived research lanes.** Their code and negative results stay reproducible, but their family-decision evidence is not promoted to malicious-component ground truth.

This decision and alternatives are recorded in [`../decisions/ADR-001-deepreflect-baseline.md`](../decisions/ADR-001-deepreflect-baseline.md).

## 1. What was rechecked

The supplied design review correctly identified DeepReflect as the closest prior work, but its public-dataset investigation contained facts marked “live verification required.” Those critical facts were rechecked against primary sources on 2026-09-04.

### 1.1 DeepReflect

The [USENIX Security 2021 paper page](https://www.usenix.org/conference/usenixsecurity21/presentation/downing) describes a static malware-component localizer trained without component labels. The reported analyst evaluation used five analysts and more than 26,000 malware samples; the page reports an average 85% reduction in functions reviewed and 80% component detection versus 43% for capa.

The [official artifact](https://github.com/evandowning/deepreflect) is live. For this plan, upstream `main` is pinned at:

```text
4358a7e8ef7fc5951360094867dca852ed23712e
```

The artifact documents Python 3.7.3, Binary Ninja 2.3, and PostgreSQL 11.10, and is GPL-3.0. It publishes extracted datasets and ground-truth archives through [`Dataset.md`](https://github.com/evandowning/deepreflect/blob/main/Dataset.md), while stating that most training/evaluation binaries cannot be redistributed.

The paper's limitations matter to this design:

- the source-grounded set contains rbot, pegasus, and carbanak;
- malicious functions were located in the CFG using source knowledge, markers, strings, and API calls;
- 14%–30% of malicious functions could not be located and were treated as benign in the reported ground truth;
- the authors selected per-sample thresholds at 80% TPR for one evaluation and a combined 40% TPR/5% FPR threshold for large-scale clustering;
- Binary Ninja and capa function boundaries could disagree.

Therefore DeepReflect is a strong direct baseline, but its original ground truth and thresholds cannot be imported as an unquestioned gold standard.

### 1.2 DECODE

The [Scientific Reports article](https://doi.org/10.1038/s41598-025-21848-z) and [official repository](https://github.com/dtuuba/DECODE-DEep_Classification_Of_Dynamic_Exploits) confirm that DECODE builds images from dynamic behavior/API-call sequences, generates Bayesian Grad-CAM regions, groups them into COCO-style pseudo-annotations, and trains object detectors for multi-label behavior analysis. The upstream repository is pinned for reference at:

```text
e6a7aaf99dd8a80d0319416ff3b980887c754fee
```

This is relevant related work, but it does not estimate the same quantity as static malicious-function or byte-interval recall. Removing it from the numeric baseline table is scientifically correct.

### 1.3 EMBER2024-capa

The live [EMBER2024-capa dataset card](https://huggingface.co/datasets/joyce8/EMBER2024-capa) reports approximately 18.6 million function records from malicious Win32/Win64 files, with function address, raw function bytes, disassembly, and capa capabilities. It explicitly states that the dataset is not deduplicated and that capabilities are not necessarily malicious behaviors. The hosted dataset is marked Apache-2.0 and approximately 23.8 GB.

Consequences:

- it is useful for representation pretraining, capability retrieval, and Tier 2 silver evaluation;
- it is not a balanced raw-file benign/malicious corpus;
- function-hash deduplication and group splitting are mandatory;
- capa labels stay silver and are never silently promoted to malicious gold.

## 2. Research question and estimand

### 2.1 Primary question

> At a fixed analyst or compute budget, can a model trained primarily from file-level labels retrieve more independently validated malicious PE components than static prior systems, attribution/MIL baselines, and simple heuristics?

### 2.2 Unit of prediction

For a PE file `F`, a method returns a ranked sequence:

```text
(sample_sha256, rank, score, file_offset_intervals,
 rva_intervals, function_ids, basic_block_ids, provenance)
```

Each interval is half-open `[start, end)`. A component may contain multiple disjoint intervals. Invalid, virtual-only, certificate, overlay, or unmapped ranges carry explicit states instead of fabricated coordinates.

### 2.3 Primary estimands

- gold malicious-component recall at top-K functions;
- gold byte recall at fixed reviewed-byte fraction;
- time or functions reviewed until the first gold component;
- end-to-end latency and analyzer coverage at matched recall;
- paired improvement over the strongest eligible baseline on the same samples.

File-classification accuracy is a constraint and secondary question, not proof of localization quality.

## 3. Scope and claims

### 3.1 Included in the primary track

- native Windows PE32/PE32+;
- static, nonexecuting analysis;
- unpacked or successfully unpacked samples for which declared analyzers recover stable functions;
- raw on-disk bytes with authorized access;
- x86/x64 reported separately if feature extraction differs.

### 3.2 Excluded or separate strata

- managed .NET;
- self-modifying or runtime-decrypted code;
- kernel drivers unless a dedicated track is defined;
- samples whose packing or corruption prevents stable static analysis;
- source builds with unresolved source-to-binary mapping;
- files with unresolved disagreement between coordinate mappers in the primary gold metrics.

Packed, optimized, obfuscated, and analyzer-disagreement cases remain robustness/failure-analysis strata rather than being silently dropped.

### 3.3 Claims that are allowed only after gates pass

- “malicious-component localization” only after G1 gold feasibility;
- “budget-efficient” only after G4 Pareto improvement including preprocessing and UA optimization;
- “analyst workload reduction” only after G5 analyst evaluation;
- “robust” only after G6 layout/compiler/padding tests;
- “first” only for a precisely scoped combination supported by a systematic audit.

If a gate fails, the paper changes its claim as specified in Section 11; thresholds are not moved after results are seen.

## 4. Hypotheses

- **H1 — File-level validity:** the weak model remains competitive with declared file-level baselines on a temporal test split.
- **H2 — Gold retrieval:** at matched top-K function or byte budget, UA-SAHI-Mal improves gold recall over DeepReflect, attribution/MIL, and simple heuristics.
- **H3 — Budget Pareto:** hierarchical selection approximates exhaustive retrieval with materially fewer encoder/analyzer calls.
- **H4 — Structural reconstruction:** structural guidance improves byte-level localization over nearest/bilinear/bicubic/JBU enough to justify its complete online cost.
- **H5 — Robustness:** ranked evidence is stable in file-offset space across allowed layout, compiler, optimization, and padding changes.
- **H6 — Analyst utility:** ranked evidence reduces time-to-first-relevant-component and reviewed functions in a blinded crossover study.

All six are open hypotheses. The pre-results manuscript must not phrase them as achieved contributions.

## 5. Evaluation evidence tiers

Results from different tiers are never pooled into a single score.

### Tier 0 — Mapping and transformation tests

Purpose: establish coordinate correctness, not malware localization.

- PE parser cross-checks;
- file offset ↔ pixel round trips;
- RVA ↔ file-offset success and explicit failure cases;
- interval-union ↔ mask conversion;
- row-boundary and alignment-padding tests;
- function/basic-block mapping across at least two analyzers on a subset.

### Tier 1 — Controlled provenance

Purpose: verify recoverability and shortcut resistance.

- safely compiled capability-shaped modules plus size/entropy/section-matched inert controls;
- exact source/build/offset provenance;
- multiple locations, lengths, raster widths, and compiler modes;
- no claim that an inserted marker is itself in-the-wild malicious behavior.

### Tier 2 — Rule-derived silver evidence

Purpose: scalable evidence agreement and pretraining.

- YARA match intervals;
- capa instruction/basic-block/function scopes;
- EMBER2024-capa function records;
- rule-family and capability holdouts;
- deduplication by normalized function bytes and source/hash groups.

### Tier 3 — Source-grounded, analyst-adjudicated gold

Purpose: primary localization evaluation.

- reproducible builds with source, compiler flags, symbols, map files, and hashes;
- gold build: no inlining/LTO/ICF and optimization disabled where possible;
- domain-shift build: O1/O2, inlining/LTO/ICF, and selected packing/obfuscation;
- source-linked interval boundaries plus independent maliciousness adjudication by at least two analysts;
- `MALICIOUS_COMPONENT`, `SUPPORTING_COMPONENT`, `BENIGN_OR_SHARED`, and `UNCERTAIN` labels;
- DeepReflect source-grounded artifacts used only under a documented split/leakage policy.

Source/symbol mapping supplies location evidence, not maliciousness. The analyst label remains a separate field.

### Tier 4 — In-the-wild analyst evaluation

Purpose: measure actual triage benefit.

- randomized, blinded crossover conditions;
- UA-SAHI-Mal, DeepReflect, capa, and no-guidance control;
- fixed time or function budget;
- identical reverse-engineering environment and sample information;
- preregistered endpoints, exclusions, experience strata, and applicable ethics review.

## 6. Baseline suite

The plan separates the **minimum defensible suite** from stretch comparisons so that an unbounded baseline list does not block the paper.

### 6.1 Minimum file-level baselines

| Role | Method | Required output |
|---|---|---|
| Engineered features | EMBER LightGBM | calibrated file score |
| Raw bytes | MalConv or MalConv2 | calibrated file score |
| Image/full context | full-image CNN | calibrated file score |
| Weak high resolution | Peters–Farhat-style MIL or a faithful public implementation | file score and instance ranking |
| Proposed | UA-SAHI-Mal file head | file score |

PE-MILCon and a vision transformer are stretch baselines unless a faithful implementation and compute budget are available before the protocol freeze.

### 6.2 Minimum localization/ranking baselines

| Class | Method | Why it is required |
|---|---|---|
| Lower bound | random-K | chance-level paired control |
| Coverage | uniform section/grid-K | tests whether broad coverage is sufficient |
| Cheap heuristic | entropy-K | tests texture/packing shortcuts |
| Attribution | Grad-CAM or Integrated Gradients | standard classifier-explanation baseline |
| Weak learning | ABMIL or Peters–Farhat attention | matched file-label learning baseline |
| Closest prior system | **DeepReflect** | direct static function/basic-block localizer |
| Rules | capa; YARA where applicable | operational signature/capability comparison, labelled silver |
| Upper bound | exhaustive tile/function scan | recall denominator and compute upper bound |
| Supervised | detector/segmenter or function ranker on Tier 3 train gold | prevents an artificial weak-supervision advantage |
| Proposed | UA-SAHI-Mal | budgeted hierarchical interval retrieval |

DSMIL/TransMIL, HiResCAM/LayerCAM, DLLicious-style attribution, FunctionSimSearch, and additional supervised architectures are stretch comparisons selected before test evaluation.

### 6.3 Explicit DECODE treatment

DECODE appears in related work with this conclusion:

> DECODE localizes discriminative regions in images derived from dynamic API-call sequences and uses them for proportional multi-label behavior analysis. Because the present task localizes independently evaluated components in static PE coordinates, DECODE's reported accuracy and pseudo-box AP are not directly comparable and are not included in our numeric baseline tables.

No result table may contain a row labelled `DECODE` unless a future experiment first defines a genuinely shared dataset, input, target, and metric. A Grad-CAM implementation inspired by DECODE is labelled by the actual method name, not as a DECODE reproduction.

### 6.4 Upsampling comparisons

- nearest;
- bilinear;
- bicubic;
- JBU/guided filtering;
- Upsample Anything with byte-only guidance;
- Upsample Anything with structural guidance.

All per-input optimization, transfer, preprocessing, and cache warmup rules are disclosed. If UA is not Pareto-efficient, it is removed from the final method/name rather than protected by a secondary metric.

## 7. Faithful DeepReflect protocol

### 7.1 Environment and provenance

- upstream commit: `4358a7e8ef7fc5951360094867dca852ed23712e`;
- upstream license: GPL-3.0;
- execute in a separate, isolated environment;
- record OS, Python, TensorFlow/Keras, Binary Ninja build/license type, PostgreSQL, capa and rule-set versions;
- do not commit the Binary Ninja license or real-malware archives;
- keep upstream code unmodified for the faithful run; record any patch as a separate experiment.

The repository holds only the integration record in [`../../external/deepreflect/README.md`](../../external/deepreflect/README.md), not a relicensed vendor copy.

### 7.2 Output adapter contract

Each run exports a nonexecutable JSON/Parquet record containing:

```text
sample_sha256
upstream_commit
environment_fingerprint
analyzer_name_and_version
function_id
basic_block_ids
native_addresses
file_offset_intervals
reconstruction_score
rank
threshold_and_calibration_split
feature_extraction_time_ms
ranking_time_ms
failure_code
```

The adapter validates hashes, bounds, nonempty intervals, and mapper version. Scores with unresolved address mapping stay in coverage statistics but not byte-level primary metrics.

### 7.3 Fair comparison rules

1. Train the DeepReflect autoencoder only on the declared benign training split.
2. Keep source project, malware family, near-duplicate function, and compiled variants in one group.
3. Choose thresholds on validation gold only. Never reproduce a per-test-sample 80% TPR threshold as if it were deployable.
4. Always report a threshold-free rank curve in addition to a selected operating point.
5. Compare top-K functions, reviewed-byte fraction, and end-to-end time separately; do not convert one budget into another without showing the mapping.
6. Charge static feature extraction and disassembly as online or clearly amortized offline cost.
7. Use the all-method intersection for paired significance tests and the full eligible set for coverage/failure rates.
8. Report the authors' artifact result and any modernized port separately.
9. Do not use DeepReflect source-grounded test labels to tune UA-SAHI-Mal or its baseline.
10. Record disassembler disagreements and perform a sensitivity analysis on common recovered functions.

### 7.4 Reproduction exit states

- `FAITHFUL`: upstream semantics and pinned environment reproduced;
- `PATCHED_COMPATIBILITY`: only documented compatibility patches, with both diffs and effects reported;
- `INSPIRED`: feature/model/ranking semantics changed; not called DeepReflect in tables;
- `UNAVAILABLE`: dependency, license, artifact, or data limitation prevents execution; coverage reason reported without a fabricated proxy.

## 8. Proposed system work packages

### WP1 — PEAtlas

- typed file-offset/RVA/VA/pixel conversion;
- section-aligned and fixed-width layouts;
- raw/loaded/valid masks;
- pixel-to-offset lookup and disjoint interval unions;
- parser/analyzer disagreement ledger;
- fuzz/property tests and deterministic edge cases.

### WP2 — Benchmark and annotation

- versioned schema and validation tool;
- controlled-provenance build recipes;
- silver ingestion with rule/capability provenance;
- source/symbol mapping;
- dual annotation and adjudication workflow;
- dataset card, consent/ethics status, licenses, and nonredistributable-data instructions.

### WP3 — Coarse weak learner

- negative-bag supervision and positive-unlabeled treatment;
- relation-aware tile/function aggregation;
- file-level calibration;
- counterfactual deletion/sufficiency checks;
- cross-layout consistency in file-offset space.

### WP4 — Reconstruction and selector

- baseline upsamplers and structural guidance;
- uncertainty/section-coverage guard;
- explicit byte/function/latency budgets;
- recursive refinement with measured stop conditions;
- no use of test gold in selection or stopping.

### WP5 — Baseline adapters

- shared versioned output contract;
- DeepReflect faithful adapter;
- capa/YARA adapters;
- attribution and MIL adapters;
- supervised-gold and exhaustive reference implementations;
- uniform timing and failure accounting.

### WP6 — Evaluation and paper

- frozen split hashes and preregistration record;
- grouped confidence intervals and paired tests;
- robustness matrix and failure inventory;
- analyst-study protocol if G1–G4 pass;
- venue-template manuscript and artifact appendix.

## 9. Metrics and statistics

### 9.1 File level

- PR-AUC and ROC-AUC;
- TPR at 0.1% and 1% FPR;
- F1 with threshold-selection protocol;
- NLL/Brier/ECE for calibration;
- per-family/time/architecture strata.

### 9.2 Localization

- byte precision, recall, F1, and AUPRC;
- relevant-function recall@K and precision@K;
- component recall at fixed reviewed-byte/function/time budget;
- first-hit rank and reciprocal rank;
- reviewed-byte and reviewed-function fractions;
- interval IoU and boundary error;
- mask IoU/Dice and bbox AP50/AP75 only as secondary derived metrics.

### 9.3 Efficiency and coverage

- parser/disassembler time;
- coarse encoder time;
- UA optimization time;
- selection/refinement time;
- end-to-end p50/p95;
- throughput, RAM, VRAM, FLOPs/calls;
- success/failure/unsupported coverage by method;
- offline preprocessing reported separately from online latency, never omitted.

### 9.4 Statistical protocol

- file or source-project is the resampling unit, not correlated functions;
- paired bootstrap or permutation tests on the common sample set;
- confidence intervals plus effect sizes;
- multiple independent training seeds where training variability is relevant;
- family/source/toolchain stratification;
- no averaging across evidence tiers;
- missing method output is a coverage result, not an implicitly negative prediction.

Exact sample-size and analyst-study power calculations are frozen before test evaluation.

## 10. Split and leakage controls

- exact SHA-256 deduplication;
- normalized function-byte hash grouping;
- near-duplicate TLSH/ssdeep or appropriate binary-similarity grouping;
- temporal split where collection time is trustworthy;
- malware-family and source-project groups;
- compiler/toolchain/build-option groups;
- packer and unpacked-derivative groups;
- all builds of one source component in one split unless build transfer is the explicit question;
- YARA rule-family and capa capability holdouts;
- annotators blinded to method rankings for gold adjudication;
- DeepReflect threshold/model selection restricted to training/validation;
- benchmark construction and final test labels versioned and frozen before final method tuning.

## 11. Go/No-Go gates

### G0 — Legal, safety, and artifact feasibility

Pass when authorized raw PE access, redistribution rules, malware handling, analyst access, Binary Ninja licensing, and DeepReflect artifact availability are documented.

Failure outcome: paper remains a design/audit document; no claim of runnable cross-system evaluation.

### G1 — Coordinate integrity

Pass when every valid tested raw byte round-trips through PEAtlas, every mapping failure is explicit, and interval unions agree with independent parser/analyzer checks on the preregistered test suite.

Failure outcome: stop localization experiments or narrow to a mapper/artifact paper.

### G2 — Gold feasibility

Provisional planning floor, to be replaced by a power calculation before annotation:

- at least three unrelated source projects/families;
- at least two build modes per project;
- at least 200 adjudicated `MALICIOUS_COMPONENT` instances in total;
- inter-annotator agreement and unresolved fraction reported;
- no single project supplies a majority of primary test components.

Failure outcome: replace “malicious-component localization” with “weak evidence retrieval,” remove unsupported analyst claims, and keep silver/controlled results separate.

### G3 — Faithful baseline and signal

Pass when DeepReflect has a declared reproduction exit state, the minimum baseline suite runs with coverage reported, file-level validity is adequate, and the proposed ranking exceeds random/entropy and at least one learned weak baseline on validation gold.

Failure outcome: diagnose benchmark/model identifiability; do not proceed to a broad superiority claim.

### G4 — Budget Pareto

Pass when the proposed method improves gold recall at matched cost or reduces end-to-end cost at matched recall, with parser/disassembly and UA optimization included.

Failure outcome: remove the efficiency claim and any component, including UA, that is not Pareto-efficient.

### G5 — Analyst utility

Pass when a preregistered blinded study shows a practically meaningful reduction in time-to-first-evidence or functions reviewed, with uncertainty intervals.

Failure outcome: position the work as benchmark/method evaluation, not analyst-productivity improvement.

### G6 — Robustness

Pass when evidence remains stable in authoritative offset/function space across the declared layout, compiler, optimization, and padding changes, and failures are stratified.

Failure outcome: narrow scope and describe the method as shortcut-sensitive; do not use “robust.”

## 12. Execution order

| Phase | Work | Exit artifact | Blocking gate |
|---|---|---|---|
| P0 | licenses, data authorization, reference audit, threat model | signed-off feasibility record | G0 |
| P1 | PEAtlas schema, mapper, tests | versioned mapper + Tier 0 report | G1 |
| P2A | controlled/source builds and annotation pilot | Tier 1 + gold feasibility report | G2 |
| P2B | isolated DeepReflect reproduction | pinned environment + adapter sample | G0/G1 |
| P3 | minimum baselines and benchmark freeze | split hashes + preregistration | G2/G3 |
| P4 | weak learner, selector, upsampling ablation | validation Pareto report | G3/G4 |
| P5 | frozen test, robustness, coverage | final result tables + failures | G4/G6 |
| P6 | analyst study if justified | preregistered Tier 4 report | G1–G4 |
| P7 | venue template, artifact packaging | submission-ready paper/repository | all claimed gates |

P2A and P2B may run in parallel. No test-set results are inspected before P3 freezes metrics, budgets, split hashes, exclusions, and hyperparameter ranges.

## 13. Repository layout for v3

```text
paper/
  README.md
  plan/                  current plan and preregistration material
  decisions/             ADRs
  draft/                 manuscript source and reviewed renders
  references/            BibTeX and official-source index
  reviews/               design, dataset, and manuscript reviews
docs/                     implementation contracts, runbooks, results, verification
src/ua_sahi_mal/          reusable implementation
external/deepreflect/     integration record only; no vendored GPL/malware payload
external/sahi/            historical dependency
external/upsample-anything/ pinned vendored source with provenance record
```

New v3 modules should be added only after their contracts are tested. Existing DECODE/YOLO and BIG2015 evidence code remains in place for reproducibility and is labelled historical at the repository entry point.

## 14. Paper-authoring plan

### 14.1 Manuscript claim order

1. operational problem and exact estimand;
2. closest prior work, led by DeepReflect;
3. benchmark gap stated as an audit-bounded finding, not universal nonexistence;
4. PEAtlas coordinate contract;
5. method only to the level actually implemented;
6. provenance-separated evaluation;
7. matched-cost results and failures;
8. analyst utility only if G5 passes;
9. limitations, safety, and artifact access.

### 14.2 Intended contributions after validation

Limit the final abstract to at most three primary contributions:

1. a versioned, analyst-audited byte-interval benchmark and audit protocol;
2. a budget-aware weak component retriever with explicit coordinate and cost semantics;
3. matched static-PE evaluation against DeepReflect and other baselines, including analyst/robustness evidence where gates pass.

PEAtlas may be named separately in the body, but the abstract should not list five unvalidated systems as already completed contributions.

### 14.3 Current PDF

The 23-page venue-neutral PDF is a review snapshot. Before submission:

- choose the venue and official template;
- redesign wide tables rather than shrinking or allowing character-level wrapping;
- split resource/dataset/baseline tables when necessary;
- replace every `[TBD]` only from frozen output artifacts;
- add the explicit DECODE non-comparability sentence;
- update the EMBER2024-capa facts and citation;
- ensure Markdown, TeX, BibTeX, and rendered PDF are generated from one revision.

## 15. Highest-risk reviewer questions

| Question | Required evidence |
|---|---|
| “Is this only DeepReflect with image tiles?” | precise algorithmic difference, equal-budget comparison, and ablation |
| “Why is DECODE missing?” | explicit task/input/label mismatch in related work and ADR |
| “Did you tune DeepReflect on test gold?” | frozen validation threshold and threshold-free curves |
| “Are capa/YARA being called gold?” | separate silver tier and rule/capability holdout |
| “Do symbols prove maliciousness?” | analyst label separated from source/symbol boundary provenance |
| “Does a bbox corrupt byte semantics?” | interval-union canonical labels and round-trip tests |
| “Is attention being treated as explanation?” | external gold, perturbation checks, and analyst outcomes |
| “Did you hide unsupported samples?” | full-set coverage/failure table plus intersection paired test |
| “Does UA cost more than it saves?” | complete end-to-end Pareto curve |
| “Is the gold set just three old families?” | new source projects, group split, and G2 diversity floor |

## 16. Definition of done

The v3 paper is ready for submission only when:

- G0–G4 and every gate named in the abstract have passed;
- the minimum baseline suite, including a declared DeepReflect reproduction state, is complete;
- test splits and labels were frozen before final tuning;
- all claims trace to versioned raw result artifacts;
- the repository safety scan finds no malware payload or secret;
- third-party licenses and revisions are recorded;
- the final PDF has been rendered and visually checked page by page;
- tables contain no placeholders, overlaps, clipped text, or character-level wrapping;
- limitations include DeepReflect ground-truth incompleteness, analyzer disagreement, source-build domain shift, and silver-label semantics.
