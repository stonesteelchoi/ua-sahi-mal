# 정확도를 넘어 설명의 신뢰성으로: 악성코드 바이트 이미지 분류기의 구조 정합 및 예산 기반 XAI 평가

**영문 제목:** Beyond Accuracy: Evaluating Structure-Aligned and Budgeted Explanations for Malware Image Classification

> 문서 상태: 결과 전 초안. 대괄호로 표시한 값과 문장은 실제 동결 실험 결과로만 채운다.
> 이 초안은 Grad-CAM 영역을 악성 코드 ground truth로 간주하지 않는다.

## 초록

악성코드 바이너리를 2차원 이미지로 변환하고 합성곱 신경망으로 분류하는 방법은 별도의
수작업 특징 설계 없이 악성코드 패밀리를 구분할 수 있다. 그러나 높은 분류 정확도만으로는
모델이 어떤 입력 구간을 사용했는지, 그 구간이 예측에 실제로 필요한지, 또는 데이터 변환
과정에서 생긴 위치·padding·무효 영역을 지름길로 사용했는지 판단할 수 없다. 기존의
Grad-CAM 기반 사례 시각화는 이러한 질문에 직관적인 그림을 제공하지만, 선명한 히트맵이
설명의 충실성을 보장하지는 않는다.

본 연구는 파일 수준 패밀리 라벨만으로 학습한 악성코드 이미지 분류기를 대상으로,
Grad-CAM 설명을 제한된 입력 면적 예산에서 검증하는 평가 프레임워크를 제시한다. 제안
프레임워크는 주소와 validity 정보를 보존하는 이미지 표현, Grad-CAM 상위 영역 선택,
동일 면적의 무작위·엔트로피·위치 기준선, 선택 영역을 제거하는 deletion 평가와 선택
영역만 보존하는 sufficiency 평가, 그리고 주소 기반 구조 구간별 CAM 질량 분석으로
구성된다. Microsoft BIG2015의 9개 패밀리를 주 데이터로 사용하고, [선택 시: MaleVis
224×224를 보조 데이터로 사용한다].

실험에서 ResNet-18은 test accuracy [TBD], macro-F1 [TBD]를 기록하였다. 10% 유효 면적
예산에서 Grad-CAM 영역의 deletion 효과는 matched random 대비 [TBD, 95% CI]였고,
keep-only 효과는 [TBD, 95% CI]였다. [게이트 통과 시: 두 결과는 Grad-CAM 상위 영역이
패밀리 판정에 필요한 정보와 제한된 충분성을 제공함을 보였다.] [게이트 실패 시: 시각적으로
집중된 Grad-CAM이 matched control보다 높은 충실성을 보이지 않아, 사례 히트맵만으로
의심 구역을 주장하기 어렵다는 한계를 확인하였다.] 구조 분석에서는 [TBD]가 관측되었다.
이 결과는 악성코드 이미지 XAI를 실제 악성 구간의 정답으로 확대 해석하기 전에, 동일
예산의 인과적 교란과 데이터 표현 shortcut을 검증해야 함을 보여준다.

**주요어:** 악성코드 이미지, 패밀리 분류, 설명 가능한 인공지능, Grad-CAM, 약지도
국지화, 설명 충실성

## 1. 서론

악성코드의 변종과 패밀리가 증가하면서 모든 파일을 수작업으로 역분석하는 것은 비용이
크다. 이에 실행파일의 바이트 배열을 이미지로 변환하고 CNN 또는 vision transformer로
분류하는 malware-as-an-image 접근이 활발히 연구되어 왔다. 이 방법은 정적 입력만으로
동작하고 기존 영상 모델을 활용할 수 있다는 장점이 있다.

그러나 분류기가 높은 정확도를 달성하더라도 그 판단 근거가 분석가에게 유용하다는 보장은
없다. 모델이 PE 구조에 관계된 패턴을 사용했을 수도 있지만, 파일 길이, padding, packer,
변환 해상도, 데이터셋 고유 위치 편향을 사용했을 수도 있다. 특히 픽셀 또는 바이트 단위의
악성 위치 ground truth가 없는 상황에서 Grad-CAM의 붉은 영역을 곧바로 악성 코드 위치로
해석하면, 모델 설명과 보안 의미를 혼동하게 된다.

본 연구는 이러한 간극을 “설명 생성”보다 “설명 검증”의 문제로 다룬다. 파일 수준
패밀리 라벨만으로 분류기를 학습하고 Grad-CAM을 생성하되, 같은 면적의 무작위 영역보다
예측에 더 필요한지와 해당 영역만으로 예측 정보가 더 잘 보존되는지를 실제 재추론으로
측정한다. 또한 주소와 validity를 보존하여 CAM을 입력 구간으로 환산하고, 복원 가능한
구조 구간별 분포를 분석한다.

