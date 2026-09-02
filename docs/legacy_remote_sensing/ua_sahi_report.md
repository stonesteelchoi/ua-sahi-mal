# UA-SAHI 베이스 코드와 모델 선정 요약

출처: ChatGPT 프로젝트 대화 `YOLOv8s 업샘플링 SAHI 보고서` (`6a8bf8ef-443c-83ee-bc80-5e574dcf38cf`)

## 1. 연구안의 핵심

연구안은 모든 SAHI 타일을 무조건 검출하지 않습니다. 먼저 전체 영상을 한 번 검출해 P3/P4/P5의 dense class probability map을 얻고, 이 저해상도 확률지도를 Upsample Anything으로 원영상 구조에 맞게 업샘플링합니다. 이후 확률과 불확실성에 따라 타일 우선순위를 매기고, 정해진 예산 안에서 선택된 타일만 고해상도 검출합니다.

```text
원본 영상
  └─ full-image detector 1회
       ├─ 일반 검출 결과
       └─ P3/P4/P5 raw class logits
            └─ 저해상도 확률지도 P_lr
                 └─ UA 구조 보존 업샘플링
                      └─ P_hr + foreground uncertainty
                           └─ 타일 점수·guard·coverage 정책
                                └─ 선택된 K개 SAHI 타일만 검출
                                     └─ 좌표 복원 + class-aware GreedyNMM
```

목표는 detector 자체의 학습 가중치를 바꾸는 것이 아니라, **어떤 타일에 detector 호출 예산을 쓸지 더 잘 결정하는 것**입니다.

## 2. 권장 코드 베이스

하나의 저장소를 통째로 포크하기보다 팀 전용 통합 저장소를 만들고, 공식 구현을 고정 의존성으로 조합하는 구조가 적합합니다.

| 역할 | 권장 저장소 | 적용 방식 |
|---|---|---|
| 슬라이싱·좌표 이동·병합 | `obss/sahi` | 라이브러리 의존성 |
| 검출기·학습·raw logit | `ultralytics/ultralytics` | 고정 버전 패키지와 얇은 wrapper |
| 구조 보존 업샘플링 | `seominseok0429/Upsample-Anything_Pytorch` | 최소 wrapper, 내부 코드 복제 최소화 |
| xView 절차 참고 | `fcakyon/small-object-detection-benchmark` | 평가 프로토콜 참고 |

SAHI는 슬라이스 생성, 모델 adapter, 원영상 좌표 복원, NMS/NMM/GreedyNMM을 분리해 제공하므로 통합 엔진으로 적합합니다. 프로젝트 보고서는 SAHI 0.12.6을 신규 기준선 후보로 제시하지만, 이미 0.12.1 결과가 있다면 논문 중간에 버전을 섞지 말아야 합니다.

## 3. UA의 “가중치”와 학습 여부

UA는 데이터셋 전체를 대상으로 별도 supervised training을 하지 않지만, 영상마다 test-time optimization(TTO)을 수행합니다. 따라서 `training-free`라고 단정하기보다는 `router-training-free` 또는 “데이터셋 수준 라우터 학습이 없음”이라고 표현하는 것이 정확합니다.

영상별 파라미터는 다음과 같은 공간·색상 커널 파라미터입니다.

\[
\phi_I = \{\sigma_x, \sigma_y, \theta, \sigma_r\}
\]

고해상도 위치 \(p\)와 저해상도 이웃 \(q\) 사이의 공간 가중치는 회전된 비등방성 Gaussian으로 계산합니다.

\[
w_s(p,q)=\exp\left[-\frac{1}{2}\left(\frac{{d'_x}^2}{\sigma_{x,q}^2}+\frac{{d'_y}^2}{\sigma_{y,q}^2}\right)\right]
\]

RGB 차이에 따른 range 가중치는 다음과 같습니다.

\[
w_r(p,q)=\exp\left[-\frac{\lVert I_{hr}(p)-I_{lr}(q)\rVert_2^2}{2\sigma_{r,q}^2}\right]
\]

정규화된 혼합 가중치와 업샘플된 확률지도는 다음처럼 계산합니다.

\[
\alpha_{pq}=\frac{w_s(p,q)w_r(p,q)}{\sum_{k\in\mathcal N(p)} w_s(p,k)w_r(p,k)}
\]

\[
P_{hr}(p)=\sum_{q\in\mathcal N(p)}\alpha_{pq}P_{lr}(q)
\]

핵심 성질:

- detector checkpoint를 변경하지 않습니다.
- 객체 라벨을 사용하지 않습니다.
- RGB 복원으로 찾은 구조 가중치를 확률지도에 재사용합니다.
- coarse probability map에서 이미 완전히 사라진 객체 신호를 새로 생성할 수는 없습니다.
- 공개 구현의 CUDA·정수 배율 가정, 영상별 최적화 비용, 직사각형 영상과 padding 처리를 wrapper에서 보완해야 합니다.

권장 wrapper 옵션은 `device`, 직사각형 입력, padding/unpadding, 10/25/50 TTO step, AMP, 조기 종료입니다.

## 4. SAHI의 “가중치”

표준 SAHI에는 학습되는 타일 가중치가 없습니다.

1. 슬라이스 크기와 overlap으로 후보 창을 기하학적으로 만듭니다.
2. 모든 창에 동일한 detector checkpoint를 적용합니다.
3. 각 결과를 슬라이스 offset만큼 이동해 원영상 좌표로 복원합니다.
4. 겹치는 결과를 NMS, NMM 또는 GreedyNMM으로 결합합니다.

