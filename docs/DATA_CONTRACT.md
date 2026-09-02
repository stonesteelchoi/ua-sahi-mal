# Dataset and annotation contract

## Why the contract comes first

A malware family label assigned to an entire image is a classification label, not an object-detection label. YOLO training requires spatial evidence. UA-SAHI-MAL therefore refuses to infer boxes from a file-level class silently: every object must have either a direct `bbox_xywh` or a source `start`/`end` interval that can be mapped to pixels.

## Manifest version 1

The manifest is UTF-8 JSON with these root keys:

- `version`: exactly `1`
- `name`: immutable dataset revision name
- `categories`: ordered, unique category objects with contiguous IDs beginning at 1
- `samples`: one object per unique source artifact or existing visualization

Each sample contains:

- `sample_id`: stable `[A-Za-z0-9_.-]` identifier; it cannot create a path
- `source`: local absolute path or path relative to the manifest
- `sha256`: optional expected digest; preparation always calculates and records the actual digest
- `split`: `train`, `val`, or `test`
- `family_id`: optional group key; one value cannot cross splits
- `encoding`: `existing-image`, `word16-rgb`, `opcode-3gram-rgb`, or `raw-rgb`
- `width`: row width for generated RGB encodings; ignored by `existing-image`
- `annotations`: zero or more spatial evidence annotations

Benign images may have an empty annotation list. Duplicate source hashes are rejected even within the same split; combine their labels into one sample instead.

Dataset preparation requires both `train` and `val`. An independently reviewed `test` split is strongly required for the paper's primary localization claim, although pilot preparation can omit it.

## Coordinate rules

All ranges are half-open: `[start, end)`.

### Existing image

The image is converted to RGB without resize. A direct COCO-style `bbox_xywh` is preferred. Pixel-index ranges are accepted when an independent tool reports row-major positions.

### Raw RGB

Bytes are grouped as non-overlapping triples:

```text
pixel 0 = bytes [0, 1, 2]
pixel 1 = bytes [3, 4, 5]
...
```

The last pixel is zero-padded. No image resize is performed.

### 16-bit word RGB

`word16-rgb-v1` divides the approved static byte stream into non-overlapping, big-endian 16-bit words. One word maps losslessly to one RGB pixel:

```text
word 0xA1B2 → pixel (0xA1, 0xB2, 0xA1 XOR 0xB2)
```

The first two channels preserve the complete word; the XOR channel is a deterministic derived feature. An odd final byte is right-padded with `0x00`, metadata retains the unpadded source byte count, and source ranges use a two-byte stride. This is an optional representation ablation, not the DECODE ASCII behavior-image algorithm. Do not mix results from the two representations under one dataset revision.

### Opcode sliding 3-gram RGB

The input must be sanitized text such as:

```text
48 8B 05 FF 10 20
```

The pixels are sliding windows:

```text
pixel 0 = (48, 8B, 05)
pixel 1 = (8B, 05, FF)
pixel 2 = (05, FF, 10)
pixel 3 = (FF, 10, 20)
```

A source opcode interval maps to every window that overlaps it. When the resulting row-major pixel interval crosses image rows, the exporter creates up to three exact rectangles: first partial row, complete middle rows, and last partial row. This avoids including unrelated pixels in one oversized rectangle.

The definition above is versioned as `opcode-3gram-rgb-v1`. If the research later chooses non-overlapping 3-grams or hashed n-grams, it must use a new encoder version and a new prepared dataset revision.

### Static behavior-report visualization

`encode-behavior-report` accepts one already-produced UTF-8 JSON object with a `behavior.processes[]` array and a `calls[]` array for every process. It does not execute a sample, import executable code, contact a sandbox, or request a dynamic-analysis job. Only two call fields participate in the visualization:

- `category`: one of `process`, `registry`, `network`, `filesystem`
- `api`: a non-empty ASCII API name of at most 512 characters

Arguments, return values, buffers, payloads, process paths, and all other keys are ignored. Consecutive duplicate `(category, api)` calls are removed within a process, and a later process with the same cleaned sequence is ignored. Other call categories are counted as ignored but not rendered.

For each category, API names are concatenated without delimiters and each ASCII code is scaled by `floor(256 × code / 128)`. An empty category becomes black; a short sequence is repeated to fill 128×128 pixels; a long sequence is truncated. Each category image is nearest-neighbor upscaled to 256×256 and placed as follows:

```text
+----------------------+----------------------+
| process              | registry             |
+----------------------+----------------------+
| network              | filesystem           |
+----------------------+----------------------+
```

The resulting 512×512 RGB representation is versioned `decode-static-behavior-v1`. It is deliberately called **DECODE-like**, not an exact DECODE reproduction: the public DECODE pipeline contains additional dataset-specific sequence reduction, padding, and tiling choices that are not silently approximated here. Changing any of these rules requires a new encoder and dataset revision.

The PNG includes `ua_sahi_mal_sensitive=true`; the adjacent metadata JSON records the source SHA-256, quadrant order, API counts, ignored count, and per-category truncation/repetition counts. The resulting PNG may be registered in a manifest as `existing-image`, but object boxes must still come from an independent ROI source or human review. This converter never infers behavior-class boxes.

## Annotation provenance

Every annotation requires `annotation_source`:

- `human_verified`
- `bayesian_gradcam`
- `source_range`
- `synthetic`

Bayesian Grad-CAM labels also require `annotation_version`; `teacher_model`, `source_score`, threshold, dropout passes, and component-filter settings should be encoded into the versioned pseudo-label manifest or teacher checkpoint record.

The exporter keeps COCO JSON standard and writes non-standard evidence to `annotation_provenance.jsonl`. Each generated component records its source range/direct box, source SHA-256, encoder version, teacher metadata, score, and verification flag.

## Split and evaluation rules

1. Split original samples before training the teacher classifier.
2. Keep identical SHA-256 values out of all duplicate positions.
3. Keep family/source groups in one split.
4. Train the teacher on train only.
5. Generate train/val/test pseudo-labels with a frozen teacher.
6. Tune detector and routing settings on train/val only.
7. Use a human-verified or independently localized test subset for the primary localization claim.
8. Report pseudo-label agreement and human-verified localization as separate results.

Random image splitting after derived images or pseudo-boxes have been generated is not allowed because it can leak near-duplicate variants and teacher training information.

## Prepared output

`prepare-data` produces:

- lossless PNG images
- normalized YOLO label text
- strict COCO JSON per available split
- annotation provenance JSONL
- a prepared manifest without absolute source paths
- a relative-path Ultralytics `dataset.yaml`

Original artifacts are never copied to the prepared directory.

The RGB pixels may nevertheless preserve the original byte/opcode stream. Prepared images inherit the source artifact's sensitivity, include a machine-readable PNG marker, and must remain in an approved non-Git location. `--allow-sensitive-output` is an explicit acknowledgement, not permission to redistribute the result.
