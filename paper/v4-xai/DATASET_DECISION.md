# XAI-v4 데이터셋 결정

## 결정

**현재 권장 주 데이터는 BIG2015, 빠른 보조 기준선은 MaleVis 224×224이다.** SOREL-20M
300개 파일럿은 PE 구조 및 독립 silver 증거와의 정합성을 점검하는 선택적 보조 분석에
한정한다. Maldataset-2021은 출처, 라이선스, split, 원본 좌표 정보를 재확인하기 전에는
사용하지 않는다.

KISA 정보보호 R&D 데이터셋 재검토 결과, 패밀리 분류를 이진 정상·악성 탐지로 변경할
수 있다면 `KISA_CISC2017_datachallenge_Malwares.01`이 조건부 주 데이터 후보가 된다.
원본 파일과 이진 정답지가 실제로 제공되면 BIG2015보다 정확한 PE file-offset/section
분석이 가능하다. 다만 공개 페이지에 데이터 다운로드, 현재 이용조건과 라이선스가 없어
실제 접근 및 파일 감사를 통과하기 전에는 주 데이터 결정을 바꾸지 않는다. 상세 판정은
[`KISA_DATASET_AUDIT.md`](KISA_DATASET_AUDIT.md)에 기록했다.

이 결정은 “이미 분류하기 쉬운 PNG가 있는가”보다 다음 질문에 우선순위를 둔다.

1. 분류 라벨이 있는가?
2. 모델이 본 픽셀을 원래 입력 위치로 추적할 수 있는가?
3. 무효 영역, padding, resize가 설명의 지름길이 되는 것을 통제할 수 있는가?
4. 현재 저장소의 코드와 보관 자산을 재사용할 수 있는가?

## 후보 비교

| 데이터 | 현재 자산 | 분류 과제 | 위치 해석 | 핵심 위험 | v4 역할 |
|---|---|---|---|---|---|
| BIG2015 | Drive에 파생 코퍼스 10개 ZIP과 원본 보관본, 코드·감사 문서 존재 | 9개 malware family | `.bytes` 주소 공간 및 `.asm` 구간과 연결 가능 | `??`·주소 공백 validity shortcut, 원본 PE file offset이 아닌 VA dump 좌표 | **주 데이터** |
| MaleVis 224 | Drive에 1.742 GB ZIP, 과거 3-seed 결과·체크포인트 보관 | 25 malware + 1 legitimate | resize된 PNG 픽셀까지만 가능 | 원본 바이너리·정확한 역매핑 부재, 공식 split의 독립성 확인 필요 | **보조 분류/XAI 기준선** |
| MaleVis 300 | Drive에 3.137 GB ZIP | MaleVis 224와 동일 | PNG 픽셀까지만 가능 | 기존 실험에서 224보다 macro-F1이 낮았음 | 해상도 ablation만 |
| SOREL-20M 파일럿 | 코드·프로토콜과 300개 실행 기록은 존재, private payload는 Git 밖 | family가 아니라 vendor-derived behavior tag | PEAtlas로 file offset/RVA/VA/pixel 연결 가능 | disarmed sample, family label 부재, silver evidence 희소·편향 | 선택적 구조/silver 감사 |
| Maldataset-2021 | 현재 보관 목록과 checkout에 없음 | CDMC 2021의 28 class, 224×224 RGB 과제로 확인 | 공개 PNG 위치만 가능 | `phoenixml` 출처 미확인, 원본 PE·변환 규칙·라이선스·중복 정보 미확인 | 보류 |
| KISA 2017 대용량 정상/악성파일 I | 공식 페이지에는 15,000개·6.733 GB·원본 파일·이진 정답지로 기재, 실제 archive 미확보 | 정상/악성 이진 탐지 | 실제 PE subset이면 exact file offset과 PE 구조 연결 가능 | family label 없음, 다운로드·라이선스·중복·PE 비율 미확인 | **이진 탐지 전환 시 조건부 후보** |
| KISA 2018/2019 | 공식 페이지에는 labeled training set과 원본 `.vir`로 기재 | 연도 이동 이진 탐지 | suffix 제거 후 PE subset에서 exact mapping 가능 | `KISA` 4-byte suffix, unlabeled test, 2019 비 PE 혼합, 접근조건 미확인 | 선택적 외부 평가 후보 |
| DECODE | 코드·문헌 어댑터 존재, 실제 주 데이터 없음 | 동적 API 기반 8-category/multilabel | API 이미지 좌표 | 정적 PE family 및 byte-image와 estimand 불일치 | 관련 연구 |

## 왜 BIG2015인가

BIG2015는 9개 패밀리 라벨과 `.bytes`/`.asm` 표현을 함께 제공하므로, v4의 두 질문을
한 데이터 안에서 연결할 수 있다.

- 분류기는 패밀리를 예측한다.
- Grad-CAM은 모델이 사용한 이미지 위치를 제시한다.
- 해당 위치를 `.bytes` 주소 범위로 환산한다.
- 가능한 구간은 `.asm`의 section 또는 영역 정보와 비교한다.
- top-k 영역을 실제로 제거하거나 보존한 뒤 다시 추론해 충실성을 측정한다.

다만 BIG2015의 `.bytes`는 원본 PE 파일 자체가 아니며 주소가 빠진 `??`와 gap을 포함할
수 있다. 따라서 결과 좌표를 `file offset`이라고 부르지 않고 `BIG2015 byte-dump address
range` 또는 `address-indexed byte range`라고 부른다.

