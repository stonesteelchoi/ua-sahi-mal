# Security and malware-data policy

UA-SAHI-MAL is intended for defensive malware research. The public Git repository contains code, documentation, and synthetic fixtures only.

## Never commit

- PE, ELF, APK, DEX, sample-carried scripts, archives, memory dumps, packet captures, or other real malware artifacts
- private dynamic-analysis reports that contain victim, network, credential, or filesystem information
- API keys for VirusTotal, MalwareBazaar, experiment tracking, cloud storage, or GitHub
- model checkpoints or generated datasets unless their license and release process have been reviewed separately

The `.gitignore` and `scripts/check_repository_safety.py` provide a guardrail, not a sandbox. Review every staged file before pushing.

## Processing boundary

- `existing-image` loads an already-sanitized image with Pillow.
- `opcode-3gram-rgb` accepts only a strict text stream of two-digit hexadecimal tokens.
- `raw-rgb` performs bounded file reads and maps bytes to pixels.
- None of these encoders execute, import, emulate, disassemble, or dynamically load the input.
- `raw-rgb` is losslessly reversible and sliding opcode RGB is substantially reversible. Their PNG outputs remain sensitive malware-derived artifacts even though opening the PNG does not execute the sample.
- Encoded PNGs include a `ua_sahi_mal_sensitive` metadata marker. The repository scanner rejects marked PNGs, but metadata can be stripped; do not treat this guardrail as data-loss prevention.
- Dynamic analysis and disassembly must happen in a separately administered, isolated environment. Transfer only approved reports, token streams, images, hashes, and annotations into this pipeline.

Use a dedicated non-administrator account, restrict outbound network access, store samples on encrypted/quarantined media, and follow the dataset provider's terms. Do not rely on this repository as the containment boundary.

## Model and dependency trust

Model checkpoints may use serialization formats capable of executing code when loaded. Use weights from a trusted origin, record their SHA-256, and prefer safer serialization formats when supported. Verify dependency sources and pinned versions before reproducing an experiment.

The Upsample Anything submodule had no explicit license file when integrated. Do not copy, modify, or redistribute its source without permission from its authors.

## Reporting a vulnerability

Use the GitHub repository's private Security Advisory flow. Do not attach a live sample, credential, exploit archive, or sensitive sandbox report. Provide a minimal synthetic reproduction and hashes when possible.
