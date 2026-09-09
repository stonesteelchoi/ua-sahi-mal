# v3 P0/G0 feasibility check

- **Date:** 2026-09-07
- **Machine:** cau (Windows 11, RTX 5070 Laptop, torch 2.8.0+cu128, Python 3.12.10)
- **Repo commit basis:** `98d64c1` (main) + branch `codex/peatlas-tier0`
- **Author:** automated agent hand-off; external-authorization items require the
  researcher / institution and are marked accordingly.

This records the status of every **G0** item from `paper/plan/RESEARCH_PLAN_v3.md`
§11 and the current **G1** status, with evidence and next actions. Items that
depend on external authorization are not asserted; they are marked
`UNKNOWN — needs user/institution` so the paper does not overclaim runnability.

## G0 — Legal, safety, and artifact feasibility

| Item | Status | Evidence / next action |
|---|---|---|
| Authorized raw PE data access | **UNKNOWN — needs user/institution** | No approved raw-PE corpus is present or referenced in the repo. Next: user confirms whether an authorized raw-PE dataset (and its data agreement) exists. |
| Redistribution rules | **DOCUMENTED (policy), data pending** | `SECURITY.md`, `THIRD_PARTY.md`, `external/deepreflect/README.md` state non-redistribution of malware/binaries and GPL/proprietary boundaries. Applies once actual data is chosen. |
| Malware handling procedure | **PARTIAL** | Repo policy forbids executing/committing malware and any dynamic analysis; static-only. Institutional isolated-environment approval is **UNKNOWN — needs user/institution**. |
| Analyst (gold reviewer) access | **UNKNOWN — needs user/institution** | Tier 3 needs ≥2 independent analysts for adjudication; none identified. Next: user states whether analyst reviewers are available. |
| Binary Ninja licensing | **UNKNOWN — needs user/institution** | DeepReflect requires Binary Ninja 2.3; not installed on cau and no license recorded. Next: user states license availability. |
| DeepReflect artifact availability | **AVAILABLE (upstream), NOT_RUN** | Public repo `evandowning/deepreflect` pinned `4358a7e8…`; GPL-3.0; legacy env Debian10/Py3.7.3/BinaryNinja2.3/PostgreSQL11.10. Status `NOT_RUN` (`external/deepreflect/README.md`). Needs a separate isolated checkout. |

**G0 verdict:** **NOT PASSED.** Legal/tooling/analyst authorization items are
unconfirmed. Per the plan, until G0 passes the work stays a design/mapper track
with no claim of runnable cross-system evaluation. Independent, non-blocked work
(PEAtlas coordinate integrity) proceeds regardless.

## G1 — Coordinate integrity

G1 passes when (a) every valid tested raw byte round-trips through PEAtlas,
(b) every mapping failure is explicit, and (c) interval unions agree with
**independent parser/analyzer** checks on a **preregistered** test suite.

| Clause | Status | Evidence |
|---|---|---|
| (a) valid bytes round-trip | **MET (synthetic suite)** | `tests/test_peatlas_atlas.py` round-trips offset↔rva↔va over mapped regions; `tests/test_peatlas_regressions.py` checks every successful point and interval segment across small malformed layouts; `tests/test_peatlas_intervals.py` verifies all subset pairs in the small integer-set oracle. |
| (b) explicit failure states | **MET** | All non-mappable coordinates return a typed `MapStatus` (virtual-only, padding, overlay, certificate, truncated, unmapped, overlapping); no fabricated offsets. |
| (c) independent parser/analyzer agreement, preregistered | **OPEN (partial evidence)** | An independent-parser cross-check now exists: `tests/test_peatlas_disarmed.py::test_disarmed_cross_parser_agreement_pefile` compares PEAtlas section fields and sampled conversions against **pefile** (armed and SOREL-style disarmed fixtures), and `ua_sahi_mal.sorel.static_stage` cross-checks every parsed SOREL file against pefile. `pefile` is a dev dependency so CI runs it (it was previously `importorskip`'d and skipped). Still OPEN because the fixtures are self-authored synthetic PEs, no second *analyzer* is compared, and the suite is not preregistered on real PEs. The SOREL pilot (E1) is the planned real-PE cross-parser evidence. |

**G1 verdict:** **PARTIALLY MET.** The coordinate-correctness core (round-trip +
explicit failures + interval algebra) is implemented and green, and a pefile
cross-parser check runs in CI on synthetic (armed + disarmed) fixtures. A
preregistered real-PE suite (SOREL E1) and analyzer-level agreement remain before
G1 can be declared.

## G2 — Gold feasibility (not started)

Requires ≥3 unrelated source projects, ≥2 build modes each, ≥200 adjudicated
`MALICIOUS_COMPONENT` instances. Blocked on G0 (data + analysts). Not started.

## What is independently done now (no external input required)

- PEAtlas contract (`docs/PEATLAS_CONTRACT.md`) and first implementation
  (`src/ua_sahi_mal/peatlas/`): file-offset/RVA/VA per-section mapping, explicit
  failure states, half-open interval-union algebra, section-boundary interval
  splitting, analyzer component + provenance interface.
- Tier 0 tests green (66 tests, local Python 3.10): round-trip, boundary
  splitting, exhaustive interval algebra, strict coordinate types, complete
  header bounds, and malformed layouts (overlap/truncation/padding/overlay/
  virtual-only/certificate/PE32+). The PR's GitHub CI provides the authoritative
  Python 3.10/3.12 and Docker results for each pushed revision.

## Next actions

1. **User/institution input (G0):** raw-PE dataset = SOREL-20M under its Terms
   (G0-S PARTIAL: internal research permitted; publication pending §2(c)
   clarification — see `docs/sorel20m_protocol.md`). Analyst reviewers: not
   secured (Tier 3 gold out of current scope). **Binary Ninja: confirmed
   unobtainable (2026-09-09)** — DeepReflect faithful reproduction is an explicit
   exclusion, not a gate (amendment §1.2/§10).
2. **Independent-parser agreement (to close G1c):** the pefile cross-check is in
   place and CI-enforced; remaining: run it on the preregistered SOREL pilot
   (real PEs, E1) and add the parser/analyzer disagreement ledger (WP1).
3. **Pixel projection (next task):** wire `ua_sahi_mal.encoding` pixel↔offset into
   PEAtlas behind the contract interface (not in this change).
4. **DeepReflect adapter (P2B, separate env):** realize the `Provenance`/component
   interface against a pinned isolated DeepReflect run; export nonexecutable
   result rows only.

Code-verification success here is a **coordinate-correctness** result and is **not**
a malicious-component localization result.
