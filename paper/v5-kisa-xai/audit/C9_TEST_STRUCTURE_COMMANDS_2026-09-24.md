# C9 test structure audit handoff — 2026-09-24

Run from the repository root in the user's working `.venv` PowerShell window. Each output directory must be new. The smoke commands open five test source files, so run them only when ready for held-out test structure access. These commands do not evaluate a model.

```powershell
$common = @('--rasters-dir','D:\secure-malware-data\psa\rasters','--manifest','D:\secure-malware-data\psa\manifest_stage2.csv','--samples-dir','D:\secure-malware-data\psa\pe-machine-learning-dataset\samples','--population','test','--static-only','--adjudication-policy','conservative_unknown_v1','--workers','4')
& .\.venv\Scripts\python.exe scripts\psa_structure_audit.py @common --limit 5 --outdir D:\secure-malware-data\psa\audit\main_test_structure_smoke_20260924
if ($LASTEXITCODE -ne 0) { throw 'main smoke failed' }
& .\.venv\Scripts\python.exe scripts\psa_structure_audit.py @common --outdir D:\secure-malware-data\psa\audit\main_test_structure_census_20260924
if ($LASTEXITCODE -ne 0) { throw 'main census failed' }
```

The era manifest assigns a separate test population (10,652 effective IDs after duplicate exclusion), so era needs its own structure map. It uses the same source integrity checks, policy, ledger fields, and descriptive reporting. Run the era smoke and census with these additional options:

```powershell
$era = @('--split-manifest','D:\secure-malware-data\psa\audit\era_stratified_freeze_20260924\split_manifest_era.csv','--split-manifest-sha256','fd0a99000b05785ecf3fc01108529b37e08bb31f162b6defc3f3621459d2d91a')
& .\.venv\Scripts\python.exe scripts\psa_structure_audit.py @common @era --limit 5 --outdir D:\secure-malware-data\psa\audit\era_test_structure_smoke_20260924
if ($LASTEXITCODE -ne 0) { throw 'era smoke failed' }
& .\.venv\Scripts\python.exe scripts\psa_structure_audit.py @common @era --outdir D:\secure-malware-data\psa\audit\era_test_structure_census_20260924
if ($LASTEXITCODE -ne 0) { throw 'era census failed' }
```

After each census, inspect both summaries. `complete` must be true and `selected_n` should equal `population_n` (main 30,146; era 10,652). Reason counts are descriptive. Check `unattributable_count` and `unattributable_reason_counts` before any downstream structural attribution. The summary intentionally has no `p2_structure_gate_passed` or `protocol_freeze_authorized` field.

```powershell
$auditDirs = @('D:\secure-malware-data\psa\audit\main_test_structure_census_20260924','D:\secure-malware-data\psa\audit\era_test_structure_census_20260924')
foreach ($dir in $auditDirs) {
  $s = Get-Content -LiteralPath (Join-Path $dir 'structure_audit_summary.json') -Encoding utf8 | ConvertFrom-Json
  [pscustomobject]@{ dir=$dir; complete=$s.complete; selected=$s.selected_n; population=$s.population_n; status=$s.status_counts; fallback=$s.fallback_reason_counts; unattributable=$s.unattributable_count; reasons=$s.unattributable_reason_counts; ledger_sha256=$s.ledger_sha256 } | Format-List
}
```

Synthetic regression command, before any source access:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests\test_psa_structure_audit_policy.py -q --basetemp=runs\psa-orchestration\pytest_c9_structure_user
```
