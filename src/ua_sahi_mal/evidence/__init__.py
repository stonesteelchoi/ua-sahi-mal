"""Evidence-region localization (research plan v2).

The v2 question is not "which bytes are malicious" -- that is undefined for a
corpus whose samples are malicious in their entirety -- but "which byte ranges
are the *evidence* a family classifier relies on".  A range is evidence when
masking it destroys the classifier's ability to name the correct family
(necessity) and keeping only it preserves that ability (sufficiency).  Both are
verified by computation, so no human annotation is required.

Nothing in this package disassembles, imports, loads, or executes a sample.  It
reads bytes and hexadecimal text only.
"""

from __future__ import annotations

__all__ = [
    "corpus",
    "criteria",
    "features",
    "metrics",
    "occlusion",
    "raster",
    "routing",
    "search",
    "synthetic",
]
