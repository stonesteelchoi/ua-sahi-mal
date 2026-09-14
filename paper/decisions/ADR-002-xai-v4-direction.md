# ADR-002: XAI-v4 설명 신뢰성 평가 연구선 채택

- 상태: Accepted for draft implementation
- 날짜: 2026-09-14
- 결정 브랜치: `research/xai-v4`
- 이전 활성 계획: `paper/plan/RESEARCH_PLAN_v3.md`

## 맥락

v3는 SOREL-20M disarmed PE에서 embedded PE와 YARA 문자열 match를 silver evidence로
정의하고, 제한된 타일 예산에서 정적 증거를 회수하는 문제를 다뤘다. 좌표 매핑과 파일럿
평가는 완료됐지만 semantic gold 부재, silver 위치 편향, 실제 downstream 비용 부재로
인해 “악성 근거 국소화”라는 강한 주장을 하기 어려웠다.

새 아이디어는 이미 이미지화된 malware family dataset을 분류하고 Grad-CAM으로 의심
영역을 시각화하는 것이다. 이 방향은 단기간에 분류 모델과 Figure를 만들 수 있지만,
Grad-CAM을 적용하는 것만으로는 신규성이 약하고 히트맵을 실제 악성 구역으로 해석하면
동일한 정답 부재 문제가 반복된다.

## 결정

활성 논문 방향을 다음으로 변경한다.

> 악성코드 이미지 분류기의 Grad-CAM 영역을 예산 제한 mask로 변환하고, 동일 면적
> control에 대한 실제 deletion/keep-only 재추론으로 충실성을 검증하며, 가능한 입력에
> 대해 주소 및 구조 정합성을 분석한다.

주 데이터는 BIG2015 파생 코퍼스, 보조 데이터는 MaleVis 224×224로 한다. SOREL은
선택적 구조/silver 감사에만 사용한다. Maldataset-2021은 공식 provenance와 변환 규칙을
검증하기 전까지 보류한다.

## 근거

1. BIG2015는 family label과 주소가 있는 `.bytes`/`.asm` 표현을 함께 제공해 분류와 위치
   해석을 한 데이터에서 연결할 수 있다.
2. 저장소에는 BIG2015 파생 코퍼스, raster/occlusion 코드, 감사 결과와 Drive 복원본이
   이미 있어 재사용 비용이 낮다.
3. 기존 감사가 validity shortcut과 fill 민감도를 발견했으므로, 이를 통제한 새
   Grad-CAM 평가가 단순 응용보다 강한 연구 질문이 된다.
4. MaleVis는 준비된 RGB image와 3-seed 분류 결과가 있어 파이프라인 점검에 좋지만 원본
   byte offset 또는 PE 구조를 복원할 근거가 부족하다.
5. v3의 예산 선택, paired control, PEAtlas 경험을 버리지 않고 XAI 평가에 재사용할 수 있다.

## 기각한 대안

### Maldataset-2021 + ResNet-50 + Grad-CAM 사례 그림만 사용

빠르지만 공식 출처와 라이선스가 아직 고정되지 않았고, PNG-only 입력에서 PE 구조 및
file offset 주장을 할 수 없다. Grad-CAM 적용 자체도 충분한 방법 기여가 아니다.

### SOREL v3를 그대로 확장

좌표와 silver 평가는 강하지만 family classification 논문으로 바로 전환할 수 없고,
현재 사용자가 원하는 vision/XAI 중심 소논문과 거리가 있다.

### MaleVis만 사용

분류와 Figure 생성에는 가장 빠르지만 구조 인지 및 역매핑 주장을 포기해야 한다. 마감
상황에서 BIG2015 복원이 실패하면 허용하는 fallback이다.

## 결과

- v1–v3 문서·결과·코드는 삭제하지 않는다.
- v4는 별도 폴더, protocol ID, data revision, run directory를 사용한다.
- 기존 BIG2015 체크포인트는 validity bug 때문에 v4 결과로 재사용하지 않는다.
- 기존 MaleVis 결과는 baseline provenance로만 보존하고 v4 모델의 성능으로 보고하지 않는다.
- G1/G2가 실패하면 “국지화 성공”이 아니라 Grad-CAM faithfulness의 한계를 결론으로 쓴다.
