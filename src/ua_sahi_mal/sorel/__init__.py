"""SOREL-20M selection and gated acquisition tooling (amendment §5/§6/§9).

Compliance boundary (G0-S determination, 2026-09-08 — PARTIAL / publication
permission pending):
  * Legitimate internal security research use: permitted subject to the SOREL Terms.
  * A public SHA manifest is NOT permitted without written authorization.
  * Public sample-linked derived intervals are NOT permitted without written
    authorization.
  * Aggregate publication results: written clarification required (Terms §2(c)
    broadly restricts derivative works).

Practical consequences enforced by this package:
  * ``select``/``manifest`` never write SHA lists into the repository tree; the
    output-path guards in ``paths`` refuse repo-relative and common cloud-sync
    destinations.
  * ``acquire`` never downloads into the repo or a sync folder, keeps binaries
    zlib-compressed, never re-arms (Machine/Subsystem), and requires an explicit
    Terms acknowledgement plus a byte budget.
"""

from __future__ import annotations
