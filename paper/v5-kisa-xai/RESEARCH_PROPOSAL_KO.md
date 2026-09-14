# 개인 프로젝트 연구 계획서

**연구자:** 최석철
**프로토콜 식별자:** `KISA-XAI-V5.0-DRAFT`
**작성일:** 2026년 9월 14일
**상태:** 데이터 접근 전 연구 설계
**투고 목표:** 2026 한국국방기술학회 추계학술대회
**행사 일정:** 2026년 10월 28일–30일, 신협제주연수원
**투고 마감:** 공식 모집 공지에서 재확인 필요

## 1. 연구 주제

### 1.1 논문 제목

**국문 제목**

> 정확도를 넘어 설명의 신뢰성으로: 정적 PE 악성코드 탐지기의 구조 정합 XAI와
> 교차연도 외부 평가

**영문 제목**

> Beyond Accuracy: Structure-Mapped XAI with Cross-Year External Evaluation for Static PE Malware Detection

외부 연도 평가를 완료하지 못하면 제목에서 `교차연도 외부 평가`를 삭제하고 다음의
축소 제목을 사용한다.

> 정적 PE 악성코드 탐지기의 구조 정합 및 예산 기반 XAI 충실성 평가

### 1.2 연구의 한 문장 정의

본 연구는 KISA 원본 정상·악성파일로 학습한 정적 PE 이미지 분류기의 Grad-CAM 상위
구간이 동일 바이트 예산의 대조 구간보다 악성 판정에 더 필요하고 충분한지를 실제
재추론으로 검증하고, 해당 구간의 PE 구조 분포와 다른 연도 데이터셋에서의 재현성을
평가한다.

### 1.3 논문 유형

본 연구는 새로운 악성코드 탐지 모델을 제안하는 논문이 아니라, **정적 PE 탐지기의
설명 충실성, 구조 정합성 및 외부 일반화를 검증하는 평가 중심 소논문**이다. Grad-CAM
자체의 적용이나 높은 분류 정확도를 신규 기법으로 주장하지 않는다.

## 2. 연구 개요

### 2.1 연구 배경

악성코드 바이트를 이미지로 변환하고 합성곱 신경망으로 분류하는 접근은 별도의 수동
특징 설계 없이도 파일의 전역적 패턴을 학습할 수 있다는 장점이 있다(Nataraj et al.,
2011). 또한 원시 실행파일을 직접 입력으로 사용하는 정적 탐지 모델은 특징 추출기의
가정에서 벗어난 표현 학습 가능성을 보여주었다(Raff et al., 2018). 그러나 높은 분류
정확도만으로 모델이 악성 행위와 관련된 위치를 사용했다고 결론 내릴 수는 없다.

Grad-CAM은 목표 클래스 점수에 대한 합성곱 특징맵의 기울기를 이용하여 입력 영역의
상대적 기여도를 시각화한다(Selvaraju et al., 2017). 이 방법으로 생성한 히트맵은 모델이
사용한 후보 영역을 보여주지만, 위치 정답이나 개입 실험 없이 실제 악성 코드의 위치를
보증하지 않는다. 특히 PE 이미지에서는 파일 선두, 파일 크기, section 배열, 패커,
padding, 인증서, overlay와 같은 구조적 요인이 라벨과 우연히 결합될 수 있다. 따라서
선명한 히트맵을 제시하는 정성적 사례만으로는 설명 가능성이나 분석 유용성을 입증할 수
없다.

KISA의 `KISA_CISC2017_datachallenge_Malwares.01`은 공식 페이지상 7,500개씩 두 세트,
총 15,000개의 정상·악성 원본 파일과 이진 정답지로 구성되어 있다. 실제 archive가 해당
설명과 일치한다면, 원본 PE의 file offset, RVA, section 및 overlay를 직접 계산하고
이미지 설명을 원본 파일 구간으로 투영할 수 있다. 이는 PNG만 제공하는 이미지
데이터셋이나 원본 파일이 아닌 byte dump보다 구조 정합 분석에 적합하다.

### 2.2 문제 정의

본 연구가 해결하려는 문제는 다음과 같다.

1. 파일 단위 정상·악성 라벨만 있는 상황에서 모델이 사용한 입력 구간을 어떻게
   제한된 바이트 예산으로 요약할 것인가?
2. 선택된 구간이 단순히 시각적으로 두드러진 위치가 아니라 모델의 악성 판정에 실제로
   필요하거나 충분하다는 것을 어떻게 검증할 것인가?
3. 파일 선두, 엔트로피, PE 구조 크기와 같은 값싼 지름길이 Grad-CAM의 효과로 오인되는
   것을 어떻게 통제할 것인가?
4. 한 연도의 KISA 데이터에서 관찰된 분류 및 설명 효과가 다른 연도 데이터셋에서도
   유지되는지 어떻게 평가할 것인가?

