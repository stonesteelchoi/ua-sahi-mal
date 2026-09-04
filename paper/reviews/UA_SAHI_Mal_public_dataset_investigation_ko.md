# UA-SAHI-Mal 조사 보고서: 정적 PE 악성코드의 "파일 내부 위치(localization) 정답" 공개 데이터셋 존재 여부 및 detection 정식화 가능성

> **보존 상태:** 사용자가 제공한 사전 조사 원문을 추적 가능하도록 보존한 문서다. 아래의 “실시간 웹 검증 불가” 고지는 작성 당시 환경에 대한 기록이며, 2026-09-04에 공식 논문·저장소·데이터셋 페이지를 다시 확인한 현재 판정은 [`PAPER_DRAFT_REVIEW_2026-09-04.md`](PAPER_DRAFT_REVIEW_2026-09-04.md), 실험 계획은 [`../plan/RESEARCH_PLAN_v3.md`](../plan/RESEARCH_PLAN_v3.md), 출처와 고정 revision은 [`../references/README.md`](../references/README.md)를 우선한다.

> **중요 방법론 고지 (먼저 읽을 것):** 본 조사 환경에서 실시간 웹 검증 도구(web_search/web_fetch)가 작동하지 않아, **URL·레코드 수·현재 다운로드 가능 여부·라이선스 등을 라이브로 확인하지 못했다.** 아래 내용은 도메인 지식 기반 재구성이며, 논문에 인용하기 전 각 항목을 반드시 라이브로 재확인해야 한다. 확인하지 못한 값은 명시적으로 "확인 불가(라이브 재확인 필요)"로 표기했으며, 임의로 수치를 지어내지 않았다.

## TL;DR
- **원본 PE 바이트 + benign 포함 + 분석가 검증된 악성 바이트 구간 정답을 동시에 만족하는 표준 공개 벤치마크는 확인되지 않는다.** 지도교수 문서의 5조건 결론(원본 바이트 / 악성+정상 / 함수·BB·capability 수준 실제 증거 정답 / file offset↔이미지 bbox·mask 대응 / 통제된 재현 split)은 재조사로도 반증되지 않았다.
- **가장 근접한 단일 후보는 DeepReflect의 gold GT**(rbot/pegasus/carbanak, 소스 기반·분석가 검증 함수 수준 정답)이나, 검체 수가 극소이고 주소가 VA/RVA 기반이라 그대로 대규모 detection 벤치마크로 쓰기엔 부족하다.
- 따라서 논문 기본형은 **"budget-aware weakly-supervised malicious region localization"** 으로 두되, DeepReflect·capa·YARA-offset을 **평가용 정답**으로 붙이고, "**소스 공개 악성코드 + 재컴파일 + 디버그 심볼(PDB) 자동 GT 생성**" 경로를 추가하면 소규모 controlled set에 한해 detection/instance-segmentation 정식화가 조건부 가능하다.

