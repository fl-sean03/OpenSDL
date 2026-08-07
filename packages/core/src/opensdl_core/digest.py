"""One way to take a digest of a captured document, so two records cannot disagree.

A digest is only useful as evidence if the bytes it was taken over are reproducible from the
document alone. JSON is not: key order, separator whitespace, and non-ASCII escaping all vary by
writer while the document does not. So a canonical form is fixed here — sorted keys, no spaces,
ASCII escapes — and every digest OpenSDL records is taken over that form.

The twin binding pinned onto a run was the first user and is still the reference case: a run
records the canonical digest of the twin definition it ran against, and projection refuses a
mismatch. A run now records the same kind of digest of the workflow definition its ``RunCreated``
captured, and a resume refuses a mismatch for the same reason — a record that cannot say what it
was asked to do is not evidence of having done it.

This deliberately does not hash a pydantic model directly. What is worth digesting is the document
that was *written down*, because that is what a later reader holds; passing the model's own dump in
keeps the digest a statement about the record rather than about the process that produced it.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(document: Any) -> bytes:
    """The one byte form of a JSON-able document that a digest may be taken over."""

    return json.dumps(
        document,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_digest(document: Any) -> str:
    """The SHA-256 of :func:`canonical_json`, as lowercase hexadecimal.

    ``document`` must already be JSON-able — the output of ``model_dump(mode="json")`` rather than
    a model — so that a reader holding only the recorded document can recompute the same value.
    """

    return hashlib.sha256(canonical_json(document)).hexdigest()