### 2.3 연구 목적

본 연구의 목적은 다음 네 가지이다.

1. 원본 PE 바이트와 224×224 이미지 픽셀 사이의 half-open file-offset interval을
   보존하는 결정론적 변환기를 구축한다.
2. 8GB VRAM 환경에서 실행 가능한 ResNet-18 이진 탐지기를 학습하고, 분류 성능과
   calibration을 함께 측정한다.
3. Grad-CAM 상위 영역을 source-byte 예산으로 변환한 뒤 deletion과 keep-only 재추론을
   수행하여 설명의 필요성과 충분성을 정량화한다.
4. 구조 일치 대조군과 교차연도 외부 평가를 통해 설명 효과가 위치·구조·데이터셋 표식에
   의존하는지 검증한다.

### 2.4 연구의 필요성

가. **정성적 XAI의 한계 보완:** 붉은 히트맵 사례만으로는 설명이 모델 결정에 충실한지
판단할 수 없으므로 실제 입력 개입과 재추론이 필요하다.

나. **원본 좌표 보존:** 분석가가 검토할 수 있는 단위는 이미지 픽셀이 아니라 파일
오프셋과 PE 구조이므로, 이미지 생성 단계에서 원본 위치로의 역투영 계약을 보존해야 한다.

다. **지름길 편향 통제:** 정상·악성 데이터의 파일 형식, 크기, 패커, 서명, source 및
dataset marker가 다르면 높은 정확도가 악성 의미의 학습을 나타내지 않을 수 있다.

라. **외부 재현성 평가:** 단일 데이터셋의 임의 분할 성능만으로 배포 환경의 변화를
대표할 수 없으므로, 독립적인 연도 데이터셋에서 분류와 설명의 효과 방향을 다시 확인할
필요가 있다(Anderson & Roth, 2018; Yang et al., 2021).

### 2.5 연구 질문

- **RQ1 — 탐지 성능:** group-stratified 내부 test에서 ResNet-18은 단순 다수 클래스,
  파일 크기·PE 메타데이터 및 byte-histogram 기준선보다 정상·악성 탐지를 안정적으로
  수행하는가?
- **RQ2 — 설명 필요성:** 악성 파일의 Grad-CAM 상위 10% source-byte 구간을 제거했을
  때 악성 클래스 NLL 증가와 확률 감소가 동일 예산의 matched random보다 큰가?
- **RQ3 — 설명 충분성:** Grad-CAM 상위 10% source-byte 구간만 보존했을 때 악성 클래스
  점수와 예측 유지율이 matched random보다 높은가?
- **RQ4 — 구조 및 지름길:** Grad-CAM 질량과 선택 구간은 PE header, executable section,
  non-executable section, certificate 및 overlay 중 어디에 집중되며, 위치·엔트로피·파일
  크기·패커를 통제한 뒤에도 설명 효과가 유지되는가?
- **RQ5 — 교차연도 외부 평가:** KISA 2017에서 동결한 모델·설명 설정의 분류 성능과
  Grad-CAM 대 matched-random 효과 방향이 KISA 2018 라벨 보유 PE 부분집합에서도
  유지되는가?

### 2.6 사전 가설과 성공 게이트

주 설명 예산은 원본 파일 길이의 10%로 고정한다.

- **H1:** Grad-CAM top-10%의 deletion `ΔNLL`은 matched random top-10%보다 크다.
- **H2:** Grad-CAM top-10% keep-only의 악성 클래스 점수는 matched random top-10%보다
  높다.
- **H3:** H1과 H2의 효과 방향은 외부 연도 데이터에서도 유지된다.

H1과 H2는 파일 또는 근접 변종 group 단위 paired bootstrap 2,000회로 95% 신뢰구간을
계산하고 Holm 보정을 적용한다. 두 가설이 모두 통과할 때만 `충실한 악성 판정 근거
후보`라고 표현한다. H1만 통과하면 필요성, H2만 통과하면 충분성만 주장한다. 두 가설이
모두 실패하면 연구를 Grad-CAM 설명의 한계 또는 데이터셋 지름길 평가로 마무리한다.

## 3. 연구 방법

### 3.1 데이터셋 구성

#### 3.1.1 주 데이터

주 데이터 후보는 KISA 대용량 정상/악성파일 I
`KISA_CISC2017_datachallenge_Malwares.01`이다. 공식 설명은 다음 정보를 제공한다.

- 총 15,000개, 두 세트 각 7,500개
- 정상·악성 원본 파일
- MD5 형태의 파일명과 정상 `0`, 악성 `1`의 정답지
- 총 파일 크기 약 6.733GB

위 수치는 공개 페이지의 설명이며 실제 archive의 파일 수, 클래스 비율, 파일 형식,
중복률 및 손상률은 아직 검증되지 않았다. 실제 manifest 감사가 끝날 때까지 `주 데이터
후보` 상태를 유지한다.

