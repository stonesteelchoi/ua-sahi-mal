// UA-SAHI-MAL 논문 초고 생성기 (전자공학회논문지 정규논문 양식)
// 실행:  node output/paper/build_paper.js
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, AlignmentType, HeadingLevel,
  Table, TableRow, TableCell, WidthType, BorderStyle, ShadingType,
  ImageRun, SectionType, PageNumber, Header, convertInchesToTwip,
} = require("docx");

const DIR = __dirname;
const FIG = path.join(DIR, "figures");
const KR = "Batang";          // 한글 본문 (바탕)
const EN = "Times New Roman"; // 영문·숫자

// ── 서식 헬퍼 ───────────────────────────────────────────────────────────────
const run = (text, o = {}) => new TextRun({ text, font: o.font || KR, size: o.size || 18,
  bold: !!o.bold, italics: !!o.italics, superScript: !!o.sup, color: o.color });
const body = (text, o = {}) => new Paragraph({
  alignment: o.align || AlignmentType.JUSTIFIED,
  spacing: { line: o.line || 240, before: o.before || 0, after: o.after || 40 },
  indent: o.indent === null ? undefined : { firstLine: o.indent ?? 200 },
  children: Array.isArray(text) ? text : [run(text, o)],
});
const chapter = (t) => new Paragraph({ alignment: AlignmentType.CENTER,
  spacing: { before: 260, after: 140 }, children: [run(t, { bold: true, size: 21 })] });
const section = (t) => new Paragraph({ alignment: AlignmentType.LEFT,
  spacing: { before: 180, after: 80 }, children: [run(t, { bold: true, size: 19 })] });
const sub = (t) => new Paragraph({ alignment: AlignmentType.LEFT,
  spacing: { before: 120, after: 60 }, children: [run(t, { bold: true, size: 18 })] });
const caption = (kr, en, o = {}) => [
  new Paragraph({ alignment: AlignmentType.LEFT, spacing: { before: o.before ?? 60, after: 0 },
    children: [run(kr, { size: 16 })] }),
  new Paragraph({ alignment: AlignmentType.LEFT, spacing: { before: 0, after: o.after ?? 140 },
    children: [run(en, { font: EN, size: 16 })] }),
];

// ── 표 헬퍼 ─────────────────────────────────────────────────────────────────
const TW = 4520;                                   // 1단 폭(DXA)
const thin = { style: BorderStyle.SINGLE, size: 4, color: "666666" };
const none = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
function cell(text, { w, bold = false, align = AlignmentType.CENTER, shade = null,
                      top = none, bottom = none, size = 15 } = {}) {
  return new TableCell({
    width: { size: w, type: WidthType.DXA },
    margins: { top: 30, bottom: 30, left: 60, right: 60 },
    shading: shade ? { type: ShadingType.CLEAR, fill: shade, color: "auto" } : undefined,
    borders: { top, bottom, left: none, right: none },
    children: [new Paragraph({ alignment: align, spacing: { before: 0, after: 0 },
      children: [run(String(text), { size, bold, font: /^[\x00-\x7F±·×–—]*$/.test(String(text)) ? EN : KR })] })],
  });
}
// 학술지 관례: 표 위·아래 굵은 선, 머리글 아래 가는 선 (세로선 없음)
function table(widths, rows) {
  const last = rows.length - 1;
  return new Table({
    columnWidths: widths,
    width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA },
    rows: rows.map((r, i) => new TableRow({
      tableHeader: i === 0,
      children: r.map((c, j) => cell(c.t ?? c, {
        w: widths[j], bold: i === 0 || c.bold, align: c.align ?? (j === 0 ? AlignmentType.LEFT : AlignmentType.CENTER),
        top: i === 0 ? thin : none, bottom: i === 0 ? thin : (i === last ? thin : none),
      })),
    })),
  });
}
function figure(file, ratio, widthPx = 300) {
  return new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120, after: 40 },
    children: [new ImageRun({ type: "png", data: fs.readFileSync(path.join(FIG, file)),
      transformation: { width: widthPx, height: Math.round(widthPx * ratio) } })] });
}