본 연구의 기여는 다음과 같다.

1. Grad-CAM 상위 영역을 동일 면적의 random, entropy, front-position 기준선과 비교하는
   예산 기반 설명 평가 프로토콜을 제시한다.
2. 선택 영역의 deletion과 keep-only를 매 예산에서 실제 재추론하여 필요성과 충분성을
   분리 측정한다.
3. BIG2015 byte dump의 validity와 주소 대응을 보존하고, 설명의 구조 정합성 및
   transformation shortcut 가능성을 함께 분석한다.

본 연구의 `의심 구역`은 모델의 패밀리 판정 근거 후보를 뜻한다. 독립적으로 검증된 악성
함수 또는 행위 코드 ground truth를 뜻하지 않는다.

## 2. 관련 연구

### 2.1 악성코드 이미지 분류

초기 malware image 연구는 바이트를 grayscale 또는 RGB pixel로 배열한 뒤 texture와
형태 차이를 이용해 패밀리를 분류하였다. Malimg, BIG2015, MaleVis 등은 이 접근을 비교할
때 널리 사용된다. 이들 데이터는 파일 수준 패밀리 라벨을 제공하지만 일반적으로 의미론적
악성 구간의 위치 정답은 제공하지 않는다.

### 2.2 XAI 기반 약지도 위치화

Grad-CAM은 목표 class score의 gradient를 마지막 convolution feature map과 결합하여
class-discriminative activation map을 생성한다. 별도 bounding-box label이 필요 없다는
점에서 악성코드 이미지에 적용하기 쉽다. 그러나 CAM은 모델 귀속 결과이며 실제 객체
경계나 인과적 증거를 자동으로 보증하지 않는다. 모델 parameter randomization, 입력
교란, deletion 및 insertion과 같은 sanity·faithfulness 검증이 함께 필요하다.

### 2.3 악성코드 설명의 좌표 문제

자연영상에서 한 픽셀은 시각 객체의 일부이지만, 악성코드 이미지의 한 픽셀은 변환 규칙에
따라 byte, opcode 또는 API call에 대응한다. resize와 padding은 이 대응을 흐릴 수 있다.
따라서 보안 분석에 연결하려면 원입력 위치, 유효성, rasterization version을 보존하고
역매핑 실패도 보고해야 한다.

## 3. 제안 방법

### 3.1 전체 구조

Figure 1은 전체 절차를 나타낸다. 주소와 validity를 보존한 byte image를 분류기에 입력하고,
Grad-CAM으로 class score map을 계산한다. 유효 입력의 상위 5%, 10%, 20%, 40%를 선택한 뒤
deletion과 keep-only 입력을 생성한다. 같은 면적의 random, entropy, front-position
mask를 동일 조건에서 평가한다. 마지막으로 선택 mask를 원주소 및 복원 가능한 구조
구간과 연결한다.

**Figure 1.** 주소 보존 byte image, 패밀리 분류, Grad-CAM, 예산 mask, 재추론 검증,
구조 정합 분석으로 이어지는 제안 프레임워크.

### 3.2 데이터 표현

BIG2015의 address-indexed `.bytes` 표현을 사용한다. 관측되지 않은 `??`와 주소 gap을
실제 0 byte와 구분하기 위해 validity를 보존한다. 주 입력 표현은 [compact-valid 또는
mask-aware 중 validation에서 동결한 값]이며, raster index와 원주소의 lookup table을
sample별로 기록한다. 이미지 회전과 반전은 byte 순서를 바꾸므로 사용하지 않는다.

`.bytes` 파일의 각 행은 시작 가상주소와 16진수 byte token의 열로 구성된다. 전처리기는
첫 주소를 기준으로 선형 배열을 생성하고, 정상적인 16진수 token에는 `valid=1`을 부여한다.
`??`, 행 사이의 주소 gap, 마지막 행의 padding에는 `valid=0`을 부여한다. 이에 따라 실제
값이 `0x00`인 byte는 유효한 관측값으로 유지되고, 관측되지 않은 위치를 0 byte로 오인하지
않는다. 각 sample은 byte 값, validity, 기준 가상주소, 원본 행 주소, source hash를 함께
저장하며, 이 정보 중 하나라도 일치하지 않으면 학습 입력에서 제외하고 제외 사유를
기록한다.

