# UA-SAHI-Mal 논문 설계·초안 패키지

## 포함 파일

- `UA_SAHI_Mal_top_tier_design_review_ko.md`
  - 최상위 보안/ML 학회 기준 타당성 판정
  - 현재 설계의 주요 거절 위험
  - 수정 아키텍처, benchmark tier, 지표, baseline, Go/No-Go 게이트

- `UA_SAHI_Mal_pre_results_paper_draft_en.md`
  - 영문 venue-neutral pre-results manuscript
  - Abstract부터 Conclusion 및 Appendix까지 포함
  - 실험 결과는 모두 `[TBD]`로 유지

- `UA_SAHI_Mal_pre_results_paper_draft_en.tex`
  - 위 Markdown을 독립 실행형 LaTeX로 변환한 버전
  - 특정 학회 템플릿이 아닌 검토용 `article` 형식

- `UA_SAHI_Mal_pre_results_paper_draft_en.pdf`
  - LaTeX 빌드·시각 검증본, 23쪽

- `UA_SAHI_Mal_references.bib`
  - 초안에서 사용한 핵심 참고문헌 BibTeX

## 사용 순서

1. 한국어 검토서의 G0와 G1부터 수행한다.
2. gold annotation 가능성이 확인되기 전에는 detector 학습을 본격 시작하지 않는다.
3. 실험 프로토콜과 split hash를 동결한 뒤 영문 초안의 `[TBD]`를 실측값으로 교체한다.
4. 목표 학회를 결정한 후 해당 공식 LaTeX 템플릿으로 본문을 이식한다.
5. Tier 1, Tier 2, Tier 3, Tier 4 결과를 한 점수로 합치지 않는다.

## 현재 초안의 상태

이 문서는 연구계획과 사전 논문 구조를 제공하며, 실험 결과를 주장하지 않는다. 제목, author, 기관, 데이터 규모, 실험값, 통계 결과, IRB/윤리 절차 번호는 실제 확정 후 입력해야 한다.
