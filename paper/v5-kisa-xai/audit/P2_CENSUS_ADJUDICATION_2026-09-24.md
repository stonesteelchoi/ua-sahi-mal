# P2 census adjudication — 2026-09-24

## Decision

**Freeze the P2 structural mapping policy** `conservative_unknown_v1` with
`P2-MALFORMED-HEADER-V1` and `P2-SECTION-DISAGREEMENT-V1` for the recorded
train/validation population and implementation hashes below. The observed
fallback reasons and counts satisfy the preregistered P2 gate. Every selected
sample remains in the ledger; 73 uncertain files are mapped entirely to
`unknown` without fabricated structure labels.

This is a **P2 policy freeze**, not authorization to freeze the entire
PSA-XAI protocol or access held-out test payloads. The census summary records
`protocol_freeze_authorized=false`; subsequent protocol gates remain pending.
Any mapping-policy or implementation change requires a new version, synthetic
regression fixture, and a new census before that version can replace this one.

## Evidence

- Git commit at adjudication supplement: `ff57e250d0d58b0ae3e2bfa1b638b521c7573885`.
- Execution environment: repository `.venv/pyvenv.cfg` records Python 3.12.10; the `.venv` launcher is currently broken because its configured base interpreter is unavailable. The census audit plan records `pefile` 2024.8.26.
- Policy documents: `paper/v5-kisa-xai/protocol/P2_MALFORMED_HEADER_POLICY_V1.md` and `paper/v5-kisa-xai/protocol/P2_SECTION_DISAGREEMENT_POLICY_V1.md`.
- Census summary: `D:\secure-malware-data\psa\audit\p2_census_20260924_policy_v1\structure_audit_summary.json`, SHA-256 `b43de95029e5d1ade046843d36786db5bdc43eef081b3cce9b6302de3b192039`.
- Portable copies: `paper/v5-kisa-xai/audit/p2_census_20260924_policy_v1/summary.json` and `paper/v5-kisa-xai/audit/p2_census_20260924_policy_v1/audit_plan.json` (ledger excluded).
- Ledger: sibling `structure_ledger.jsonl`, 217,302,754 bytes; independently recomputed SHA-256 `de937d73b45ab9d33679671508001489d79904be61c0540ad8e073548c9f133c`, matching the summary.
- Census: `complete=true`, `limit=0`, population and selected count 169,020, with `test_payload_access=false`; 139,087 train and 29,933 validation ledger rows, 169,020 unique IDs, no duplicate IDs.
- Statuses: 168,947 `agreement`; 73 `accepted_unknown_fallback`. Expected and actual fallback reasons match exactly: directory count exceeds optional-header capacity 62; declared optional header missing or truncated 1; section count disagreement 10. No new P2 reason appears.
- Ledger check: all 73 fallback structures have `unknown` bytes equal to file size and only `unknown` spans; all have `map_entire_file_as_unknown` action. No missing source SHA-256 or noncontiguous/wrong-size span was found.
- Crosscheck mismatches: `section_count` 10 and `raw_section_overlay_boundary` 5, all on accepted fallback rows. No mismatch field appears on agreement rows. Native overlay differences (1,854) are diagnostic under the established policy.
- Summary reports `p2_structure_gate_passed=true` and `protocol_freeze_authorized=false`. The latter is retained as a separate full-protocol decision.
- Input manifest SHA-256 `3dc0bd7fb42935692462013f716bbd8ccd339b20bb436289aa93e78852b17414` matches the summary. Current `scripts/psa_structure_audit.py` SHA-256 `fdc5ce7d1124fb678c5c36ae47b2de061d45fb7ae1017ccefdc6ef9ab4e46ce9` and `src/ua_sahi_mal/kisa_xai/structure.py` SHA-256 `6d79fa79175e9c991f2128f6fb6f6a598650bd2593d328b827c3de193853eb44` also match the summary.

The full census invocation from `C:\research\ua-sahi-mal` (the command reconstructed from the prior diagnostic invocation and the recorded audit-plan parameters) was:

```powershell
.\.venv\Scripts\python.exe -u scripts\psa_structure_audit.py `
  --rasters-dir D:\secure-malware-data\psa\rasters `
  --manifest D:\secure-malware-data\psa\manifest_stage2.csv `
  --samples-dir D:\secure-malware-data\psa\pe-machine-learning-dataset\samples `
  --outdir D:\secure-malware-data\psa\audit\p2_census_20260924_policy_v1 `
  --workers 4 --static-only --adjudication-policy conservative_unknown_v1
```

## Scope and follow-up

The decision uses the user-completed static census and independently streamed
its ledger. No original PE was executed, imported, dynamically loaded, or
modified during this adjudication. The local `.venv` launcher currently fails
because its configured Python path is unavailable; read-only ledger validation
used `C:\TOOL\anaconda\python.exe`. C7 should resolve the environment before
runtime checks and continue batch/target-layer validation under the frozen P2
mapping policy.