본 연구에서 `.bytes`의 주소는 원본 실행파일의 file offset이 아니라 배포된 dump의
가상주소 좌표다. PE 형식에서 file offset, RVA, VA는 서로 다른 좌표이므로(Microsoft,
2025), 본 데이터만으로 선택 영역을 원본 파일의 정확한 byte offset이라고 표현하지
않는다. 좌표가 보존되는 표현에서는 선형 위치 \(i\)의 주소를 기준 가상주소와의 합으로
계산하고, compact-valid 표현에서는 압축 후 index와 압축 전 가상주소 사이의 lookup
table을 별도로 유지한다. 이후 본문에서 `원주소`는 이 복원된 dump 가상주소를 뜻한다.

byte를 2차원 격자에 배열하는 방식은 원시 byte sequence의 texture 차이를 영상 모델로
학습하게 한다(Nataraj et al., 2011). 다만 행 끝과 다음 행 시작의 인접성은 프로그램
의미가 아니라 rasterization 규칙에서 생긴다. 이를 통제하기 위해 모든 sample의 원
raster 폭은 512 byte로 고정하고, \(i\)번째 위치를
\((\lfloor i/512\rfloor, i\bmod512)\)에 배치한다. 폭, 높이, 마지막 행의 유효 길이는
manifest에 저장하며, CAM의 열 경계 집중 여부를 별도 shortcut 지표로 보고한다.

ResNet 입력은 원 raster를 임의로 잘라내지 않고 224×224의 고정 격자로 집계한다. 출력
cell \((u,v)\)마다 대응하는 원 raster의 half-open 직사각형을 결정론적으로 기록하고,
그 안의 유효 byte 평균을 값 channel로 사용한다. mask-aware 후보에서는 같은 직사각형의
유효 byte 비율을 별도 channel로 제공하며, 유효 byte가 없는 cell은 값과 validity를 0으로
설정한다. 이 집계는 여러 byte를 하나의 cell로 축약하므로 pixel-to-byte 일대일 역변환을
주장하지 않는다. 대신 각 cell이 참조한 가상주소 집합을 보존하여, CAM 점수를 해당
집합으로 투영할 수 있게 한다.

Grad-CAM은 마지막 합성곱 층에서 계산한 뒤 224×224 입력 격자로 보간한다. 각 CAM cell의
점수는 그 cell이 참조한 유효 주소에 동일하게 부여하고, 동일 점수는 가상주소 오름차순으로
정렬한다. 따라서 상위 예산 mask의 분모는 224×224 canvas 면적이 아니라 sample에 실제로
존재하는 유효 주소 수가 된다. deletion과 keep-only 입력은 선택된 가상주소에서 원 byte
배열을 먼저 교란한 뒤 동일한 집계 절차를 다시 적용하여 생성한다. 이 순서는 축약된 영상만
직접 칠할 때 생길 수 있는 보간 artifact와 주소 집합의 불일치를 줄인다.

표현 선택 자체가 family label의 지름길을 만들 가능성도 통제한다. compact-valid 후보는
무효 위치를 제거하여 validity pattern의 직접 사용을 막지만 주소 간 거리 정보를 바꾼다.
mask-aware 후보는 거리 정보를 보존하지만 validity fraction이 family를 예측할 수 있다.
두 후보는 같은 source-level 분할에서 비교하고, 입력 표현은 validation set의 사전 지정
기준으로 하나만 선택한 뒤 test 공개 전에 동결한다. 선택된 표현에 대해서는
validity-only와 position-only 기준선, family별 validity fraction, CAM과 validity의
상관을 함께 보고한다. 또한 유효 주소를 원 raster, 집계 cell, 투영 주소 집합 순서로
왕복했을 때 시작 주소가 해당 집합에 포함되는지 검사하고, 실패 건수와 mapping coverage를
정량적으로 제시한다.

### 3.3 분류 모델

주 분류기는 ResNet-18이다. ImageNet 사전학습 여부는 validation 성능으로 선택한 뒤
test 평가 전에 동결한다. ResNet-50은 backbone 규모 변화에 대한 보조 비교로 사용한다.
class imbalance를 고려해 validation macro-F1으로 checkpoint를 선택한다.

### 3.4 Grad-CAM과 예산 영역

정답 class score에 대한 Grad-CAM을 계산하고 양의 값을 정규화한다. CAM을 원 raster
해상도로 bilinear interpolation한 뒤, score가 높은 valid position부터 주어진 예산만큼
선택한다. 동일 score의 순서는 row-major index로 결정한다. 연결요소와 box는 시각화에만
사용하고 정량 평가는 원 mask에서 수행한다.

### 3.5 충실성 평가

