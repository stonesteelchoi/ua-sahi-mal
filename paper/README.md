# UA-SAHI-Mal paper workspace

> **현재 활성 연구선은 KISA-XAI-v5이다.** KISA 원본 PE 정상·악성 이진 탐지와 구조
> 매핑 XAI 평가 계획은 [`v5-kisa-xai/README.md`](v5-kisa-xai/README.md)에서 관리한다.
> 패밀리 분류 XAI-v4와 그 이전 자료는 연구 이력과 재현성을 위해 보존하며 v5 결과와
> 합치지 않는다.

이 폴더는 논문 설계·초안·참고문헌의 단일 진입점이다. v3는 **archived pre-results**,
v4는 **superseded design draft**, v5는 **access-gated design draft** 상태다. v5의 실제
KISA 데이터와 결과는 아직 없으며 새 성능이나 analyst utility를 주장하지 않는다.

## 현재 결정

- KISA 2017 대용량 정상/악성파일 I을 접근 조건부 주 데이터로 사용한다.
- 분류 과제는 malware family가 아니라 Windows PE 정상·악성 이진 탐지이다.
- KISA 2018 라벨 보유 PE를 우선 외부 평가로 사용하며, challenge 연도를 sample 수집일로
  간주하지 않는다.
- Grad-CAM의 10% source-byte 구간을 structure-matched random과 deletion·keep-only로
  비교한다.
- 위치 ground truth가 없으므로 결과를 실제 악성 코드 구간이라고 부르지 않는다.
- 기존 v1–v4 코드와 결과는 삭제하지 않되 v5 통계와 합치지 않는다.

결정의 근거는 [`decisions/ADR-003-kisa-binary-xai.md`](decisions/ADR-003-kisa-binary-xai.md),
전체 계획과 실행 조건은 [`v5-kisa-xai/RESEARCH_PROPOSAL_KO.md`](v5-kisa-xai/RESEARCH_PROPOSAL_KO.md)와
[`v5-kisa-xai/EXPERIMENT_PROTOCOL.md`](v5-kisa-xai/EXPERIMENT_PROTOCOL.md)에 있다.

## 폴더 구성

| 경로 | 역할 | 상태 |
|---|---|---|
| `v5-kisa-xai/` | KISA 이진 탐지, 구조 매핑 XAI, 외부 평가 계획 | current access-gated draft |
| `v4-xai/` | BIG2015 패밀리 분류 XAI 설계 | superseded design draft |
| `plan/RESEARCH_PLAN_v3.md` | 과거 연구 질문, 실험 순서, gate, 최소 baseline | archived |
| `decisions/ADR-001-deepreflect-baseline.md` | DECODE 제외/DeepReflect 채택 결정과 trade-off | accepted |
| `decisions/ADR-002-xai-v4-direction.md` | XAI-v4 전환과 주장 범위 결정 | accepted |
| `decisions/ADR-003-kisa-binary-xai.md` | KISA 원본 PE 이진 탐지로 전환한 결정 | accepted |
| `draft/` | v3 영문 pre-results Markdown·LaTeX·23쪽 검토용 PDF | archived snapshot |
| `reviews/PAPER_DRAFT_REVIEW_2026-09-04.md` | v3 초안 재검토의 우선순위와 수정 기준 | archived review |
| `reviews/UA_SAHI_Mal_top_tier_design_review_ko.md` | 제공받은 top-tier 설계 검토서 | imported |
| `reviews/UA_SAHI_Mal_public_dataset_investigation_ko.md` | 제공받은 공개 데이터셋 조사서 | imported; live facts rechecked in v3 plan |
| `references/UA_SAHI_Mal_references.bib` | 초안의 BibTeX | canonical bibliography |
| `references/README.md` | 공식 논문·artifact 링크, 버전 및 재배포 정책 | current |

## 보존된 v3 초안 상태

초안은 결과를 `[TBD]`로 남긴 점, provenance tier를 합치지 않는 점, byte interval을 authoritative coordinate로 둔 점이 좋다. 그러나 gold corpus, DeepReflect adapter, analyst study는 저장소에 없고(Binary Ninja 확보 불가 확정으로 DeepReflect 재현은 명시적 제외), PEAtlas는 저장소에 있으나(P1) 실제 PE 결과가 아직 없는데, 초안이 이들을 이미 완성된 시스템처럼 서술하므로 **submission-ready가 아니다**.

검토용 PDF는 전체 23쪽을 렌더링해 확인했다. 내용은 읽을 수 있지만 7쪽 resource table의 열 겹침, 14쪽 dataset table의 과도한 단어 분할, 17–18쪽 결과/ablation table의 행·단어 분할이 있어 최종 venue template 이식 전에 표를 다시 설계해야 한다. 상세 판정은 [`reviews/PAPER_DRAFT_REVIEW_2026-09-04.md`](reviews/PAPER_DRAFT_REVIEW_2026-09-04.md)에 기록했다.

## 과거 연구선

- BIG2015 family-decision evidence 계획: [`../docs/RESEARCH_PLAN_v2.md`](../docs/RESEARCH_PLAN_v2.md)
- v2 구현 감사와 잠정 negative result: [`../docs/RESEARCH_AUDIT_2026-09-04.md`](../docs/RESEARCH_AUDIT_2026-09-04.md)
- v2 선행연구 감사: [`../docs/LITERATURE_REVIEW.md`](../docs/LITERATURE_REVIEW.md)
- DECODE 직접 비교 불가 판정의 과거 기록: [`../docs/DECODE_BASELINE_PLAN.md`](../docs/DECODE_BASELINE_PLAN.md)
- remote-sensing 원형: [`../docs/legacy_remote_sensing/README.md`](../docs/legacy_remote_sensing/README.md)

과거 문서의 수치와 gate는 v5의 PE 이진 탐지 및 XAI 결과로 이월하지 않는다.

## 문서·artifact 정책

- 이 폴더에는 사용자가 제공한 초안 패키지의 Markdown, LaTeX, PDF, BibTeX, 설계 검토서와 데이터셋 조사서를 모두 보존한다.
- 제3자 논문 PDF는 공개 Git 저장소에 복제하지 않고 `references/README.md`의 공식 링크와 BibTeX로 고정한다. 공개 열람 가능성과 재배포 권한은 같은 의미가 아니다.
- 실제 malware, password-protected malware archive, Binary Ninja license, API key, 원본 PE와 가역 malware image는 커밋하지 않는다.
- 실험 결과는 split hash, environment, code revision, baseline revision과 함께 생성된 것만 논문 값으로 사용한다.
