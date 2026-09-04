# UA-SAHI-Mal pre-results paper draft review

- **Review date:** 2026-09-04
- **Reviewed artifacts:** Markdown, LaTeX, 23-page PDF, bibliography, Korean design review, public-dataset investigation, current repository implementation/results
- **Decision:** promising research design, not submission-ready

## 1. Bottom line

Replacing DECODE with DeepReflect as the direct prior-system baseline is correct, but it must not be implemented as a one-row name substitution.

DeepReflect matches the static PE function/basic-block localization task. DECODE does not: it operates on dynamic API-call images and trains from Bayesian Grad-CAM pseudo-regions for multi-label behavior analysis. The paper should therefore:

1. use DeepReflect as the primary prior-system comparison;
2. retain random/uniform/entropy, attribution, MIL, capa/YARA, exhaustive, and supervised-gold controls;
3. compare all methods at matched function, byte, and latency budgets;
4. report method coverage and analyzer failures;
5. keep DECODE in related work with an explicit non-comparability explanation.

The current English draft already contains DeepReflect in its localization and analyst-study tables and does not contain a DECODE result row. That part is directionally consistent. What is missing is the explicit rationale and the faithful-reproduction protocol now captured in the v3 plan and ADR.

## 2. What the draft does well

- It does not invent numerical results. `[TBD]` is consistently used for unmeasured values.
- It distinguishes file detection from component retrieval.
- It treats ranked byte intervals as authoritative and bbox as a derived view.
- It separates controlled provenance, rule-derived silver, source-grounded gold, and analyst evaluation instead of averaging incompatible evidence.
- It explicitly states that YARA/capa matches and model attribution have different semantics.
- It includes leakage controls across source, family, time, compiler, packer, file hash, function hash, and rule/capability groups.
- It charges Upsample Anything's per-input optimization to the online budget.
- It keeps supervised localizers as baselines once gold annotations exist, avoiding an artificial weak-supervision advantage.
- It defines failure gates that can narrow the claim instead of forcing a positive result.

These are strong foundations for a security venue paper.

## 3. P0 issues to resolve before experiments are presented

### P0-1 — The manuscript reads like a completed system, but the repository does not implement it

The draft says “we introduce” PEAtlas, relation-aware MIL, structure-guided UA, guarded selection, a multi-tier benchmark, and an analyst study. The current repository instead contains:

- historical DECODE/YOLO and SAHI-oriented code;
- a BIG2015 family-decision evidence protocol;
- partial raw/source interval conversion utilities;
- no `PEAtlas` implementation;
- no DeepReflect adapter;
- no source-grounded analyst-adjudicated component corpus;
- no analyst-study protocol/data;
- no complete v3 baseline harness.

Until those work packages exist, the abstract and contributions must use future or planned language consistently. A pre-results design paper can be legitimate, but a normal empirical submission cannot present planned components as completed artifacts.

**Required action:** track every claimed component against a repository path, test, dataset version, and result artifact. Remove or conditionalize any contribution without that trace.

### P0-2 — DeepReflect fairness is underspecified

The official DeepReflect paper used three source-grounded malware projects for ground truth, could not locate 14%–30% of malicious functions, and chose thresholds from those samples. The public implementation depends on Binary Ninja 2.3, Python 3.7.3, PostgreSQL 11.10, and GPL-3.0 code.

The current draft lists `DeepReflect` but does not yet specify:

- faithful upstream commit and environment;
- how native addresses become canonical file-offset interval unions;
- whether the authors' threshold or a newly validated threshold is used;
- how test-gold threshold leakage is prevented;
- what happens when Binary Ninja and another analyzer disagree;
- how unsupported/failed samples affect paired comparisons;
- whether feature extraction time is online or amortized.