필요성은 선택 영역을 제거했을 때의 정답 class NLL 증가로 측정한다.

\[
\Delta \mathrm{NLL}_{del}=\mathrm{NLL}(x\setminus S,y)-\mathrm{NLL}(x,y).
\]

충분성은 선택 영역만 남긴 입력에서 정답 score와 예측이 얼마나 유지되는지 측정한다.
두 평가 모두 같은 면적의 random control과 쌍으로 비교한다. deletion fill은 valid-byte
histogram 기반 값을 주 방식으로 사용하고, local fill을 민감도 분석으로 사용한다.

### 3.6 구조 정합성

CAM 질량과 선택 면적을 복원 가능한 구조 구간에 할당한다. 구조별 CAM 질량은 해당 구간의
유효 면적으로 정규화하여 큰 구간이 자동으로 높은 값을 얻는 것을 막는다. 이 값은 구조와
모델 귀속의 연관성을 나타내며 해당 구조가 악성이라는 의미는 아니다.

## 4. 실험 설계

### 4.1 데이터와 분할

BIG2015의 9개 malware family를 사용한다. 전체 sample 수, 제외 수 및 class별 분포는
Table 1에 제시한다. exact duplicate와 가능한 near duplicate를 source group으로 묶고,
group-stratified train/validation/test 분할을 사용한다. test split은 모델과 XAI 설정을
동결한 뒤 한 번 평가한다.

**Table 1. 데이터 구성**

| Family | Train | Validation | Test | Excluded | Exclusion reason |
|---|---:|---:|---:|---:|---|
| [TBD] | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] |
| 합계 | [TBD] | [TBD] | [TBD] | [TBD] | — |

### 4.2 구현 환경

- GPU: NVIDIA RTX 5070, 8 GB VRAM
- framework: PyTorch [TBD], torchvision [TBD], CUDA [TBD]
- optimizer: AdamW
- maximum epoch: 30
- seed: 42, 43, 44
- batch size: GPU pilot에서 측정한 [TBD]
- mixed precision: [TBD]

### 4.3 비교 방법

Grad-CAM을 random, entropy, front-position과 비교한다. 모든 방법은 같은 valid-area
budget을 사용한다. 선택적으로 exhaustive occlusion을 고비용 reference로 사용한다.

### 4.4 평가지표와 통계

분류에는 accuracy, macro-F1, balanced accuracy, MCC, ECE를 사용한다. 설명에는 deletion
ΔNLL, keep-only score, AOPC, seed 간 CAM rank correlation 및 top-k IoU를 사용한다.
파일별 paired bootstrap 2,000회로 95% 신뢰구간을 계산하고, 10% 예산의 necessity와
sufficiency 두 주 검정에 Holm 보정을 적용한다.

## 5. 결과

### 5.1 분류 성능

**Table 2. 패밀리 분류 결과**

| Model | Accuracy | Macro-F1 | Balanced Acc. | MCC | ECE |
|---|---:|---:|---:|---:|---:|
| Majority baseline | [TBD] | [TBD] | [TBD] | [TBD] | — |
| Compact CNN | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] |
| ResNet-18 | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] |
| ResNet-50 | [선택] | [선택] | [선택] | [선택] | [선택] |

분류 sanity gate는 [통과/실패]하였다. [결과에 따른 사실 문장 입력].

### 5.2 설명 충실성

**Table 3. 10% 유효 면적 예산에서의 설명 평가**

| Method | Deletion ΔNLL ↑ | Keep-only score ↑ | Label retention ↑ | Components |
|---|---:|---:|---:|---:|
| Random | [TBD] | [TBD] | [TBD] | [TBD] |
| Entropy | [TBD] | [TBD] | [TBD] | [TBD] |
| Front | [TBD] | [TBD] | [TBD] | [TBD] |
| Grad-CAM | [TBD] | [TBD] | [TBD] | [TBD] |

Grad-CAM과 matched random의 deletion 차이는 [TBD, 95% CI], keep-only 차이는
[TBD, 95% CI]였다. 사전 지정한 G1은 [통과/실패], G2는 [통과/실패]하였다.

**Figure 2.** 5–40% 예산에서 Grad-CAM, random, entropy, front-position의 누적
deletion 및 keep-only 곡선. 신뢰구간과 실제 eligible sample 수를 표시한다.

### 5.3 설명 안정성

세 seed 사이의 top-10% CAM IoU는 [TBD], rank correlation은 [TBD]였다. label-shuffled
및 random-weight sanity 결과는 [TBD]였다. [안정/불안정]이라는 평가는 이 결과에 따라
기술한다.