과거 v2의 1,636개 파생 코퍼스와 45개 평가 결과는 데이터 준비와 코드 경로를 확인하는
자료로만 사용한다. 당시 모델 입력이 validity mask를 버렸으므로 체크포인트와 설명
결과는 v4 결과로 재사용할 수 없다. v4에서는 다음 두 표현 중 하나를 동결해야 한다.

- `compact-valid-v1`: 관측된 바이트만 이어 붙이고 원주소 lookup table을 별도 보존
- `mask-aware-v1`: 좌표 배열을 유지하되 validity를 명시적으로 처리하고
  valid-fraction matched 평가를 수행

두 표현을 동시에 주 실험으로 돌리면 범위가 커지므로, 짧은 파일럿으로 shortcut이 더
작은 하나를 선택하고 다른 하나는 robustness ablation으로 둔다.

## MaleVis를 쓰는 방법

MaleVis 공식 소개는 25개 malware class와 1개 legitimate class로 이루어진 RGB byte
image corpus라고 설명한다. 현재 프로젝트는 224×224와 300×300 보관본 및 과거 3-seed
분류 결과를 갖고 있다. 과거 224 결정론적 결과는 평균 accuracy 0.769, macro-F1 0.820이지만,
이는 새 v4 모델의 결과가 아니며 재학습 없이 새 초록에 인용하지 않는다.

MaleVis는 다음 용도에는 적합하다.

- 8 GB GPU에서 데이터 로더·전이학습·Grad-CAM 파이프라인 점검
- 이미지 패밀리 분류 성능과 calibration 비교
- 동일 면적 deletion/keep-only에 대한 XAI faithfulness 재현
- Figure용 설명 사례 생성

다음 주장에는 적합하지 않다.

- 히트맵을 원본 PE의 정확한 file offset으로 역산했다.
- 활성 영역이 `.text`, `.rsrc`, overlay 등 특정 PE 구조라고 확인했다.
- 활성 영역이 실제 악성 행위 코드다.

따라서 MaleVis만 사용한다면 제목에서 `structure-aware`와 `byte-offset localization`을
빼고, “Explainable Malware Image Classification with Faithfulness Evaluation”로 범위를
줄여야 한다.

## SOREL-20M을 쓰는 방법

SOREL은 family classification 주 데이터로 쓰지 않는다. 현재 파일럿의 라벨은
vendor-derived behavior tag이고 표본은 Machine/Subsystem이 0으로 변경된 disarmed PE다.
대신 BIG2015 실험을 완료한 뒤 다음 질문을 별도 탐색 분석으로 확인할 수 있다.

- behavior-tag classifier의 attribution이 embedded PE/YARA silver interval과 겹치는가?
- CAM 질량이 header, section, overlay 중 어디에 분포하는가?
- front-position prior를 제거하거나 통제해도 같은 구조 정합이 나타나는가?

이 분석은 silver agreement이며 semantic malicious-code ground truth가 아니다. H와 Y를
분리하고, embedded-header 주변을 제외한 YARA 결과도 별도로 보고한다.

## Maldataset-2021 사용 전 확인표

CDMC 2021 자료에서 28개 class와 224×224 RGB PNG 과제라는 점은 확인되지만, 현재
초안의 `phoenixml/Maldataset-2021` 경로는 공식 출처로 확인되지 않았다. 사용하려면
다음 항목을 먼저 기록한다.

- 공식 다운로드 URL과 접근일
- 재배포 및 논문 사용 조건
- 28개 라벨의 실제 family name 또는 익명 label 여부
- 공식 train/test split과 test label 공개 여부
- binary-to-image 변환 규칙, resize·crop·padding 방식
- 원본 PE 또는 pixel-to-byte map 제공 여부
- 정확 중복 및 근접 중복 비율
- 이미지 채널이 실제 서로 다른 3-byte 값인지, grayscale 복제인지

이 항목 중 원본 좌표 규칙을 확인하지 못하면 Maldataset-2021은 MaleVis와 같은
PNG-only 분류/XAI 데이터로 취급한다.

## 복원 우선순위

현재 새 checkout에는 실제 데이터가 없다. `docs/artifacts/`의 Drive catalog만 있다.
공간과 시간을 아끼기 위한 순서는 다음과 같다.

1. BIG2015 파생 코퍼스 10개 ZIP을 빈 `datasets/big2015/`에 복원하고 manifest와 PNG
   metadata를 검증한다.
2. 기존 v2 체크포인트는 회귀 확인용으로만 복원하고 v4 결과에는 사용하지 않는다.
3. MaleVis는 224×224 ZIP만 먼저 복원한다. 300×300은 해상도 ablation을 실제로 할 때만
   받는다.
4. 37.9 GB BIG2015 원본은 `.asm` 또는 split 재생성이 필요할 때만 복원한다.
5. SOREL private compressed payload는 선택적 외부 감사를 확정하기 전에는 다시 받지 않는다.

## 최종 권장안

제출 일정이 짧다면 다음 한 줄 구성으로 끝낸다.

> BIG2015 validity-aware family classifier + Grad-CAM + random/entropy matched controls +
> budgeted deletion/keep-only + 구조 구간별 CAM 질량 분석

MaleVis는 외부 재현 또는 시각적 예시를 한 절에 추가할 여유가 있을 때만 포함한다.
SOREL과 Maldataset-2021을 모두 넣어 데이터셋 수를 늘리는 것은 이번 소논문의 완성도를
높이지 않는다.