#### 3.1.2 외부 평가 데이터

우선 외부 평가 후보는 KISA 대용량 정상/악성파일 III
`KISA-datachallenge2018-Malwares.03`의 라벨 보유 세트이다. 공식 설명상 10,000개씩
5세트이고 앞의 세 세트에는 라벨이 제공된다. 모든 파일 끝에 `KISA` 4바이트가 추가된
것으로 설명되므로 다음 감사를 통과한 PE만 사용한다.

1. suffix의 실제 바이트, 위치 및 전 파일 적용 여부 확인
2. suffix 제거 전·후 SHA-256과 파일 길이 기록
3. 제거 전·후 PE parser 결과 비교
4. suffix 포함·제거 민감도 분석
5. KISA 2017과의 exact 및 near-duplicate 제거

KISA 2017을 확보하지 못하고 2018 라벨 세트만 확보하면, 2018을 주 데이터로 전환하고
KISA 2019의 라벨 보유 PE 부분집합을 외부 평가 후보로 사용한다. 2019 자료에는 HTML,
HWP 등 비 PE 형식이 섞인 것으로 설명되어 있으므로 PE32/PE32+만 별도 선별한다.

#### 3.1.3 기존 보유 자료의 역할

| 자료 | v5에서의 역할 | 제외되는 용도 |
|---|---|---|
| SOREL-20M disarmed 300건 파일럿 | PEAtlas file-offset/RVA/pixel 왕복과 parser 회귀 검사 | KISA 탐지 성능·XAI 효과 추정 |
| BIG2015 파생 코퍼스 | 이미지 변환 및 결과 저장 코드의 비악성 회귀 확인 | KISA 이진 라벨과 결합, 외부 test 대체 |
| MaleVis 224/300 | 사용하지 않음 | 원본 PE 구조 또는 교차연도 검증 주장 |
| 과거 v1–v4 결과 | 연구 이력과 실패 분석 | v5 결과표 또는 통계에 이월 |

### 3.2 데이터 접근 Go/No-Go

실험 전에 다음 조건을 모두 확인한다.

1. 연구 이용과 논문 통계·파생 그림 공개 조건이 문서로 확인된다.
2. archive와 label 파일이 정상적으로 열리고 source archive SHA-256을 기록한다.
3. label과 파일의 결합률이 99% 이상이며 불일치 항목을 별도 목록으로 보존한다.
4. exact duplicate 제거 후 정상과 악성에 각각 최소 1,000개의 parseable PE가 남는다.
5. PE32/PE32+, parser failure, 파일 크기와 dataset marker만으로 라벨을 거의 완벽하게
   예측하는 회복 불가능한 confounder가 없다.
6. exact 또는 near-duplicate group 단위 분할을 구성할 수 있다.

이 조건을 통과하지 못하면 test 결과를 만들지 않는다. 2017 접근만 실패하면 2018 라벨
세트로 같은 감사를 반복할 수 있으나, 서로 다른 데이터셋을 편의에 따라 합쳐 sample 수를
늘리지 않는다.

### 3.3 안전한 취급과 재현성

KISA 원본은 실행 가능한 악성파일일 수 있으므로 실행, 동적 분석 및 일반 사용자
디렉터리 저장을 수행하지 않는다. 전용 비동기화 저장 위치에서 read-only 정적 파싱만
수행한다. Git에는 원본 파일, 복원이 가능한 byte image, archive, checkpoint를 커밋하지
않고 다음 비민감 산출물만 저장한다.

- 데이터셋 revision과 집계 수치
- 익명 sample ID와 split group ID
- source 및 파생 산출물의 hash
- parser 성공 여부와 제외 사유
- 재현 가능한 설정 파일과 코드 revision
- 원본 바이트를 복원할 수 없는 집계 표·그림

### 3.4 PE 선별과 누수 통제

1. 모든 파일에 SHA-256을 새로 계산하고 원래 MD5 filename과 분리해 기록한다.
2. magic, PEAtlas 및 독립 parser가 모두 PE32 또는 PE32+로 인정한 파일만 주 실험에
   포함한다.
3. exact SHA-256 중복을 제거한다.
4. import hash, section별 hash, 파일 크기 및 fuzzy similarity를 사용하여 근접 변종
   graph를 만들고 connected component를 하나의 source group으로 취급한다.
5. 하나의 group은 train, validation, internal test 중 한 split에만 배치한다.
6. 정상·악성별 file type, 크기, architecture, section 수, executable-section 비율,
   overlay 비율, 인증서, packer, compiler 및 parser success를 비교한다.
7. 파일 크기와 위 메타데이터만 입력한 logistic baseline을 학습한다. 이 기준선의
   AUROC가 0.90 이상이면 지름길 원인을 분석하고, matching 또는 stratification으로
   완화하지 못할 경우 의미 기반 탐지 주장을 포기한다.

