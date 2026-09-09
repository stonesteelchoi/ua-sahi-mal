# UA-SAHI-Mal paper workspace

이 폴더가 2026-09-04 이후 논문 설계·초안·참고문헌의 단일 진입점이다. 현재 상태는 **v3 pre-results**이며, 아직 성능이나 analyst utility를 주장하지 않는다.

## 현재 결정

- DECODE는 직접 수치 baseline에서 제외한다. 동적 CAPE API-call 영상, multi-label 행동 분류, Bayesian Grad-CAM pseudo-box를 쓰기 때문에 정적 PE component retrieval과 입력·라벨·평가 단위가 다르다.
- DeepReflect를 가장 직접적인 선행 static function/basic-block localization baseline으로 사용한다.
- DeepReflect 하나로 비교군을 대체하지 않는다. random/uniform/entropy, attribution, MIL, capa/YARA, supervised-gold 및 exhaustive 기준선을 동일 예산에서 함께 측정한다.
- canonical prediction과 ground truth는 `file_offset_intervals: [[start, end), ...]`이다. mask와 bbox는 파생 표현이다.
- 기존 DECODE/YOLO 및 BIG2015 v1/v2 코드는 삭제하지 않는다. 새 논문과 구분된 재현성·negative-result 자산이다.

결정의 근거와 실행 조건은 [`decisions/ADR-001-deepreflect-baseline.md`](decisions/ADR-001-deepreflect-baseline.md), 전체 계획은 [`plan/RESEARCH_PLAN_v3.md`](plan/RESEARCH_PLAN_v3.md)에 있다.

## 폴더 구성

| 경로 | 역할 | 상태 |
|---|---|---|
| `plan/RESEARCH_PLAN_v3.md` | 현재 연구 질문, 실험 순서, gate, 최소 baseline | current |
| `decisions/ADR-001-deepreflect-baseline.md` | DECODE 제외/DeepReflect 채택 결정과 trade-off | accepted |
| `draft/` | 영문 pre-results Markdown·LaTeX·23쪽 검토용 PDF | source snapshot |
| `reviews/PAPER_DRAFT_REVIEW_2026-09-04.md` | 이번 재검토의 우선순위와 수정 기준 | current |
| `reviews/UA_SAHI_Mal_top_tier_design_review_ko.md` | 제공받은 top-tier 설계 검토서 | imported |
| `reviews/UA_SAHI_Mal_public_dataset_investigation_ko.md` | 제공받은 공개 데이터셋 조사서 | imported; live facts rechecked in v3 plan |
| `references/UA_SAHI_Mal_references.bib` | 초안의 BibTeX | canonical bibliography |
| `references/README.md` | 공식 논문·artifact 링크, 버전 및 재배포 정책 | current |

## 초안 상태

초안은 결과를 `[TBD]`로 남긴 점, provenance tier를 합치지 않는 점, byte interval을 authoritative coordinate로 둔 점이 좋다. 그러나 gold corpus, DeepReflect adapter, analyst study는 저장소에 없고(Binary Ninja 확보 불가 확정으로 DeepReflect 재현은 명시적 제외), PEAtlas는 저장소에 있으나(P1) 실제 PE 결과가 아직 없는데, 초안이 이들을 이미 완성된 시스템처럼 서술하므로 **submission-ready가 아니다**.

검토용 PDF는 전체 23쪽을 렌더링해 확인했다. 내용은 읽을 수 있지만 7쪽 resource table의 열 겹침, 14쪽 dataset table의 과도한 단어 분할, 17–18쪽 결과/ablation table의 행·단어 분할이 있어 최종 venue template 이식 전에 표를 다시 설계해야 한다. 상세 판정은 [`reviews/PAPER_DRAFT_REVIEW_2026-09-04.md`](reviews/PAPER_DRAFT_REVIEW_2026-09-04.md)에 기록했다.

## 과거 연구선

- BIG2015 family-decision evidence 계획: [`../docs/RESEARCH_PLAN_v2.md`](../docs/RESEARCH_PLAN_v2.md)
- v2 구현 감사와 잠정 negative result: [`../docs/RESEARCH_AUDIT_2026-09-04.md`](../docs/RESEARCH_AUDIT_2026-09-04.md)
- v2 선행연구 감사: [`../docs/LITERATURE_REVIEW.md`](../docs/LITERATURE_REVIEW.md)
- DECODE 직접 비교 불가 판정의 과거 기록: [`../docs/DECODE_BASELINE_PLAN.md`](../docs/DECODE_BASELINE_PLAN.md)
- remote-sensing 원형: [`../docs/legacy_remote_sensing/README.md`](../docs/legacy_remote_sensing/README.md)

과거 문서의 수치와 gate는 v3의 component-localization 결과로 이월하지 않는다.

## 문서·artifact 정책

- 이 폴더에는 사용자가 제공한 초안 패키지의 Markdown, LaTeX, PDF, BibTeX, 설계 검토서와 데이터셋 조사서를 모두 보존한다.
- 제3자 논문 PDF는 공개 Git 저장소에 복제하지 않고 `references/README.md`의 공식 링크와 BibTeX로 고정한다. 공개 열람 가능성과 재배포 권한은 같은 의미가 아니다.
- 실제 malware, password-protected malware archive, Binary Ninja license, API key, 원본 PE와 가역 malware image는 커밋하지 않는다.
- 실험 결과는 split hash, environment, code revision, baseline revision과 함께 생성된 것만 논문 값으로 사용한다.
