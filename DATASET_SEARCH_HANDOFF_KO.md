# 데이터셋 탐색 인수인계 프롬프트 — KISA-XAI-v5 (정적 Windows PE 정상·악성 이진 탐지)

> 이 문서 전체가 다음 LLM에게 주는 지시문이다. 읽고 바로 §6의 탐색을 시작하라.
> 작성: 2026-09-15, 기준 프로토콜 `KISA-XAI-V5.0-DRAFT`, 저장소 `stonesteelchoi/ua-sahi-mal` 브랜치 `research/kisa-xai-v5`.

---

## 0. 네가 할 일 (한 문장)

**원본 Windows PE 바이트를 정상·악성 양쪽 다 제공하는 공개 데이터셋을 찾아라.** 이미 평가가 끝난 후보(§4)는 다시 조사하지 말고, §3의 게이트로 새 후보를 판정해 §7 형식으로 보고하라.

## 1. 왜 "원본 바이트"가 절대 조건인가

이 연구는 Grad-CAM이 짚은 픽셀이 **정말 악성 판정의 근거인지**를 바이트 단위로 검증한다. 파이프라인이 이렇다:

1. 파일 전체 → 224×224 grayscale (`interval-binned-v1`). 픽셀 ↔ 파일 오프셋의 half-open interval 지도를 보존한다.
2. Grad-CAM 상위 픽셀 → **고유 원본 바이트 10%** 를 선택한다.
3. 그 바이트를 **채워 넣고(fill) 모델에 다시 넣어** 확률·NLL 변화를 측정한다(deletion / keep-only).
4. structure-matched random 대조군과 쌍체 부트스트랩 2,000회 + Holm 보정으로 비교한다.

3단계가 핵심이다. **바이트를 바꿔 다시 추론해야 하므로 원본 바이트가 없으면 연구 자체가 성립하지 않는다.** 그래서 다음은 전부 무용지물이다:

- PE 헤더 특징 CSV (EMBER, Kaggle 대부분, KISA C-TAS)
- 이미 이미지로 변환된 데이터셋 (Malimg, MaleVis, KISA C-TAS의 bmp) — 픽셀↔오프셋 지도가 없고 원본 복원 불가
- opcode/API 시퀀스, 동적 분석 로그, 메모리 덤프 (CIC-MalMem 등)
- 바이트가 있어도 **PE 헤더가 제거·난독화된 것** (Microsoft BIG 2015의 `.bytes`는 MZ 헤더가 지워져 있어 PE 파싱 불가 → 구조 enrichment 분석 §11이 불가능)

## 2. 진짜 병목은 "악성"이 아니라 "정상"이다

이걸 먼저 이해하고 탐색하라. **원본 악성 PE는 넘친다** (VirusShare, MalwareBazaar, VX-Underground, MalShare, SOREL-20M, MOTIF, Avast-CTU). 반면 **원본 정상 PE는 거의 없다.** 이유는 기술이 아니라 저작권이다 — 정상 실행파일은 상용 소프트웨어라 누구도 재배포할 수 없다. 그래서 대부분의 "malware dataset"은 악성만 원본으로 주고 정상은 특징 벡터로만 준다(BODMAS, SOREL-20M이 정확히 이 패턴).

따라서 현실적 경로는 셋뿐이다:

- **경로 A** — 정상 원본을 이미 묶어 배포하는 드문 데이터셋을 찾는다 (PSA, figshare 6635642가 여기 해당). 법적으로 회색지대이므로 이용조건을 반드시 확인하라.
- **경로 B** — 악성은 공개 저장소에서, **정상은 직접 구축**한다 (Windows 설치본, winget/Chocolatey/Ninite/PortableApps/FossHub 설치 파일). 해시만 공개하고 파일은 재배포하지 않는다. 수집 프로토콜·연도·중복·라이선스 감사를 새로 설계해야 한다.
- **경로 C** — 단일 제출 스트림(예: VirusTotal 피드)에서 정상·악성을 함께 표집한다. **방법론적으로 가장 좋다**(§3의 G6 출처 불일치 문제가 사라진다). EMBER의 sha256 목록 + VirusTotal Academic/Enterprise API가 이 형태다. **VT 학술 접근이 실제로 가능한지 확인하는 것이 가장 가치 있는 조사 항목이다.**

## 3. 판정 게이트 (각 후보를 이 7개로 채점하라)

