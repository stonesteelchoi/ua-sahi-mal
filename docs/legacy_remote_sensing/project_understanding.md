# 프로젝트 이해 정리

## 한 문장 정의

이 프로젝트는 원격탐사 영상의 tiny object 검출에서 **학습 단계에서는 객체 특징의 생존과 스케일 표현을 개선하고**, **추론 단계에서는 UA 기반 확률지도 라우팅으로 SAHI 타일 호출을 줄이려는 연구 묶음**입니다.

## 연구 축 A: Survival/TOSD + RPST

접근 가능한 결과 라벨과 인접 프로젝트 문맥을 종합하면 A0~A3는 다음 계열의 ablation으로 이해됩니다.

### Survival/TOSD 계열

초기 stride-2 downsampling에서 몇 픽셀 크기의 객체 정보가 배경에 섞여 사라지는 문제를 다룹니다. 일반적인 stride convolution 의미 경로와 PixelUnshuffle 기반 detail 경로를 병렬로 두고, 소실 위험이 높은 위치에서 세부 경로를 더 반영하는 설계입니다.

개념식은 다음과 같습니다.

\[
Y=X_s+\gamma M\odot X_d
\]

- \(X_s\): stride convolution 의미 특징
- \(X_d\): PixelUnshuffle 기반 세부 특징
- \(M\): 공간별 소실 위험도
- \(\gamma\): 세부 경로의 학습 가능한 전체 강도

크기가 작은 객체일수록 높은 위험 target을 주는 size-aware survival supervision을 사용한다는 것이 핵심입니다.

### RPST 계열

student는 원본 전체 영상을 보고, EMA teacher는 tiny object 주변을 crop·확대한 영상을 봅니다. teacher가 더 높은 해상도에서 얻는 피라미드 스케일 반응과 foreground-context 관계를 student에 증류합니다.

일반적인 같은 레벨 feature matching 대신 확대 배율에 따른 피라미드 레벨 이동을 고려합니다.

\[
\Delta_i=\operatorname{round}(\log_2\rho_i)
\]

이 축은 학습 시에만 teacher와 crop 연산을 추가하고, 추론 시 제거할 수 있다는 장점이 있습니다. 다만 정확한 구현은 linked project의 저장 소스 원문이 직접 열리지 않아 확인이 필요합니다.

## 연구 축 B: UA-SAHI

UA-SAHI는 detector의 정확도만 높이는 모델 구조가 아니라 **추론 예산을 배분하는 router**입니다.

1. full-image inference 1회
2. P3/P4/P5 raw class logit 추출
3. 레벨별 확률지도 생성 및 P3 좌표계로 결합
4. UA로 구조 보존 업샘플링
5. 확률·불확실성·guard·coverage를 이용해 타일 선택
6. 선택 타일만 detector 실행
7. class-aware GreedyNMM으로 통합

성공 조건은 단순히 타일 호출 수가 줄어드는 것이 아닙니다. 다음을 동시에 만족해야 합니다.

- Tile Recall이 충분히 높아 중요 타일을 놓치지 않음
- Full SAHI 대비 AP/AP_S 하락이 허용 범위 이내
- UA TTO와 router 비용을 포함한 end-to-end latency가 실제로 감소
- 서로 다른 데이터셋과 detector에서도 같은 경향이 재현됨

## 두 축의 관계

두 연구 축은 결합 가능하지만 실험에서는 분리해야 합니다.

| 층위 | Survival/TOSD + RPST | UA-SAHI |
|---|---|---|
| 목적 | tiny object 표현 자체 개선 | 고해상도 타일 추론 예산 절감 |
| 적용 시점 | 주로 학습, 일부 모듈은 추론에 잔존 | 추론 시 router와 slicing |
| detector checkpoint | 재학습 필요 | 기존 checkpoint 재사용 가능 |
| 주요 비용 | 학습 복잡도, TOSD 추론 비용 | full-image pass, UA TTO, 선택 타일 추론 |
| 핵심 지표 | mAP50, mAP50-95, 크기별 AP | AP_S, Tile Recall, 호출 수, latency |

공정한 ablation은 다음 순서가 적합합니다.

