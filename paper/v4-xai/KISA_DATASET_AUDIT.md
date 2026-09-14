# KISA 정보보호 R&D 악성코드 데이터셋 감사

- 조사일: 2026-09-14
- 조사 대상: <https://www.ksecurity.or.kr/kisis/subIndex/372.do> 및 연결된 PC 악성코드 데이터셋
- 상태: 공개 카탈로그 검토 완료, 실제 데이터 접근·이용조건·파일 내용 미검증
- 적용 대상: `XAI-V4.0-DRAFT`

## 판정

현재의 **악성코드 패밀리 분류** 과제를 유지하면 KISA 목록에서 BIG2015를 즉시 대체할
후보는 없다. `VX Heavens Snapshot_2010`만 여러 악성코드 그룹을 제공하지만, taxonomy가
family label과 다르고 매우 오래됐으며 페이지 안에서도 그룹 수가 일치하지 않는다.

과제를 **정적 PE 정상·악성 이진 탐지와 설명 충실성 평가**로 바꿀 수 있다면
`KISA_CISC2017_datachallenge_Malwares.01`이 가장 유망하다. 이 데이터는 원본 정상·악성
파일과 이진 정답지를 제공한다고 명시되어 있어, 실제 PE만 선별할 경우 file offset,
section, overlay를 직접 계산할 수 있다. 이 경우 BIG2015 `.bytes`의 VA dump와 validity
문제를 피할 수 있다.

다만 현재 공개 페이지 HTML에는 데이터 archive 다운로드 링크, 명시적 라이선스, 현재
신청 절차가 없다. PC악성코드 페이지에서 확인되는 유일한 파일 다운로드는 기술 설명
PPTX이며 데이터 자체가 아니다. 따라서 실제 archive와 이용허가를 확보하기 전에는 KISA
데이터를 v4의 확정 주 데이터로 선언하지 않는다.

## 데이터셋별 평가

| 데이터셋 | 페이지가 명시한 구성 | v4에 가능한 역할 | 핵심 결함 | 판정 |
|---|---|---|---|---|
| PC악성코드, `KISA_2016_Malwares.01` | 5,045건, 700 MB, SHA-256, 3개 AV 진단명, packer, import DLL/API, entropy view, strings, 외부 접속, 실행 API sequence | packer·vendor·행위별 설명 차이를 보는 보조 metadata | 데이터 구조에 원본 binary가 명시되지 않고 위치 interval도 없음; AV 이름을 family 정답으로 바로 쓰기 어려움 | **보조 metadata 후보** |
| 지능형 악성코드, `KISA_CISC2017_datachallenge_Intelligent-Mal.01` | 분석이 어려운 원본 악성파일 300건, 184.576 MB | 외부 난이도 stress set 또는 사례 분석 | 모두 악성이고 family·behavior 정답이 명시되지 않음 | **주 학습 불가** |
| 대용량 정상/악성파일 I, `KISA_CISC2017_datachallenge_Malwares.01` | 7,500건씩 2세트, 총 15,000건, 6.733 GB, 원본 파일, MD5 파일명, 정상 0/악성 1 정답지 | PE 이진 탐지, exact file-offset/section XAI, 내부 train/validation/test 재분할 | family label 없음; 수집 시점·source group·중복·접근조건 불명 | **최우선 조건부 후보** |
| 대용량 정상/악성파일 II, `KISA_CISC2017_datachallenge_Malwares.02` | 7,500건씩 2세트, 총 15,000건, 9.982 GB, 원본 파일 | 과거 challenge test 또는 외부 평가 | 정답지 미제공; 페이지의 이메일 채점 절차가 현재 유효한지 불명 | **재현 가능한 주 평가에 부적합** |
| 대용량 정상/악성파일 III, `KISA-datachallenge2018-Malwares.03` | 10,000건씩 5세트, 총 50,000건, 14.3 GB, 32-bit Windows, 앞 3세트 label 제공, `.vir`, 끝에 `KISA` 4 byte 추가 | 2017과 다른 연도의 PE 외부 평가; 더 큰 이진 학습 데이터 | 본선 2세트 label 없음; 인위적 suffix; 변환 전후 hash와 PE-only 비율 불명 | **차선 조건부 후보** |
| 대용량 정상/악성파일 IV, `KISA-datachallenge2019-Malwares.04` | 10,000건씩 4세트, 총 40,000건, 18.6 GB, 32/64-bit Windows와 HTML/HWP 등 script, training label, `.vir`, `KISA` suffix | 연도 이동 robustness 분석 | PE 이외 형식이 섞여 file-type shortcut 위험; 공개 페이지에 labeled set별 수가 없음 | **PE 선별 후 외부 평가 후보** |
| VX Heaven, `VX Heavens Snapshot_2010` | 원본 악성파일 236,754건, 35 GB, broad malware group | 악성 그룹 분류의 대규모 보조 실험 | 2010 snapshot, Backdoor·Trojan 편중, family보다 type에 가까운 label, 중복·provenance 불명 | **권장하지 않음** |
| 메모리 상주 악성코드 | 원본 564건과 분석 보고서, 603 MB | source-grounded 사례 연구 가능성 | benign 대조와 class label 없음; 보고서의 위치 annotation 여부 불명 | **소규모 사례 후보** |
| 대용량 정상/악성파일 V, `KISA-challenge2020-Malwares.04` | 정상·악성 원본, 47.3 GB, 32/64-bit Windows | 비교적 뒤 연도의 외부 평가 가능성 | sample 수, label 공개 범위, split 구조가 페이지에 없음 | **정보 부족으로 보류** |

