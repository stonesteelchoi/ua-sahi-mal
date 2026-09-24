# PSA-XAI V1.1 protocol freeze — 2026-09-24

## Approval and frozen artifact

- User approved freezing the full PSA-XAI protocol on **2026-09-24**. This approval supersedes the historical `protocol_freeze_authorized=false` in the prerequisite recheck JSON; that JSON remains unchanged as a time-stamped preapproval result.
- Frozen protocol: `paper/v5-kisa-xai/protocol/PSA_XAI_V1_1_FROZEN.yaml`, ID `PSA-XAI-V1.1-FROZEN`, status `frozen`, frozen date `2026-09-24`, empty `freeze_blockers`.
- Frozen YAML SHA-256: `c0c7b79775b3aa36d3dc59f5a8544e5248e9517ca218319cb8ee83d88c70e709`.
- `PSA_XAI_V1_0_DRAFT.yaml` remains the historical draft and was not changed by this freeze.

## Evidence fixed at freeze

- P2 adjudication: `paper/v5-kisa-xai/audit/P2_CENSUS_ADJUDICATION_2026-09-24.md` (SHA-256 recalculated here: `c26b63cc6423a2c0c0e33995538c731123372f9923c8d37b2f0ffdd86bc8ccfb`). Train/validation census covered 169,020 files: 168,947 agreement and 73 accepted unknown fallbacks (directory count 62, optional header 1, section count 10; raw section boundary 0). No unclassified parse error or other disagreement remained. The adjudicated `conservative_unknown_v1` mapping and P2 reason codes are frozen.
- Freeze prerequisite recheck: `runs/psa-orchestration/freeze_prereqs_recheck_20260924b.json` (SHA-256 `5913ce7018a8ff7467aa5ba26e4cd6a0c74d170af7223616541b539f2b856404`). It verifies batch size 512, peak 6,072.7/8,123.4 MiB, Grad-CAM layer `layer4.1` (`BasicBlock`), CUDA activation and gradient `[1,512,7,7]`, output `[1,2]`, and malicious logit index 1. `source_payload_access=false` at recheck time. Its pending authorization field is historical; the user approval above closes it.
- Main model provenance commit: `62a15542f14b94b16271dbac8defbe99ee57b3ca`. Three C8 retrain checkpoints in `D:\secure-malware-data\psa\runs\c8_retrain_20260924\seed{42,43,44}_imagenet_bs512\best.pt` were independently rehashed on 2026-09-24:

  | Seed | SHA-256 |
  | --- | --- |
  | 42 | `291af0bd0b2133f3c501fe3efdae0f5503b6de7d4e095a5fc2b1c27a7561f48f` |
  | 43 | `4156f2b8bf8c7995c8d62e4132102b28430d9fc69de49b293ec561af68bcaf56` |
  | 44 | `62c0d8b002586676d61c7488099e362b4c15777a9406424c324c1f4fbec5639c` |

- Era model provenance commit: `8323ab7501ad4763fb0436121a9466bf50720016`. `runs/psa-orchestration/era_training_verify_20260924.json` (SHA-256 `9b8e23b87a7beca2d8942cf4fd9dfd4cfba5827dac2c07423d5f6110c6b6c66b`) records validation sanity gate success and seed direction agreement for all three seeds, deduplicated train/validation/test counts 49,593/10,660/10,652, and `test_evaluation_performed=false`. Three era checkpoints in `D:\secure-malware-data\psa\runs\era_20260924\seed{42,43,44}_imagenet_bs512\best.pt` were independently rehashed on 2026-09-24:

  | Seed | SHA-256 |
  | --- | --- |
  | 42 | `a1121de1a69992c9032d2278f2a43b6560ada3e5d03716097c145bc5c23dc2b6` |
  | 43 | `f031295be823c37158411180f63c64a4eee5189e6077cc744aa69d408b6ee7bf` |
  | 44 | `da30a11b32904116a83f3b408e37e7508bb6d4969fee8336fa8392a1caa729f1` |

All six recomputed checkpoint hashes match their recorded values. Both provenance commit IDs resolve to commits in this checkout. Earlier C9 freeze preparation also reported five designated artifact hashes unchanged; see `audit/C9_FREEZE_PREP_2026-09-24.md`. This freeze rechecked the six model checkpoints and three evidence files listed above.

## Postfreeze scope

- **Allowed:** one held-out main test evaluation using the fixed main models and one held-out era test evaluation using only the fixed era models. Test structure mapping follows the preregistered `P2-MALFORMED-HEADER-V1`, `P2-SECTION-DISAGREEMENT-V1`, and `conservative_unknown_v1` rules. Test reason counts are descriptive; the train/validation 62/1/10 gate is not imposed on test.
- **Forbidden within V1.1:** changing mapping policy, hypotheses, or statistical unit after test access. Any additional analysis belongs to `PSA-XAI-V1.2-EXPLORATORY` and must be labeled exploratory.
- The next chunk is C9, preparation of main test structure mapping. This freeze did not access or evaluate held-out payloads.

## C9 tool-only addendum

- `scripts/psa_structure_audit.py` now has an explicit `--population test` mode. It selects only deduplicated test IDs from the main raster split or a SHA-256 checked era split manifest, and applies the already frozen structure policy, P2 reason codes, and whole-file unknown fallback unchanged.
- Test output records reason counts as descriptive statistics. It omits the train/validation 62/1/10 gate and the `protocol_freeze_authorized` field. Unclassified parse errors and non-target disagreements stay in the ledger with `structure_attribution_available=false`; the summary counts them. This is an audit-tool change, not a mapping-policy change or a new freeze decision.
- No test census or model evaluation was executed during this preparation. User-run commands and output checks are in `audit/C9_TEST_STRUCTURE_COMMANDS_2026-09-24.md`.

## User-run Git tag

After committing the frozen YAML, this record, and `PROGRESS.md`, run from the repository root:

```powershell
git tag -a psa-xai-v1.1-frozen -m "PSA-XAI V1.1 protocol frozen 2026-09-24"
```

The tag must point to the commit containing the frozen protocol and this SHA-256 record. No tag was created in this session.
