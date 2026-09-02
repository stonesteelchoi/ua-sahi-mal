# AI-TOD·VEDAI·DIOR 실험 결과 정리

출처: ChatGPT 프로젝트 대화 `논문초안 재작성` (`6a8bff55-d61c-83e8-a24d-ffa0ea6cc9dd`)

## 구성 이름

프로젝트 대화에서는 네 구성을 다음 이름으로 구분합니다.

- A0: UA Baseline
- A1: Survival
- A2: RPST
- A3: Full

다만 접근 가능한 자료만으로는 다음이 확정되지 않았습니다.

- A0의 UA가 실제 공개 Upsample Anything 구현인지 여부
- A1 Survival의 정확한 모듈, 손실, 적용 위치
- A2 RPST의 정확한 crop·teacher·loss 규칙
- A3 Full에 포함된 모듈 조합

따라서 이 문서의 구성 이름은 실험표 라벨로만 사용해야 하며, 구현 정의로 간주하면 안 됩니다.

## 데이터셋별 최고 결과

### AI-TOD

A3 Full이 접근 가능한 요약의 모든 핵심 지표에서 최고였습니다.

| Precision | Recall | mAP50 | mAP50-95 |
|---:|---:|---:|---:|
| 0.7436 | 0.5902 | 0.6280 | 0.2786 |

### VEDAI

- A3 Full: Recall 0.6561, mAP50 0.6483으로 최고
- A0 UA Baseline: Precision 0.7338, mAP50-95 0.3549로 최고

VEDAI에서는 Full 구성이 모든 지표를 지배하지 않습니다. 탐지 누락을 줄이는 관점에서는 A3가 유리하지만, 정밀한 localization과 오탐 억제는 A0가 더 나았습니다.

### DIOR

- A2 RPST: Precision 0.8125, mAP50 0.7622, mAP50-95 0.5296으로 최고
- A0 UA Baseline: Recall 0.7299로 최고

DIOR에서는 RPST 단독 구성이 정확도 관련 지표에서 강했고, baseline이 recall에서 강했습니다. Full 조합의 보편적 우월성을 주장할 수 없는 대표적인 결과입니다.

## 세 데이터셋 단순 평균의 최고 구성

| 지표 | 최고 구성 | 값 |
|---|---|---:|
| Precision | A0 UA Baseline | 0.7462 |
| Recall | A3 Full | 0.6565 |
| mAP50 | A3 Full | 0.6786 |
| mAP50-95 | A1 Survival | 0.3852 |

핵심 해석은 지표와 데이터셋에 따라 최적 구성이 다르다는 것입니다. A0~A3는 세 데이터셋 모두에서 FFCA-YOLO baseline보다 mAP50과 mAP50-95가 높았다고 정리되어 있지만, “A3가 항상 최고” 또는 “RPST가 모든 조건에서 우수”와 같은 문장은 실험 결과와 맞지 않습니다.

## UA-SAHI 계산량 분석의 상태

프로젝트 초안은 `800×800 영상`, `400×400 창`, `20% overlap`, `총 detector 호출 10회 → 6회` 분석을 포함합니다. 그러나 접근 가능한 자료에는 UA-SAHI의 실제 AP와 종단간 latency가 없습니다.

따라서 이 수치는 다음처럼 취급해야 합니다.

- 타일 수와 호출 수: 구조에서 계산한 분석값
- AP, AP_S, end-to-end latency: 아직 측정되지 않은 후속 실험 항목

논문에서는 계산 가능성 또는 실험 설계로 분리하고, 실제 성능 결과처럼 표에 섞으면 안 됩니다.

## 재현을 위해 반드시 확보할 메타데이터

- 데이터셋 버전과 train/validation/test 분할
- 입력 크기와 resize/letterbox 규칙
- random seed와 반복 횟수
- GPU, CUDA, PyTorch, Ultralytics, SAHI 버전
- 학습 epoch, batch size, optimizer, learning-rate schedule
- A0~A3의 정확한 YAML/config diff
- 사용 checkpoint와 commit SHA
- confidence/NMS/NMM threshold
- 측정 latency의 warm-up, 동기화, batch, precision 조건

평균과 표준편차 또는 최소한 3회 반복 결과가 없으면 작은 성능 차이를 구조적 개선으로 단정하기 어렵습니다.
