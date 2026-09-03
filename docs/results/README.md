# 논문 근거 데이터

`output/paper/` 의 논문 초고가 인용하는 집계 산출물의 사본이다. 원본은
`runs/malevis/` 에 있으나 `runs/` 는 `.gitignore` 대상이라 저장소에 남지 않는다.
논문의 수치를 저장소만 보고 검증할 수 있도록 여기에 사본을 둔다.

| 파일 | 원본 | 내용 |
|---|---|---|
| `aggregate.csv` | `runs/malevis/aggregate-20260829/aggregate.csv` | 해상도×추론모드별 3-seed 평균·표준편차·seed 간 95% CI (36행) |
| `paired_comparisons.csv` | `runs/malevis/aggregate-20260829/paired_comparisons.csv` | 대응 비교의 평균차와 95% CI (36행) |
| `isolated_timing.json` | `runs/malevis/isolated-timing-20260829.json` | seed 42 체크포인트의 CPU 지연시간·처리량 (논문 인용 필드만 발췌) |

## 검증

```bash
python scripts/audit_paper_numbers.py
```

논문 표 2·3·4와 본문의 파생 수치를 이 데이터로부터 다시 계산해 대조한다.
`scripts/verify_env.sh` 의 5단계로 포함되어 있으므로 컨테이너 검증과 CI 에서도 매번 돈다.
논문을 고치면 `scripts/audit_paper_numbers.py` 의 `TABLE2`/`TABLE3`/`TABLE4`/`BODY_RATIOS`
상수도 같이 고쳐야 하며, 그러지 않으면 검증이 실패한다. 의도된 설계다.

## 신뢰구간 산식

seed 간 95% CI 는 `평균 ± t(0.975, df=2) × 표준편차 / √3` 이다. 집계 구현이 실제로
사용한 t 값은 **4.3030**(72개 CI 전부에서 역산, 편차 5.6×10⁻¹³)으로, 정확값
4.302653 을 소수 4자리로 반올림한 값이다. 상대오차 8×10⁻⁵ 이며 정확값으로 다시
계산해도 36개 비교의 유의성 판정은 모두 동일하다(감사 스크립트 [G] 단계에서 확인).

## 출처와 무결성

세 파일은 `runs/` 의 원본을 **바이트 단위로 그대로 복사**한 것이다(`cmp` 확인). 전사가
개입하지 않았다. `isolated_timing.json` 은 `runs/malevis/isolated-timing-20260829.json`
과 동일한 파일이며 이름만 다르다.

원본이 있는 머신에서는 감사 스크립트가 `runs/malevis/aggregate-20260829/` 를 먼저
찾으므로 원본과 직접 대조되고, 원본이 없는 컨테이너·CI 에서는 이 사본으로 같은 285건이
실행된다. 두 경로 모두 통과함을 확인했다.

## 검증하지 않는 것

- 개별 예측(`predictions.*.csv`)으로부터 지표를 계산하는 과정 자체
- 학습 재현 (GPU 와 4.6GB MaleVis 데이터셋 필요)

즉 이 감사는 **집계·보고 계층**을 검증하며, **지표 계산 계층**은 검증하지 않는다.

---

## 실험 2 근거 (BIG2015 경계 복원)

`docs/results/big2015/` 에 있다. 논문 Ⅳ장의 모든 수치가 여기서 나온다.

| 파일 | 내용 |
|---|---|
| `p0a_result.json` | `.bytes`↔`.asm` 좌표계 일치, 세그먼트별 정렬(512/4096), `??` 비율 |
| `offgrid_summary.json` | 셀 내 경계 위치(0–4행)별 · 업샘플러별 MAE_start (논문 표 5) |
| `boundary_summary.json` | stride 8/16/32 전체 비교 (표 5 의 stride 8 부분이 논문에 실렸다) |
| `guide_discriminability.json` | 섹션 경계 전후의 Cohen's d (바이트 값 대 행 엔트로피) |

재현:

```bash
# 1) BIG2015 공개 샘플을 datasets/big2015_sample/ 에 풀어 둔다
#    (malware-classification.zip -> dataSample.7z -> *.bytes, *.asm)
python scripts/big2015_p0a.py                    # 좌표계·정렬 검증
python scripts/big2015_boundary_experiment.py    # 경계 복원 + 가이드 진단
```

### 이 실험이 검증하지 않는 것

- **Upsample Anything 자체.** 공개 구현이 CUDA 전용이고 최적화 스텝이 5,100회로
  설정되어 있어(논문 본문은 50회) CPU 환경에서 실행할 수 없었다. 전신인 고정 JBU 로
  대리했으며, JBU 는 커널을 최적화하지 않으므로 이 결과는 경계 인식 업샘플링 계열의
  하한이다.
- **검출기 오차.** 확률지도를 정답에서 만든 오라클로 두었다. 따라서 측정된 것은
  업샘플러가 경계를 되살리는 능력의 상한이다.
- **표본 규모.** 공개 샘플 2개, 실제 PE 섹션 8개. 사전 실험으로만 해석해야 한다.
