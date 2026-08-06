"""Resolution of `${provider:name}` references in a laboratory manifest.

A manifest is a committed file. Everything it needs to reach a real instrument is in it, which
until now included the instrument's password: there was no interpolation, no provider, and no
`SecretStr`, so `spec.adapters[].config` travelled verbatim from a Git-tracked file to the adapter.

This module gives a manifest a way to *name* a credential instead of carrying one. It resolves
references in the raw document, before validation, so nothing downstream has to know a value came
from somewhere else.

The scheme is `${provider:name}`. Exactly one provider is implemented — `env`, which reads a
process environment variable. The prefix exists so a real secret provider can be added later
without changing a single manifest that already works; an unimplemented prefix is refused by name
rather than ignored.

Three rules govern where a reference may appear and what happens when it does not resolve.

**Unresolved is an error, never a value.** A reference to a variable that is not set, or set to the
empty string, raises. The alternative — substituting `""` or leaving the literal text in place —
produces an authentication failure at an instrument, hours later, in a laboratory. That is a much
worse place to discover a misspelled variable name than the loader.

**A reference resolves a value, not a key.** `${env:FIELD}: x` would let the environment decide
which field is being configured, which is a different and much larger power than supplying its
contents. It is refused.

**Policy is not resolvable.** `spec.policy` decides whether a capability may execute. Allowing
`default_effect: ${env:EFFECT}` makes `EFFECT=allow` a supported configuration for a live
laboratory, and `SECURITY.md` names authorization bypass the first vulnerability class. Every other
field in a manifest is configuration; this subtree is an authorization decision, so it is refused.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

#: `${provider:name}`. A `${...}` without a provider prefix is not a secret reference and is left
#: exactly as written — workflow references such as `${inputs.sample_id}` pass through untouched.
REFERENCE = re.compile(r"\$\{(?P<provider>[A-Za-z][A-Za-z0-9_-]*):(?P<name>[^{}]*)\}")

ENVIRONMENT_PROVIDER = "env"

#: Implemented providers. The one-entry shape is deliberate: it is the extension point, and a
#: reference naming anything else fails loudly instead of resolving to nothing.
PROVIDERS = (ENVIRONMENT_PROVIDER,)

#: Subtrees where a reference is refused outright, and why.
FORBIDDEN_PREFIXES: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("spec", "policy"),
        "policy decides whether a capability may execute, so resolving it from the environment "
        "would make an environment variable an authorization decision",
    ),
)

VALID_ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ManifestSecretError(ValueError):
    """A secret reference in a manifest could not be resolved, or was not allowed where it was."""


@dataclass(frozen=True)
class SecretReference:
    """One string that contained at least one reference, and what it became.

    `reference` is the literal text as written in the manifest, including any surrounding
    characters — `postgresql://opensdl:${env:PGPASSWORD}@db/lab`, not `${env:PGPASSWORD}`. That is
    what a serializer writes back, so a round-trip through `dump_manifest` reproduces the file
    rather than committing the credential.
    """

    path: tuple[str | int, ...]
    reference: str
    resolved: str


def format_path(path: tuple[str | int, ...]) -> str:
    """`("spec", "adapters", 0, "config", "token")` as `spec.adapters[0].config.token`."""
    rendered = ""
    for element in path:
        if isinstance(element, int):
            rendered += f"[{element}]"
        elif rendered:
            rendered += f".{element}"
        else:
            rendered = str(element)
    return rendered or "<document>"


def resolve_secret_references(document: Any) -> tuple[Any, tuple[SecretReference, ...]]:
    """Return the document with every reference resolved, and a record of what was resolved.

    The document is rebuilt rather than mutated, so a caller holding the parsed YAML still holds
    the unresolved form.
    """
    found: list[SecretReference] = []
    resolved = _walk(document, (), found)
    return resolved, tuple(found)


def redact(text: str, references: tuple[SecretReference, ...]) -> str:
    """Replace every resolved value in `text` with the reference it came from.

    Used on failure messages, where the alternative is a credential on stderr. It matches by value
    rather than by position, so it over-redacts when a secret is a substring of unrelated text.
    That is the right direction to be wrong in for an error message, and the wrong direction for
    structured output — which is why `redacted_manifest_document` works by path instead.
    """
    for reference in sorted(references, key=lambda item: len(item.resolved), reverse=True):
        if reference.resolved:
            text = text.replace(reference.resolved, reference.reference)
    return text


def _walk(node: Any, path: tuple[str | int, ...], found: list[SecretReference]) -> Any:
    if isinstance(node, dict):
        rebuilt: dict[Any, Any] = {}
        for key, value in node.items():
            if isinstance(key, str) and REFERENCE.search(key):
                raise ManifestSecretError(
                    f"{format_path(path)}: a secret reference resolves a value, not a key, and "
                    f"{key!r} names one. Move the reference to the value it configures."
                )
            rebuilt[key] = _walk(value, (*path, key), found)
        return rebuilt
    if isinstance(node, list):
        return [_walk(item, (*path, index), found) for index, item in enumerate(node)]
    if isinstance(node, str):
        return _resolve_string(node, path, found)
    return node


def _resolve_string(value: str, path: tuple[str | int, ...], found: list[SecretReference]) -> str:
    matches = list(REFERENCE.finditer(value))
    if not matches:
        return value
    _refuse_forbidden_location(path)
    resolved = value
    for match in reversed(matches):
        secret = _lookup(match.group("provider"), match.group("name"), path)
        resolved = resolved[: match.start()] + secret + resolved[match.end() :]
    found.append(SecretReference(path=path, reference=value, resolved=resolved))
    return resolved


def _refuse_forbidden_location(path: tuple[str | int, ...]) -> None:
    for prefix, reason in FORBIDDEN_PREFIXES:
        if tuple(path[: len(prefix)]) == prefix:
            raise ManifestSecretError(
                f"{format_path(path)}: a secret reference is not allowed under "
                f"{format_path(prefix)} because {reason}. Write the value in the manifest."
            )


def _lookup(provider: str, name: str, path: tuple[str | int, ...]) -> str:
    where = format_path(path)
    if provider not in PROVIDERS:
        implemented = ", ".join(f"{name}:" for name in PROVIDERS)
        raise ManifestSecretError(
            f"{where}: unknown secret provider {provider!r}. This release implements "
            f"{implemented} only, which reads a process environment variable."
        )
    if not VALID_ENVIRONMENT_NAME.match(name):
        raise ManifestSecretError(
            f"{where}: {name!r} is not a valid environment variable name in ${{env:{name}}}."
        )
    value = os.environ.get(name)
    if value is None:
        raise ManifestSecretError(
            f"{where}: environment variable {name} is not set. Set it before loading this "
            f"manifest; an unresolved credential is refused here rather than sent to an "
            f"instrument as an empty string."
        )
    if value == "":
        raise ManifestSecretError(
            f"{where}: environment variable {name} is set but empty. An empty credential fails "
            f"at the instrument rather than here, so it is refused."
        )
    return value