내부 split은 group-stratified 70/15/15를 기본으로 한다. validation에서 모델, target
layer, fill 및 조기종료 epoch를 선택한 뒤 internal test를 한 번만 연다. 외부 연도
데이터는 내부 test 분석까지 끝난 뒤 한 번 평가한다.

### 3.5 이미지 표현과 좌표 매핑

주 표현은 원본 파일 전체를 224×224 grayscale로 변환하는 `interval-binned-v1`이다.
출력 픽셀 수를 `P=50,176`, 원본 파일 길이를 `L`이라고 할 때 각 row-major 픽셀은 원본의
연속 half-open 구간에 대응한다.

- `L ≥ P`: 파일을 P개의 연속 구간으로 나누고 각 구간 바이트 평균을 픽셀값으로 사용한다.
- `L < P`: 최근접 반복 방식으로 원본 바이트를 P개 위치에 배치하고 각 픽셀이 가리키는
  원본 바이트 구간을 기록한다.
- 각 sample에 pixel-to-file-offset interval map과 representation version을 저장한다.
- CAM 픽셀을 원본으로 투영할 때 중복 구간의 합집합을 계산하고, 고유 source byte 수가
  예산에 도달할 때까지 선택한다.

이 표현은 원본 바이트를 손실 없이 복원하는 형식이 아니다. 그러나 각 모델 입력 위치가
어느 원본 구간에서 계산되었는지 추적할 수 있으므로 구조 정합과 예산 평가가 가능하다.
논문에서는 이를 `정확한 바이트 복원`이 아니라 `결정론적 file-offset interval 투영`으로
표현한다.

horizontal/vertical flip, rotation, random crop, color jitter는 바이트 순서 또는 값을
바꾸므로 사용하지 않는다. 입력 정규화와 channel 구성은 validation pilot에서 결정하고
test 전에 동결한다.

### 3.6 PE 구조 지도

Microsoft PE 형식 정의에 따라 다음 file-offset 영역을 half-open interval로 기록한다
(Microsoft, 2025).

- DOS header와 stub
- PE/COFF header와 optional header
- section table
- executable section
- non-executable section
- resource-like section
- certificate table
- overlay
- parser가 구조를 확정하지 못한 구간

section 이름만으로 의미를 결정하지 않고 characteristics flag와 raw offset을 우선한다.
인증서 table은 RVA가 아닌 file pointer를 사용한다는 점을 별도 처리한다. 교차 parser의
경계가 다르면 sample을 숨기지 않고 disagreement 유형과 비율을 보고한다.

### 3.7 탐지 모델과 기준선

주 모델은 ResNet-18이다. ResNet-50을 필수 비교로 두지 않는다. 8GB VRAM에서 AMP를
사용하고 짧은 pilot으로 peak VRAM을 측정하여 최소 10% 여유가 남는 batch size를
선택한다.

| 모델 | 역할 | 선택 기준 |
|---|---|---|
| Majority predictor | 최저 분류 기준선 | 고정 |
| 파일 크기·PE metadata logistic model | 지름길 감사 | 고정 |
| 256-bin byte histogram logistic model | 값싼 콘텐츠 기준선 | 고정 |
| ResNet-18 | 주 비전 모델 | validation macro-F1 |
| ResNet-18 random initialization | pretraining ablation | 자원 허용 시 |

optimizer는 AdamW, loss는 binary cross-entropy 또는 2-class cross-entropy 중 구현과 CAM
호환성이 단순한 하나로 동결한다. seed는 42, 43, 44를 사용한다. class imbalance가
확인되면 train split에서만 class weight를 계산한다. test threshold는 validation에서
Youden 기준 또는 macro-F1 기준 중 하나로 정하고 변경 이력을 기록한다.

분류 sanity gate는 다음과 같다.

- validation macro-F1이 majority baseline보다 최소 0.10 높음
- validation balanced accuracy가 0.70 이상
- 정상·악성 두 클래스 recall이 모두 0.60 이상
- 세 seed의 효과 방향이 일치하며 한 seed의 붕괴를 평균으로 숨기지 않음

### 3.8 Grad-CAM과 예산 구간

Grad-CAM은 ResNet-18의 마지막 convolution block에서 계산한다. 주 분석은 모든 malicious
test 파일에 대한 malicious-class logit을 사용하며, 오분류 파일을 제외하지 않는다.
정확히 탐지된 악성 파일만의 결과는 secondary로 분리한다. benign-class 설명은 동일한
구조 지름길이 양쪽 클래스에서 나타나는지 확인하는 진단 분석으로 보고한다.

예산은 원본 파일의 고유 source byte 수를 기준으로 `{5%, 10%, 20%, 40%}`로 구성하고,
10%를 primary로 고정한다. CAM score가 높은 이미지 위치를 원본 interval로 투영한 뒤
중복을 제거하면서 예산을 채운다. 연결요소와 박스는 시각화에만 사용하고, 모든 통계는
file-offset interval mask에서 계산한다.