### 5.4 구조 정합성

**Table 4. 구조 구간별 CAM 질량과 면적 정규화 enrichment**

| Region | Valid area fraction | CAM mass fraction | Enrichment | Mapping coverage |
|---|---:|---:|---:|---:|
| Header/front | [TBD] | [TBD] | [TBD] | [TBD] |
| Code-like | [TBD] | [TBD] | [TBD] | [TBD] |
| Data/resource-like | [TBD] | [TBD] | [TBD] | [TBD] |
| Unknown/gap | [TBD] | [TBD] | [TBD] | [TBD] |

**Figure 3.** 서로 다른 패밀리의 대표 sample에 대한 원 byte image, Grad-CAM,
top-10% mask 및 구조 구간. 대표 사례는 test 전체 분포에서 미리 정한 선택 규칙으로
고르며 가장 보기 좋은 성공 사례만 선택하지 않는다.

### 5.5 계산 비용

**Table 5. sample당 계산 비용**

| Stage | Median ms | p95 ms | Peak VRAM |
|---|---:|---:|---:|
| Classification | [TBD] | [TBD] | [TBD] |
| Grad-CAM | [TBD] | [TBD] | [TBD] |
| Mask/coordinate mapping | [TBD] | [TBD] | — |
| Total | [TBD] | [TBD] | [TBD] |

## 6. 논의

### 6.1 히트맵과 증거의 차이

[G1/G2 결과에 따라 작성]. Grad-CAM은 모델 내부의 공간적 기여를 시각화하지만 독립적인
악성성 라벨은 아니다. 따라서 본 연구는 설명 충실성과 구조 정합을 분리하고, 어느 것도
semantic maliciousness로 자동 승격하지 않는다.

### 6.2 구조적 shortcut

CAM이 특정 위치나 구조에 집중된 경우에도 그 이유는 악성 기능, packer, compiler,
resource 크기 또는 데이터 수집 과정일 수 있다. validity fraction과 entropy, normalized
position의 상관 및 matched control 결과를 함께 해석해야 한다.

### 6.3 분석가 활용 가능성

출력 mask는 분석 우선순위를 제시할 수 있지만, 본 실험은 분석가의 실제 리버싱 시간을
측정하지 않는다. 따라서 결과는 “후속 분석 후보 영역을 제시한다”로 제한한다. 실제 시간
절감은 IDA Pro 또는 Ghidra 연동과 사용자 연구를 수행한 뒤 검증할 수 있다.

### 6.4 한계

첫째, BIG2015는 오래된 9개 패밀리로 구성되어 최신 변종에 대한 일반화를 보장하지 않는다.
둘째, `.bytes` 주소 공간은 원본 PE file offset과 동일하지 않으며 일부 위치가 관측되지
않는다. 셋째, perturbation 입력은 원래 데이터 분포에서 벗어날 수 있고 fill 방식에
민감할 수 있다. 넷째, family-decision evidence는 악성 행위의 위치와 동일하지 않다.
다섯째, Grad-CAM의 해상도는 마지막 convolution feature map에 제한된다.

## 7. 결론

본 연구는 악성코드 이미지 분류에서 정확도와 설명 가능성을 분리하여 평가하였다.
주소·validity를 보존한 입력 표현과 예산 기반 Grad-CAM mask를 구성하고, 동일 면적
control을 이용한 deletion 및 keep-only 재추론으로 설명의 필요성과 충분성을 측정하였다.
[실제 결과 한 문장]. 이 결과는 [통과 시: 제한된 면적의 모델 귀속 영역이 패밀리 판정
정보를 우선순위화할 가능성 / 실패 시: 시각적으로 설득력 있는 히트맵만으로 악성코드
의심 구역을 정당화하기 어렵다는 한계]를 보여준다. 향후에는 source-grounded 악성 함수
또는 독립 분석 도구의 구간 라벨을 이용하여 모델 설명과 실제 악성 기능 사이의 관계를
검증할 필요가 있다.

## 결과 입력 전 금지 문장

- “95% 이상의 정확도를 쉽게 달성하였다.”
- “패밀리별 고유한 바이트 구조를 성공적으로 학습했다.”
- “붉은 영역이 암호화된 payload 또는 resource임을 입증했다.”
- “바이트 오프셋을 정확히 역산했다.”
- “분석가의 리버싱 시간을 대폭 단축하였다.”
- “bounding-box GT 부재 문제를 해결하였다.”

각 문장은 실제 지표, 독립 정답 또는 사용자 평가가 있을 때만 근거에 맞춰 다시 작성한다.