// ── 제목부 (1단) ───────────────────────────────────────────────────────────
const titleBlock = [
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 40 },
    children: [run("20년 월 전자공학회논문지 제권 제호", { size: 16 })] }),
  new Paragraph({ alignment: AlignmentType.LEFT, spacing: { after: 220 },
    children: [run("논문 20--*-*", { font: EN, size: 16 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 90 },
    children: [run("악성코드 이미지 분석의 두 기본 가정 재검토: MC Dropout 불확실성과 경계 인식 업샘플링", { bold: true, size: 26 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 },
    children: [run("(Revisiting Two Default Assumptions in Malware-Image Analysis: MC Dropout Uncertainty and Edge-Aware Upsampling)", { font: EN, size: 20 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 60 },
    children: [run("김 성 수", { size: 18 }), run("*", { font: EN, size: 18, sup: true }),
               run(", 최 석 철", { size: 18 }), run("**", { font: EN, size: 18, sup: true }),
               run(", 이 건 희", { size: 18 }), run("**", { font: EN, size: 18, sup: true }),
               run(", 김 민 규", { size: 18 }), run("**", { font: EN, size: 18, sup: true })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 240 },
    children: [run("(Seongsu Kim, Seokcheol Choi, Geonhee Lee, and Mingyu Kim", { font: EN, size: 18 }),
               run("Ⓒ", { font: EN, size: 14, sup: true }), run(")", { font: EN, size: 18 })] }),

  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 100 },
    children: [run("요    약", { bold: true, size: 19 })] }),
  new Paragraph({ alignment: AlignmentType.JUSTIFIED, spacing: { after: 200, line: 230 },
    indent: { left: 400, right: 400, firstLine: 200 },
    children: [run(
      "악성코드를 이미지로 변환해 분석하는 연구에서 두 기법이 사실상 기본값으로 채택되어 왔다. 예측 불확실성을 얻기 위한 " +
      "Monte Carlo(MC) dropout 과, 저해상도 예측을 원해상도로 되돌리기 위한 경계 인식 업샘플링이다. 본 논문은 두 기법을 " +
      "각각 통제된 조건에서 측정한다. 첫째, MaleVis 26-클래스에서 3개 seed 로 결정론적 추론과 5회 MC dropout 을 대응 비교한 결과, " +
      "정확도와 macro F1 은 유의한 차이가 없었으나(224×224 정확도 차 +0.011, 95% 신뢰구간 [-0.007, +0.029]) 기대 보정 오차는 " +
      "+0.091 [+0.071, +0.110] 로 유의하게 악화되었고 이미지당 p95 지연시간은 최대 16.4배 증가했다. 둘째, BIG2015 의 바이트 이미지에서 " +
      "실제 PE 섹션 경계를 정답으로 삼아 업샘플러를 비교한 결과, 경계 인식(bilateral) 방식은 모든 조건에서 단순 bilinear 를 이기지 못했고 " +
      "바이트 값을 가이드로 쓰면 오차가 5.0배로 커졌다. 원인은 바이트 이미지의 영역 경계가 값의 차이가 아니라 분포의 변화라는 점에 있다 " +
      "— 경계 전후의 표준화 평균차가 바이트 값에서 0.96, 행 엔트로피에서 8.50 이었다. 본 논문은 성능 향상을 주장하지 않으며, " +
      "사전 등록된 판정 기준과 컨테이너화된 재현 환경을 함께 공개한다.",
      { size: 17 })] }),

  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 100 },
    children: [run("Abstract", { font: EN, bold: true, size: 19 })] }),
  new Paragraph({ alignment: AlignmentType.JUSTIFIED, spacing: { after: 160, line: 230 },
    indent: { left: 400, right: 400, firstLine: 200 },
    children: [run(
      "Two techniques have become de facto defaults in malware-image analysis: Monte Carlo (MC) dropout for predictive " +
      "uncertainty, and edge-aware upsampling for restoring low-resolution predictions. This paper measures both under " +
      "controlled conditions. First, on the 26-class MaleVis dataset with three seeds, deterministic inference and five-pass " +
      "MC dropout differ insignificantly in accuracy and macro F1 (accuracy difference +0.011, 95% confidence interval " +
      "[-0.007, +0.029] at 224x224), while expected calibration error degrades significantly by +0.091 [+0.071, +0.110] and " +
      "per-image p95 latency grows up to 16.4 times. Second, on BIG2015 byte images with real PE section boundaries as ground " +
      "truth, edge-aware (bilateral) upsampling never beats plain bilinear, and guiding it with raw byte values inflates the " +
      "error 5.0 times. The cause is that a region boundary in a byte image is a change of distribution rather than of value: " +
      "the standardized mean difference across the boundary is 0.96 for byte value and 8.50 for row entropy. We claim no " +
      "performance improvement; we release the pre-registered decision criteria and a containerized reproduction environment.",
      { font: EN, size: 17 })] }),

  new Paragraph({ alignment: AlignmentType.JUSTIFIED, spacing: { after: 260 },
    indent: { left: 400, right: 400 },
    children: [run("Keywords: ", { font: EN, bold: true, size: 17 }),
      run("Malware image analysis, MC dropout, Calibration, Edge-aware upsampling, Reproducibility", { font: EN, size: 17 })] }),
];