GreedyNMM은 높은 confidence 예측을 keeper로 두고 IoU 또는 IoS가 임계값보다 큰 박스를 병합합니다. 기본 동작을 “confidence 가중 좌표 평균”으로 설명하면 부정확합니다. 보고서가 제안하는 권장 후처리는 `class-aware GreedyNMM`, match metric `IOS`, threshold `0.5`입니다.

UA-SAHI가 추가하는 값은 모델 가중치가 아니라 타일 우선순위 점수입니다.

\[
S_i = \operatorname{TopMean}_q(P_{hr}|w_i) + \lambda_u\operatorname{TopMean}_q(H_{fg}|w_i)
\]

여기에 다음 정책을 결합합니다.

- 낮은 threshold 이상의 full-image box가 포함된 창 보호
- 전체 예산 일부를 공간 coverage용으로 예약
- 남은 예산을 \(S_i\) 순위에 따라 할당
- 최종 선택 수 \(K=\lceil BN\rceil\)

\(\lambda_u\), coverage 비율, guard threshold는 학습 가중치가 아니라 validation set에서 고정할 하이퍼파라미터입니다.

## 5. YOLOv8s 모델 판단

YOLOv8s는 재현성과 구현 난이도 측면에서 좋은 기준선이지만, 현재의 절대적인 최적 모델로 주장하면 안 됩니다.

| 모델 | 공식 COCO AP50:95 참고값 | Params | FLOPs | 권장 역할 |
|---|---:|---:|---:|---|
| YOLOv8s | 44.9 | 약 11.2M | 약 28.6B | 재현 기준선 |
| YOLO11s | 47.0 | 약 9.4M | 약 21.5B | 주 모델 1차 후보 |
| RTMDet-s | 44.6 | 8.89M | 14.8G | 타 프레임워크 일반화 검증 |

권장 역할 분담은 다음과 같습니다.

- 주 모델 1차 후보: YOLO11s
- 재현 기준선: YOLOv8s
- detector portability 검증: RTMDet-s

다만 COCO 순위가 DIOR·AI-TOD·VEDAI에서 유지된다는 보장은 없습니다. 동일 조건에서 `Full Image AP_S`, `SAHI-100 AP_S`, 타일 1회 latency, raw map의 `Tile Recall@0.50`을 비교한 뒤 고정해야 합니다. AP 차이가 0.5%p 이내라면 더 빠르고 안정적인 모델을 선택하는 규칙이 합리적입니다.

## 6. DIOR 계산량 예시

`800×800` 영상, `400×400` 창, 20% overlap이면 축마다 3개, 총 9개 타일이 생성됩니다. 예산 \(B=0.5\)이면:

\[
K=\lceil9\times0.5\rceil=5
\]

- 타일 detector 호출: 9회 → 5회, 44.4% 감소
- full-image 호출을 포함한 총 detector 호출: 10회 → 6회, 40.0% 감소

호출 횟수 감소가 실제 지연시간 감소로 이어지려면 UA와 router 오버헤드가 절약된 타일 추론 시간보다 작아야 합니다.

\[
T_{UA}+T_{router}<4T_{slice}
\]

종단간 지연시간 25% 감소를 목표로 하면 더 엄격하게:

\[
T_{UA}+T_{router}\le1.75T_{slice}-0.25(T_{FI}+T_{merge})
\]

따라서 UA를 원영상 크기에서 무조건 50 step 실행하기보다는 256 또는 512 라우팅 좌표계, 10/25/50 step 비교, 수렴 기반 조기 종료를 실험해야 합니다.

## 7. 구현에서 반드시 지켜야 할 경계

Ultralytics의 최신 Detect head는 별도 objectness branch가 없는 구성이므로, `objectness × class`라는 구형 설명을 그대로 사용하면 안 됩니다. 각 레벨의 class logit에서 다음 확률지도를 만드는 편이 정확합니다.

\[
P_l(u,v)=\max_c\sigma(z_{l,c}(u,v)/T_l)
\]

\[
P_{lr}=\max_l \operatorname{Resize}_{l\rightarrow P3}(P_l)
\]

고수준 `YOLO.predict()`의 NMS 후 결과가 아니라, Detect head의 NMS 전 raw class logits을 hook으로 얻어야 합니다. 이 코드는 Ultralytics 내부 파일을 직접 수정하기보다 `ultralytics_dense.py` 같은 별도 adapter로 격리해야 버전 고정과 테스트가 쉬워집니다.

권장 모듈 경계:

```text
src/
  detectors/
    ultralytics_dense.py
    rtm_det_adapter.py
  upsampling/
    ua_wrapper.py
  routing/
    probability_map.py
    tile_scoring.py
    budget_selector.py
  slicing/
    sahi_adapter.py
  merging/
    postprocess.py
  evaluation/
    metrics.py
    latency.py
```

## 8. 라이선스 주의

- SAHI: MIT
- Ultralytics: AGPL-3.0
- MMDetection/RTMDet: Apache-2.0
- 공개 UA 저장소: 프로젝트 대화 기준 명시적 LICENSE 미확인

UA 코드를 저장소에 복제하기 전에 재배포 허용 범위를 확인해야 합니다. 초기에는 commit을 고정한 외부 의존성 또는 별도 설치 단계로 참조하는 편이 안전합니다.

## 결론

현재 가장 재현 가능한 조합은 다음과 같습니다.

```text
SAHI 0.12.6
+ YOLO11s 주 모델 후보
+ YOLOv8s 재현 기준선
+ Upsample Anything 최소 wrapper
+ class-aware GreedyNMM (IOS 0.5)
```

일정이나 팀 숙련도로 YOLOv8s를 주 모델로 선택할 수는 있지만, 논문에는 “최적 모델”보다 “재현성과 계산비용을 고려해 고정한 기준 검출기”라고 쓰는 것이 맞습니다.
