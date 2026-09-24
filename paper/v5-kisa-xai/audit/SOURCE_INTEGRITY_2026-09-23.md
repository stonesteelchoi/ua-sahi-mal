# PSA restored-source integrity audit — 2026-09-23

> Historical pre-repair evidence. The 51 sources were subsequently restored and
> all 201,549 expected files passed a fresh full SHA-256 census. Current status:
> `P2_POSTRESTORE_2026-09-23.md`.

## Outcome

The restored source directory is complete by filename but not yet byte-identical to
`samples.csv`. P2 has since been run as a full diagnostic census (see
`P2_CENSUS_2026-09-23.md`), but it has not passed the protocol-freeze gate.
Do not run test-payload XAI experiments yet.

- Expected IDs in `samples.csv`: 201,549
- Expected IDs present: 201,549
- Zero-byte expected files: 0
- Length and SHA-256 verified: 201,498
- Length mismatch: 41
- SHA-256 mismatch at the expected length: 10
- Unexpected files outside the CSV: 2 (`palm tree.bmp`, `tip_learntabOEM_EN,3.jpg`)

All 51 failures are malicious train/validation members in `raster_index.csv`, so none may
be silently excluded from the P2 population. They do not overlap the historical list of
180 missing IDs; that earlier recovery and this integrity defect are separate issues.

## Method and evidence

`scripts/psa_verify_source_tree.py` performed static length and SHA-256 reads only. It did
not parse, import, dynamically load, or execute a PE file, and it did not modify the source
directory.

- Output: `D:\secure-malware-data\psa\audit\source_integrity_20260923`
- Full report SHA-256: `479418ab5a78026ebc42a78a5944e146356d46c9435fb44a60df700f60e77ef8`
- Failure ledger SHA-256: `a5c1b0f20a09e289a8f0d9eb62561e1ba4a91b5264d2f9d4a4cbf00b48465e9c`
- Recovery manifest: `recovery_manifest_51.csv`
- Recovery manifest SHA-256: `d3b1f6e887b9ac792b83c1958707a805332800e1dee39f24dd717412cdd9de37`
- Total verified bytes: 126,245,009,531
- Elapsed time: 209.438 seconds

The directory contained the same 201,551 entries before and after verification. No source
file disappeared during this run.

## Archive finding

The handoff named `D:\secure-malware-data\pe-machine-learning-dataset.7z`, but that file
was not present. The available encrypted archive is `D:\secure-malware-data\pe-ml-enc.7z`
(53,543,060,903 bytes). A read-only Bandizip listing with the existing research password
reported 201,371 files and one folder. It contains the two unexpected files and, for at
least sample 100, the same wrong length as the current extracted tree. It is therefore not
accepted as the trusted complete archive and was not extracted.

The user supplied the original Google Drive file ID
`1yrcxHx5zT8cJl6o047vsVUayu15aBmbo`. Its Drive metadata identifies
`pe-machine-learning-dataset.7z` at 43,836,090,371 bytes, matching the recorded
original archive size. This confirms that a candidate recovery source is available
remotely; it does not establish the archive's SHA-256 or the integrity of the local
51 failed files. No archive was downloaded in this audit.

## P2 diagnostic on the restored tree

At the user's request, the deterministic first 256 deduplicated train/validation
files were inspected statically on 2026-09-23 in the new output directory
`D:\secure-malware-data\psa\audit\p2_preflight_20260923`.

- 208 samples had valid source hashes and agreeing PeAtlas/pefile raw fields.
- 48 samples failed source verification before either parser (39 size, 9 SHA-256).
- No raw-field disagreement was observed among the 208 valid samples.
- `pefile`'s native overlay boundary differed in seven valid samples. The
  normalized section-end boundary agreed in all 208; five of the seven native
  disagreements had a truncated section warning. These cases remain review items.
- Ledger SHA-256: `b2ee48a254f0c0dbdea97b0b2d453868c8c54eb84d978c0aec4fb255245bf638`.

This 256-file diagnostic is not a pass of the P2 gate. A subsequent full
train/validation census is documented in `P2_CENSUS_2026-09-23.md`.

## Required recovery

Use a trusted source containing the exact 51 IDs listed in `recovery_manifest_51.csv`.
Restore them into a fresh staging directory first and verify every staged file against the
manifest's expected length and SHA-256. Do not overwrite the current source tree until the
staging verification has zero errors and the replacement action is explicitly approved.

After approved replacement:

1. Re-run `psa_verify_source_tree.py` into a new output directory.
2. Require 201,549 verified files, zero length/SHA/read failures, and no disappearance
   during the scan. The two non-dataset extras may remain documented but are never selected.
3. Re-run the deterministic 256-ID P2 diagnostic into a new output directory.
4. Review all parser disagreements and structure warnings before considering protocol
   freeze. Never exclude failures to force a pass.

`protocol_freeze_authorized` remains false.