| ID | 게이트 | 통과 기준 | 탈락 시 |
|---|---|---|---|
| **G1** | 원본 바이트 | 정상·악성 **양쪽** 모두 원본 PE 파일 제공. 첫 2바이트 `4D 5A`(MZ) 확인 | 즉시 탈락 |
| **G2** | 이진 라벨 | 파일↔라벨 결합률 99% 이상, 정상/악성이 명확히 분리 | 즉시 탈락 |
| **G3** | PE 파싱 | PE32 / PE32+ 로 파싱 가능(pefile). 헤더 제거·암호화·"disarmed"로 구조가 깨진 것은 부적합 | 탈락 |
| **G4** | 규모 | **정상 ≥ 10,000** 권장(최소 5,000). 70/15/15 분할 후 test의 악성 표본이 쌍체 부트스트랩 2,000회를 견딜 만큼 필요 | 주 데이터 탈락, 보조 가능 |
| **G5** | 그룹 구조 | near-duplicate / 패밀리 그룹이 **20개 이상**. 그룹 단위 분리 분할(train/val/test)이 성립해야 함 | 주 데이터 탈락 |
| **G6** | 출처 일치 | 정상과 악성이 **비교 가능한 수집 채널**에서 왔는가. 정상=벤더 설치본 / 악성=VirusShare 조합은 shortcut 위험 최상 | 감점. 통과해도 §5 metadata-only AUROC < 0.90 감사 필수 |
| **G7** | 이용조건 | 연구 이용·논문 보고 허용. 재배포 의무 없음. 인용 요건 기록 | 탈락 |

추가 기록 항목(탈락 사유는 아니지만 반드시 적을 것): 수집 연도, 클래스 비율, 총 용량, 압축 해제 후 용량, 배포 채널(직링크/요청/로그인), 공식 해시 제공 여부.

**외부 평가용 두 번째 데이터셋**도 같은 게이트로 찾아라. 단, 주 데이터와 **수집 연도·출처가 실제로 달라야** "교차연도 일반화"를 주장할 수 있다. 겹치면 그 표현을 쓸 수 없다.

## 4. 이미 평가 끝난 후보 — 다시 조사하지 마라

### 4.1 KISA (원 계획의 주 데이터)

| 대상 | 확인 사실 | 판정 |
|---|---|---|
| KISA 2017 대용량 정상/악성파일 I (`CISC2017_datachallenge_Malwares.01`) | 공식 페이지(374/376/461.do)에 다운로드·신청·로그인·약관 요소 없음. 신청 메뉴 `278.do`는 삭제 상태 | **오프라인 방문 전용** |
| KISA 2018 라벨 보유 PE (외부 평가 후보) | 동일 | 오프라인 방문 전용 |
| C-TAS 온라인 (`ctas.krcert.or.kr/dataset/list`) | 로그인 후 카탈로그 **738건 전수 조회**. 분류 5종(악성코드 위협타입 110, 침해사고 시나리오 82, IT서비스 보안관제 118, 취약 코드 428, 공격그룹 0) | **전부 부적합** |
| C-TAS Windows exe/dll 29세트 (211,839 파일) | 표본당 `<sha256>_1.json`·`_2.json` = API 카테고리 개수 19 + md5 / PE 헤더 필드 20. 파일당 2~5 KB. **숫자 40개가 전부** | G1 탈락 |
| C-TAS `html-trojan` 등 bmp 포함 세트 | 파생 회색조 이미지, 픽셀↔오프셋 지도 없음. exe/dll 세트에는 bmp 자체가 없음 | G1 탈락 |
| C-TAS 전체 | **정상(benign) 데이터셋이 카탈로그에 아예 없다** | G2 탈락 — 이진 탐지 구성 불가 |

C-TAS 이용 안내(`/dataset/centerGuide`) 원문 요약: 온라인=AI 데이터셋(메타)만. **AI 데이터셋(원본)과 KISA 챌린지 데이터셋은 오프라인 방문 전용**(서울 송파구 중대로 135 IT벤처타워 서관 8층). 절차는 서류 3종(이용 신청서, 보안 서약서, 재직/재학 증명서) → `bigdata@krcert.or.kr` → 사전협의 → 승인 → 방문. **"원본 데이터는 반출 불가"**, 결과 반출은 관리자 승인 필요. 제공 환경은 GPU PC 1대(Ubuntu 24, RAM 64 GB, 1 TB), python 3.11 + TensorFlow/Keras (PyTorch 미기재).

→ **P0 판정: NO-GO (접근 대기).** 가이드가 언급하는 「우수사례/챌린지」 분류(Zip-Malware, PE-Malware 등)는 현재 목록 API에 노출되지 않고, 원 출처 `aibigdata.boho.or.kr`는 접속되지 않는다.