## Key Findings
1. **파일 단위 라벨만 있는 벤치마크**(Malimg, BIG2015, MalNet-Image, Dumpware10, MOTIF, MaleVis, BODMAS, SOREL-20M)에는 bbox/mask/함수 오프셋 정답이 없다는 자체 결론은 재조사에서도 유지된다.
2. **DeepReflect**(USENIX Security 2021)는 소스가 확보된 3개 악성 패밀리를 컴파일하여 함수·basic block 수준 악성 정답을 구축한, 현재까지 신뢰 등급이 가장 높은(source-gold + analyst-verified) 위치 정답이다. 단 규모가 매우 작다.
3. **EMBER2024-capa**는 함수 주소 + capa capability 라벨을 대규모로 제공하는 것으로 파악되나, EMBER 계열 특성상 **원본 PE 바이트를 배포하지 않을**(SHA256 + feature 위주) 가능성이 높고, 라벨이 규칙엔진(capa) 기반 silver 등급이라 "악성 증거 구간" 정답으로는 결정적 한계가 있다.
4. **FuncPEval**(arXiv:2504.21520)과 **Assemblage**(Windows PE + PDB 자동 빌드), **ByteWeight/BinKit/jTrans(BinaryCorp)** 등은 컴파일·디버그 심볼로 함수→바이트 오프셋 정답을 자동 생성하는 성숙한 선례이나, 정답이 "함수 식별"이지 "악성성"이 아니다(대부분 benign).
5. **컴파일 기반 자동 GT 생성 파이프라인(소스 악성코드 + PDB → 함수 바이트 구간)의 선례는 존재**한다(DeepReflect의 rbot/pegasus/carbanak, FuncPEval의 Conti). 그러나 이를 대규모로 공개·표준화한 사례는 없어, 이것이 명확한 기여 공간이다.
6. malware-image에 object detector(Faster R-CNN/YOLO)를 적용한 논문들(예: Zhao et al. IEEE Access 2020)의 bbox 정답은 대체로 **자체 제작·휴리스틱**이며 재사용 가능한 형태로 공개되지 않았고 바이트 오프셋과 엄밀히 대응되지도 않는다.

## Details

### A. 지도교수 지목 후보 검증

**A-1. DeepReflect** — Evan Downing, Yisroel Mirsky, Kyuhong Park, Wenke Lee, "DeepReflect: Discovering Malicious Functionality through Binary Reconstruction," 30th USENIX Security Symposium (2021). 저장소: github.com/evandowning/deepreflect.
- 개념: benign으로 학습한 autoencoder가 ACFG(attributed control-flow graph) feature의 재구성 오차로 이상(악성) basic block/함수를 지목하는 비지도 위치화.
- GT: 소스가 확보/복원된 **rbot, pegasus, carbanak** 세 패밀리를 컴파일, Binary Ninja로 소스 함수명↔주소 매핑 후 분석가가 악성 함수를 라벨링. `malware-gt.zip`, `malware-gt-src.zip`, `malware-gt-binja.tar.gz` 형태로 참조됨.
- 단위: 함수 / basic block. 주소는 Binary Ninja VA/RVA → **file offset 변환 필요**.
- 신뢰 등급: **source-gold + analyst-verified (최상)**. 규모: 극소(3 패밀리 수준).
- 현재 다운로드 가능 여부·라이선스·정확한 gold 검체 수·후속 재사용 사례: **확인 불가(라이브 재확인 필요)**.

**A-2. EMBER2024-capa** — huggingface.co/datasets/joyce8/EMBER2024-capa (및 joyce8/EMBER2024_*).
- capa capability 매치를 함수 주소에 연결한 라벨 세트. EMBER 계열 설계상 **원본 PE 미배포(SHA256+feature)** 가능성이 높음 → full-file 그레이스케일 이미지 생성 불가라는 결정적 제약.
- 함수 주소 VA/RVA 여부, 함수 raw bytes 제공 여부, benign 포함 여부, 레코드/distinct capability 수, 중복 함수 문제, 라이선스: **모두 확인 불가(라이브 재확인 필요)**.
- 신뢰 등급: **규칙엔진 silver(capa)**. capability는 정밀하나 "악성성"과 동일하지 않음.

**A-3. FuncPEval** — arXiv:2504.21520.
- **Chromium(benign) + Conti(유출 랜섬웨어 소스 컴파일)** 구성으로 함수 시작/경계 정답을 만든 것으로 파악. function-start 규모는 약 백만 단위(과제 설명상 ≈1,092,820)로 인용되나 **정확 수치·다운로드 가능 여부는 확인 불가**.
- 정답은 함수 식별(boundary)이며 악성성 라벨은 아님.
- 의의: **악성코드 소스 컴파일 기반 자동 GT의 실제 선례.**