**Required action:** follow [`../plan/RESEARCH_PLAN_v3.md`](../plan/RESEARCH_PLAN_v3.md) Section 7 and give each run a reproduction exit state (`FAITHFUL`, `PATCHED_COMPATIBILITY`, `INSPIRED`, or `UNAVAILABLE`).

### P0-3 — The baseline list is too large to be an executable commitment

The draft lists more than a dozen localization models, multiple file classifiers, six upsamplers, and many ablations. This is comprehensive as a survey wish list but risky as a preregistration: incomplete or shallow reproductions invite reviewer criticism, while implementing everything may consume the project before the core gold benchmark exists.

**Required action:** freeze the minimum suite first:

- random-K;
- uniform section/grid-K;
- entropy-K;
- one attribution method;
- one weak MIL method;
- DeepReflect;
- capa and YARA where applicable;
- exhaustive scan;
- one supervised-gold localizer;
- UA-SAHI-Mal.

Treat additional CAM/MIL/architecture rows as stretch baselines selected before final test access.

### P0-4 — Gold feasibility remains the true critical path

The method cannot be evaluated as malicious-component localization without independently adjudicated component labels. Source symbols provide boundaries but do not establish maliciousness; capa and YARA provide silver evidence; controlled inserts provide provenance but not in-the-wild malicious semantics.

**Required action:** run the gold pilot before expensive full-model training. Record project diversity, component counts, disagreement, uncertain fraction, and source-to-binary mapping failures. If the v3 G2 floor fails, rename the task “weak evidence retrieval” before writing results.

### P0-5 — Several dataset statements needed live correction

The supplied investigation marked EMBER2024-capa and DeepReflect artifact facts as unverified. Live primary-source checking shows:

- the DeepReflect code and dataset index are currently accessible;
- ground-truth archive links are exposed, although the artifacts include real malware and require controlled handling;
- EMBER2024-capa contains approximately 18.6 million malicious Win32/Win64 function records with address, bytes, disassembly, and capa labels;
- the dataset is explicitly not deduplicated, does not provide a balanced benign raw-file corpus, and labels capabilities rather than maliciousness;
- the hosted license is Apache-2.0.

**Required action:** update the dataset table and BibTeX to cite the actual `EMBER2024-capa` dataset card. Do not cite the parent dataset URL as if it were the supplemental function dataset.

## 4. P1 scientific and writing issues

### P1-1 — Novelty is still conditional

PEAtlas, MIL, counterfactual objectives, consistency, uncertainty coverage, hierarchical selection, and feature upsampling are individually established ideas. A top-tier claim cannot rest on assembling them. The strongest defensible novelty is likely the combination of:

- independently adjudicated byte-interval evaluation;
- matched analyst/compute budgets;
- cross-coordinate and cross-analyzer provenance;
- direct comparison with DeepReflect;
- evidence-recall/cost and analyst utility rather than attention visualization.

If the method itself does not show a clear Pareto gain, reposition around the benchmark and rigorous negative result rather than overstating algorithmic novelty.

### P1-2 — “Gold” needs two separate fields

The draft sometimes compresses two facts into “source-grounded gold”:

1. the binary interval boundary is supported by source/symbol/build evidence;
2. the component is malicious according to analyst adjudication.

These can disagree or be uncertain. The annotation schema should store location provenance and semantic label provenance separately.

### P1-3 — “SAHI” naming remains vulnerable

The draft appropriately calls the core mechanism budgeted hierarchical slicing and reserves “Full SAHI” for an actual slice detector/segmenter. Keep this discipline in the title, figures, code, and result tables. If the final method never runs a detector on slices, reviewers may still challenge `SAHI` in the system name; the paper should be prepared to rename the method if that distracts from the actual contribution.

### P1-4 — Analyst study scope may exceed available resources

The current design calls for blinded crossover analysis, recruitment, compensation, and institutional review. That is valuable but schedule- and access-sensitive.

**Required action:** decide before model claims whether the analyst study is a required paper contribution or a gated extension. If unavailable, remove workload-reduction language from the abstract/title and retain objective retrieval metrics.

