# 학습 인수인계 — PSA-XAI-V1.0-DRAFT (다음 LLM용)

## 최신 실측 상태 — 2026-09-20 19:47 KST

아래는 산출물을 직접 확인한 운영 기록이다. 이후 본문의 초기 실행 기록은 과거 상태이며,
사용자의 최신 지시가 항상 우선한다. **학습은 완료됐고 P2 원본 접근 오류로 test XAI 실험은 보류 중이다.**

- ImageNet 초기화 seed 42/43/44 모두 완료. 체크포인트 SHA256, summary, history,
  중복 제거 후 counts 및 분류 sanity gate를 검증했다. 기존 seed 42 결과를 재사용했으며 재학습하지 않았다.
- validation macro-F1: 42=0.953395, 43=0.946615, 44=0.952926 (평균 0.950979).
  별도 validation 평가 AUROC: 42=0.986835, 43=0.987373, 44=0.987116 (평균 0.987108).
  random seed 42 AUROC=0.975859. 초기화 선택 기준은 기존 validation macro-F1 그대로다.
- 필수 metadata-only AUROC 기준선은 0.95. CNN validation과 metadata group-disjoint 5-fold는
  동일 평가 분할이 아니므로 이 수치 차이만으로 통제된 우월성이나 새로운 악성 의미 학습을 주장하지 않는다.
  test 성능/Grad-CAM/perturbation/통계는 아직 완료하지 않았다.
- 근거: `C:\research\ua-sahi-mal\runs\psa-orchestration\all_seeds_verified.json`,
  `C:\research\ua-sahi-mal\runs\psa-orchestration\validation_auroc_20260920.json`.

### P2 차단 및 재개 조건

실제 원본 위치는 `D:\secure-malware-data\psa\pe-machine-learning-dataset\samples`이다.
새 정적 구조 매핑/독립 pefile 비교 구현의 합성 및 기존 회귀 테스트 61개가 통과했다.
원본 실행/import/동적 로딩 없이 train/val 256개 진단 사전검사를 수행했다.
66개는 원본 해시 및 두 파서 필드가 일치했으나 190개는 PermissionError였다.
66개 중 resource directory 비완전 section-backed 경고 5개도 별도 검토가 필요하다.
이 진단 표본은 대표성 있는 추정 표본이 아니며 P2 통과 근거가 아니다.

- 근거: `D:\secure-malware-data\psa\audit\p2_preflight_20260920\structure_audit_summary.json`,
  같은 폴더 `structure_ledger.jsonl`, `audit_plan.json`.
- 후속 내용 비접근 점검에서 오류 대상 190개 중 141개는 File.Exists=false, 49개는 true였다.
  false는 부재/접근 불가를 구분하는 증거가 아니다. 일부 개별 파일도 경로를 찾지 못했다.
  sample 3의 ACL에는 읽기 권한이 있으나 검사 당시 읽기 오류가 있었다.
- AhnLab V3 Lite와 Windows Defender 등록을 확인했으나 격리/삭제 주체는 확인하지 못했다.
  Defender 폴더 제외가 있었으며 실시간 보호는 점검 당시 false였다. 이 작업에서 설정은 변경하지 않았다.
- **사용자/관리자의 보안 제품 격리 이력 확인과 승인된 원본 접근 복구가 필요하다.**
  자동 복원/재압축해제/백신 또는 ACL 변경, 반복 원본 읽기를 하지 않는다.
  사용자가 접근 복구를 확인하면 별도 새 출력 경로로 원본 해시와 P2를 재검증한다.
  오류를 제외해서 P2를 통과 처리하거나 test 실험으로 우회하지 않는다.

### Era 분할 및 동결 주의

원래 era ID 70,938개를 유지한 그룹 분리·층화 분할을 별도 생성했다.
`D:\secure-malware-data\psa\audit\era_stratified_20260920\split_manifest_era.csv`
SHA256=`fd0a99000b05785ecf3fc01108529b37e08bb31f162b6defc3f3621459d2d91a`.
train/val/test=49,622/10,662/10,654; 근거는 같은 폴더 `era_split_report.json`.
기존 main split과 옛 era split은 덮어쓰지 않았다.
새 era test 중 5,774개는 main 학습 그룹, 3,212개는 main validation 그룹에 속한다.
따라서 기존 main 모델로 새 era test 전체를 미관측 holdout이라고 평가하면 안 된다.
별도 era 학습 또는 기존 test 교집합 분석의 범위를 먼저 결정해야 한다.

