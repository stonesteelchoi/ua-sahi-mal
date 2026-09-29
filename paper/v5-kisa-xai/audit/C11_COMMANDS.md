# C11-b V1.2 실행 명령 (준비, 실제 데이터 미실행)

동결 태그와 YAML을 먼저 검증한다. V1.1 Grad-CAM ledger와 checkpoint는 아래 고정 SHA-256과 대조한 뒤 읽기 전용 입력으로 사용한다. 여섯 run은 각각 별도 outdir를 사용한다.

```powershell
$tagCommit = git rev-parse 'psa-xai-v1.2-frozen^{commit}'
if ($tagCommit -ne '89abb69db6666ffcd92fec4261d48d2763f54afc') { throw 'V1.2 tag target mismatch' }
$addendum = 'paper/v5-kisa-xai/protocol/PSA_XAI_V1_2_ADDENDUM.yaml'
$addendumSha = '9712217fc49db0fb1f495a901526e985c731bfe3650dacb1bb875fbe4fcb4162'
if ((Get-FileHash -LiteralPath $addendum -Algorithm SHA256).Hash.ToLower() -ne $addendumSha) { throw 'addendum SHA mismatch' }
if ((Get-FileHash -LiteralPath 'paper/v5-kisa-xai/protocol/PSA_XAI_V1_1_FROZEN.yaml' -Algorithm SHA256).Hash.ToLower() -ne 'c0c7b79775b3aa36d3dc59f5a8544e5248e9517ca218319cb8ee83d88c70e709') { throw 'parent SHA mismatch' }

$py = '.\.venv\Scripts\python.exe'
$root = 'D:\secure-malware-data\psa'
$rasters = Join-Path $root 'rasters'
$runs = Join-Path $root 'runs'
$audit = Join-Path $root 'audit'
$stage2 = Join-Path $root 'manifest_stage2.csv'
$samples = Join-Path $root 'pe-machine-learning-dataset\samples'
$structurePaths = @{ main=(Join-Path $audit 'main_test_structure_census_20260924\structure_ledger.jsonl'); era=(Join-Path $audit 'era_test_structure_census_20260924\structure_ledger.jsonl') }
$structureHashes = @{ main='53bc25ecf7b144cb5d1599fba9052b0eb9d52ef973947672fdbc720ecbd85c7b'; era='bf538e933bfd87a19a0e5ed47bdf2a40344e3bbd602215b61586d00072473b16' }
$checkpointHashes = @{
    main=@{42='291af0bd0b2133f3c501fe3efdae0f5503b6de7d4e095a5fc2b1c27a7561f48f';43='4156f2b8bf8c7995c8d62e4132102b28430d9fc69de49b293ec561af68bcaf56';44='62c0d8b002586676d61c7488099e362b4c15777a9406424c324c1f4fbec5639c'}
    era=@{42='a1121de1a69992c9032d2278f2a43b6560ada3e5d03716097c145bc5c23dc2b6';43='f031295be823c37158411180f63c64a4eee5189e6077cc744aa69d408b6ee7bf';44='da30a11b32904116a83f3b408e37e7508bb6d4969fee8336fa8392a1caa729f1'}
}
$camHashes = @{
    main=@{42='0ad94ba6a89e9afa8cd769fc0af7396e83b5d529a5325c803bb354f95ab22da8';43='6f4c403c86a74e091622385736e2ffd99733f6e35709495f8cdcb17f2d55bff2';44='a39649d5abe90ad37e05fde1b2b19ba29f2efb75d4f1de47ea75144430fa2f29'}
    era=@{42='81fb930fd1bedf33e2ea69fc67c8a9bf998919ac063b136e035efd16027e7fb6';43='b6eb36f826780a09995a0754a2e4fc3750cdcc20ef0649aa8fa692341cfa32f7';44='2a02b653bb8edaa932958a34f9fcdbf60c2834ab3aaca22f4e275a62c2078063'}
}
function Invoke-V12Perturb([string]$pop, [int]$seed, [string]$outdir, [int]$limit = 0) {
    $modelDir = if ($pop -eq 'main') { 'c8_retrain_20260924' } else { 'era_20260924' }
    $checkpoint = Join-Path $runs "$modelDir\seed${seed}_imagenet_bs512\best.pt"
    $cam = Join-Path $runs "xai_v1_1\${pop}_seed${seed}_gradcam\gradcam_ledger.jsonl"
    $camSummary = Join-Path $runs "xai_v1_1\${pop}_seed${seed}_gradcam\gradcam_summary.json"
    $checkpointSha = $checkpointHashes[$pop][$seed]
    $camSha = $camHashes[$pop][$seed]
    if ((Get-FileHash -LiteralPath $checkpoint -Algorithm SHA256).Hash.ToLower() -ne $checkpointSha) { throw "$pop seed $seed checkpoint SHA mismatch" }
    if ((Get-FileHash -LiteralPath $cam -Algorithm SHA256).Hash.ToLower() -ne $camSha) { throw "$pop seed $seed Grad-CAM ledger SHA mismatch" }
    if ((Get-Content -LiteralPath $camSummary -Encoding utf8 -Raw | ConvertFrom-Json).ledger_sha256 -ne $camSha) { throw "$pop seed $seed Grad-CAM summary SHA mismatch" }
    if ((Get-FileHash -LiteralPath $structurePaths[$pop] -Algorithm SHA256).Hash.ToLower() -ne $structureHashes[$pop]) { throw "$pop structure ledger SHA mismatch" }
    $arguments = @('scripts\psa_perturb.py', '--checkpoint', $checkpoint, '--checkpoint-sha256', $checkpointSha,
        '--gradcam-ledger', $cam, '--gradcam-ledger-sha256', $camSha,
        '--structure-ledger', $structurePaths[$pop], '--structure-ledger-sha256', $structureHashes[$pop],
        '--stage2-manifest', $stage2, '--samples-dir', $samples, '--rasters-dir', $rasters,
        '--protocol-addendum', $addendum, '--protocol-addendum-sha256', $addendumSha,
        '--outdir', $outdir, '--resume', '--order', 'size-desc', '--prefetch', '16', '--workers', '16')
    if ($limit -gt 0) { $arguments += @('--limit-samples', [string]$limit) }
    & $py @arguments
    if ($LASTEXITCODE -ne 0) { throw "$pop seed $seed V1.2 perturb failed" }
}
```