// ── 본문 (2단) ─────────────────────────────────────────────────────────────
const bodyBlock = [
  chapter("Ⅰ. 서    론"),
  body("악성코드 바이너리를 2차원 이미지로 변환한 뒤 합성곱 신경망으로 분류하는 접근은 Nataraj 등[1]이 제안한 이래 정적 분석의 표준적 대안으로 자리잡았다. 실행 없이 표현을 얻을 수 있고, 특징 공학이 거의 필요 없으며, 일부 난독화에 강인하다는 점이 장점으로 보고되어 왔다[2]."),
  body("이 계열의 연구가 축적되면서 관심은 단순 정확도에서 신뢰성으로 옮겨가고 있다. 보안 운영 환경에서 분류기의 출력은 분석가의 처리 우선순위를 결정하므로, 예측 확률이 실제 정답률을 반영하는지, 즉 보정(calibration)이 맞는지가 정확도만큼 중요하다. Monte Carlo(MC) dropout[3]은 추론 시 dropout을 유지한 채 여러 번 순전파하여 예측 분산을 얻는 기법으로, 구현이 간단해 이 분야에서 사실상의 기본 선택지가 되었다."),
  body("그러나 MC dropout이 악성코드 이미지 분류에서 실제로 무엇을 개선하고 무엇을 악화시키는지는 통제된 형태로 보고된 바가 드물다. 정확도 개선 여부, 보정 품질에 미치는 영향, 그리고 추론 비용 증가를 같은 데이터·같은 분할·같은 seed에서 동시에 측정한 결과가 필요하다."),
  body("두 번째 기본값은 해상도 문제에 관한 것이다. 검출기의 확률지도는 stride 격자로 양자화되므로, 이를 원해상도로 되돌릴 때 경계를 보존하는 업샘플러가 유리하다는 것이 일반적인 전제다. Joint Bilateral Upsampling[6] 계열과 그 최신 확장인 Upsample Anything[7]이 이 전제 위에 서 있다. 자연 영상에서는 색 경계가 곧 물체 경계인 경우가 많아 이 전제가 성립하지만, 바이트를 그대로 픽셀로 옮긴 이미지에서도 성립하는지는 확인된 바 없다."),
  body("본 논문의 기여는 다음 네 가지다. 첫째, 중복 및 분할 누수를 통제한 MaleVis 프로토콜에서 결정론적 추론과 MC dropout을 3개 seed로 대응 비교하고 seed 간 95% 신뢰구간을 보고한다. 둘째, BIG2015의 실제 PE 섹션 경계를 정답으로 삼아 경계 인식 업샘플링이 바이트 이미지에서 실제로 도움이 되는지 측정한다. 셋째, 두 실험 모두에서 통념과 반대되는 부정적 결과를 제시하고 그 원인을 진단한다. 넷째, 실험 전에 고정한 판정 기준과 컨테이너화된 재현 환경을 함께 공개한다. 본 논문은 최신 성능을 주장하지 않는다."),

  chapter("Ⅱ. 본    론"),
  section("1. 관련 연구"),
  body("Nataraj 등[1]은 바이너리를 고정 폭으로 래스터화한 그레이스케일 이미지에 텍스처 특징을 적용해 계열 분류가 가능함을 보였다. 이후 Vasan 등[2]은 미세조정된 합성곱 신경망으로 정확도를 끌어올렸고, Bozkir 등[4]이 공개한 MaleVis는 25개 악성 계열과 배경 클래스를 포함한 26-클래스 RGB 이미지 벤치마크로 널리 사용되고 있다. 이들 벤치마크는 모두 파일 단위 라벨만 제공하며 객체 경계 상자를 포함하지 않는다."),
  body("불확실성 추정 측면에서 Gal과 Ghahramani[3]는 dropout을 베이지안 근사로 해석해 MC dropout을 제안했고, Guo 등[5]은 현대 신경망이 체계적으로 과신(overconfident)한다는 점과 이를 측정하는 기대 보정 오차(ECE)를 제시했다. 다만 두 방향이 만나는 지점, 즉 악성코드 이미지 분류에서 MC dropout이 보정을 개선하는가에 대한 대응 비교는 충분히 보고되지 않았다."),
  body("업샘플링 측면에서 Kopf 등[6]의 Joint Bilateral Upsampling(JBU)은 고해상도 가이드 영상의 공간 근접도와 값 유사도로 저해상도 신호를 가중 평균한다. Seo 등[7]의 Upsample Anything은 이 커널을 픽셀별 비등방 Gaussian으로 확장하고 입력 영상의 자기복원으로 test-time 최적화한다. 두 방법 모두 가중치가 값 유사도에 의존하므로, 가이드 영상에서 값이 비슷하면 같은 영역이라는 가정을 공유한다. 본 논문은 이 가정을 바이트 이미지에서 검증한다."),
  section("2. 데이터와 누수 통제"),
  body("MaleVis의 224×224와 300×300 두 배포본을 사용한다. 두 해상도에 공통으로 존재하는 표본 식별자만 남기고 동일한 분할을 적용해, 해상도 비교가 데이터 구성 차이로 오염되지 않도록 했다."),
  body("SHA-256 해시로 두 해상도의 완전 중복을 탐지한 결과 중복 그룹 225개, 그중 분할을 가로지르는 그룹 122개가 확인되었다. 같은 라벨의 중복은 한 표본만 남기고 나머지를 제외했으며, 라벨이 충돌하는 그룹은 없었다. 원본 데이터 파일은 변경하지 않았다. 표 1은 그 결과를 정리한 것이다."),
  ...caption("표 1. 데이터셋 구성과 분할", "Table 1. Dataset composition and splits.", { before: 140, after: 60 }),
  table([1760, 800, 1080, 880], [
    ["구분", "제공", "중복 제거 후", "용도"],
    ["학습 폴더", "9,100", "8,593", "—"],
    [" ├ 최적화", "—", "7,363", "학습"],
    [" └ 내부 검증", "—", "1,230", "모델 선택"],
    ["검증 폴더", "5,126", "4,999", "최종 test"],
    ["제외된 중복 레코드", "—", "511", "—"],
  ]),
  body("제외된 511건은 학습 427건과 검증 84건으로 구성된다. 최종 test는 모델 선택이 끝난 뒤 단 한 번만 평가했다.", { before: 100 }),
  section("3. 모델과 학습 설정"),
  body("모델은 dropout과 center loss를 결합한 소형 합성곱 신경망(파라미터 104,906개, 임베딩 128차원, dropout 0.30)이다. 12 epoch, 배치 32, 학습률 0.002, weight decay 1×10⁻⁴, label smoothing 0.05, center loss 가중치 0.01, patience 4로 학습했다. 224×224·seed 42 실행의 경우 11 epoch에서 내부 검증 macro F1 0.8746으로 최적점에 도달했다."),
  body("추론은 두 가지다. 결정론적 추론은 dropout을 끄고 1회 순전파하며, MC dropout 추론은 dropout을 유지한 채 5회 순전파해 확률을 평균한다. 두 방식은 동일한 체크포인트를 사용하므로 차이는 추론 절차에서만 발생한다."),
  section("4. 평가 지표와 사전 판정 기준"),
  body("정확도, macro/weighted F1, macro precision/recall, top-5 정확도와 함께, 확률 품질 지표로 음의 로그우도(NLL), multiclass Brier 점수, 15구간 ECE를 보고한다. 해상도마다 seed 42·43·44를 독립 실행하고, 보고하는 신뢰구간은 seed 간 변동에 대한 95% 구간이다."),
  body("MC dropout을 채택할 조건은 실험 전에 다음과 같이 고정했다. (가) macro F1이 결정론적 추론 대비 유의하게 낮지 않을 것, (나) ECE가 유의하게 악화되지 않을 것, (다) 이미지당 p95 지연시간 증가가 3배 이내일 것. 세 조건을 모두 만족할 때에만 채택으로 판정하며, 미달 항목은 그대로 보고한다."),
  section("5. 지역화 실험과의 범위 구분"),
  body("MaleVis는 파일 단위 라벨만 제공하고 독립적으로 검증된 경계 상자를 포함하지 않는다. 따라서 본 논문은 AP50, mAP50:95, AP_S, Tile Recall, 슬라이스 추론 비교를 산출하거나 주장하지 않는다. 해당 지표는 사람 또는 독립 도구가 검증한 경계 상자가 확보된 뒤에 별도로 보고되어야 한다."),

  chapter("Ⅲ. 실험 1: MC Dropout 의 정확도–보정 상충"),
  section("1. 실행 환경"),
  body("학습과 평가는 AMD Zen3 계열 16 논리 코어 CPU(Windows 11), PyTorch 2.13.0+cpu, torchvision 0.28.0+cpu, torch 스레드 8에서 수행했다. GPU는 사용하지 않았다."),
  body("재현을 위해 컨테이너 정의(Dockerfile, compose, 검증 스크립트)를 함께 공개한다. 다만 본 논문의 수치는 위 CPU 환경의 실행 결과이며, 컨테이너에서 재측정한 값이 아니다. 컨테이너는 Python 3.12.3, torch 2.8.0, torchvision 0.23.0, ultralytics 8.4.67, SAHI 0.12.2 조합으로 의존성 해결·정적 검사·단위 테스트 107건·외부 데이터가 필요 없는 합성 종단 스모크를 통과함을 확인했다. 지연시간 재현을 위해 OMP_NUM_THREADS와 MKL_NUM_THREADS를 1로 고정한다."),
  section("2. 정확도와 보정"),
  body("표 2는 최종 test 4,999장에 대한 3개 seed 평균과 표준편차다. 그림 1은 macro F1과 ECE를 함께 보여준다."),
  ...caption("표 2. 최종 test 성능 (3 seed 평균 ± 표준편차)", "Table 2. Final test performance (mean ± SD over 3 seeds).", { before: 140, after: 60 }),
  table([1180, 860, 860, 860, 760], [
    ["지표", "224 Det.", "224 MC", "300 Det.", "300 MC"],
    ["정확도", "0.769", "0.780", "0.751", "0.764"],
    ["Macro F1", "0.820", "0.821", "0.802", "0.808"],
    ["Weighted F1", "0.774", "0.785", "0.752", "0.765"],
    ["Top-5", "0.883", "0.891", "0.884", "0.885"],
    ["NLL", "0.892", "0.956", "0.961", "1.033"],
    ["Brier", "0.304", "0.322", "0.337", "0.351"],
    ["ECE", "0.048", "0.138", "0.049", "0.144"],
  ]),
  figure("fig1_accuracy_calibration.png", 0.5607, 296),
  ...caption("그림 1. (a) macro F1과 (b) 기대 보정 오차. 오차 막대는 3 seed 표준편차",
             "Fig. 1. (a) Macro F1 and (b) expected calibration error. Error bars are the standard deviation over three seeds.",
             { before: 20, after: 140 }),
  body("MC dropout은 정확도와 macro F1을 소폭 올리지만 그 차이는 seed 간 변동 안에 있다. 반면 ECE는 두 해상도 모두에서 세 배 가까이 커졌고, NLL과 Brier 점수도 함께 악화되었다. 즉 5회 평균이 예측을 더 정확하게 만들지 못한 채 확률만 왜곡한 것이다."),
  section("3. 대응 비교와 신뢰구간"),
  body("표 3은 같은 seed에서 두 조건을 짝지어 계산한 차이와 seed 간 95% 신뢰구간이다."),
  ...caption("표 3. 대응 비교 (차이의 95% 신뢰구간, n = 3 seed)", "Table 3. Paired comparisons (95% CI of the difference, n = 3 seeds).", { before: 140, after: 60 }),
  table([1900, 1900, 720], [
    ["비교 · 지표", "평균 차 [95% CI]", "유의"],
    ["MC−Det. (224) 정확도", "+0.011 [−0.007, +0.029]", "아니오"],
    ["MC−Det. (224) Macro F1", "+0.001 [−0.011, +0.013]", "아니오"],
    ["MC−Det. (224) ECE", "+0.091 [+0.071, +0.110]", "예"],
    ["MC−Det. (300) 정확도", "+0.013 [−0.015, +0.040]", "아니오"],
    ["MC−Det. (300) ECE", "+0.096 [+0.081, +0.111]", "예"],
    ["MC−Det. (300) NLL", "+0.072 [+0.022, +0.122]", "예"],
    ["300−224 (Det.) Macro F1", "−0.017 [−0.033, −0.002]", "예"],
    ["300−224 (Det.) Macro recall", "−0.012 [−0.023, −0.000]", "예"],
  ]),
  body("MC dropout 비교에서는 정확도 계열 지표 어디서도 신뢰구간이 0을 벗어나지 않았다. 유의한 차이는 확률 품질 지표(ECE, NLL)와, 해상도를 높였을 때의 macro F1·recall 하락에서만 나타났다.", { before: 100 }),
  body([run("표 3의 신뢰구간은 t(0.975, df=2)=4.3030을 사용한 seed 간 구간이다. 정확값 4.302653으로 다시 계산해도 여덟 행의 유의성 판정은 모두 동일하다. 마지막 행의 상한은 반올림 표기상 −0.000이지만 실제 값은 −0.00038로 0보다 작다.", { size: 16 })],
       { indent: null, after: 60 }),
  section("4. 추론 비용"),
  body("표 4와 그림 2는 seed 42 체크포인트를 학습이 모두 끝난 뒤 별도 프로세스에서 순차 측정한 결과다. 이미지당 지연시간은 배치 적재 이후의 모델 순전파 시간을 배치 크기로 나눈 값이며, 단일 요청의 종단간 지연시간이 아니다."),
  ...caption("표 4. 이미지당 추론 비용 (CPU, 배치 32, 측정 14,997장)", "Table 4. Per-image inference cost (CPU, batch 32, 14,997 measured images).", { before: 140, after: 60 }),
  table([1300, 940, 940, 1340], [
    ["구성", "p50 (ms)", "p95 (ms)", "처리량 (img/s)"],
    ["224 Det.", "1.41", "1.80", "198.5"],
    ["224 MC(5)", "7.03", "29.45", "84.9"],
    ["300 Det.", "2.52", "9.03", "127.4"],
    ["300 MC(5)", "13.30", "22.73", "53.0"],
  ]),
  figure("fig2_latency.png", 0.6099, 296),
  ...caption("그림 2. 구성별 이미지당 순전파 지연시간", "Fig. 2. Per-image model-forward latency by configuration.",
             { before: 20, after: 140 }),
  body("224×224에서 MC dropout은 p50을 5.0배, p95를 16.4배 늘렸다. 300×300에서도 p50이 5.3배 증가했다. 사전에 고정한 세 조건 중 (가)는 충족했으나 (나)와 (다)는 명백히 미달이므로, 본 설정의 MC dropout은 채택 기준을 통과하지 못한다."),
  section("5. 논의"),
  body("이 결과는 MC dropout 자체가 무용하다는 주장이 아니라, 5회 통과·dropout 0.30이라는 본 설정에서 확률 평균이 과신을 줄이지 못하고 오히려 분포를 평탄화해 ECE를 키웠다는 관찰이다. Guo 등[5]이 보고한 대로 보정은 온도 스케일링 같은 사후 보정으로 훨씬 낮은 비용에 개선될 여지가 있으며, 이는 후속 과제로 남긴다."),
  body("해상도를 224에서 300으로 높였을 때 macro F1이 유의하게 하락한 점도 주목할 만하다. MaleVis 300×300 배포본은 224×224의 단순 확대가 아니라 별도 렌더링이므로, 화소가 늘어난 만큼 계열을 구분하는 텍스처 정보가 늘어난다는 보장이 없다. 파라미터 10만 규모의 소형 모델에서는 오히려 수용 영역 대비 표현이 희석되었을 가능성이 있다."),
  body("본 실험의 한계는 다음과 같다. seed가 3개로 신뢰구간이 넓고, 단일 소형 구조에서만 관찰했으며, MC 통과 횟수와 dropout 비율을 변화시킨 절제 실험을 포함하지 않았다. 또한 MaleVis의 'Other' 클래스는 정상 파일을 의미하지 않으므로 정상/악성 이분 판정 성능으로 해석해서는 안 된다."),

  chapter("Ⅳ. 실험 2: 바이트 이미지에서의 경계 복원"),
  section("1. 동기와 데이터"),
  body("Ⅱ.5에서 유보한 지역화 문제를 다룬다. 바이트를 폭 512의 이미지로 옮기면 검출기의 P3 확률지도는 8행 단위, 곧 4,096바이트 단위로 양자화된다. 경계 인식 업샘플링이 이 양자화를 되돌릴 수 있다면 악성 영역의 시작 오프셋을 훨씬 정밀하게 지목할 수 있다. 이 절은 그 전제를 실제 데이터로 검증한다."),
  body("데이터는 BIG2015[8]의 공개 샘플이다. 각 검체는 가상주소로 색인된 바이트 덤프(.bytes)와 IDA 디스어셈블리(.asm)로 이루어져 있어, 후자에서 섹션 경계를 읽어 전자의 좌표로 옮길 수 있다. 두 파일의 좌표계가 실제로 일치하는지 먼저 확인했다. 덤프는 가상주소 0x401000에서 시작하고 .asm의 세그먼트 주소도 같은 공간을 쓴다."),
  body("확인 결과 세 가지가 드러났다. 첫째, 실제 PE 섹션 8개는 모두 덤프 오프셋이 4,096의 배수였다. 가상주소 공간 덤프이므로 정렬 단위는 FileAlignment(0x200)가 아니라 SectionAlignment(0x1000)이며, 512의 배수이므로 폭 512에서 섹션 경계는 정확히 행 경계에 떨어진다. 둘째, IDA가 붙이는 .idata·HEADER 같은 하위 라벨 3개 중 2개는 정렬되지 않았고 다른 세그먼트와 주소 구간이 겹쳤다. 이들은 PE 섹션이 아니므로 정답에서 제외해야 한다. 셋째, 확보되지 않은 바이트(??)의 비율이 검체마다 1.0%와 38.1%로 크게 달랐다."),
  section("2. 실험 설정"),
  body("검출기 품질을 배제하고 업샘플러만 비교하기 위해 확률지도를 오라클로 만들었다. 섹션별 정답 밴드를 stride 8 격자로 area 풀링해 저해상도 지도를 얻고, 이를 nearest, bilinear, 고정 JBU로 원해상도 복원한 뒤 0.5에서 이진화해 경계 행을 읽었다. 따라서 이 실험이 재는 것은 업샘플러가 경계를 되살리는 능력의 상한이다."),
  body("JBU의 가이드는 두 가지를 비교했다. G1은 바이트 값을 그대로 세 채널에 복제한 것이고, G3는 R에 바이트 값, G에 행 엔트로피, B에 전역 출현빈도 순위를 넣은 것이다. 섹션 경계가 4,096 정렬이면 P3 셀 경계와 정확히 일치해 셀 내부에 복원할 정보가 없으므로, 정답 밴드를 셀 안에서 0~4행 이동시켜 격자에 어긋난 조건을 함께 만들었다."),
  body("Upsample Anything의 공개 구현은 CUDA 전용이고 최적화 스텝이 5,100회로 설정되어 있어(논문 본문의 50회와 다르다) 본 실험 환경에서는 실행할 수 없었다. 따라서 그 전신인 고정 JBU로 대리했다. JBU는 커널을 최적화하지 않으므로 이 결과는 경계 인식 업샘플링 계열의 하한으로 읽어야 한다."),
  section("3. 결과"),
  ...caption("표 5. 경계가 P3 셀 안으로 이동했을 때의 시작 경계 오차 (바이트)", "Table 5. Start-boundary error as the boundary moves inside the P3 cell (bytes).", { before: 140, after: 60 }),
  table([1080, 800, 860, 900, 880], [
    ["셀 내 위치", "nearest", "bilinear", "JBU G1", "JBU G3"],
    ["0행 (정렬)", "0", "0", "1,609", "0"],
    ["1행", "512", "171", "2,645", "341"],
    ["2행", "1,024", "683", "2,816", "1,024"],
    ["3행", "1,536", "853", "3,157", "1,365"],
    ["4행", "2,048", "683", "3,328", "1,707"],
    ["1–4행 평균", "1,280", "597", "2,987", "1,109"],
  ]),
  body("경계가 격자에 정렬된 조건(0행)에서 nearest와 bilinear의 오차는 0이었다. 섹션 경계가 P3 셀 경계와 정확히 겹치므로 셀 내부에 잃어버린 정보가 없고, 따라서 복원할 것도 없다. 설계 단계에서 상정한 4,096바이트 양자화는 적어도 PE 섹션 경계에 대해서는 실재하지 않는 문제였다.", { before: 100 }),
  figure("fig3_boundary.png", 0.5611, 296),
  ...caption("그림 3. (a) 셀 내 경계 위치별 시작 경계 오차. (b) 섹션 경계 전후의 표준화 평균차",
             "Fig. 3. (a) Start-boundary error by boundary offset within the cell. (b) Standardized mean difference across section boundaries.",
             { before: 20, after: 140 }),
  body("경계를 셀 안으로 옮긴 조건(1–4행)에서도 결론은 같았다. 평균 오차는 bilinear 597바이트, 엔트로피 가이드 JBU 1,109바이트, nearest 1,280바이트, 바이트 값 가이드 JBU 2,987바이트였다. 경계 인식 업샘플링은 어느 조건에서도 단순 bilinear를 이기지 못했고, 바이트 값을 가이드로 쓴 경우에는 오차가 5.0배로 커졌다."),
  section("4. 원인 진단"),
  body("바이트 값이 경계를 구분하지 못하기 때문이다. 섹션 경계 전후 8행씩을 비교한 표준화 평균차(Cohen's d)는 바이트 값에서 0.96, 행 엔트로피에서 8.50으로 8.8배 차이가 났다(그림 3(b)). bilateral 커널은 가이드 영상의 값 유사도로 이웃을 가중하는데, 바이트 이미지에서 영역 경계는 값의 차이가 아니라 분포의 변화다. 같은 섹션 안에서도 인접 바이트의 값은 크게 흔들리므로, 값 기반 가중치는 경계를 가로질러 섞이는 것을 막지 못한다."),
  body("가이드를 바꾸면 실제로 개선된다는 점이 이 진단을 뒷받침한다. 행 엔트로피를 채널에 넣은 G3는 정렬 조건에서 JBU의 오차를 1,609바이트에서 0으로, 비정렬 조건에서 2,987바이트에서 1,109바이트로 낮췄다. 그럼에도 bilinear를 넘지는 못했다."),
  body("이 결과는 Upsample Anything을 이 도메인에 그대로 옮기는 설계의 근거를 약화시킨다. UA의 커널은 입력 영상의 자기복원 손실로 최적화된다. 즉 바이트 값을 잘 재현하도록 학습되는데, 그 바이트 값이 경계 판별에 거의 기여하지 않는다. 다만 이는 메커니즘에 근거한 예측이며 UA 자체를 측정한 결과가 아니다."),
  section("5. 한계"),
  body("공개 샘플 2개와 그로부터 얻은 섹션 8개에 기반한 사전 실험이다. 확률지도를 오라클로 두었으므로 검출기 오차가 포함되지 않았고, 경계 인식 업샘플러는 고정 JBU로 대리했다. UA 자체의 측정, 표본 확대, 그리고 주입 페이로드처럼 임의 오프셋을 갖는 경계에 대한 평가는 후속 과제다. 다만 원인 진단이 특정 커널이 아니라 가이드 신호의 성질에 관한 것이므로, 표본을 늘려도 방향이 바뀔 가능성은 낮다고 본다."),

  chapter("Ⅴ. 결    론"),
  body("본 논문은 악성코드 이미지 분석에서 기본값처럼 쓰이는 두 기법을 통제된 조건에서 측정하고, 두 경우 모두 통념과 반대되는 결과를 얻었다."),
  body("MC dropout은 MaleVis 26-클래스 분류에서 정확도와 macro F1을 유의하게 개선하지 못한 채 기대 보정 오차를 224×224에서 +0.091, 300×300에서 +0.096만큼 유의하게 악화시켰고, 이미지당 p95 지연시간을 최대 16.4배 늘렸다. 사전에 고정한 세 조건 중 두 개를 충족하지 못했으므로 본 설정에서는 채택하지 않는다. 부수적으로 입력 해상도를 224에서 300으로 높이면 결정론적 추론의 macro F1이 오히려 유의하게 하락함을 확인했다."),
  body("경계 인식 업샘플링은 BIG2015 바이트 이미지에서 단순 bilinear를 어느 조건에서도 이기지 못했다. 바이트 값을 가이드로 쓰면 오차가 5.0배로 커졌고, 행 엔트로피를 가이드에 넣으면 크게 개선되지만 여전히 bilinear에 못 미쳤다. 원인은 바이트 이미지의 영역 경계가 값의 차이가 아니라 분포의 변화이며, bilateral 계열 커널이 의존하는 값 유사도가 경계에서 거의 판별력을 갖지 못한다는 데 있다(Cohen\u0027s d 0.96 대 8.50). 아울러 실제 PE 섹션 경계는 4,096바이트에 정렬되어 P3 격자와 정확히 겹치므로, 복원할 셀 내부 정보 자체가 존재하지 않았다."),
  body("두 결과가 공유하는 함의는 같다. 어떤 기법을 기본값으로 채택하기 전에, 그것이 개선한다고 알려진 양뿐 아니라 대가로 치르는 양까지 같은 데이터·같은 분할·같은 seed에서 함께 측정해야 한다는 것이다. 후속 연구에서는 온도 스케일링을 포함한 사후 보정과의 비교, MC 통과 횟수·dropout 비율 절제 실험, 그리고 Upsample Anything 자체를 GPU에서 측정해 본 논문의 대리 실험 결과를 확인하는 작업을 수행할 계획이다."),

  chapter("REFERENCES"),
  ...[
    'L. Nataraj, S. Karthikeyan, G. Jacob, and B. S. Manjunath, "Malware images: visualization and automatic classification," in Proc. 8th International Symposium on Visualization for Cyber Security, pp. 1-7, Pittsburgh, USA, July 2011.',
    'D. Vasan, M. Alazab, S. Wassan, H. Naeem, B. Safaei, and Q. Zheng, "IMCFN: Image-based malware classification using fine-tuned convolutional neural network architecture," Computer Networks, vol. 171, 107138, April 2020.',
    'Y. Gal and Z. Ghahramani, "Dropout as a Bayesian approximation: Representing model uncertainty in deep learning," in Proc. International Conference on Machine Learning, pp. 1050-1059, New York, USA, June 2016.',
    'A. S. Bozkir, A. O. Cankaya, and M. Aydos, "Utilization and comparison of convolutional neural networks in malware recognition," in Proc. 27th Signal Processing and Communications Applications Conference, pp. 1-4, Sivas, Turkey, April 2019.',
    'C. Guo, G. Pleiss, Y. Sun, and K. Q. Weinberger, "On calibration of modern neural networks," in Proc. International Conference on Machine Learning, pp. 1321-1330, Sydney, Australia, August 2017.',
    'J. Kopf, M. F. Cohen, D. Lischinski, and M. Uyttendaele, "Joint bilateral upsampling," ACM Transactions on Graphics, vol. 26, no. 3, Article 96, July 2007.',
    'M. Seo, M. Hamilton, and C. Kim, "Upsample Anything: A simple and hard to beat baseline for feature upsampling," in Proc. IEEE/CVF Conference on Computer Vision and Pattern Recognition, 2026.',
    'R. Ronen, M. Radu, C. Feuerstein, E. Yom-Tov, and M. Ahmadi, "Microsoft Malware Classification Challenge," arXiv preprint arXiv:1802.10135, February 2018.',
    'F. C. Akyon, S. O. Altinuc, and A. Temizel, "Slicing aided hyper inference and fine-tuning for small object detection," in Proc. IEEE International Conference on Image Processing, pp. 966-970, Bordeaux, France, October 2022.',
  ].map((t, i) => new Paragraph({
      alignment: AlignmentType.JUSTIFIED, spacing: { after: 60, line: 220 },
      indent: { left: 300, hanging: 300 },
      children: [run(`[${i + 1}] `, { font: EN, size: 16 }), run(t, { font: EN, size: 16 })] })),
];