프로토콜 수치/가설은 변경하지 않았고 동결하지 않았다. P2 복구·경고 검토,
정확한 target layer 고정 및 peak VRAM 기록 등 동결 요건은 남아 있다.
중복 제거 후 test 악성 수는 17,407개로 프로토콜 원래 수와 구분해 보고한다.
학습 중복 실행, 요청 없는 commit/push를 하지 않는다.

### 2026-09-21 재개 기록

원본과 래스터를 열지 않고 검증된 체크포인트와 합성 입력만 사용해 두 동결 항목을 확정했다.
근거는 `C:\research\ua-sahi-mal\runs\psa-orchestration\freeze_prereqs_20260921.json`이다.

- batch 512: pilot peak 6,070.7 MiB / 총 8,123.4 MiB = 74.73%; 실제 세 학습 run의
  최대 peak 6,072.7 MiB = 74.76%. 동결 기준인 총 VRAM 80% 미만을 만족한다.
- Grad-CAM target layer: 정확한 `named_modules()` 경로 `layer4.1`, 클래스 `BasicBlock`.
  CUDA 합성 forward/backward에서 activation과 gradient가 모두 `[1,512,7,7]`, 분류 출력은 `[1,2]`,
  악성 target logit index는 1로 확인했다.
- 이 두 항목만 통과했으며 전체 프로토콜 동결은 아니다. 독립 pefile P2는 원본 접근 복구 전까지 차단된다.

### 2026-09-21 P2 재시도 결과 — 원본 접근 중지

사용자 요청으로 동일한 256개 train/val 표본을 새 출력 폴더에서 한 번 재시도했다.
일치는 66→50개로 감소하고 오류는 190→206개로 증가했다. 재시도 오류는 파일 부재 158개,
래스터 인덱스 대비 크기 불일치 39개, 원본 manifest 대비 SHA-256 불일치 9개였다.
이전 일치 표본 중 17개가 오류로 바뀌고 이전 오류 중 1개만 일치로 바뀌었다.
해시가 유효해 두 파서까지 도달한 표본에서는 필드 불일치가 없었다.

따라서 현재 추출 원본 트리는 반복 접근 중 안정적이지 않다. 더 읽으면 증거가 추가로 소실될 수 있어
원본 읽기와 전체 P2/XAI를 중지한다. 원인은 특정 보안 제품으로 확정하지 않았다.
상세 근거와 안전한 복구 게이트는
`audit/P2_SOURCE_INTEGRITY_BLOCKER_2026-09-21.md`를 따른다. 검증된 아카이브를 승인된 새 경로에
복원하고 선택 P2 모집단의 missing/size/SHA 오류가 모두 0임을 확인하기 전에는 재시도하지 않는다.

> 이 문서 전체가 지시문이다. 데이터·환경·P0 게이트는 모두 끝났다. 네 일은 **모델 학습 → Grad-CAM →
> deletion/keep-only → 통계**를 프로토콜대로 실행하는 것이다. 사용자가 Windows에서 명령을 직접 돌리고
> 결과 로그를 너에게 붙여넣는다. 너는 스크립트를 고치고 결과를 해석한다.

## 0. 절대 규칙
1. `protocol/PSA_XAI_V1_0_DRAFT.yaml`의 수치를 바꾸지 마라. 동결 전이라도 결과를 보고 규칙을 고치지 마라.
2. 원본 PE를 실행·import·동적 로딩하지 마라. 학습은 파생 래스터(`rasters.npy`)만 쓴다.
3. **검증한 것만 보고하라.** 정확도·CAM 성능을 산출물 확인 전에 완료됐다고 쓰지 마라.
4. 결론 범위: **"악성 판정 근거"라고 쓸 수 없다.** §5 게이트가 걸려(§아래) 결론은 설명 충실성 +
   데이터셋 편향 평가로 제한된다. metadata-only AUROC **0.95**가 필수 보고 기준선이다.

## 1. 환경 (확인됨)
- Windows 11, RTX 5070 Laptop **8 GB**, torch 2.8.0+cu128, torchvision 0.23.0, Python 3.12, venv `C:\research\ua-sahi-mal\.venv`.
- CUDA Grad-CAM 검증됨: `pytorch-grad-cam` CAM과 직접 hook 구현이 Spearman 0.9999999999 일치 → 둘 중 무엇을 써도 동일.
- 백신: `D:\secure-malware-data` 폴더 제외만. 전역 비활성화 금지.

