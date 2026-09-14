# XAI-v4 결과 폴더

현재 v4 결과는 없다. 이 폴더에는 원본 또는 가역 malware image를 넣지 않는다.

실험 완료 후 다음 비민감 집계 산출물만 추가한다.

- `dataset_summary.json`
- `classification_metrics.csv`
- `faithfulness_metrics.csv`
- `stability_metrics.csv`
- `structure_alignment.csv`
- `runtime.json`
- 논문용 비가역 집계 figure

모든 파일은 `protocol_id`, Git commit, dataset revision, split hash, checkpoint hash와
생성 명령을 포함해야 한다. 과거 v1–v3 결과를 이 폴더로 복사하지 않는다.
