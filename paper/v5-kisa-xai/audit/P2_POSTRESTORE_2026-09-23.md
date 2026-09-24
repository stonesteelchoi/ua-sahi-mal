# PSA P2 after source restoration — 2026-09-23

## Outcome

The source-integrity blocker is resolved. Static length and SHA-256 verification
against `samples.csv` passed for all 201,549 expected files, with no missing or
zero-byte expected files and no source change observed during the scan. The two
previously documented non-dataset files remain outside the selected population.
The 51 restored train/validation sources also reproduce their existing raster
rows, raster-index hashes, interval-map hashes, representation policies, and
file sizes exactly (34 train, 17 validation). Therefore the restored files do
**not** require raster rematerialisation or model retraining.

P2 was rerun with the original, unmodified crosscheck implementation. The
256-ID deterministic preflight had 256 comparison-field agreements. The full
deduplicated train/validation census completed as follows:

| Status | Files |
| --- | ---: |
| Selected | 169,020 |
| Comparison fields agree | 168,947 |
| Hash-valid PE header parse error | 63 |
| Parser comparison disagreement | 10 |

There were no source-size or source-SHA-256 failures in the full P2 census.
The process returned code 2 because it deliberately treats any error or
disagreement as a non-pass; the summary has `complete: true` and
`protocol_freeze_authorized: false`.

## Edge-case diagnosis

All 63 parse-error sources match their expected SHA-256. In 62 cases PeAtlas
rejected a declared data-directory count that exceeds the declared optional
header space; one further case has a missing/truncated declared optional
header. Independent `pefile` parsing returned an object for all 63, but in
all 63 the declared directory count exceeds the directory capacity of the
declared optional header. That includes 61 files with capacity 16, one with
capacity 3, and one with capacity 0. For example, sample 6683 declares 17
directories in a 16-slot optional header; sample 6909 declares 16 in a
3-slot optional header. A permissive parser's success is not proof that
reading beyond the declared header is a valid structure map.

The 10 comparison disagreements all concern section count; five also affect
the normalized raw-section overlay boundary. PeAtlas retains the section
headers declared by the file, whereas `pefile` accepts fewer sections when
their contents or offsets are malformed. For example, sample 14533 declares
three sections; `pefile` accepts one and warns that a subsequent section
points beyond the file. This is a parser-policy difference, not evidence of
source-byte damage. All 10 IDs remain in the P2 ledger.

The native `pefile` overlay start differs from the PeAtlas section-end
definition in 1,854 parsed files (975 lower, 879 higher); 935 of these have
a PeAtlas truncated-section warning. `pefile`'s native method considers
only accepted in-file section extents and certain data-directory extents,
while PeAtlas clamps raw section ends and treats certificates separately.
These are different definitions. The normalized raw-section boundary agrees
in all but the five section-disagreement cases above; native overlay
differences must not be silently substituted for that field.

## Evidence and commands

- Post-restoration source report:
  `D:\secure-malware-data\psa\audit\source_integrity_20260923_postrestore\source_integrity_report.json`
  (SHA-256 `9c5ecdaab9be8021c05e14e8f424711d0a704ba89b4af60bafe2045459b497be`)
- Restored-source versus raster report:
  `D:\secure-malware-data\psa\audit\restored_raster_drift_20260923_final.json`
  (SHA-256 `0751a88bcccadda9fe17e254ab61e52ce17a78ef4088661dcc9bd670c1c9323c`)
- P2 preflight: `D:\secure-malware-data\psa\audit\p2_preflight_20260923_postrestore`
- Full P2 summary and ledger:
  `D:\secure-malware-data\psa\audit\p2_census_20260923_postrestore`
  (ledger SHA-256 `bbd50133d4ac8dc6ece274653e809292be9b890d907b6725186eb844c8efdf22`)
- Hash-valid parser-edge diagnosis:
  `D:\secure-malware-data\psa\audit\p2_edge_diagnostic_20260923_postrestore_final.json`
  (SHA-256 `acdb987c43745281e57eb2141353acdc553f8b5fafad74ea19b56f76c5210337`)
- Read-only raster-audit script SHA-256:
  `d2e1548e9de6b3b7879cc7a43579a74fc6f286ad5fb5b125b3b1298f1da8a2f1`
- Parser-edge diagnostic script SHA-256:
  `c0e61c8a3c5ceb6f287d767bd9836a8872061ae59f36879a716dafc72c1f4e6c`
- Input raster-index SHA-256:
  `94d02b247fc761d64fdea5aeac9afe2da6dc56bdcc998cc84d4a5c7d3f76f785`
- Input stage-2 manifest SHA-256:
  `3dc0bd7fb42935692462013f716bbd8ccd339b20bb436289aa93e78852b17414`
- PSA structure-mapping source SHA-256:
  `4a2b13be35e5298643726e6805f47828c6f9e6091cfbb96cbb83aa42e83f7d29`
- `pefile` version 2024.8.26; full-census elapsed 323.234 seconds.

The source audit read files only for hashing; P2 read train/validation files
only for static parsing. Neither executed, imported, dynamically loaded, or
modified a source PE. No held-out test payload was accessed.

## Freeze disposition

Source restoration is no longer a blocker. The independent parser crosscheck
has **not** passed: 63 malformed-header cases need an explicit non-fabricating
mapping/fallback rule, and 10 section-policy differences need a pre-test
adjudication rule. The native overlay diagnostic needs separate semantic
documentation. Keep every file in the population and retain every exception
in the ledger. Any changed mapping policy must be versioned and checked with
synthetic regression fixtures before repeating P2. Do not freeze the
protocol or run test-payload XAI until this decision and recheck are complete.
