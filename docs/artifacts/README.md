# 가중치와 데이터셋 복원

`.gitignore`로 제외된 로컬 연구 자산의 Google Drive 보관본입니다. v1/v2·MaleVis의 과거 실험과 합성 검증 자산이며 v3에서 검증된 모델이 아닙니다.

[전체 보관 폴더](https://drive.google.com/drive/folders/1nQWy27-OQmfamBgIvc2822QDXn2_iL4C) · [파일별 다운로드](FILES.md) · [크기·SHA-256 목록](manifest.json)

Drive의 기존 접근 권한을 유지했습니다. 해당 Google 계정 또는 별도 공유 권한이 필요할 수 있으며 제공자의 데이터 이용 조건은 그대로 적용됩니다.

## 다운로드와 복원 위치

| 자산 | 용도 | 복원 위치 |
|---|---|---|
| MaleVis 224·300 원본 ZIP | 기존 Drive에 보관된 이미지 데이터셋 | `datasets/malevis_train_val_224x224/`, `datasets/malevis_train_val_300x300/` |
| `ua-sahi-mal-runs-*.zip` | MaleVis 체크포인트 7개와 실행 설정·결과, 기타 run | 저장소 루트에 풀어 `runs/` 복원 |
| `yolo11n.pt` | Ultralytics 일반 사전학습 초기 가중치 | 저장소 루트 |
| `ua-sahi-mal-verification-weights-*.zip` | 합성 검증용 YOLO best/last 체크포인트 4개 | 저장소 루트에 풀어 `.codex-review/`의 원래 위치 복원 |
| `ua-sahi-mal-big2015-*-part*.zip` | 기존 BIG2015 파생 이미지와 메타데이터 | 저장소 루트에 10개 ZIP을 모두 풀어 `datasets/big2015/` 복원 |
| `ua-sahi-mal-big2015-sample-*.zip` | 정적 `.asm`·`.bytes` 샘플 2쌍 | 저장소 루트에 풀어 `datasets/big2015_sample/` 복원 |
| `ua-sahi-mal-uasahi-cache-*-part*.zip` | 기존 실험의 파생 캐시 | 저장소 루트에 18개 ZIP을 모두 풀어 `datasets/uasahi_cache/` 복원 |
| [BIG2015 원본 ZIP](https://drive.google.com/file/d/1MgoxMX2OHh3Y6L8Mi4VP40xNL5p496Cy/view?usp=drivesdk) | 원본 데이터 보관본 | `datasets/malware-classification.zip` 또는 승인된 데이터 저장 위치 |

**`*-partNN-ofNN.zip`은 각각 독립된 ZIP입니다. 파일을 이어 붙이지 않고 모두 같은 저장소 루트에 풉니다.** 원본 BIG2015는 하나의 ZIP으로 제공하므로 조각 결합이 필요하지 않습니다. 기존 실험 결과를 덮어쓰지 않도록 새 checkout 또는 빈 복원 위치를 사용하십시오.

## BIG2015 원본

파일 크기는 **37,885,110,014 B**입니다. ZIP 내부에는 `dataSample.7z`, `sampleSubmission.csv`, `test.7z`, `train.7z`, `trainLabels.csv`가 있습니다.

로컬 `datasets/train.7z`는 ZIP 내부 `train.7z`와 크기·CRC32가 일치해 중복 업로드하지 않았습니다. 원본 ZIP과 로컬 train 아카이브의 SHA-256, ZIP 엔트리별 크기·CRC32는 [목록](manifest.json)의 `original_archive.source`에 있습니다. 파일을 내려받을 공간 외에 이후 압축 해제 공간은 별도로 준비하십시오.

데이터 접근·전처리는 제공자의 조건과 [데이터 정책](../../SECURITY.md)을 따릅니다. 보관·무결성 검증 과정에서는 데이터나 모델을 실행하지 않았습니다.

## 무결성 확인과 검증 범위

```powershell
Get-FileHash C:\secure-research\ua-sahi-mal-runs-20260905.zip -Algorithm SHA256
Get-FileHash C:\secure-research\malware-classification.zip -Algorithm SHA256
```

결과를 [manifest.json](manifest.json)의 SHA-256과 대조하십시오. 새로 생성한 ZIP 31개는 ZIP CRC 검사와 로컬 SHA-256 계산을 마쳤고, 업로드 후에는 Drive 파일 크기를 다시 읽어 대조했습니다. 원본 ZIP과 `yolo11n.pt`에도 로컬 SHA-256과 업로드 후 크기 검증 결과를 기록했습니다. 원격 파일을 전부 다시 다운로드해 해시를 대조한 것은 아닙니다.

MaleVis 두 ZIP은 기존 Drive 보관본을 재사용했습니다. Drive 크기와 접근 가능 여부를 확인했으며 기존 ZIP과 현재 로컬 추출본의 바이트 단위 동일성까지 검증한 것은 아닙니다.