// ── 각주 블록 (양식상 1쪽 하단) ────────────────────────────────────────────
const footBlock = [
  new Paragraph({ spacing: { before: 300, after: 0 },
    border: { top: { style: BorderStyle.SINGLE, size: 6, color: "000000" } }, children: [] }),
  ...[
    ["※ Acknowledgment: 내용을 입력하십시오. (심사용 논문에서는 삭제)", KR],
    ["* 정회원, 중앙대학교 (Department of **, Chung-Ang University)", KR],
    ["** 정회원, 국방부 (Ministry of National Defense)", KR],
    ["Ⓒ Corresponding Author (E-mail: ***@***.**)", EN],
    ["Received: Month , 20    Revised: Month , 20    Accepted: Month , 20", EN],
  ].map(([t, f]) => new Paragraph({ spacing: { after: 20 },
    children: [run(t, { font: f, size: 14 })] })),
];

// ── 저자 소개 ──────────────────────────────────────────────────────────────
const authorBlock = [
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 320, after: 40 },
    border: { top: { style: BorderStyle.SINGLE, size: 6, color: "000000" },
              bottom: { style: BorderStyle.SINGLE, size: 6, color: "000000" } },
    children: [run("저 자 소 개", { bold: true, size: 19 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 140 },
    children: [run("(심사용 논문에서는 삭제)", { size: 14 })] }),
  ...["김 성 수(정회원)", "최 석 철(정회원)", "이 건 희(정회원)", "김 민 규(정회원)"].flatMap((n) => ([
    new Paragraph({ spacing: { before: 100, after: 20 }, children: [run(n, { bold: true, size: 17 })] }),
    new Paragraph({ spacing: { after: 20 }, indent: { left: 200 },
      children: [run("저자 약력과 관심분야를 입력해 주십시오. 사진 23×30 mm.", { size: 16 })] }),
    new Paragraph({ spacing: { after: 80 }, indent: { left: 200 },
      children: [run("<주관심분야 : 악성코드 분석, 컴퓨터 비전, 기계학습>", { size: 16 })] }),
  ])),
];

// ── 문서 조립 ──────────────────────────────────────────────────────────────
const PAGE = {
  size: { width: 11906, height: 16838 },                         // A4
  margin: { top: 1200, right: 1080, bottom: 1200, left: 1080, header: 700, footer: 700 },
};
const doc = new Document({
  creator: "UA-SAHI-MAL",
  title: "악성코드 이미지 분석의 두 기본 가정 재검토",
  styles: { default: { document: { run: { font: KR, size: 18 } } } },
  sections: [
    { properties: { page: PAGE, column: { count: 1 } },
      children: [...titleBlock, ...footBlock] },
    { properties: { type: SectionType.CONTINUOUS, page: PAGE,
        column: { count: 2, space: 420, equalWidth: true } },
      children: bodyBlock },
    { properties: { type: SectionType.CONTINUOUS, page: PAGE, column: { count: 1 } },
      children: authorBlock },
  ],
});

const OUT = path.join(DIR, "UA-SAHI-MAL_논문초고_v2.docx");
Packer.toBuffer(doc).then((b) => { fs.writeFileSync(OUT, b); console.log("written:", OUT, b.length, "bytes"); });