**A-4. Zhao et al. IEEE Access 2020 (Faster R-CNN + malware code texture)**
- malware 그레이스케일 이미지에 bbox를 그린 방식이며, 정답은 **자체 제작/휴리스틱**으로 추정되고 재사용 가능한 공개 데이터셋으로 배포되지 않은 것으로 파악(확인 불가). 유사 계열(YOLO/SSD on malware image) 논문들도 대개 자체 주석 box를 사용하며, 바이트 오프셋 대응·악성성 검증이 약하다. 즉 이 계열은 "detection 형식"을 취하지만 정답 provenance가 약해 detection 벤치마크로서 신뢰하기 어렵다.

### B. 신규 후보 탐색 결과

- **컴파일 기반 자동 함수-바이트 GT(benign)**:
  - **Assemblage** — Windows PE를 오픈소스에서 자동 빌드하고 PDB로 함수·심볼 바이트 정답을 생성(원본 PE + 오프셋 + 규모 3박자, 단 benign). 정확 URL/규모 확인 불가.
  - **BinKit**(SoftSec-KAIST, 크로스컴파일+심볼), **jTrans/BinaryCorp** — Hao Wang, Wenjie Qu, Gilad Katz, Wenyu Zhu, Zeyu Gao, Han Qiu, Jianwei Zhuge, Chao Zhang, "jTrans: Jump-Aware Transformer for Binary Code Similarity Detection," ISSTA 2022 (저장소: github.com/vul337/jTrans).
  - **ByteWeight** — Tiffany Bao, Jonathan Burket, Maverick Woo, Rafael Turner, David Brumley, "ByteWeight: Learning to Recognize Functions in Binary Code," 23rd USENIX Security Symposium (2014) — 함수 경계 GT.
  - **DIRE/DIRTY** — DWARF 기반 변수/타입 복원 GT.
  - 이들 모두 "함수 식별" 정답이며 악성성 라벨은 없다.
- **악성코드 소스 컬렉션**: github.com/vxunderground/MalwareSourceCode, github.com/ytisf/theZoo — Zeus/Carberp/Mirai/Conti/Carbanak 등 유출 소스. 이를 PDB 기반 GT 추출과 결합한 대규모 공개 연구는 없음(DeepReflect, FuncPEval이 소규모 선례).
- **패킹 구간 GT**: Packware(IEEE S&P 2020)는 주로 파일/패커 라벨이며, 세밀한 패킹 구간 바이트 오프셋 정답은 드묾(확인 불가). OEP/언패킹 마커 수준.
- **주입 페이로드 위치 GT**: 표준 공개 데이터셋 미확인. 다만 **적대적 주입 연구(github.com/pralab/secml_malware, Demetrio 등 partial-DOS/slack injection)** 는 주입 오프셋을 정확히 알므로 **합성 "planted evidence" 바이트 오프셋 정답**의 선례가 된다. UA-SAHI-Mal의 sanity check용 controlled GT로 특히 유용.
- **타 포맷 위치 정답 선례**: 악성 PDF(embedded object/stream 위치, Contagio 계열), Office VBA 매크로 모듈 위치(oletools), 펌웨어 취약 컴포넌트 위치 — 대개 object/module 수준이며 PE의 함수/섹션 수준과 유사한 조도.
- **capa/YARA를 라벨 오라클로**: capa(github.com/mandiant/capa)는 capability→함수/BB 주소, YARA는 문자열 매치 바이트 오프셋을 제공 → silver 등급 바이트 위치 정답의 원천이나, 이를 표준 데이터셋으로 패키징한 공개물은 없음.
- **최근 MIL/segmentation 연구**: Peters & Farhat MIL(arXiv:2311.12760), PE-MILCon, MAlign, PRISM 등은 대체로 **파일 단위 라벨 + 약지도**이며 instance 수준 정답을 공개하지 않은 것으로 파악(확인 불가).

### C. 핵심 비교표

