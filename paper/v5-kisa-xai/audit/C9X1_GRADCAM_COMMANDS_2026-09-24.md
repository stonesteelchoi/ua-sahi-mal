# C9x-1 Grad-CAM 실행 명령 (미실행)

`scripts/psa_gradcam.py`는 동결 YAML의 representation, xai, statistics를 읽고 악성 test 표본 전부에 대해 checkpoint SHA-256, raster index SHA-256, 기존 P2 구조 ledger SHA-256을 확인한다. 원본 PE를 다시 열지 않는다. 각 표본과 budget마다 요청/달성 고유 바이트 수, overshoot, source interval, empty CAM flag, 구조 영역별 CAM mass를 JSONL에 쓴다. 구조 귀속이 불가능한 기존 census 행도 유지하고 mass를 null로 표시한다. 대조군과 perturbation은 후속 청크에서 이 ledger의 달성 budget에 맞춘다.

아래 명령은 사용자 `.venv` PowerShell 창에서 실행할 수 있도록 기록한 것이며 **이 청크에서 실행하지 않았다**. 여섯 출력 디렉터리는 기존에 없어야 한다. 체크포인트 해시는 동결 판정 문서의 지정값이다.

```powershell
$py = '.\.venv\Scripts\python.exe'
$rasters = 'D:\secure-malware-data\psa\rasters'
$runs = 'D:\secure-malware-data\psa\runs'
$audit = 'D:\secure-malware-data\psa\audit'
$mainLedger = Join-Path $audit 'main_test_structure_census_20260924\structure_ledger.jsonl'
$eraLedger = Join-Path $audit 'era_test_structure_census_20260924\structure_ledger.jsonl'
$mainLedgerSha = '53bc25ecf7b144cb5d1599fba9052b0eb9d52ef973947672fdbc720ecbd85c7b'
$eraLedgerSha = 'bf538e933bfd87a19a0e5ed47bdf2a40344e3bbd602215b61586d00072473b16'
$eraManifest = Join-Path $audit 'era_stratified_freeze_20260924\split_manifest_era.csv'
$eraManifestSha = 'fd0a99000b05785ecf3fc01108529b37e08bb31f162b6defc3f3621459d2d91a'
$mainHashes = @{42='291af0bd0b2133f3c501fe3efdae0f5503b6de7d4e095a5fc2b1c27a7561f48f';43='4156f2b8bf8c7995c8d62e4132102b28430d9fc69de49b293ec561af68bcaf56';44='62c0d8b002586676d61c7488099e362b4c15777a9406424c324c1f4fbec5639c'}
$eraHashes = @{42='a1121de1a69992c9032d2278f2a43b6560ada3e5d03716097c145bc5c23dc2b6';43='f031295be823c37158411180f63c64a4eee5189e6077cc744aa69d408b6ee7bf';44='da30a11b32904116a83f3b408e37e7508bb6d4969fee8336fa8392a1caa729f1'}
foreach ($seed in 42,43,44) {
    & $py scripts\psa_gradcam.py --checkpoint (Join-Path $runs "c8_retrain_20260924\seed${seed}_imagenet_bs512\best.pt") --checkpoint-sha256 $mainHashes[$seed] --rasters-dir $rasters --structure-ledger $mainLedger --structure-ledger-sha256 $mainLedgerSha --outdir (Join-Path $runs "xai_v1_1\main_seed${seed}_gradcam")
    if ($LASTEXITCODE -ne 0) { throw "main seed $seed Grad-CAM failed" }
    & $py scripts\psa_gradcam.py --checkpoint (Join-Path $runs "era_20260924\seed${seed}_imagenet_bs512\best.pt") --checkpoint-sha256 $eraHashes[$seed] --rasters-dir $rasters --structure-ledger $eraLedger --structure-ledger-sha256 $eraLedgerSha --split-manifest $eraManifest --split-manifest-sha256 $eraManifestSha --outdir (Join-Path $runs "xai_v1_1\era_seed${seed}_gradcam")
    if ($LASTEXITCODE -ne 0) { throw "era seed $seed Grad-CAM failed" }
}
```

합성 회귀 실행 명령(실제 test 데이터 접근 없음):

```powershell
& .\.venv\Scripts\python.exe -m pytest tests\test_psa_gradcam.py -q --basetemp .pytest_gradcam_tmp
```

이 세션에서 Anaconda Python으로 합성 회귀 `2 passed, 1 skipped`를 확인했다. skip은 이 환경에 torch가 없어 hook 테스트를 실행할 수 없기 때문이다. `.venv` Python 런처는 기존 base Python 경로 오류로 실행할 수 없었으므로 사용자 창의 위 명령으로 hook 경로를 확인해야 한다. `py_compile`도 통과했다. 실제 test Grad-CAM 명령은 실행하지 않았다.