3건 smoke 명령(각 run의 앞 3개 표본, 별도 outdir):

```powershell
$smokeRuns = @(
    @{pop='main'; seed=42; name='smoke_main_seed42_3'},
    @{pop='main'; seed=43; name='smoke_main_seed43_3'},
    @{pop='era'; seed=42; name='smoke_era_seed42_3'}
)
foreach ($smoke in $smokeRuns) {
    $outdir = Join-Path $runs "xai_v1_2\$($smoke.name)"
    $elapsed = Measure-Command { Invoke-V12Perturb $smoke.pop $smoke.seed $outdir 3 }
    $summary = Get-Content -LiteralPath (Join-Path $outdir 'perturb_summary.json') -Encoding utf8 -Raw | ConvertFrom-Json
    if ($summary.counts.samples -ne 3) { throw "$($smoke.name): expected 3 samples" }
    '{0}: {1:N1} seconds/sample' -f $smoke.name, ($elapsed.TotalSeconds / $summary.counts.samples)
}
```

각 smoke 직후 `perturb_ledger.jsonl`의 eligible 행 기준 placement fallback·run split 비율을 확인한다. 재개 실행에서는 위의 경과 시간이 새로 처리한 표본의 시간만 포함하므로, 시간 측정은 빈 outdir에서 시작한 smoke에 적용한다.

```powershell
foreach ($smoke in $smokeRuns) {
    $ledgerPath = Join-Path $runs "xai_v1_2\$($smoke.name)\perturb_ledger.jsonl"
    $rows = @(Get-Content -LiteralPath $ledgerPath -Encoding utf8 | ForEach-Object { $_ | ConvertFrom-Json })
    $eligible = @($rows | Where-Object { $_.eligible -eq $true })
    if ($rows.Count -ne 120) { throw "$($smoke.name): expected 120 rows" }
    if ($eligible.Count -eq 0) { throw "$($smoke.name): no eligible rows" }
    $fallback = @($eligible | Where-Object { $_.placement_fallback -eq $true }).Count
    $split = @($eligible | Where-Object { $_.run_split -eq $true }).Count
    '{0}: eligible={1}, placement_fallback={2}/{1} ({3:P2}), run_split={4}/{1} ({5:P2})' -f `
        $smoke.name, $eligible.Count, $fallback, ($fallback / $eligible.Count), $split, ($split / $eligible.Count)
}
```

전체 6 run 명령(중단 뒤 같은 명령으로 resume):

```powershell
foreach ($pop in @('main','era')) {
    foreach ($seed in 42,43,44) {
        Invoke-V12Perturb $pop $seed (Join-Path $runs "xai_v1_2\${pop}_seed${seed}_perturb")
    }
}
```

완료 기대값은 **seed별** main `samples=17407`, `rows=696280`, `structure_ineligible_rows=1680`, `forward_passes=2778400`; era `samples=5332`, `rows=213280`, `structure_ineligible_rows=40`, `forward_passes=852960`이다. `perturb_summary.json`의 `ledger_sha256`은 완료 뒤 실제 ledger 재해시와 대조한다. 3건 smoke는 전체 기대값에 해당하지 않는다.