### 4.2 Kaggle

| 대상 | 확인 사실 | 판정 |
|---|---|---|
| `amauricio/pe-files-malwares` | PE 헤더 특징 CSV(단일 표). 원본 바이트 없음 | G1 탈락 |
| Kaggle 전수 검색 (`PE malware benign`, `malware executable files`, `portable executable`, `virusshare`, `dikedataset`) | 검색된 PE 관련 데이터셋 대부분이 **헤더 특징 표 또는 파생 이미지** | 전부 G1 탈락 |

→ **Kaggle은 이미 훑었다. 같은 검색어로 반복하지 마라.**

### 4.3 GitHub·figshare·기타

| 대상 | 실측/확인 사실 | 판정 |
|---|---|---|
| **PSA PE Malware Machine Learning Dataset** (practicalsecurityanalytics.com, M. Lester) | 원본 PE **201,549개** = 정상 86,812 / 악성 114,737. 확장자 제거, `samples.csv`에 md5/sha1/sha256/positives/total/list/length/entropy. 악성=VirusShare·MalShare·TheZoo, 정상=Windows 7+ 설치본 및 각종 설치 소프트웨어. 2018년 구축. 배포=OneDrive 단일 링크, **`pe-machine-learning-dataset.7z`** (페이지는 "encrypted zip"이라 적었으나 실제는 7z, 암호 `infected`), 선언 크기 **43,836,090,371 B**, SHA-256 `A8B02407A1F8C77DD9DCCC229503A4F668083271EDCBB0289D53C28EBF51215E`, 해제 후 117 GB | **현재 1순위.** G1·G2·G4 통과. G6는 감점(정상/악성 출처 다름). 다운로드가 42,580,586,496 B에서 절단되어 재시도 중 |
| **DikeDataset** (github.com/iosifache/DikeDataset, MIT) | 라벨 CSV 전수 집계: **PE 정상 982 / PE 악성 8,970**, OLE 정상 100 / 악성 1,871. `files/{benign,malware}/<sha256>.exe` 선두 `4D 5A 90 00` 확인 → 원본 맞음. `malice` = 정상 전부 정확히 0.000, 악성 0.675~0.981 | **주 데이터 부적합.** G4·G5 탈락, G6 위험 |
| **figshare `10.6084/m9.figshare.6635642`** ("Malware Detection PE-Based Analysis Using Deep Learning Algorithm Dataset", 2018-06) | 악성 8,970(Locker 300, Mediyes 1,450, Winwebsec 4,400, Zbot 2,100, Zeroaccess 690) + 정상 1,000. 악성=virusshare.com·malicia-project.com, 정상=cnet.com 정품 설치 폴더 | **DikeDataset PE의 원본.** 둘은 같은 데이터이므로 독립 데이터셋으로 계수 금지 |
| BODMAS (2021) | 악성 57,293 원본(요청 시) + 정상 77,142 **특징만** | G1 탈락(정상 원본 없음) |
| SOREL-20M | 악성 ~10M disarmed 원본 + 정상 **특징만**. 약 8 TB | G1·G3 탈락 |
| MalwareBazaar (CC0) + 자체 정상 수집 | 악성 원본 무제한, 정상은 직접 구축 | 가능하나 §2 경로 B — 수집 프로토콜을 새로 설계해야 함 |

**DikeDataset 탈락 근거를 구체적으로 남긴다** (같은 실수를 반복하지 않도록):

- 정상 982개 → 70/15/15 분할 시 val·test 각 약 147개. 쌍체 부트스트랩 2,000회 + Holm 보정의 검정력 부족 (G4)
- 악성이 **5패밀리**뿐이고 Winwebsec 하나가 49.1%. 패밀리를 그룹으로 쓰면 그룹이 5개라 **그룹 분리 70/15/15 자체가 성립하지 않음** (G5)
- 정상 = cnet 설치본 / 악성 = VirusShare·Malicia → 컴파일러·패커·코드서명 유무가 출처와 상관. **Grad-CAM이 "악성 영역"이 아니라 "출처 영역"을 가리켜도 지표가 좋아진다** (G6)
- 클래스 비 1 : 9.1
- 표본이 Malicia(2013~2015) 계열이라 "최신"·"교차연도" 주장 불가

## 5. 원본 바이트 여부를 다운로드 없이 판별하는 법

이 기법을 그대로 쓰라. 오늘 DikeDataset을 이렇게 판정했다.

