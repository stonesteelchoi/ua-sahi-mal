# Reference index and source policy

The canonical bibliography for the manuscript is [`UA_SAHI_Mal_references.bib`](UA_SAHI_Mal_references.bib). This index records the primary sources that materially affect the v3 design decision and the exact upstream revision used for reproducibility planning.

## Decision-critical sources

| Source | Official location | v3 role | Verification/status on 2026-09-04 |
|---|---|---|---|
| DeepReflect paper | [USENIX Security 2021](https://www.usenix.org/conference/usenixsecurity21/presentation/downing) | primary prior-system baseline | official paper, slides, video, and BibTeX available |
| DeepReflect code | [evandowning/deepreflect](https://github.com/evandowning/deepreflect) | faithful baseline implementation | live; GPL-3.0; pin `4358a7e8ef7fc5951360094867dca852ed23712e` |
| DeepReflect artifact index | [`Dataset.md`](https://github.com/evandowning/deepreflect/blob/main/Dataset.md) | extracted features and small source-grounded seed | links are published; includes real-malware archives requiring controlled handling |
| DECODE article | [Scientific Reports 15, 37979](https://doi.org/10.1038/s41598-025-21848-z) | related work, explicitly not a direct baseline | open-access article under CC BY 4.0 |
| DECODE code/data index | [dtuuba/DECODE-DEep_Classification_Of_Dynamic_Exploits](https://github.com/dtuuba/DECODE-DEep_Classification_Of_Dynamic_Exploits) | verifies dynamic API-image/pseudo-box task mismatch | live; pin `e6a7aaf99dd8a80d0319416ff3b980887c754fee`; no repository license was visible during review, so do not vendor |
| EMBER2024 paper | [arXiv:2506.05074](https://arxiv.org/abs/2506.05074) and DOI in BibTeX | file-level corpus context | official paper and project links available |
| EMBER2024-capa | [Hugging Face dataset](https://huggingface.co/datasets/joyce8/EMBER2024-capa) | Tier 2 silver function bytes/disassembly | ~18.6M non-deduplicated malicious Win32/Win64 function records; Apache-2.0; ~23.8 GB |
| SAHI | [ICIP 2022 DOI](https://doi.org/10.1109/ICIP46576.2022.9897990) | slicing lineage and Full-SAHi comparison | citation recorded in BibTeX |
| Upsample Anything | [arXiv:2511.16301](https://arxiv.org/abs/2511.16301) and [official code](https://github.com/seominseok0429/Upsample-Anything_Pytorch) | optional reconstruction component | code pin `39251463a8bb352785c063c3c3f941f1dcdf4c51`; local provenance in `external/upsample-anything/VENDORED_SOURCE.md` |

## Why third-party PDFs are not mirrored here

The repository stores the project's own draft PDF in `paper/draft/`. It does not copy every cited third-party PDF into Git. Public download access is not automatically a redistribution license, and binary paper copies create stale duplicates that no longer follow corrections at the publisher.

Use the official links above and the URLs/DOIs in BibTeX. A third-party PDF may be added only when all of the following are recorded:

1. the exact source URL and retrieval date;
2. a license that permits repository redistribution;
3. authorship and required attribution;
4. SHA-256 of the stored file;
5. confirmation that the file contains no malware sample or restricted supplement.

## Malware and licensed-tool artifacts

- Never commit DeepReflect's password-protected `malware.zip`, source-grounded malware binaries, or any derived executable.
- Never commit Binary Ninja binaries or `license.dat`.
- Never commit EMBER/BODMAS raw malware or reversible malware images.
- Store hashes, annotations, build recipes, nonexecutable extracted records, and access instructions where redistribution is not allowed.

## Citation maintenance

- Prefer the publication record for scholarly claims and the artifact record for implementation/version claims.
- Keep dataset version, retrieval date, license, and deduplication caveat in the methods or artifact appendix.
- Before submission, validate every DOI/URL, run a missing/unused citation check, and regenerate Markdown, TeX, and PDF from the same bibliography revision.
