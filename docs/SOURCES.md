# Research source provenance

No source code was copied from the research notebook or the linked repositories during the v0.2 migration. They were used to derive requirements, risks, and upstream links.

## User-provided planning material

- `최석철_개인프로젝트계획서_2-2.docx` (local planning draft; not redistributed)
- Gemini Notebook / NotebookLM: <https://notebook.google.com/notebook/ca674f09-fc53-4bbf-872b-4fe0bb70494a>

The notebook was consulted for the DECODE dynamic API visualization flow, KISA PE opcode 3-gram representation, Bayesian Grad-CAM pseudo-box concept, DexRay risks, and related implementation repositories. Notebook-generated summaries must be verified against the primary sources before publication.

## Referenced implementation repositories

- DECODE repository: <https://github.com/dtuuba/DECODE-DEep_Classification_Of_Dynamic_Exploits>
- DECODE revision inspected: [`e6a7aaf99dd8a80d0319416ff3b980887c754fee`](https://github.com/dtuuba/DECODE-DEep_Classification_Of_Dynamic_Exploits/commit/e6a7aaf99dd8a80d0319416ff3b980887c754fee)
- DECODE image generation source: <https://github.com/dtuuba/DECODE-DEep_Classification_Of_Dynamic_Exploits/blob/e6a7aaf99dd8a80d0319416ff3b980887c754fee/Malware-Object-Dataset/Malware_Image/Malware_image_generation.py>
- DECODE ROI segmentation source: <https://github.com/dtuuba/DECODE-DEep_Classification_Of_Dynamic_Exploits/blob/e6a7aaf99dd8a80d0319416ff3b980887c754fee/Malware-Object-Dataset/Segmentation/ROI_Segmentation.py>
- DECODE feature grouping directory: <https://github.com/dtuuba/DECODE-DEep_Classification_Of_Dynamic_Exploits/tree/e6a7aaf99dd8a80d0319416ff3b980887c754fee/Malware-Object-Dataset/Feature_Grouping>
- DexRay: <https://github.com/Trustworthy-Software/DexRay>
- DEYO: <https://github.com/ouyanghaodong/DEYO>
- Two-step object detection: <https://github.com/FerminT/Two-step-object-detection>
- YOLO detection/classification example: <https://github.com/JayanthSrinivas06/YOLO-Object-Detection-and-Classification-Model>
- SAHI: <https://github.com/obss/sahi>
- Upsample Anything adapter upstream: <https://github.com/seominseok0429/Upsample-Anything_Pytorch>
- Ultralytics: <https://github.com/ultralytics/ultralytics>

## Literature named in the planning sources

- Uysal et al., “[A multi-label visualisation approach for malware behaviour analysis](https://www.nature.com/articles/s41598-025-21848-z),” Scientific Reports (2025), DOI `10.1038/s41598-025-21848-z`
- Daoudi et al., “DexRay: A Simple, yet Effective Deep Learning Approach to Android Malware Detection Based on Image Representation of Bytecode” (2021)
- Akyon et al., “Slicing Aided Hyper Inference and Fine-Tuning for Small Object Detection” (SAHI, ICIP 2022)
- “Upsample Anything: Test-Time Feature Upsampling in the Wild” (CVPR 2026 source named in the plan)

## MaleVis DECODE-transfer experiment sources

- A. S. Bozkir, A. O. Cankaya, and M. Aydos, “Utilization and Comparison of Convolutional Neural Networks in Malware Recognition,” 27th SIU, 2019, DOI [`10.1109/SIU.2019.8806511`](https://doi.org/10.1109/SIU.2019.8806511). This is the primary MaleVis paper; local image counts, dimensions, hashes, and split anomalies are reported from the workspace audit rather than copied from later papers.
- Y. Gal and Z. Ghahramani, “[Dropout as a Bayesian Approximation: Representing Model Uncertainty in Deep Learning](https://proceedings.mlr.press/v48/gal16.html),” ICML/PMLR 48, 2016. Used to motivate MC dropout inference; it does not itself establish calibration gains for MaleVis.
- Y. Wen, K. Zhang, Z. Li, and Y. Qiao, “A Discriminative Feature Learning Approach for Deep Face Recognition,” ECCV 2016, DOI [`10.1007/978-3-319-46478-7_31`](https://doi.org/10.1007/978-3-319-46478-7_31). Used for the center-loss formulation adopted by DECODE and the compact transfer model.
- C. Guo, G. Pleiss, Y. Sun, and K. Q. Weinberger, “[On Calibration of Modern Neural Networks](https://proceedings.mlr.press/v70/guo17a.html),” ICML/PMLR 70, 2017. Used to define why confidence calibration must be reported separately from accuracy and to motivate ECE/NLL analysis.

The MaleVis experiment is a modality-aware transfer study: it reuses visual feature learning, center loss, and dropout sampling from the DECODE baseline, but it does not claim to reproduce CAPE dynamic-behavior encoding, Bayesian Grad-CAM ROI generation, feature grouping, EfficientDet, or multi-label localisation. Because the local MaleVis folders contain class labels but no bounding boxes, localisation metrics remain explicitly not applicable.

Before citing a statistic, architecture detail, dataset count, or license in the paper, verify it in the corresponding primary paper/repository and record the accessed revision.

For the current class-policy decision, the revision above was checked directly: initial Grad-CAM ROI records carry the target family label, while the later object-dataset construction groups visually similar regions within each family into feature-region category IDs and retains family as a supercategory. The public training code assumes pre-existing dataset directories; it does not establish the source-group/hash split contract required by this repository. These observations justify class-agnostic localization as the primary UA-routing task, `roi-family` only as an initial baseline, and an explicit feature-cluster adapter for strict DECODE reproduction.
