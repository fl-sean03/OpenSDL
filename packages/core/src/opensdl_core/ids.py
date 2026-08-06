from __future__ import annotations

import re
from typing import Annotated, TypeAlias
from uuid import uuid4

from pydantic import AfterValidator, StringConstraints


RUN_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$"
_RUN_ID = re.compile(RUN_ID_PATTERN, flags=re.ASCII)


def validate_run_id(value: str) -> str:
    """Validate a portable run identifier suitable for routes and filenames."""
    if not isinstance(value, str) or _RUN_ID.fullmatch(value) is None:
        raise ValueError(
            "run ID must be 1-80 ASCII characters, start with an alphanumeric "
            "character, and contain only alphanumerics, '.', '_', or '-'"
        )
    return value


RunId: TypeAlias = Annotated[
    str,
    StringConstraints(min_length=1, max_length=80, pattern=RUN_ID_PATTERN),
    AfterValidator(validate_run_id),
]

#: A campaign identifier, with the run identifier's grammar and for the same reason: it is used in
#: a URL path and in a file name, so it must not carry a separator or an escape.
#:
#: It is deliberately not applied to `EventRecord.campaign_id`. That field's published schema would
#: then constrain identifiers minted before the constraint existed, and an event log is a record of
#: what happened rather than a document to be revalidated.
CampaignId: TypeAlias = RunId


def new_id(prefix: str) -> str:
    """Return a readable, globally unique identifier."""
    clean = prefix.strip().lower().replace(" ", "-")
    if not clean:
        raise ValueError("identifier prefix cannot be empty")
    return f"{clean}_{uuid4().hex}"
