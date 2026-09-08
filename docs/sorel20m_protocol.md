# SOREL-20M Acquisition & Selection Protocol (v3 amendment §5/§6/§9)

This protocol governs how the SOREL-20M disarmed-malware corpus is selected,
preflighted, and acquired for the UA-SAHI-MAL v3 Tier-2 silver / real-malware
stress cohort. It exists so that the process is deterministic, auditable, and
strictly within the SOREL Terms and this project's safety boundary.

Binaries are **never** downloaded, decompressed, or executed in the ephemeral
cloud session. Acquisition is run only by the operator on the isolated machine
(cau) into an approved isolated data path. The cloud session builds and verifies
the tooling only.

## G0-S determination (Terms gate) — 2026-09-08

**Status: PARTIAL / PUBLICATION PERMISSION PENDING.**

| Use | Determination |
| --- | --- |
| Legitimate internal security research use | Permitted, subject to the SOREL Terms. |
| Public SHA manifest | **Not permitted** without written authorization. |
| Public sample-linked derived intervals | **Not permitted** without written authorization. |
| Aggregate publication results | Written clarification required — Terms §2(c) broadly restricts derivative works. |

Consequences enforced by the tooling:

- The selection SHA manifest (`*_manifest.csv`) and the SHA list
  (`*_selected_sha256.txt`) are **private**. They are never committed to Git and
  never written to a cloud-sync folder. `ua_sahi_mal.sorel.paths` refuses such
  destinations at runtime.
- Downloaded binaries live only in an approved isolated data path
  (e.g. `D:\datasets\sorel20m-private\compressed`), kept zlib-compressed, never
  re-armed.
- Any publication of aggregate results (coordinate-integrity rates, coverage,
  silver-evidence retrieval) is **blocked** pending written clarification of
  Terms §2(c). Until then, results are internal only, and no sample-linked
  derived interval may be published.

## Directory layout (isolated, private; not in Git)

```
D:\datasets\sorel20m-private\
  metadata\meta.db                 # ~3.5 GB, read-only source of truth
  selection_v1_manifest.csv        # private frozen manifest (NOT publishable)
  selection_v1_selected_sha256.txt # one 64-hex SHA per line (NOT publishable)
  compressed\<sha>.zlib            # disarmed binaries, kept zlib-compressed
```

The 72 GB feature LMDB, 480 GB PE metadata, and 8 TB full binary set are **not**
downloaded. Only `meta.db` plus the budgeted selected binaries are fetched.

## Step 1 — Freeze the selection (no network, no binaries)

`scripts/sorel20m_select.py` reads `meta.db` (read-only), selects malware-only
rows (`is_malware = 1`), assigns each to its **official temporal split**
(boundaries `1543542570.0` / `1547279640.0`, unchanged for comparability), and
performs a deterministic, tag-stratified pick keyed by `SHA256(seed || sha)`. A
20% reserve pool per split is frozen alongside the primary selection.

```
python scripts/sorel20m_select.py \
  --meta-db  D:\datasets\sorel20m-private\metadata\meta.db \
  --out-prefix D:\datasets\sorel20m-private\selection_v1 \
  --seed sorel-v3-frozen-2026 \
  --train 180 --validation 60 --test 60
```

Outputs the private manifest and `selection_v1_selected_sha256.txt` (one 64-hex
SHA per line — the format the acquisition steps consume). The command refuses if
either output path is inside the repo or a sync folder.

## Step 2 — Preflight the byte budget (HEAD only, no download)

`scripts/sorel20m_preflight.py` issues an anonymous `s3api head-object`
(`--no-sign-request`) per SHA and reports each `ContentLength` + `ETag` and the
total. Confirm the total is within the intended budget before fetching.

```
python scripts/sorel20m_preflight.py \
  --sha-list D:\datasets\sorel20m-private\selection_v1_selected_sha256.txt \
  --budget-mb 4096
```

Each SHA is validated as `^[0-9a-f]{64}$`; malformed lines are reported, not
fetched. The S3 key is `09-DEC-2020/binaries/<sha>`.

## Step 3 — Gated fetch (kept zlib-compressed)

`scripts/sorel20m_fetch.py` downloads into the isolated directory. Before any
byte is fetched it enforces three gates: `--accept-terms` (SOREL Terms
acknowledgement), an isolated destination path, and the byte budget cap against
the preflight total.

```
python scripts/sorel20m_fetch.py \
  --sha-list D:\datasets\sorel20m-private\selection_v1_selected_sha256.txt \
  --dest-dir D:\datasets\sorel20m-private\compressed \
  --budget-mb 4096 \
  --accept-terms
```

Files are stored as `<sha>.zlib` exactly as served. The tooling **never**
decompresses and **never** re-arms (Machine/Subsystem stay zeroed). The S3 key is
the *original* SHA-256; because disarming zeroes `Machine` and `Subsystem`, the
disarmed binary's own hash differs from the S3 key. Decompression and any parsing
happen only later, in an approved static-only isolated environment.

## Hashes recorded in the manifest

- `sorel_original_sha256` — the S3 key / original hash (from `meta.db`).
- `stored_artifact_sha256` — sha256 of the on-disk `<sha>.zlib` as stored
  (compressed), filled at fetch time as an integrity anchor.
- `disarmed_local_sha256` — sha256 of the **decompressed disarmed** binary; left
  empty by acquisition and filled only in the later static-only stage.

## Safety invariants (asserted by tests)

- Selection reads only `meta.db`; no network, no binaries.
- Selection is deterministic in the seed; reserve is disjoint from primary; no
  duplicates; malware-only.
- Official split boundaries are applied exactly.
- Output-path guards refuse repo-relative and sync-folder destinations for the
  SHA manifest, the SHA list, and the binary directory.
- Fetch refuses without a Terms acknowledgement and refuses to exceed the budget.
- Fetch keeps artefacts compressed and never modifies bytes (no re-arming).