하나의 이미지 픽셀이 여러 source byte를 대표하므로 마지막 interval에서 요청 예산을
소폭 초과할 수 있다. 요청 예산과 실제 선택 바이트 비율을 모두 기록하고, 각 대조군은
같은 파일에서 Grad-CAM이 실제로 선택한 고유 바이트 수에 맞춘다.

### 3.9 대조 선택기

모든 대조군은 Grad-CAM과 동일한 source-byte 예산을 사용한다.

1. **Uniform random:** 유효 file offset에서 균등 표집하며 파일당 최소 20회 반복한다.
2. **Front-position:** 파일 선두부터 동일 바이트 수를 선택한다.
3. **Entropy:** 고엔트로피 구간부터 동일 바이트 수를 선택한다.
4. **Structure-matched random:** Grad-CAM이 선택한 각 구조 영역의 바이트 수를 유지한 채
   해당 영역 내부 위치를 무작위로 선택한다.
5. **Size/position diagnostic:** 파일 크기와 정규화 위치만으로 설명 효과를 예측하여
   Grad-CAM advantage가 구조적 선험에 의해 설명되는지 점검한다.

주 비교는 Grad-CAM 대 structure-matched random으로 한다. uniform random은 전체 위치
기준의 직관적 비교이며, front와 entropy는 기존의 값싼 지름길이 어느 정도 성능을 내는지
보여주는 보조 비교이다.

### 3.10 설명 충실성 평가

**Deletion necessity:** 선택 구간의 입력값을 대체하고 다시 추론한다.

```text
delta_nll = NLL(masked) - NLL(original)
delta_p_mal = p_mal(original) - p_mal(masked)
```

**Keep-only sufficiency:** 선택 구간만 유지하고 나머지를 같은 정책으로 대체한다.

```text
retained_p_mal = p_mal(keep_only) / max(p_mal(original), epsilon)
retained_prediction = argmax(keep_only) == malicious
```

perturbation artifact를 통제하기 위해 두 fill을 사용한다.

- primary: 같은 PE 구조 영역의 입력값 분포에서 뽑는 structure-conditioned resampling fill
- robustness: local median 또는 blur 기반 fill
- diagnostic only: zero fill

각 budget에서 실제로 재추론하여 deletion 및 keep-only AOPC를 계산한다. 개별 픽셀
효과를 합산하여 재추론을 대체하지 않는다.

### 3.11 설명 sanity와 안정성

1. 정상 학습 checkpoint, label-shuffled model, random-weight model의 CAM과 faithfulness를
   비교한다.
2. 동일 sample에 대한 세 seed CAM의 Spearman rank correlation과 top-10% source-byte
   IoU를 계산한다.
3. target layer를 test 결과에 맞추지 않는다.
4. 시각적으로 선명해도 randomized model과 차이가 없으면 설명으로 인정하지 않는다.

### 3.12 구조 정합 분석

각 구조 영역 `r`에 대해 다음 enrichment를 계산한다.

```text
enrichment(r) =
  (positive CAM mass in r / total positive CAM mass)
  /
  (source bytes in r / total source bytes)
```

header, executable section, non-executable section, certificate, overlay별 CAM mass,
선택 바이트 수와 enrichment를 보고한다. 악성·정상, packed·unpacked, signed·unsigned,
32·64비트 층을 분리한다. 구조 enrichment가 높다는 사실만으로 그 영역을 악성 코드라고
해석하지 않는다.

### 3.13 교차연도 외부 평가

KISA 2018 외부 PE에는 내부 validation에서 동결한 다음 항목을 그대로 적용한다.

- image representation과 normalization
- checkpoint와 decision threshold
- Grad-CAM target layer와 normalization
- source-byte budget과 tie-breaking
- fill과 대조 선택기
- 통계 코드

외부 데이터로 재학습하거나 threshold를 조정하지 않는다. challenge 연도와 실제 수집
시점이 같다는 근거가 없으면 결과를 `시간적 일반화`가 아니라 `교차연도 데이터셋 외부
평가`라고 표현한다.

### 3.14 평가 지표

**분류 지표**

- AUROC, AUPRC
- accuracy, macro-F1, balanced accuracy, MCC
- 정상·악성 precision, recall, F1
- NLL, Brier score, ECE
- confusion matrix

**설명 지표**

- deletion `ΔNLL`, `Δp_mal`, label-flip rate
- keep-only probability retention과 prediction retention
- 5–40% budget의 deletion/keep-only AOPC
- Grad-CAM과 각 대조군의 paired difference
- seed 간 CAM rank correlation과 source-byte IoU
- 구조별 CAM mass와 area-normalized enrichment

**비용 지표**