| 데이터셋 | 연도 | 원본PE/가역바이트 | benign 포함 | 위치 정답 단위 | 정답 신뢰 등급 | 규모 | file offset 대응 | 공개 split | 라이선스/접근 | 다운로드 가능(현재) |
|---|---|---|---|---|---|---|---|---|---|---|
| DeepReflect gold GT | 2021 | 부분(소스 컴파일본) | 학습 코퍼스만 | 함수/BB | source-gold+분석가 | 극소(3 패밀리) | VA/RVA→변환 필요 | 확인 불가 | 확인 불가 | 확인 불가 |
| EMBER2024-capa | 2024 | 아니오(추정) | 확인 불가 | 함수 주소 | 규칙엔진 silver | 대규모(확인 불가) | raw 없으면 불가 | 확인 불가 | 확인 불가 | 확인 불가(HF) |
| FuncPEval | 2025 | 부분(컴파일본) | 예(Chromium) | 함수 시작/경계 | 심볼-gold(식별) | 대규모(확인 불가) | 가능 | 확인 불가 | 확인 불가 | 확인 불가 |
| Zhao et al. box | 2020 | 아니오 | 아니오 | 이미지 bbox | 휴리스틱/자체 | 소규모 | 부정확 | 미공개 | - | 미공개(추정) |
| Assemblage | 2024 | 예(PE+PDB) | 예(전부) | 함수/심볼 바이트 | 심볼-gold(식별) | 대규모(확인 불가) | 가능 | 확인 불가 | 확인 불가 | 확인 불가 |
| BinKit | - | 예 | 예 | 함수 | 심볼-gold(식별) | 대규모 | 가능 | 예 | 오픈(확인 불가) | 확인 불가 |
| jTrans/BinaryCorp | 2022 | 예 | 예 | 함수 | 심볼-gold(식별) | 대규모 | 가능 | 예 | 오픈(확인 불가) | 확인 불가 |
| ByteWeight | 2014 | 예 | 예 | 함수 경계 | 심볼-gold(식별) | 중간 | 가능 | 예 | 확인 불가 | 확인 불가(구형) |
| secml_malware 주입 | - | 예(합성) | 예 | 바이트 구간(주입) | 합성 gold | 가변 | 정확 | - | 오픈(확인 불가) | 확인 불가 |

### D. 최종 판정

**D-1. 존재하는가?** 정적 PE에서 "원본 바이트 + benign + 분석가 검증 악성 구간 + file-offset↔이미지 좌표 대응 + 통제 split"의 5조건을 **동시에** 만족하는 표준 공개 데이터셋은 확인되지 않는다. 가장 근접한 것은 **DeepReflect gold GT**(신뢰도 최상, 규모 최소)이며, 규모·benign·raw 배포 측면에서 각각 EMBER2024-capa(라벨 규모)와 Assemblage(raw PE+오프셋)가 부분 보완재다.

**D-2. detection으로 정식화 가능한가?** 대규모 표준 벤치마크만으로는 **불가** → 기본형은 weakly-supervised/budget-aware region selection이 정직하다. 단 **조건부 가능**: DeepReflect의 소수 검체 + 컴파일 기반 자동 GT로 만든 소규모 gold set에 한해 "instance-level detection 평가"를 별도로 붙일 수 있다.

**D-3. 조합으로 detection급 GT를 만드는 최단 경로(사람 주석 없이 gold 생성):**
소스 공개 악성코드(vxunderground/theZoo의 rbot/Conti/Mirai 등) → 재컴파일하며 **PDB/디버그 심볼 생성** → Assemblage식 파이프라인으로 함수↔바이트 오프셋 자동 매핑(사람 주석 없이 gold 경계) → capa/YARA로 "악성 capability 함수"에 silver 라벨 부여 → 소수 함수는 분석가 스팟체크. 이는 선례(DeepReflect, FuncPEval)가 있는 현실적 경로이며, 사람 주석 없이 gold 경계 + silver 악성 라벨을 얻는다.

**D-4. 학술대회 일정(수 주) 내 확보 가능/불가:**
- 확보 가능: DeepReflect GT 재사용(공개 확인 시), capa/YARA 오라클 실행, secml_malware 합성 주입 정답, 소수 소스 악성코드 재컴파일 GT.
- 확보 어려움: 대규모 raw PE 악성 코퍼스의 합법적 확보, EMBER2024-capa로부터 원본 PE 복원, 대규모 분석가 검증 정답.

