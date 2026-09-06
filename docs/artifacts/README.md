# 가중치와 데이터셋 복원

이 보관본은 `.gitignore`로 제외된 로컬 연구 자산의 백업입니다. v1/v2·MaleVis의 과거 실험과 합성 검증 자산이며, v3에서 학습·검증된 모델로 해석하지 않습니다.

- [프로젝트 Drive](https://drive.google.com/drive/folders/1rHmSUINadLPMBunDRoIpvQEumJAC1NH5)
- [이번 자산 보관 폴더](https://drive.google.com/drive/folders/1nQWy27-OQmfamBgIvc2822QDXn2_iL4C)
- [파일별 다운로드·SHA-256 목록](manifest.json)

Drive의 기존 접근 권한을 유지했습니다. 링크가 보여도 해당 Google 계정 또는 별도 공유 권한이 필요할 수 있습니다. 제공자의 데이터 이용 조건은 그대로 적용됩니다.

## 어떤 파일을 받을까요?

| 자산 | 용도 | 복원 위치 |
|---|---|---|
| MaleVis 224·300 원본 ZIP | 기존 Drive에 보관된 이미지 데이터셋 | `datasets/malevis_train_val_224x224/`, `datasets/malevis_train_val_300x300/` |
| `ua-sahi-mal-runs-*.zip` | MaleVis 체크포인트 7개와 실행 설정·결과, 기타 기존 run | 저장소 루트에 풀어 `runs/` 복원 |
| `yolo11n.pt` | Ultralytics 일반 사전학습 초기 가중치. 악성코드 탐지 학습 결과가 아님 | 저장소 루트 |
| `ua-sahi-mal-verification-weights-*.zip` | 합성 검증용 YOLO best/last 체크포인트 4개 | 저장소 루트에 풀어 `.codex-review/` 아래 원래 위치 복원 |
| `ua-sahi-mal-big2015-*-part*.zip` | 기존 BIG2015 파생 이미지와 메타데이터 | 저장소 루트에 모든 ZIP을 풀어 `datasets/big2015/` 복원 |
| `ua-sahi-mal-big2015-sample-*.zip` | 기존 정적 `.asm`·`.bytes` 샘플 2쌍 | 저장소 루트에 풀어 `datasets/big2015_sample/` 복원 |
| `ua-sahi-mal-uasahi-cache-*-part*.zip` | 기존 실험의 파생 캐시 | 저장소 루트에 모든 ZIP을 풀어 `datasets/uasahi_cache/` 복원 |
| `malware-classification.zip.partNNN` | BIG2015 원본 ZIP의 연속 바이트 조각 | 아래 명령으로 ZIP을 먼저 결합 |

`*-partNN-ofNN.zip`은 **각각 독립된 ZIP**입니다. 모두 같은 저장소 루트에 풀면 됩니다. 반면 `.zip.partNNN`은 ZIP의 바이트 조각이므로 **번호순 결합**이 필요합니다. 두 형식을 혼동하지 마십시오.

MaleVis 두 ZIP은 이번에 재업로드한 파일이 아니라 기존 보관본입니다. Drive 파일 크기와 접근 가능 여부를 확인했으며, 기존 ZIP과 현재 로컬 추출본의 바이트 단위 동일성까지 확인한 것은 아닙니다. 새로 만든 ZIP에는 로컬 SHA-256과 ZIP CRC 검증 결과를 기록했습니다. 업로드 뒤에는 Drive의 파일 크기를 다시 읽어 대조했습니다.

## 원본 ZIP 결합

목록의 `original_archive.status`가 `complete`인지 먼저 확인합니다. `parts` 배열의 링크에서 모든 조각을 다운로드해 한 폴더에 놓습니다. 자동으로 파일명에 `(1)`이 붙은 중복 다운로드는 원래 이름으로 정리하십시오.

```powershell
# Python 3.10–3.12. 아래 경로는 자신의 승인된 데이터 저장 위치로 바꾸세요.
python scripts/restore_drive_archive.py `
  --manifest docs/artifacts/manifest.json `
  --parts-dir C:\secure-research\big2015-parts `
  --output C:\secure-research\malware-classification.zip
```

스크립트는 조각 개수·순서·크기·각 SHA-256과 결합된 ZIP의 SHA-256을 검사합니다. 출력 파일이 이미 있으면 중단하며, 파일 내용의 압축 해제나 실행은 하지 않습니다. 조각을 보관한 디스크에 ZIP도 만들 경우 약 75.8GB의 공간이 필요합니다(조각 약 37.9GB + 완성 ZIP 약 37.9GB). 이후 압축 해제 공간은 별도입니다.

원본 ZIP 안에는 `train.7z`가 포함됩니다. 로컬 `datasets/train.7z`의 크기·CRC32와 ZIP 엔트리를 대조한 결과는 목록의 `original_archive.source.local_train`에 기록합니다. 중복 사본은 별도로 업로드하지 않습니다. 필요한 데이터 접근·전처리는 제공자 조건과 기존 [데이터 정책](../../SECURITY.md)을 따릅니다.

## 무결성 확인

작은 ZIP이나 가중치는 다음과 같이 내려받은 파일의 SHA-256을 목록과 비교할 수 있습니다.

```powershell
Get-FileHash C:\secure-research\ua-sahi-mal-runs-20260905.zip -Algorithm SHA256
```

원본 ZIP 조각은 결합 스크립트가 검사하므로 별도의 해시 계산 명령은 필요하지 않습니다. `manifest.json`은 파일명·크기·해시·복원 위치·Drive 링크를 보관하며 실제 데이터나 가중치를 포함하지 않습니다.