VX Heaven 페이지는 “15개 그룹”이라고 서술하지만 열거된 이름은 Backdoor부터 Worm까지
16개다. 이 불일치는 실제 label manifest를 보기 전에는 class 수조차 확정할 수 없음을
뜻한다.

## 현재 XAI-v4와의 적합성

### 패밀리 분류를 유지하는 경우

BIG2015를 주 데이터로 유지한다. KISA 2017/2018/2019의 공개 정답은 정상·악성 이진
label이므로 현재 초안의 9개 family classifier와 같은 과제가 아니다. VX Heaven의 broad
group도 Microsoft BIG2015의 family taxonomy를 대체하지 못한다.

### 이진 탐지로 바꾸는 경우

KISA 2017 training set은 다음 장점이 있다.

1. 원본 파일이 제공된다는 설명이 사실이면 PEAtlas로 file offset, RVA, section,
   overlay를 직접 계산할 수 있다.
2. 정상 sample이 있어 악성 sample 내부에서만 family 차이를 찾는 것보다 `malicious`
   판정에 대한 설명을 직접 평가할 수 있다.
3. 15,000건과 6.733 GB는 RTX 5070 8 GB 환경에서 제한된 ResNet-18 실험을 설계하기에
   현실적인 규모다.
4. KISA 2018 또는 2019의 labeled PE subset을 확보하면 수집 연도가 다른 외부 평가를
   구성할 수 있다.

이 장점은 semantic localization ground truth를 제공한다는 뜻이 아니다. 파일 수준
이진 label만 있으므로 Grad-CAM은 여전히 모델 귀속 영역이다. deletion, keep-only,
matched random, position, entropy 대조를 통과한 뒤에만 `malicious-decision evidence
candidate`로 부를 수 있다.

## KISA 사용 시 필수 전처리와 누수 통제

1. archive를 열기 전에 이용조건, 논문 공개 가능 범위, 파생 이미지·hash·통계의 공개
   가능 범위를 문서로 확보한다.
2. 원본 archive hash와 개별 파일 hash를 기록하고 실제 payload는 Git에 넣지 않는다.
3. magic과 PE parser가 모두 인정하는 PE32/PE32+만 주 실험에 포함한다. HTML, HWP,
   script와 비 PE 파일은 별도 stratum으로 분리한다.
