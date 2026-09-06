# Documentation map

The repository now separates the current paper workspace from implementation documentation and historical research lanes.

## Current paper work

- paper hub: [`../paper/README.md`](../paper/README.md)
- v3 plan: [`../paper/plan/RESEARCH_PLAN_v3.md`](../paper/plan/RESEARCH_PLAN_v3.md)
- DeepReflect baseline decision: [`../paper/decisions/ADR-001-deepreflect-baseline.md`](../paper/decisions/ADR-001-deepreflect-baseline.md)
- manuscript review: [`../paper/reviews/PAPER_DRAFT_REVIEW_2026-09-04.md`](../paper/reviews/PAPER_DRAFT_REVIEW_2026-09-04.md)
- draft and bibliography: [`../paper/draft/README.md`](../paper/draft/README.md), [`../paper/references/README.md`](../paper/references/README.md)

## Reusable implementation contracts and runbooks

- [`NEW_MACHINE_HANDOFF.md`](NEW_MACHINE_HANDOFF.md): new GPU machine setup, selective asset restoration, and copy-ready LLM handoff

- [`DATA_CONTRACT.md`](DATA_CONTRACT.md): safe source-range/bbox dataset contract for the historical detector lane
- [`EVIDENCE_PROTOCOL.md`](EVIDENCE_PROTOCOL.md): BIG2015 v2 evidence protocol execution
- [`DECODE_PIPELINE.md`](DECODE_PIPELINE.md): historical static DECODE-shaped import/detection runbook
- [`SOURCES.md`](SOURCES.md): earlier implementation-source inventory
- [`verification/`](verification/): environment and result-verification records
- [`results/`](results/): immutable measured outputs and interpretation notes

## Historical research documents

- [`RESEARCH_PLAN.md`](RESEARCH_PLAN.md): v1 DECODE/YOLO and budgeted-SAHi plan
- [`RESEARCH_PLAN_v2.md`](RESEARCH_PLAN_v2.md): BIG2015 family-decision evidence plan
- [`RESEARCH_AUDIT_2026-09-04.md`](RESEARCH_AUDIT_2026-09-04.md): validity-mask and control audit of v2 results
- [`RESEARCH_SUMMARY.md`](RESEARCH_SUMMARY.md): historical experiment summary
- [`LITERATURE_REVIEW.md`](LITERATURE_REVIEW.md): v2 malware-image XAI literature check
- [`DECODE_BASELINE_PLAN.md`](DECODE_BASELINE_PLAN.md): superseded v2 DECODE/Grad-CAM comparison analysis
- [`EXTERNAL_REVIEW_PROMPT.md`](EXTERNAL_REVIEW_PROMPT.md): snapshot of the v2 external-review brief
- [`legacy_remote_sensing/`](legacy_remote_sensing/): original remote-sensing prototype documentation

Historical documents remain where old result links can resolve, but their headings point readers to the active v3 paper workspace. Do not combine v1/v2 measurements with v3 malicious-component metrics.
