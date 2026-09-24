# C9c-b test structure adjudication

## Scope and evidence

- No model evaluation was performed. This entry uses the frozen main test structure ledger at `D:\secure-malware-data\psa\audit\main_test_structure_census_20260924\structure_ledger.jsonl` and `D:\secure-malware-data\psa\rasters\raster_index.csv`.
- Only ledger rows with `status=accepted_unknown_fallback` were joined on `sample_id` to raster index `label` and `group` (imphash group). The join is 42 unique ledger IDs to 42 raster rows. The census summary was recorded in C9c-a: 30,146 test rows, 30,104 agreements, 42 accepted fallbacks, zero unattributable.
- All 42 fallback rows have `label=1` (malicious); benign 0. Reasons: 40 `directory_count_exceeds_optional_header_capacity`, 2 `section_count_disagreement`.

## Main fallback group census

The 42 fallback files occupy 10 groups. Fallback-only group sizes are 16, 14, 4, 2, and six singletons; maximum 16. The two largest groups account for 30/42 files. No fallback group mixes malicious and benign fallback files. A group size here counts fallback files, not all test files in that imphash group; notably, the 14-fallback group has 490 test members in total.

| Imphash group | Fallback n | All test members | Reason | Fallback sample IDs |
| --- | ---: | ---: | --- | --- |
| `e85cf9ccae1b44abfd545cb6e70a1add` | 16 | 16 | directory count | 11958, 12838, 1349, 14218, 3224, 35559, 38019, 40964, 42123, 43391, 48844, 51134, 56792, 5749, 59878, 62518 |
| `87bed5a7cba00c7e1f4015f1bdae2183` | 14 | 490 | directory count | 14571, 14665, 27647, 27654, 27874, 27957, 39337, 4340, 57515, 6150, 63526, 913, 93355, 9800 |
| `48936dc0e7e70ceb857001d265fda216` | 4 | 4 | directory count | 14578, 4424, 47006, 63564 |
| `0ad1c353022daca0807e069bc0b15174` | 2 | 7 | directory count | 15520, 41439 |
| `aab70c7ad50e818c0354dff5ba1aaaf9` | 1 | 1 | directory count | 64884 |
| `87f613aaf8ee96fac52e8de926c82c23` | 1 | 1 | directory count | 7229 |
| `228bdedfe7d4b4e9943e632f052ac619` | 1 | 1 | section count | 7670 |
| `__noimp_115106` | 1 | 1 | section count | 115106 |
| `b6f8a608ce5b421247fa32cc2d1ac518` | 1 | 1 | directory count | 39271 |
| `4eb5895a810a02bd9834b8d4632836b6` | 1 | 1 | directory count | 43857 |

## H1/H2 eligibility interpretation

The frozen protocol defines the primary population as all 17,407 deduplicated malicious main test files, with a structure-matched random comparator and `eligible_n` reported for H1/H2. A whole-file `unknown` fallback retains the sample for image/model analysis, but provides no attributed PE regions with which to perform a meaningful structure-matched comparison. The ledger field `structure_attribution_available=true` means a fallback representation exists; its only span is `unknown` and it is not evidence of a usable PE-region attribution. Accordingly, the expected H1/H2 *structure-matched comparison* eligible count is **17,407 − 42 = 17,365 malicious files**, before any later execution-specific eligibility flags. The 42 files remain in the full malicious test population and other applicable descriptive/model analyses; they are not deleted from the split. Both H1 and H2 use the same eligibility decision. This is an interpretation of the frozen comparison definition, not a new mapping policy or a model result.

## Era fallback and H1/H2 eligibility

- The frozen era test ledger at `D:\secure-malware-data\psa\audit\era_test_structure_census_20260924\structure_ledger.jsonl` contains one `accepted_unknown_fallback` among 10,652 deduplicated test rows (10,651 agreements, zero unattributable). It has `sample_id=64884`, `split=test`, and reason `directory_count_exceeds_optional_header_capacity`.
- Joining that ID to `D:\secure-malware-data\psa\rasters\raster_index.csv` yields exactly one row: `label=1` (malicious), `split=test`, imphash group `aab70c7ad50e818c0354dff5ba1aaaf9`. The fallback occupies one group; this is a fallback-only group count, not the size of the entire era test group.
- The era protocol's deduplicated malicious test population is 5,332. The whole-file `unknown` fallback remains in the test population but has no usable PE-region attribution for the structure-matched random comparator. Expected H1/H2 structure-matched **eligible_n = 5,332 − 1 = 5,331**, before execution-specific eligibility checks. This applies the same interpretation as main test; it does not change the frozen policy or evaluate a model.

## Census access record

The two repository `audit_plan.json` copies each record `test_payload_access=true`. Their original file creation/last-write times provide approximate census start times, not exact first-read timestamps: era 2026-09-24 19:01:05 KST and main 2026-09-24 19:02:47 KST. See `PROTOCOL_FREEZE_2026-09-24.md` for the audit trail. No model evaluation was performed in C9c-b.
