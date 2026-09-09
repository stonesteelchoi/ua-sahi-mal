# SOREL-20M E2 Protocol — Silver-Evidence Retrieval (v3 amendment §7)

This protocol governs E2: whether a cheap byte-scope selector localizes the
static file-offset regions that carry real malicious evidence better than naive
baselines, and at what cost. It is pre-registered and frozen as `E2_prereg_v1`
in `configs/sorel20m_e2_v1.yaml` **before** any result is produced.

E2 uses **silver** (weak, tool-attributed) evidence targets, not gold: Binary
Ninja / DeepReflect function-level ground truth is an explicit v3 exclusion. E2
is therefore framed as a silver-target *retrieval* study with that limitation
stated.

Binaries are **never** decompressed or analyzed in the cloud session. E2 runs
only on the operator machine (cau), from the isolated data path, in memory. The
cloud session builds and verifies the tooling only.

## G0-S publication scope

Silver-evidence intervals are sample-linked derived data. Until written Terms
§2(c) clarification arrives, every E2 aggregate report is stamped
`INTERNAL_ONLY`; no SHA and no sample-linked offset list is ever published.
`e2_report.assert_no_sample_link` refuses to emit a report that carries either.

## Silver evidence (union per file)

| Source | Scope | Overlay-valid | In-memory | How |
| --- | --- | --- | --- | --- |
| `embedded_artifact` | byte | yes | yes | scan raw bytes for embedded PE images; claim the (exactly computable) header region |
| `yara` | byte | yes | yes | YARA rule string matches via `rules.match(data=...)` — no disk, no disassembly |
| `capa` | function | no | **no (writes to disk)** | capability matches -> enclosing function RVA extent -> file offsets via the E1-verified `PeAtlas.map_component` |

Entropy is **not** a silver source — it is a selector feature only — so the
retrieval comparison is free of circularity.

**Environment split (v2).** `embedded_artifact` and `yara` scan the decompressed
bytes purely in memory, so they run on the AV-monitored operator machine (cau).
**capa does not**: its vivisect backend (`viv_utils.getWorkspaceFromBytes`)
writes the decompressed sample to a temp file to build the workspace, which
persists a disarmed-but-signature-intact sample to disk and trips resident AV
(observed on cau: AhnLab quarantined it — see
`claude/E2_capa_디스크persist_안전이슈`). The capa runner therefore **refuses
without an isolated `--capa-work-dir`**, confines its temp writes to that dir, and
must be run **only in a dedicated isolated environment without resident AV**.
On any failure the run degrades to the other silver sources and records the
reason. `E2_prereg_v2` (`configs/sorel20m_e2_v2.yaml`) is the cau pilot
(silver = `embedded_artifact ∪ yara`); the capa arm runs `v1` in the isolated
environment.

## Tiles, selectors, strata

A tile is a contiguous `tile_bytes` (49,152 B) file-offset interval. Budgets are
`{2, 5, 10, 20, 50}%`, primary 10%. Pilot selectors (no training): `random`,
`uniform`, `front_first`, `back_first`, `entropy`, `entropy_boundary`;
`oracle_silver` is the unfair ceiling. `attribution` / `MIL` / `exhaustive` are
deferred to full E2. Pre-registered strata: **overlay_dominant** (overlay share
> 50%, ~40% of the cohort per E1) vs **non_dominant**.

## Metrics and gate

Per file (defined only where silver mass > 0): `coverage@budget`
(silver ∩ selected / silver), `byte_iou`, `interval_recall_50`, `evidence_hit`.
Selectors are compared by paired bootstrap of per-file coverage@10% with
Holm-Bonferroni correction, per stratum.

**Gate (pilot):** a byte-scope selector (`entropy` / `entropy_boundary`) beats
both `random` and `front_first`, paired and Holm-significant, in **both** strata;
and in `overlay_dominant` it beats `front_first` — confirming the E1 hypothesis
that the file-front positional prior inverts where the payload lives in the
overlay. A negative result is reported (it questions the premise of cheap
selection), not hidden.

## Pipeline (operator, cau)

cau pilot (in-memory silver — AV-safe):

```
sorel20m_e2_run.py --compressed-dir <iso>/compressed --sha-list <iso>/..._effective_sha256.txt \
    --out-prefix <iso>/e2 --static-only [--enable-yara --yara-rules <dir>]
sorel20m_e2_aggregate_gate.py --results <iso>/e2_e2_results.json --out <iso>/e2_report.json
```

Isolated environment only (no resident AV) — the capa arm:

```
sorel20m_e2_run.py ... --static-only --enable-capa --capa-rules <dir> \
    --capa-work-dir <iso>/capa_work --capa-version <v>
```

`--static-only` is required. `--enable-capa` is **refused without
`--capa-work-dir`** and must never be run on cau (capa writes the sample to
disk). Per-file results (SHA-carrying) stay in the isolated path; the aggregate
report is SHA-free and INTERNAL_ONLY.