4. 2018·2019의 `KISA` 4-byte suffix는 모든 파일에서 정확히 확인한 경우에만 제거하고,
   제거 전·후 SHA-256과 길이를 모두 보존한다. suffix 포함/제거 sensitivity를 보고한다.
5. exact duplicate뿐 아니라 import table, section hash, fuzzy hash를 이용해 근접 변종을
   group으로 묶고 group 단위로 분할한다.
6. label별 file type, 크기, parser success, 서명, packer, compiler, source year 분포를
   먼저 비교한다. 이들 변수가 label을 거의 예측하면 이미지 분류 결과를 악성 의미로
   해석하지 않는다.
7. 2017 내부 split과 2018/2019 외부 split 사이의 hash 중복을 제거한다.
8. 실행, import, load, dynamic analysis를 금지하고 격리된 저장소에서 read-only 정적
   parsing만 수행한다.

## 선택 가능한 논문 설계

### 설계 A: 현재 방향 유지

> BIG2015 9-family classification + validity-aware image + Grad-CAM faithfulness +
> address/structure alignment

데이터가 이미 보관되어 있고 family task를 유지할 수 있다. KISA 접근 지연이 없다는
가정이 필요하지 않아 마감 위험이 가장 작다.

### 설계 B: KISA 접근 성공 시 권장 전환

권장 제목은 다음과 같다.

> 정확도를 넘어 설명의 신뢰성으로: 정적 PE 악성코드 탐지기의 구조 정합 및 연도 이동
> XAI 평가

> Beyond Accuracy: Structure-Mapped and Temporally Robust XAI for Static PE Malware Detection

주 실험은 KISA 2017 labeled PE, 외부 평가는 KISA 2018 또는 2019 labeled PE로 구성한다.
모델은 ResNet-18, 설명은 Grad-CAM, primary budget은 유효 byte의 10%로 유지한다. 기존
G1 necessity, G2 sufficiency, randomization sanity를 그대로 적용하고, 외부 연도에서
효과 방향이 유지되는지를 추가 gate로 둔다.

설계 B는 패밀리 분류 논문이 아니라 binary detection + XAI evaluation 논문이다. 제목,
초록, RQ, Table 1의 class 정의를 함께 바꾸어야 하며, KISA 데이터를 family label로
오인해 현재 원고에 끼워 넣어서는 안 된다.

## 접근 Go/No-Go

KISA를 주 데이터로 올리려면 실제 archive를 확보한 뒤 다음 조건을 모두 통과해야 한다.

- 연구 이용 및 논문 보고 허가가 확인됨
- labeled training archive와 label file이 실제로 열림
- 개별 파일 수가 페이지 설명과 일치하거나 차이가 설명됨
- parseable PE가 각 class에 충분히 존재함
- `KISA` suffix와 기타 dataset marker가 label shortcut이 아님
- class별 중복·크기·file type·packer 편향을 정량화함
- source-level split을 만들 식별 정보가 있거나 근접 중복 group split이 가능함

하나라도 충족하지 못하면 현재 BIG2015 주 데이터 결정을 유지한다.

## 공식 페이지

- PC악성코드: <https://www.ksecurity.or.kr/kisis/subIndex/372.do>
- 지능형 악성코드: <https://www.ksecurity.or.kr/kisis/subIndex/373.do>
- 대용량 정상/악성파일 I: <https://www.ksecurity.or.kr/kisis/subIndex/374.do>
- 대용량 정상/악성파일 II: <https://www.ksecurity.or.kr/kisis/subIndex/375.do>
- 대용량 정상/악성파일 III: <https://www.ksecurity.or.kr/kisis/subIndex/376.do>
- 대용량 정상/악성파일 IV: <https://www.ksecurity.or.kr/kisis/subIndex/461.do>
- VX Heaven: <https://www.ksecurity.or.kr/kisis/subIndex/377.do>
- 메모리 상주 악성코드: <https://www.ksecurity.or.kr/kisis/subIndex/378.do>
- 대용량 정상/악성파일 V: <https://www.ksecurity.or.kr/kisis/subIndex/493.do>