### P1-5 — Statistical power is not specified

`[TBD]` seeds and analyst counts are honest, but the plan needs a power/sensitivity analysis before test access. Functions within one binary and builds from one source are correlated; treating them as independent would produce invalidly narrow intervals.

**Required action:** resample at file or source-project level, preregister the minimum detectable effect, and report between-seed and between-sample uncertainty separately.

## 5. PDF and presentation review

The supplied PDF was rendered page by page. It has 23 letter-size pages, no encryption, no forms, and no suspicious embedded JavaScript. Overall text is legible, but it is a review artifact rather than a polished submission.

Observed defects:

- **Page 7:** the “Position of existing resources” table has crowded columns and overlapping/wrapped text around EMBER2024-capa, YARA, and capa rows.
- **Pages 13–14:** the dataset table crosses a page boundary and narrow cells split words such as `controlled-provenance` into character-like fragments.
- **Page 17:** the gold-retrieval and upsampling tables wrap method names awkwardly; `UA-SAHI-Mal` is broken across lines.
- **Page 18:** the ablation table has severe word fragmentation (`uncertainty`, `representation`, `section atlas`) and poor scanability.
- The document uses a generic single-column `article` layout and a long table of contents; it does not estimate the page budget of USENIX Security, CCS, IEEE S&P, NDSS, TIFS, or TDSC templates.
- The authors remain placeholders, and all result/statistical/ethics identifiers remain TBD as intended.

**Required action:** do not merely reduce the font. Split wide tables, shorten column labels, move detailed matrices to an appendix/artifact, and rebuild in the selected official venue template. Re-render and inspect every final page.

## 6. Required manuscript changes for the next revision

1. Add an explicit related-work paragraph explaining why DECODE is not a numeric baseline.
2. Expand the DeepReflect paragraph to disclose its three-project gold set, incomplete function recovery, threshold selection, and analyzer dependency.
3. Replace the current baseline wish list with minimum and stretch groups.
4. Correct EMBER2024-capa metadata and citation.
5. Separate location provenance from maliciousness adjudication in the annotation schema.
6. Convert “we introduce” to “we design/will evaluate” wherever no implementation/artifact exists, or wait to use present tense until the artifact exists.
7. Reduce intended contributions from five to at most three primary claims.
8. Add an implementation-status table linking each claimed component to code, tests, data, and result artifacts.
9. Add analyzer coverage/failure rate to the primary result tables.
10. State that all-method intersection results and full-set coverage results are both reported.
11. Define the validation-only DeepReflect threshold protocol and threshold-free ranking curve.
12. Replace the generic PDF only after the target venue and page budget are chosen.

## 7. Recommended paper structure

1. Introduction and exact analyst-facing estimand
2. Background and closest prior work, with DeepReflect first
3. Dataset/benchmark audit and bounded gap statement
4. PEAtlas coordinate and annotation contract
5. Proposed weak retriever and budget definition
6. Provenance-separated benchmark construction
7. Experimental protocol and faithful baseline contracts
8. Results: validity, gold retrieval, cost, robustness, analyst utility if gated
9. Failure analysis and security/adaptive considerations
10. Ethics, artifact access, limitations, and conclusion

The current 16-section manuscript can be compressed into this flow; repeated motivation and defense text can move to an artifact appendix.

## 8. Final review verdict

The new direction is materially stronger than using DECODE as a direct baseline. DeepReflect forces a fair comparison with the closest known static localization system and makes novelty claims more credible. The remaining risk is not baseline choice but execution feasibility: a trustworthy gold set, an address mapping contract, and a faithful legacy baseline must exist before the current draft's contribution language is justified.

Proceed in the order: legal/artifact feasibility → PEAtlas integrity → gold pilot → DeepReflect reproduction → minimum baselines → proposed method → robustness/analyst study → venue manuscript.