- 파일 parsing 및 이미지 변환 시간
- 분류 forward latency
- Grad-CAM forward/backward latency
- perturbation 재추론 시간
- peak VRAM과 sample당 저장량

분석가 수행시간을 측정하지 않으므로 `리버싱 시간 감소`는 결과 지표나 결론에 포함하지
않는다.

### 3.15 통계 분석

- 분석 단위는 파일이며, near-duplicate dependence가 남을 수 있으면 group cluster
  bootstrap을 사용한다.
- primary test는 10% budget의 H1과 H2 두 개이다.
- H1/H2의 p-value에는 Holm 보정을 적용하고 effect size, 95% CI, eligible n을 모두
  보고한다.
- random control은 파일당 20회 이상 반복하고 평균과 분산을 보존한다.
- 세 seed를 각각 보고하고 seed 평균을 별도로 제시한다.
- 전체 malicious test와 correctly detected subset을 모두 보고하되 전자를 primary로 둔다.
- 5%, 20%, 40%, 구조별·패커별 결과는 secondary 또는 exploratory로 표시한다.
- archive 감사 후 group 수와 validation 분산으로 최소 검출 가능 효과를 산출하고 test를
  열기 전에 power note를 동결한다.

## 4. 기대 효과와 기여도

### 4.1 결과 전 단계에서 정당화되는 기여

1. KISA 원본 PE의 이미지 픽셀을 file-offset interval 및 PE 구조로 투영하는 재현 가능한
   좌표 계약을 제시한다.
2. 악성코드 이미지 Grad-CAM을 같은 바이트 예산의 강한 대조군과 실제 재추론으로
   검증하는 설명 충실성 프로토콜을 제시한다.
3. 파일 형식·크기·위치·엔트로피·구조·suffix·근접 중복 지름길을 분리 감사한다.
4. 내부 분할의 성능과 다른 연도 데이터셋의 외부 성능을 분리하여 보고한다.
5. 긍정·부분·부정 결과를 모두 수용하는 사전 종료 규칙과 비민감 재현 산출물을 제공한다.

### 4.2 기대되는 실용적 가치

게이트를 통과하면 모델이 사용한 상위 10% 바이트 구간을 분석 시작점 후보로 제공할 수
있다. 이 결과는 자동 악성 구간 정답이 아니라 모델 판정 근거의 우선순위이며, 분석가가
PE section·overlay·header 중 어느 부분을 먼저 검토할지 결정하는 보조 정보로 사용할 수
있다. 실제 분석시간 단축 효과는 후속 사용자 연구에서 별도로 검증한다.

### 4.3 예상 문제점과 해결방안

| 예상 문제 | 연구 타당성에 미치는 영향 | 대응 및 종료 규칙 |
|---|---|---|
| KISA archive 또는 이용조건 미확보 | 실험 자체 불가 | 접근 gate를 최우선 수행; 확보 전 결과 주장 금지 |
| family·행위 위치 정답 없음 | semantic localization 불가 | `악성 판정 근거 후보`로 용어 제한; faithfulness만 검증 |
| 파일 형식·크기 shortcut | 높은 정확도의 의미 붕괴 | metadata baseline, matching, stratification; 완화 불가 시 bias paper로 전환 |
| 2018 `KISA` suffix | dataset marker 및 parser 교란 | 전수 검사, 제거 전후 hash, sensitivity 보고 |
| 근접 변종 누수 | 내부 test 과대평가 | exact/fuzzy group split과 cross-year dedup |
| Grad-CAM 저해상도 | 넓고 모호한 구간 | source-byte budget, occlusion diagnostic, 해상도 한계 명시 |
| deletion fill의 OOD | faithfulness 왜곡 | 두 fill의 효과 방향 합의 요구, zero fill은 진단 한정 |
| 외부 연도 성능 저하 | 강건성 주장 실패 | 실패를 그대로 보고하고 drift·shortcut 원인을 분석 |
| 일정 부족 | 외부 평가 또는 ablation 미완 | 최소 논문 범위를 내부 2017 실험으로 축소하고 제목 조정 |

## 5. 최소 실험 행렬

| 우선순위 | 데이터 | 모델/기준선 | 설명·대조 | seed | 목적 |
|---:|---|---|---|---:|---|
| P0 | KISA 2017 | 데이터·누수·구조 감사 | 해당 없음 | 해당 없음 | 사용 가능성 판정 |
| P1 | KISA 2017 internal | metadata logistic, byte histogram | 해당 없음 | 3 | shortcut 및 값싼 기준선 |
| P1 | KISA 2017 internal | ResNet-18 | Grad-CAM, uniform random, front, entropy, structure-matched random | 3 | 주 결과 |
| P1 | KISA 2017 internal | trained, label-shuffled, random-weight ResNet-18 | Grad-CAM | 1 이상 | explanation sanity |
| P2 | KISA 2018 labeled PE | 동결 ResNet-18 | 동결 설명 프로토콜 | 3 checkpoint | 교차연도 외부 평가 |
| P3 | KISA 2019 labeled PE | 동결 최종 모델 | Grad-CAM | 선택 | 추가 외부 robustness |

