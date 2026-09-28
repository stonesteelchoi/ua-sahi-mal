# C10 실행 명령 준비

사용자 `.venv` PowerShell 창에서 저장소 루트를 현재 디렉터리로 놓고 실행한다. 이 문서는 실행 기록이 아니다. 동결된 main/era test를 각 체크포인트에서 한 번씩 평가한다. `eval`은 checkpoint 기대 해시를 검증한 뒤 성능을 산출하고, 기존 test 출력 파일을 덮어쓰지 않는다. 출력 JSON의 `input_sha256`에는 raster index, raster array, duplicate groups(존재 시), era manifest(해당 시)의 해시가 들어간다. 대형 `rasters.npy` 해시에 시간이 걸릴 수 있다.

```powershell
$python = '.\.venv\Scripts\python.exe'
$raster = 'D:\secure-malware-data\psa\rasters'
$runs = 'D:\secure-malware-data\psa\runs'
$outdir = 'runs\psa-orchestration'
$eraManifest = 'D:\secure-malware-data\psa\audit\era_stratified_freeze_20260924\split_manifest_era.csv'
New-Item -ItemType Directory -Path $outdir -Force | Out-Null
$checks = @{
  main = @{
    42='291af0bd0b2133f3c501fe3efdae0f5503b6de7d4e095a5fc2b1c27a7561f48f'
    43='4156f2b8bf8c7995c8d62e4132102b28430d9fc69de49b293ec561af68bcaf56'
    44='62c0d8b002586676d61c7488099e362b4c15777a9406424c324c1f4fbec5639c'
  }
  era = @{
    42='a1121de1a69992c9032d2278f2a43b6560ada3e5d03716097c145bc5c23dc2b6'
    43='f031295be823c37158411180f63c64a4eee5189e6077cc744aa69d408b6ee7bf'
    44='da30a11b32904116a83f3b408e37e7508bb6d4969fee8336fa8392a1caa729f1'
  }
}
if ((Get-FileHash -LiteralPath $eraManifest -Algorithm SHA256).Hash.ToLower() -ne 'fd0a99000b05785ecf3fc01108529b37e08bb31f162b6defc3f3621459d2d91a') { throw 'era manifest hash mismatch' }
foreach ($pop in @('main','era')) {
  foreach ($seed in @(42,43,44)) {
    $runSet = if ($pop -eq 'main') { 'c8_retrain_20260924' } else { 'era_20260924' }
    $checkpoint = Join-Path $runs "$runSet\seed${seed}_imagenet_bs512\best.pt"
    $out = Join-Path $outdir "test_eval_${pop}_seed${seed}.json"
    $evalArgs = @('scripts\psa_train.py','eval','--rasters-dir',$raster,'--checkpoint',$checkpoint,'--checkpoint-sha256',$checks[$pop][$seed],'--split','test','--batch-size','512','--workers','4','--out',$out)
    if ($pop -eq 'era') { $evalArgs += @('--split-manifest',$eraManifest) }
    & $python @evalArgs
    if ($LASTEXITCODE -ne 0) { throw "test eval failed: $pop seed $seed" }
  }
}
```

통계는 여섯 완전한 perturb/Grad-CAM ledger 쌍을 사용한다. 출력 디렉터리는 새 경로여야 한다. 통계 스크립트가 ledger와 동결 protocol SHA-256을 JSON에 기록한다.

```powershell
$python = '.\.venv\Scripts\python.exe'
$xai = 'D:\secure-malware-data\psa\runs\xai_v1_1'
$statsArgs = @('scripts\psa_xai_stats.py')
foreach ($pop in @('main','era')) {
  foreach ($seed in @(42,43,44)) {
    $perturb = Join-Path $xai "${pop}_seed${seed}_perturb\perturb_ledger.jsonl"
    $gradcam = Join-Path $xai "${pop}_seed${seed}_gradcam\gradcam_ledger.jsonl"
    if (-not (Test-Path -LiteralPath $perturb -PathType Leaf)) { throw "missing $perturb" }
    if (-not (Test-Path -LiteralPath $gradcam -PathType Leaf)) { throw "missing $gradcam" }
    $statsArgs += @('--ledger',$pop,"$seed",$perturb,$gradcam)
  }
}
& $python @statsArgs --outdir 'runs\psa-orchestration\xai_stats_20260930'
if ($LASTEXITCODE -ne 0) { throw 'XAI statistics failed' }
```

두 스크립트 모두 C10-prep에서는 실행하지 않았다. Checkpoint SHA-256과 동결 YAML SHA-256은 `PROTOCOL_FREEZE_2026-09-24.md`, era manifest SHA-256은 `PROGRESS.md`의 동결 기록을 따른다.