## 2. 데이터 (P0 통과, D:\secure-malware-data\psa\)
- `rasters/rasters.npy` — (199316, 50176) float32, 값 0~255(로더가 /255). `raster_index.csv`(`row,sample_id,label,split,group,pe_kind,file_size,policy,raster_sha256,map_sha256`) sha256 `94d02b24…f785`.
- `audit/split_manifest.csv` sha256 `843bcb80…099b`: imphash 그룹 분리 + label×pe_kind×repr_policy 층화. train 139,192 / val 29,953 / test 30,171.
- 래스터 중복 116그룹(`raster_duplicate_groups.csv`) → 로더가 대표 1개만 남기고 제외(누수 0 확인됨).
- 원본 바이트가 필요한 건 **test split의 deletion/keep-only뿐**. `D:\…\samples\<sample_id>`에 그대로 있다.

## 3. 동결된 설정 (프로토콜)
| 항목 | 값 |
|---|---|
| 모델 | ResNet-18, conv1을 1채널로 교체(입력 1×224×224) |
| 초기화 | validation으로 선택 후 동결 (§4.1 참조) |
| optimizer | AdamW, lr 1e-3, weight_decay 1e-2 |
| epochs / early stop | 최대 30 / patience 5 |
| 선택 지표 | validation macro-F1 |
| seeds | **42, 43, 44** (셋 다) |
| AMP | on |
| augmentation | **금지** (flip/rotation/crop/jitter 없음) |
| batch size | **pilot로 실측** (동결 차단 1번) |
| target layer | 후보 `layer4.1` — pilot 후 정확한 module path로 고정 |
| 분류 sanity gate | macro-F1 > majority+0.10, balanced acc ≥ 0.70, 두 class recall ≥ 0.60, seed 방향 일치 |

## 4. 실행 순서

### 4.0 pilot — batch size 실측 (동결 차단 1번 해소)
```powershell
cd C:\research\ua-sahi-mal
.\.venv\Scripts\python.exe scripts\psa_train.py pilot `
  --rasters-dir D:\secure-malware-data\psa\rasters `
  --out-dir     D:\secure-malware-data\psa\runs
```
→ `runs\pilot_batch_size.json`의 `recommended_batch_size`(총 VRAM 80% 이하 최대 배치)를 이후 배치로 쓴다.
peak VRAM·img/s가 배치별로 기록된다. 이 값을 프로토콜 `model.batch_size`에 적어 동결한다.

### 4.1 초기화 선택 (프로토콜: validation으로 선택 후 동결)
seed 42로 **imagenet**과 **random** 둘 다 학습해 val macro-F1이 높은 쪽을 초기화로 확정한다.
(ImageNet 가중치는 Windows에서 `download.pytorch.org`로 자동 다운로드된다 — 클라우드 프록시에서는 막혔지만
사용자 PC 인터넷에서는 받아진다.)
```powershell
.\.venv\Scripts\python.exe scripts\psa_train.py train --rasters-dir D:\secure-malware-data\psa\rasters `
  --out-dir D:\secure-malware-data\psa\runs --batch-size <PILOT값> --init imagenet --seed 42
.\.venv\Scripts\python.exe scripts\psa_train.py train --rasters-dir D:\secure-malware-data\psa\rasters `
  --out-dir D:\secure-malware-data\psa\runs --batch-size <PILOT값> --init random  --seed 42
```
승자 초기화를 `<INIT>`로 고정.