1. 동일 detector의 Full Image
2. 동일 detector의 Full SAHI
3. 동일 detector의 budget-only SAHI (단순 점수/균등 선택)
4. 동일 detector의 UA-SAHI
5. Survival/RPST로 학습된 detector의 Full Image와 Full SAHI
6. Survival/RPST detector + UA-SAHI

이렇게 해야 정확도 개선이 학습 구조에서 왔는지, 타일 라우팅에서 왔는지 분리할 수 있습니다.

## 현재 신뢰 가능한 결론

1. AI-TOD에서는 A3 Full이 접근 가능한 요약의 모든 핵심 지표에서 최고입니다.
2. VEDAI와 DIOR에서는 지표별 최적 구성이 달라 A3의 보편적 우월성은 입증되지 않았습니다.
3. UA-SAHI는 9개 타일 중 5개만 선택하면 detector 호출 수를 10회에서 6회로 줄일 수 있지만, 실제 latency 개선은 아직 측정 결과가 아닙니다.
4. YOLOv8s는 좋은 재현 기준선이지만, YOLO11s와 RTMDet-s를 포함한 동일 조건 비교 없이 최적이라고 할 수 없습니다.
5. 최신 Ultralytics 계열에서는 objectness가 별도 branch가 아닐 수 있으므로 raw class logits 기반 확률지도 정의가 필요합니다.

## 가장 큰 위험 요소

### 1. 구성 정의가 불명확함

A0~A3의 정확한 코드 diff가 없으면 실험을 재현하거나 기여도를 설명할 수 없습니다. 각 구성은 YAML과 commit으로 고정해야 합니다.

### 2. 0.x%p 개선의 통계적 의미

작은 mAP 차이는 seed, 데이터 순서, NMS 설정, checkpoint 선택만으로 바뀔 수 있습니다. 반복 실험의 평균·표준편차가 필요합니다.

### 3. UA TTO가 절약 시간을 상쇄할 가능성

UA가 영상마다 최적화되므로, detector 호출을 줄여도 전체 추론이 느려질 수 있습니다. GPU 동기화와 warm-up을 포함한 종단간 측정이 필요합니다.

### 4. 라이선스

Ultralytics의 AGPL-3.0과 라이선스가 명확하지 않은 UA 코드를 한 저장소에 복제하면 공개·배포 방식에 제약이 생길 수 있습니다.

### 5. 서로 다른 연구 주장 혼합

모델 학습 기여와 inference router 기여를 한 표에서 섞으면 무엇이 성능을 만든 것인지 불명확해집니다. 논문 구조에서도 기여와 ablation을 분리해야 합니다.

## 구현 전 체크리스트

- [ ] A0~A3의 정확한 구조와 loss를 코드/YAML로 확정
- [ ] 데이터셋 분할과 전처리 스크립트 고정
- [ ] detector, SAHI, UA commit과 라이선스 기록
- [ ] YOLOv8s와 YOLO11s 동일 조건 기준선 측정
- [ ] Full Image, Full SAHI, budget-only, UA-SAHI 비교
- [ ] Tile Recall@0.50과 타일 선택 recall 측정
- [ ] AP_S, 전체 AP, 호출 수, VRAM, 종단간 latency 동시 기록
- [ ] UA 10/25/50 step과 조기 종료 ablation
- [ ] 최소 3개 seed 반복 및 평균·표준편차 보고
- [ ] 논문 표의 수치와 본문 서술 자동 검증

## 권장 다음 단계

첫 구현 단계는 거대한 통합보다 **재현 가능한 얇은 vertical slice**가 적합합니다.

1. YOLOv8s 또는 YOLO11s checkpoint 하나를 고정합니다.
2. DIOR 이미지 한 장에서 P3/P4/P5 raw class probability map을 저장합니다.
3. 표준 SAHI가 만드는 9개 타일과 GT 기반 중요 타일을 시각화합니다.
4. 단순 TopMean router로 Tile Recall을 측정합니다.
5. UA를 추가하고 단순 bilinear/bicubic 대비 Tile Recall과 오버헤드를 비교합니다.
6. 그 다음에만 전체 데이터셋 AP와 latency 실험으로 확장합니다.

이 순서라면 UA가 정말 타일 선택을 개선하는지 먼저 검증한 뒤, 학습 구조와 대규모 실험으로 넘어갈 수 있습니다.