1. **데이터셋 카드/README에서 폴더 구조와 파일명 규칙을 읽는다.** `files/`, `samples/`, `<sha256>.exe` 같은 구조면 원본일 가능성이 높다. `.csv` 하나뿐이면 특징 표다.
2. **파일당 평균 크기를 계산한다.** 총 용량 ÷ 파일 수. **2~10 KB면 특징 JSON/CSV, 100 KB~5 MB면 원본 PE.**
3. **표본 하나의 앞부분만 HTTP Range로 읽어 MZ 서명을 확인한다.**
   ```bash
   curl -sS -r 0-63 "https://raw.githubusercontent.com/<org>/<repo>/main/files/malware/<hash>.exe" | od -A d -t x1z | head -4
   # 4d 5a 90 00 ... 로 시작하면 원본 PE
   ```
4. **라벨 파일을 받아 전수 집계한다.** 행 수, 클래스별 수, 해시 중복, 라벨 분포. (수 MB라 부담 없다)
5. **압축 파일이면 컨테이너 헤더만 읽어 절단 여부를 판정한다.**
   - 7z: 선두 32바이트에 `NextHeaderOffset`(12..19, uint64 LE)와 `NextHeaderSize`(20..27) → **전체 크기 = 32 + offset + size**
   - zip: 끝의 EOCD / ZIP64 EOCD 레코드
6. **절대 전체를 받아서 확인하지 마라.** 40 GB를 받고 나서 특징 표인 걸 알게 되는 일이 없도록 1~4를 먼저 한다.

## 6. 탐색 지시

### 6.1 아직 안 본 곳 — 우선순위 순

1. **VirusTotal 학술/연구 접근** — 가능 여부, 신청 절차, 원본 파일 다운로드 허용 범위, 비용. 가능하다면 **EMBER 2018/2024의 sha256 목록으로 원본을 회수**하는 §2 경로 C가 열린다. 정상·악성이 같은 제출 스트림이라 G6가 해결되는 유일한 길이다. **이것을 가장 먼저 조사하라.**
2. **AI Hub (aihub.or.kr)** — 한국지능정보사회진흥원. 악성코드 관련 데이터셋 존재 여부와 원본 포함 여부. KISA와 별개 경로다.
3. **DACON** — 과거 악성코드 탐지 경진대회 데이터의 현재 공개 상태.
4. **금융보안원(FSI)**, **KISTI**, **공공데이터포털** — 악성/정상 PE 원본 제공 여부.
5. **Zenodo, IEEE DataPort, Mendeley Data, Hugging Face Datasets, OpenML** — 각각 사이트 내 검색.
6. **MOTIF / MalDICT** (Booz Allen) — 악성 원본 + 패밀리 라벨. 정상이 없으므로 단독 불가지만, **그룹 구조(G5)와 외부 평가 악성 측 보강**에 쓸 수 있는지 확인.
7. **Avast-CTU Public CAPE Dataset**, **EMBER 2024**, **PE Malware Detection 관련 최신 논문의 "Data Availability" 절** — 2024~2026 논문이 새로 공개한 코퍼스가 있는지.
8. **정상 PE 대량 확보 경로**(경로 B용): winget 매니페스트, Chocolatey 패키지 저장소, PortableApps, FossHub, SourceForge, Windows ISO/WinSxS, NIST NSRL RDS(해시만 — 파일은 없음을 확인하라).

### 6.2 검색어 (영문·국문 병행)

```
"raw PE files" dataset benign malicious
"portable executable" dataset "benign" "malware" raw binaries download
malware dataset "original binaries" NOT features
"benign executables" dataset download research
PE malware dataset site:zenodo.org
PE malware dataset site:ieee-dataport.org
malware benign executable site:data.mendeley.com
악성코드 정상파일 데이터셋 원본 실행파일
악성코드 데이터셋 개방 원본 PE 정상
```

논문 쪽: `"malware detection" "raw bytes" dataset 2024..2026`, MalConv/BinaryNet 계열 후속 논문의 데이터 가용성 절.

### 6.3 반드시 지킬 것 (이전 세션에서 사용자가 명시한 제약)

1. **파일 URL을 추측하지 마라.** 페이지에 실제로 있는 링크만 따라가라.
2. **로그인이나 승인 절차를 우회하지 마라.**
3. **약관·이용조건을 읽고 원문을 인용해 기록하라.**
4. **접근 권한이 없는 상태에서 데이터를 받았다고 쓰지 마라.**
5. 확인하지 않은 것을 확인했다고 쓰지 마라. 추정은 "추정"이라고 명시하라.
6. 내려받기 전에 반드시 사용자에게 용량·시간·저장 위치를 알리고 승인을 받아라.