### 4.2 본 학습 — seed 42/43/44 (승자 초기화로)
```powershell
foreach ($s in 42,43,44) {
  .\.venv\Scripts\python.exe scripts\psa_train.py train --rasters-dir D:\secure-malware-data\psa\rasters `
    --out-dir D:\secure-malware-data\psa\runs --batch-size <PILOT값> --init <INIT> --seed $s
}
```
각 run은 `runs\seed<S>_<INIT>_bs<B>\best.pt`(+sha256)와 `summary.json`을 남긴다.
`summary.json.sanity_gate`가 세 seed 모두 통과하는지 확인. **하나라도 실패하면 XAI로 진행하지 말고**
라벨·표현·누수를 먼저 감사한다(프로토콜 §7).


## 4.3 첫 실행 결과 (2026-09-15, 참고용 — 아직 확정 아님)
사용자가 pilot을 건너뛰고 `--init random --seed 42 --batch-size 512`를 직접 돌렸다. 결과:
- **스크립트 정상 동작.** batch 512가 8 GB에서 OOM 없이 돌아감(~525 img/s, ~265 s/epoch). → 배치 512 확정,
  peak VRAM은 `runs\seed42_random_bs512\summary.json`의 `history[].peak_vram_mib`에서 읽어 프로토콜에 기록.
- val macro-F1 **0.9355** @ epoch 3, epoch 8 early stop. 분류 sanity gate 통과(margin 0.57, bal_acc·recall 모두 OK).
- **주의:** 이건 random 초기화 1개 seed일 뿐이다. 아직 (a) imagenet 초기화 seed 42(초기화 선택용),
  (b) 승자 초기화로 seed 43·44 가 남았다.

### 반드시 볼 숫자 — val AUROC vs 0.95
스크립트에 **val AUROC 보고**를 추가했다(메타데이터 기준선이 AUROC 0.95이므로 같은 지표로 비교해야 함).
다음 실행부터 epoch 줄에 `val_AUROC`가 찍히고 `summary.json`에 `cnn_val_auroc_over_baseline`이 남는다.
- CNN val AUROC ≈ 0.95 → **바이트 이미지가 메타데이터 단축경로 이상을 못 본다** = 데이터셋 편향 서사 강화.
- CNN val AUROC ≫ 0.95 → 이미지가 메타데이터에 없는 것을 본다 = 그 증분이 논점.
어느 쪽이든 이 한 숫자가 논문의 핵심이다. macro-F1(0.9355)만으로 결론 내지 마라.

## 5. 학습 후 (아직 스크립트 없음 — 네가 만들 것)
프로토콜 §8~§11. 순서대로 새 스크립트를 작성해 사용자에게 명령을 준다.
1. **`psa_gradcam.py`** — test의 악성 표본에 Grad-CAM(target `layer4.1`, malicious logit, bilinear
   align_corners=False). budget 0.05/0.10/0.20/0.40의 고유 바이트 선택. 대조군: uniform random×20,
   front, entropy, **structure-matched random×20**(primary comparator). overshoot·empty CAM 기록.
   → `src/ua_sahi_mal/kisa_xai/representation.py`의 `select_source_bytes_by_budget` 재사용.
2. **`psa_perturb.py`** — deletion ΔNLL, keep-only. fill 3종(structure-conditioned resampling / local
   median·blur / zero). Grad-CAM과 대조군이 같은 sample·budget·fill random state 공유. 원본 바이트는
   test 표본만 `D:\…\samples\`에서 읽는다(실행 금지).
3. **통계** — H1(deletion ΔNLL > structure-matched random), H2(keep-only > random). 파일/그룹 단위
   쌍체 부트스트랩 2,000 + Holm(2검정). effect·95% CI·adjusted p·eligible n, seed별 + 평균.
4. **구조 enrichment** — header/exec/non-exec/resource/cert/overlay/unknown별 CAM mass.
   **검증 가능한 예측: CAM이 헤더가 아니라 고엔트로피 실행 섹션에 몰려야 한다**(§5 해석이 맞다면).
   PE 구조 지도는 P2에서 pefile로 만든다(`manifest_stage2.csv`의 섹션 정보 재사용 가능).

## 6. §5 결과 (왜 결론이 제한되는가)
metadata-only(바이트 유도 20변수) 그룹 분리 5-fold AUROC **0.95**. ablation은 중복 교란(툴체인 연대,
정상 VS2005~2013 vs 악성 VC6/Delphi). 연대 변수만 매칭 제거 시 0.90~0.91 — 남는 분리력은 패킹
엔트로피·서브시스템 등 실제 정적 특성. 따라서 CNN이 0.95 위로 얼마나 올라가는지, 그리고 Grad-CAM이
그 신호를 충실히 짚는지가 논점. 상세: `audit/DATA_AUDIT_2026-09-15_psa_p0_stage2.md`.

## 7. 동결 (`PSA-XAI-V1.1-FROZEN`) 남은 차단
1. batch size 실측(4.0) 2. target layer module path 고정 3. P2 독립 pefile 교차검사
4. era 부분집합 분할을 층화 버전으로 재생성(`split_manifest_era.csv`는 층화 이전 빌드).
넷 다 끝나면 프로토콜 YAML의 해시·batch·layer를 채우고 동결 태그.

## 8. 참고 파일
`protocol/PSA_XAI_V1_0_DRAFT.yaml`, `audit/DATA_AUDIT_2026-09-15_psa_p0_stage{1,2}.md`,
`PROGRESS_2026-09-15.md`, `scripts/psa_{stream_audit,shortcut_audit,confound_drilldown,build_rasters,p0_finalize,train}.py`.
