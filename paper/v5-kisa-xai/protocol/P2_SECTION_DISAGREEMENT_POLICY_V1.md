# P2-SECTION-DISAGREEMENT-V1

Status: preregistered policy for the P2 train/validation structure audit. This document does not authorize protocol freeze.

## Mapping and ledger

- PeAtlas remains the source of structural ownership when the independent pefile comparison agrees.
- If the only mismatched raw fields are `section_count` and/or `raw_section_overlay_boundary`, keep the hash-valid sample and map its entire byte range to `unknown`. Preserve PeAtlas's original region byte totals in `pre_adjudication_region_bytes` and the full mismatch details in `crosscheck` and `adjudication`.
- Use `section_count_disagreement` when section count differs, including when both eligible fields differ. Use `raw_section_boundary_disagreement` when only the normalized raw-section boundary differs. Record `P2-SECTION-DISAGREEMENT-V1` as the adjudication policy version. These reasons are distinct from `P2-MALFORMED-HEADER-V1` parse-error reasons.
- Any other raw-field mismatch, including one alongside an eligible field, remains `disagreement` without fallback. Any unclassified parse error remains an error. Never drop a sample.
- Native pefile overlay offset is a diagnostic value in the ledger and summary. Its difference alone never triggers fallback or gate failure. The normalized raw-section boundary is the comparable boundary field.

## P2 acceptance criterion, registered before rerun

On the complete deduplicated train/validation population, require `fallback_reason_counts` to equal the previous audit's observed breakdown: `directory_count_exceeds_optional_header_capacity: 62`, `declared_optional_header_missing_or_truncated: 1`, `section_count_disagreement: 10`, and `raw_section_boundary_disagreement: 0`. Require zero unclassified parse errors, zero hash/size errors, zero remaining disagreements, and zero new reason codes. Verify complete ledger coverage and retain `protocol_freeze_authorized=false` pending C6 evidence review.

Only when these checks hold may the work proceed to C6. If any differs, document the cause and then adjudicate it; do not silently accept a changed count or mapping. The 1,854 prior native overlay differences are diagnostic and have no required equality count.
