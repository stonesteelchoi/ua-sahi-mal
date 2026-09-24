# P2 malformed optional-header mapping policy v1

## Decision

Apply this rule to a train/validation source only when the PeAtlas parser reports
one of the two malformed optional-header conditions below. Keep the source in
the selected population and in the census ledger. Do not infer header,
directory, section, certificate, or overlay ownership from bytes outside the
declared optional-header extent. Do not substitute fields recovered by a more
permissive parser.

| Stable reason code | Trigger | Structure-map result |
| --- | --- | --- |
| `directory_count_exceeds_optional_header_capacity` | The declared data-directory count exceeds the number of complete directory entries that fit in `SizeOfOptionalHeader`. | One span `[0, file_size)` labelled `unknown`; warning `conservative_unknown_v1:directory_count_exceeds_optional_header_capacity`. |
| `declared_optional_header_missing_or_truncated` | The declared optional header is absent or shorter than the fixed fields needed to locate its declared directories. | One span `[0, file_size)` labelled `unknown`; warning `conservative_unknown_v1:declared_optional_header_missing_or_truncated`. |

The map must cover the complete non-empty file exactly once. The sample remains
eligible for later image/model analysis; structure-based attribution for this
sample is unavailable. The original parse error and reason code remain in the
ledger. Do not mark the independent parser comparison as an agreement: its
status remains a parse error, even though the representation fallback is
defined.

## P2 census accounting

Keep the existing parse-error event and identify its reason code. Report the
number of fallback maps separately from parser agreements. Never turn a
fallback into a successful raw-field comparison, silently remove the sample,
or claim that unknown bytes have a more specific owner. Apply only to the two
diagnosed classes; any new parse-error class is unresolved and blocks the
crosscheck disposition pending adjudication.

The independent `pefile` object's ability to parse a file does not authorize
reading beyond the declared optional header. The two classes above account for
the 63 hash-valid errors in the 2026-09-23 P2 census (62 directory-capacity
errors and one missing/truncated optional header). This rule is a mapping
policy; it does not by itself authorize protocol freeze.

## Synthetic regression vectors and expected values

Use synthetic non-empty byte buffers only; do not open dataset payloads. Invoke
the conservative fallback with each stable reason code and assert the exact
whole-file partition, complete byte coverage, `unknown == file_size`, all other
region byte counts zero, and the exact versioned warning shown above. Include
both reason codes as separate cases. These vectors pin fallback semantics;
they do not claim to test parser detection or establish cross-parser agreement.

## Change control

Policy ID: `P2-MALFORMED-HEADER-V1`  
Mapping fallback: `conservative_unknown_v1`  
Effective scope: P2 train/validation only  
Freeze state: not authorized by this decision alone.

Any change to the triggers, reason codes, map, or warning format requires a new
policy version and updated synthetic expected values before another full P2
census.
