# P2 source-integrity blocker — 2026-09-21

## Decision

Stop all further reads of the extracted PSA PE files. Do not run the full P2 census,
Grad-CAM perturbation, deletion/keep-only, or test-payload experiments until an intact
source tree is restored and verified from a trusted archive. Do not exclude failed files.

No PE was executed, imported, or dynamically loaded during these checks. The P2 audit
only performed file size/SHA-256 validation and static parsing with PeAtlas and `pefile`.

## Evidence

The first diagnostic run selected the first 256 deduplicated train/validation IDs:

- output: `D:\secure-malware-data\psa\audit\p2_preflight_20260920`
- agreement: 66
- errors: 190 (`PermissionError`)
- parser-field disagreements among readable, hash-valid inputs: 0
- ledger SHA-256: `19567268ff38db80208b395b35e7ad31f8f8a294ddd2dd98834848cb1db2edf2`

After the user requested a retry, the same deterministic 256 IDs were checked once in a
new output directory:

- output: `D:\secure-malware-data\psa\audit\p2_preflight_retry_20260921`
- agreement: 50
- errors: 206
- errors by observed condition: 158 missing files, 39 file-size mismatches against
  `raster_index.csv`, and 9 SHA-256 mismatches against `manifest_stage2.csv`
- parser-field disagreements among readable, hash-valid inputs: 0
- ledger SHA-256: `9f96868a5850e93583a57de305552f1b220ce6d1d71dfe2cf51d43f204b801d2`

Status transition between the two runs:

| First run | Retry | Count |
|---|---:|---:|
| agreement | agreement | 49 |
| agreement | error | 17 |
| error | agreement | 1 |
| error | error | 189 |

The 17 agreement-to-error transitions show that the extracted source tree is not stable
under repeated access. The original 2018 timestamps on surviving files do not identify
the cause. AhnLab V3 Lite and Windows Defender are registered on the system, but no
specific product was proven to have quarantined or changed these files. No antivirus,
ACL, or exclusion setting was changed by this work.

## Preserved evidence

Derived rasters, split manifests, trained checkpoints, summaries, and validation metrics
remain separate from the extracted source directory. Their previously recorded hashes
were not replaced. The retry output was written to a new directory; the first audit was
not overwritten.

## Safe recovery gate

Before any further source-file read:

1. The user or administrator reviews the security product quarantine/history and confirms
   an approved handling procedure for the research dataset. Do not disable protection
   globally.
2. Restore/extract the verified archive into a fresh, explicitly approved directory rather
   than repairing the current tree in place.
3. Verify the archive SHA-256 and available disk capacity before extraction.
4. Verify every restored file against `manifest_stage2.csv` before running either parser.
   Record missing, size-mismatched, and SHA-mismatched counts. The gate requires zero in
   all three categories for the selected P2 population.
5. Re-run the 256-ID diagnostic into another new output directory. Only a stable, fully
   hash-valid diagnostic may authorize a separately reviewed full train/validation census.

Until these conditions are met, `protocol_freeze_authorized` remains false.