### 6.4 악성코드 취급 규칙 (데이터를 실제로 받게 되면)

- 원본 바이너리를 **실행하지 않는다. import 하지 않는다. 동적 분석·에뮬레이션을 하지 않는다.**
- 일반 개발 PC를 malware sandbox로 간주하지 않는다. 관리자 권한이 아닌 전용 계정을 쓴다.
- **Git 저장소, OneDrive, Google Drive, Dropbox 등 자동 동기화 경로에 두지 않는다.** (예: `D:\secure-malware-data\<dataset>\`)
- 원본 파일과 **복원 가능한 raw-byte 이미지**를 Git에 넣지 않는다.
- 매 커밋·push 전 `scripts/check_repository_safety.py`를 실행한다.
- `git clone`으로 악성 실행파일을 디스크에 쓰면 백신 실시간 검사가 clone을 중단시킬 수 있다.

## 7. 보고 형식

후보마다 이 표를 채워라. **추측 금지 — 확인한 것만, 확인 방법과 함께.**

```
### 후보: <이름> (<배포처 URL>)

| 항목 | 값 | 확인 방법 |
|---|---|---|
| 정상 원본 수 | | |
| 악성 원본 수 | | |
| 파일 형식 | 원본 PE / 특징표 / 이미지 / 기타 | MZ 확인 여부 |
| 평균 파일 크기 | | 총용량÷파일수 |
| 라벨 방식 | | |
| 패밀리·그룹 수 | | |
| 정상 수집 출처 | | 원문 인용 |
| 악성 수집 출처 | | 원문 인용 |
| 수집 연도 | | |
| 총 용량 / 해제 후 | | |
| 배포 채널 | 직링크 / 요청 / 로그인 / 오프라인 | |
| 공식 해시 | | |
| 이용조건 | | 원문 인용 |

게이트: G1 ☐ G2 ☐ G3 ☐ G4 ☐ G5 ☐ G6 ☐ G7 ☐
판정: 주 데이터 / 외부 평가 / 보조 / 부적합
탈락 사유:
```

마지막에 **순위표와 권고 1개**를 붙여라. 권고에는 "왜 PSA보다 나은가(또는 못한가)"를 §3 게이트 기준으로 명시하라.

## 8. 현재 상태 요약 (네가 이어받는 지점)

- **P0 = NO-GO (접근 대기).** KISA 원본은 오프라인 방문 전용, 반출 불가. C-TAS 온라인은 정상 표본 자체가 없다.
- 사용자 결정 대기 중: **A** KISA 오프라인 방문 신청 / **B** 데이터 교체(PSA 1순위) / **C** 설계만 보존.
- 코드·환경은 준비 완료다. `interval-binned-v1` 구현·테스트 30건 통과, 전체 420건 통과, Windows RTX 5070에서 CUDA Grad-CAM 검증 완료(library vs hook Spearman 0.9999999999). **막힌 것은 데이터 하나뿐이다.**
- PSA 아카이브는 다운로드가 97.14%에서 절단되어 재시도 중. 이것이 해결되면 경로 B가 바로 열린다. **네 조사 결과가 PSA보다 확실히 낫지 않으면 PSA를 뒤집지 마라.**
- 어느 경로든 `KISA-XAI-V5.0-DRAFT`를 덮어쓰지 않고 **새 protocol ID를 부여**하며, P0 감사(약관·해시·라벨 결합률·PE 파싱·중복·shortcut)를 그 데이터로 다시 수행한다.

## 9. 참고 문서 (저장소 내)

- `paper/v5-kisa-xai/EXPERIMENT_PROTOCOL.md` — P0 게이트, manifest 필드, eligibility·분할, 누수 감사 §5, 종료 규칙 §14
- `paper/v5-kisa-xai/INTERVAL_BINNED_V1_CONTRACT.md` — 입력 표현 계약
- `paper/v5-kisa-xai/audit/DATA_ACCESS_AUDIT_2026-09-14.md` — KISA 공식 페이지 감사
- `paper/v5-kisa-xai/audit/DATA_ACCESS_AUDIT_2026-09-15_ctas.md` + `ctas_online_dataset_catalog_20260915.csv` — C-TAS 738건 전수
- `paper/v5-kisa-xai/audit/ALTERNATIVE_RAW_PE_DATASETS_2026-09-15.md` — 대체 후보 조사, PSA 배포본 사실(§3.1), DikeDataset 실측(§3.2)