마감이 촉박하면 P0와 P1을 완료 조건으로 두고 P2를 제거한다. 이때 제목과 초록에서
교차연도·시간적 강건성 표현을 삭제한다. P0가 끝나지 않은 상태에서 P1을 시작하지 않는다.

## 6. 연구 일정

### 6.1 권장 4주 일정

| 단계 | 내용 | 기간 | 완료 기준 |
|---:|---|---|---|
| 1 | KISA 접근·이용조건·archive 확보 | 1–2일 | 접근 기록과 archive hash |
| 2 | 파일·라벨·PE·suffix·중복·shortcut 감사 | 3–4일 | Go/No-Go 보고서 |
| 3 | interval-binned 이미지와 PE 구조 map 생성 | 3일 | 왕복·교차 parser 검사 통과 |
| 4 | group split, baseline, ResNet-18 3-seed 학습 | 4–5일 | 분류 sanity gate 판정 |
| 5 | Grad-CAM, 대조군, deletion/keep-only 실행 | 4–5일 | per-sample 결과와 H1/H2 판정 |
| 6 | KISA 2018 외부 평가 | 2–3일 | 동결 모델 외부 결과 |
| 7 | 표·그림 생성, 원고 작성 및 수치 감사 | 3–4일 | 제출 패키지와 재현성 부록 |

### 6.2 2026년 9월 압축 일정

기존 계획서의 2026년 9월 23일 내부 제출 목표를 유지해야 할 경우 다음의 최소 범위로
진행한다. 공식 투고 마감은 별도로 재확인한다.

| 날짜 | 작업 | 중단 조건 |
|---|---|---|
| 9월 14–15일 | 접근조건과 KISA 2017 archive 확보 | 미확보 시 결과 논문 일정 재설정 |
| 9월 15–16일 | manifest, PE 비율, 중복, metadata shortcut 감사 | Go gate 실패 시 학습 금지 |
| 9월 16–17일 | 이미지·좌표·구조 map 생성 및 protocol 동결 | mapping 오류 미해결 시 중단 |
| 9월 17–19일 | 기준선과 ResNet-18 3-seed 학습 | sanity gate 실패 시 bias 분석으로 전환 |
| 9월 19–21일 | Grad-CAM, 대조군, deletion/keep-only | H1/H2 결과를 그대로 고정 |
| 9월 21–22일 | 내부 결과 표·그림 및 가능한 외부 pilot | 외부 미완료 시 제목 축소 |
| 9월 22–23일 | 원고·참고문헌·수치 대조와 제출본 생성 | 미검증 수치·예상 결과 삽입 금지 |

## 7. 논문 목차와 예정 산출물

### 7.1 논문 목차

1. 서론
2. 관련 연구
3. 데이터 감사와 문제 정의
4. 구조 매핑 이미지 표현 및 탐지 모델
5. 예산 기반 XAI 충실성 평가 방법
6. 실험 설정
7. 분류·설명·구조·외부 평가 결과
8. 타당성 위협과 논의
9. 결론

### 7.2 예정 표와 그림

| 번호 | 내용 | 생성 조건 |
|---|---|---|
| Figure 1 | 원본 PE→이미지→ResNet-18→Grad-CAM→file offset→재추론 파이프라인 | 설계 단계 |
| Figure 2 | 이미지 픽셀과 PE 구조 half-open interval의 대응 예시 | mapping 검사 후 |
| Figure 3 | budget별 deletion/keep-only 곡선 | 내부 test 후 |
| Figure 4 | PE 구조별 CAM mass와 enrichment | 구조 map 성공 표본 후 |
| Figure 5 | 내부·외부 분류 및 설명 효과 비교 | 외부 평가 완료 시 |
| Table 1 | 데이터 수, 라벨, PE 비율, 중복 및 제외 사유 | 데이터 감사 후 |
| Table 2 | 기준선과 ResNet-18 분류·calibration | 학습 후 |
| Table 3 | 10% budget의 H1/H2 paired effect와 CI | 설명 평가 후 |
| Table 4 | sanity, seed, fill, subgroup 결과 | robustness 후 |
| Table 5 | KISA 2018 외부 결과 | 외부 평가 완료 시 |

모든 표와 그림은 per-sample 결과에서 자동 생성한다. 결과 수치를 Word나 논문 본문에
수동 입력한 경우 원자료와의 자동 대조표를 함께 생성한다.

## 8. 결과별 마무리 규칙