## Recommendations
1. **1차(수 주, 안전):** 논문 기본 정식화를 "budget-aware weakly-supervised malicious region localization"으로 확정하고, 학습·라벨은 EMBER/SOREL/BODMAS 파일 단위 라벨을 사용한다. UA-SAHI-Mal의 evidence map → 구조 보존 업샘플 → SAHI 타일 재추론 기여를 핵심 축으로 세운다. 이는 정답 부재 상황에서 가장 방어 가능한 프레이밍이다.
2. **2차(평가 정답 부착):** DeepReflect gold GT(가용 확인 시) + capa capability 함수 주소 + YARA 매치 오프셋을 **localization 평가용 GT**로 붙여 "약지도지만 정량 평가 가능"을 확보한다. VA/RVA→file offset 변환 유틸리티(섹션 헤더 기반)를 먼저 구현할 것.
3. **3차(detection 승격, 소규모):** rbot/Conti 등 소스 공개 악성코드를 PDB 포함 재컴파일해 함수-바이트 gold를 자동 생성하고, capa로 악성 함수에 silver 라벨을 부여한 소규모 controlled set을 만들어 "instance-level detection 평가"를 별도 섹션으로 제시한다. secml_malware식 합성 주입 GT를 sanity check로 병행한다.
4. **판정 전환 임계값:** (a) 분석가 검증 또는 소스-gold 악성 함수가 최소 수백 instance 이상 확보되고 (b) raw PE↔이미지 좌표 대응이 검증되면 detection/instance-segmentation으로 승격한다. 그 이하이면 weak-supervision 프레이밍을 유지한다. EMBER2024-capa가 (라이브 확인 결과) 원본 PE 또는 함수 raw bytes를 제공한다면 이 데이터셋만으로 2차→3차 승격이 가능해지므로, 이 사실 확인이 최우선 검증 항목이다.

## Caveats
- **본 조사는 실시간 웹 검증 실패**로, 모든 URL·레코드 수·다운로드 가능 여부·라이선스는 미검증이다. 특히 (1) DeepReflect artifact 현재 가용성과 gold 검체 수, (2) EMBER2024-capa의 원본 PE·함수 raw bytes·VA/RVA·benign·레코드/capability 수, (3) FuncPEval 함수 수(≈1,092,820로 인용됨)와 다운로드, (4) Assemblage 정확 URL/규모, (5) BinKit·ByteWeight의 현재 호스팅 상태는 반드시 라이브로 재확인해야 한다.
- capa/YARA 기반 라벨은 규칙 의존적(silver)이며 "악성 증거"와 완전히 동일하지 않다. detection GT로 쓸 경우 이 한계를 논문에 명시해야 한다.
- 악성코드 소스 재컴파일 GT는 컴파일러/옵션에 따라 원본 in-the-wild 검체와 바이트 구조가 달라질 수 있어 도메인 갭이 존재한다(FuncPEval의 Conti도 동일 이슈).
- 유출 악성 소스·라이브 샘플 취급은 기관 IRB/보안 정책 및 각 저장소 라이선스 검토가 필요하다.
- "없다"는 결론의 근거로 탐색한 범위: 함수/BB 수준 malware GT, binary analysis 데이터셋(ByteWeight/BinKit/jTrans/DIRE·DIRTY/Assemblage), 소스 악성코드 컬렉션(vxunderground/theZoo), 패킹/언패킹 구간 GT(Packware 등), 주입 페이로드 위치(secml_malware), 타 포맷 위치 정답(PDF/Office/펌웨어), capa/YARA 오라클, 2023–2026 MIL/segmentation 논문(Peters & Farhat, PE-MILCon, MAlign, PRISM). 이 범위 내에서 5조건 동시 충족 표준 벤치마크는 발견되지 않았다.