| 관찰 결과 | 논문 결론 |
|---|---|
| H1·H2·sanity 통과, 외부 방향 유지 | 구조 매핑 가능한 충실한 악성 판정 근거 후보 평가 |
| H1·H2 통과, 외부 실패 | 단일 데이터셋에서만 유효한 설명과 교차연도 일반화 한계 |
| H1만 통과 | 선택 영역은 필요하지만 작은 요약으로 충분하지 않음 |
| H2만 통과 | 작은 영역이 정보를 보존하지만 제거 효과는 약함 |
| H1·H2 실패 | 시각적으로 그럴듯한 Grad-CAM의 충실성 한계 |
| metadata baseline이 비전 모델에 근접 | KISA 데이터셋 지름길 및 평가 편향 분석 |
| randomization sanity 실패 | Grad-CAM을 설명으로 해석하지 않고 방법 실패 보고 |

어떤 결과에서도 test 이후 budget, target layer, fill 또는 eligible subset을 변경해 성공
주장을 만들지 않는다. 사후 분석은 `KISA-XAI-V5.2-EXPLORATORY`로 분리한다.

## 9. 주장 범위

현재 계획으로 정당화할 수 있는 최대 주장은 다음과 같다.

> KISA 원본 PE 기반 정적 탐지기의 모델 귀속 구간을 file offset 및 PE 구조로 투영하고,
> 동일 바이트 예산의 대조군과 실제 재추론을 통해 그 필요성·충분성 및 교차 데이터셋
> 재현성을 평가한다.

다음 주장은 별도 근거 없이 사용하지 않는다.

1. Grad-CAM이 실제 악성 코드 위치를 찾았다.
2. 선택된 10% 구간만 분석하면 리버싱 시간이 단축된다.
3. 높은 내부 정확도가 미지의 악성코드에 대한 일반화를 입증한다.
4. challenge 연도가 다르다는 이유만으로 실제 시간적 drift를 측정했다.
5. ResNet-18 또는 Grad-CAM 자체가 새로운 악성코드 분석 알고리즘이다.

## 10. 참고문헌

Anderson, H. S., & Roth, P. (2018). EMBER: An open dataset for training static PE
malware machine learning models. *arXiv*. https://arxiv.org/abs/1804.04637

Joyce, R. J., Miller, G., Roth, P., Zak, R., Zaresky-Williams, E., Anderson, H.,
Raff, E., & Holt, J. (2025). EMBER2024: A benchmark dataset for holistic evaluation
of malware classifiers. In *Proceedings of the 31st ACM SIGKDD Conference on
Knowledge Discovery and Data Mining*. https://doi.org/10.1145/3711896.3737431

Microsoft. (2025). *PE format*. Microsoft Learn.
https://learn.microsoft.com/en-us/windows/win32/debug/pe-format

Nataraj, L., Karthikeyan, S., Jacob, G., & Manjunath, B. S. (2011). Malware images:
Visualization and automatic classification. In *Proceedings of the 8th International
Symposium on Visualization for Cyber Security*.
https://doi.org/10.1145/2016904.2016908

Raff, E., Barker, J., Sylvester, J., Brandon, R., Catanzaro, B., & Nicholas, C.
(2018). Malware detection by eating a whole EXE. *arXiv*.
https://arxiv.org/abs/1710.09435

Selvaraju, R. R., Cogswell, M., Das, A., Vedantam, R., Parikh, D., & Batra, D.
(2017). Grad-CAM: Visual explanations from deep networks via gradient-based
localization. In *Proceedings of the IEEE International Conference on Computer
Vision* (pp. 618–626). https://doi.org/10.1109/ICCV.2017.74

Yang, L., Ciptadi, A., Laziuk, I., Ahmadzadeh, A., & Wang, G. (2021). BODMAS: An
open dataset for learning-based temporal analysis of PE malware. In *4th Deep
Learning and Security Workshop*. https://whyisyoung.github.io/BODMAS/

한국인터넷진흥원. (n.d.). *대용량 정상/악성파일 I (training set)*. 정보보호산업진흥포털.
Retrieved September 14, 2026, from
https://www.ksecurity.or.kr/kisis/subIndex/374.do

한국인터넷진흥원. (n.d.). *대용량 정상/악성파일 III*. 정보보호산업진흥포털.
Retrieved September 14, 2026, from
https://www.ksecurity.or.kr/kisis/subIndex/376.do

## 11. 확인 필요

- KISA 2017·2018 archive의 현재 신청 또는 다운로드 절차
- 연구 이용, 파생 그림·통계 및 코드 공개 조건
- 실제 파일 수, 정상·악성 비율, PE 비율과 label 결합률
- KISA 2018의 `KISA` suffix 적용 범위와 제거 허용 여부
- challenge 연도와 실제 sample 수집 시점의 관계
- 2026 한국국방기술학회 추계학술대회의 논문 접수 마감 시각과 제출 페이지
- 소속, 지도교수, 학번 등 계획서 표지에 필요한 인적 정보
