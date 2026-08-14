from __future__ import annotations

from collections.abc import Sequence
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import ConfigDict, Field, PrivateAttr, ValidationError, model_validator

from opensdl_core import CapabilityDefinition, LabMetadata, OpenSDLModel, Resource, RiskClass

from .secrets import (
    ManifestSecretError,
    SecretReference,
    format_path,
    redact,
    resolve_secret_references,
)


class DatabaseConfig(OpenSDLModel):
    url: str = "sqlite:///./.opensdl/opensdl.db"


class ArtifactStoreConfig(OpenSDLModel):
    root: str = ".opensdl/artifacts"


class StorageConfig(OpenSDLModel):
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    artifacts: ArtifactStoreConfig = Field(default_factory=ArtifactStoreConfig)


class RuntimeConfig(OpenSDLModel):
    max_concurrency: int = Field(default=4, gt=0)
    default_timeout_seconds: float = Field(default=60.0, gt=0)
    lease_ttl_seconds: float = Field(default=300.0, gt=0)
    #: How long a task waits for an instrument another task is holding before it gives up. A
    #: laboratory queues for equipment; it does not abandon an experiment because a colleague
    #: reached the balance first. Zero restores the older behaviour of failing on first contention,
    #: which is what a caller wanting to know immediately that the bench is busy should set.
    lease_wait_seconds: float = Field(default=120.0, ge=0)


class AdapterConfig(OpenSDLModel):
    name: str
    plugin: str
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class CapabilityBinding(OpenSDLModel):
    """Binds one capability identifier to the adapter that must provide it.

    A binding selects and enables; it carries no configuration. Configuration reaches an executor
    through `spec.adapters[].config`, which the composition root passes to the plugin factory.

    There was a `config` field here. Nothing ever read it, and a per-capability `config:` is
    precisely where an operator writes operating limits — the deployment obligation `SAFETY.md`
    describes. Enforcing an operating envelope is unbuilt design work, so the field is removed
    rather than left absorbing safety configuration in silence.
    """

    capability: str
    adapter: str
    enabled: bool = True

    @model_validator(mode="before")
    @classmethod
    def reject_binding_configuration(cls, data: Any) -> Any:
        if isinstance(data, dict) and "config" in data:
            raise ValueError(
                "capability bindings carry no configuration: 'config' was accepted and never "
                "read. Adapter configuration belongs in spec.adapters[].config. OpenSDL has no "
                "operating-envelope mechanism, so operating limits belong in the deployment "
                "controls SAFETY.md describes, not in this manifest."
            )
        return data


class PolicyRuleSpec(OpenSDLModel):
    id: str
    effect: Literal["allow", "deny"]
    capability: str = "*"
    environments: list[str] = Field(default_factory=lambda: ["*"])
    operators: list[str] = Field(default_factory=lambda: ["*"])
    risk_classes: list[str] = Field(default_factory=lambda: ["*"])
    reason: str = ""
    priority: int = 100


#: Every character `fnmatch` reads as a pattern rather than as itself.
_GLOB_METACHARACTERS = frozenset("*?[")

#: The closed set of risk classes a rule may name. `risk_classes` is the one selector the policy
#: engine compares as strings, so anything outside this set plus `*` matches nothing.
_DECLARED_RISK_CLASSES = frozenset(risk_class.value for risk_class in RiskClass)

#: Selectors that are lists of patterns. An empty one matches nothing, whatever the rule says.
_LIST_SELECTORS = ("environments", "operators", "risk_classes")


def _is_literal(pattern: str) -> bool:
    """Whether `pattern` matches exactly one string — itself."""
    return not (_GLOB_METACHARACTERS & set(pattern))


def _glob_covers(broader: str, narrower: str) -> bool:
    """Whether every identifier `narrower` matches is also matched by `broader`.

    Deliberately partial. Glob containment is decidable — both sides are regular — but the general
    case needs an automaton, and a wrong answer here refuses a laboratory's entire configuration.
    Three shapes are proved and everything else answers `False`:

    * identical patterns, and any pattern made only of `*`, which matches everything;
    * a `narrower` with no metacharacter, where `fnmatch` decides the question exactly;
    * a `broader` of the form `prefix*` with a literal prefix, against a `narrower` whose first
      `len(prefix)` characters are that same literal prefix — every string `narrower` matches then
      begins with it.

    `sim.*` therefore covers `sim.hazardous` and `sim.haz*`, and is *not* reported as covering
    `*.hazardous` or `sim.?azardous` even where it does.
    """
    if broader == narrower or set(broader) == {"*"}:
        return True
    if _is_literal(narrower):
        return fnmatch(narrower, broader)
    if broader.endswith("*") and _is_literal(broader[:-1]):
        prefix = broader[:-1]
        return narrower.startswith(prefix) and _is_literal(narrower[: len(prefix)])
    return False


def _selector_covers(broader: Sequence[str], narrower: Sequence[str]) -> bool:
    """Whether every value the `narrower` patterns admit is admitted by some `broader` pattern.

    Sufficient rather than necessary: patterns that only jointly cover one of `narrower` are not
    recognised, which is the safe direction.
    """
    return all(any(_glob_covers(b, n) for b in broader) for n in narrower)


def _risk_classes(entries: Sequence[str]) -> frozenset[str]:
    """The risk classes a rule actually admits, which is not what it lists.

    `*` admits every class. Any other entry admits itself and only if it names a declared class,
    because the engine compares these as strings.
    """
    if "*" in entries:
        return _DECLARED_RISK_CLASSES
    return frozenset(entries) & _DECLARED_RISK_CLASSES


def _covers(broader: PolicyRuleSpec, narrower: PolicyRuleSpec) -> bool:
    """Whether every request `narrower` matches is also matched by `broader`.

    Each of the four selectors is required to cover independently. Capability identifier and risk
    class are two attributes of one capability and are treated here as free dimensions, so a pair
    that only covers over the capabilities a particular laboratory happens to declare is not
    reported. That is stricter than the truth, and strictness is the direction without false
    positives.
    """
    return (
        _glob_covers(broader.capability, narrower.capability)
        and _selector_covers(broader.environments, narrower.environments)
        and _selector_covers(broader.operators, narrower.operators)
        and _risk_classes(narrower.risk_classes) <= _risk_classes(broader.risk_classes)
    )


def shadowed_deny_rules(
    rules: Sequence[PolicyRuleSpec],
) -> list[tuple[PolicyRuleSpec, PolicyRuleSpec]]:
    """Every `(allow, deny)` pair where the allow provably makes the deny dead code.

    The policy engine sorts by ascending priority, takes the first matching rule, and stops; a
    `deny` does not override an earlier `allow`. So a deny that some earlier allow matches for
    every request the deny matches can never decide anything. Evaluation is not changed by this
    function — `packages/policy` still behaves exactly as it did — but a manifest containing such a
    rule is refused rather than loaded, because the operator who wrote it meant it to do something.

    Incomplete by construction, in three known ways: coverage is proved one allow at a time, so
    allows that only jointly cover a deny are missed; `_glob_covers` proves only the shapes it can;
    and a *partial* shadow — an allow broader in one selector and narrower in another — is not
    detectable this way at all and is not attempted. An empty result is therefore not a proof that
    a deny can fire.

    `packages/schemas/tests/test_manifest_policy.py` pairs every selector shape with every other
    and evaluates each reported pair against the real engine, which is what keeps this function's
    idea of "covers" tied to `PolicyRule.matches` across a distribution boundary the import graph
    forbids crossing.
    """
    # `sorted` is stable, and so is the engine's: equal priorities keep declaration order.
    ordered = sorted(rules, key=lambda rule: rule.priority)
    shadowed: list[tuple[PolicyRuleSpec, PolicyRuleSpec]] = []
    for position, rule in enumerate(ordered):
        if rule.effect != "deny":
            continue
        for earlier in ordered[:position]:
            if earlier.effect == "allow" and _covers(earlier, rule):
                shadowed.append((earlier, rule))
                break
    return shadowed


class PolicyConfig(OpenSDLModel):
    default_effect: Literal["allow", "deny"] = "deny"
    version: str = "local/v0alpha1"
    rules: list[PolicyRuleSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_rules_that_can_never_fire(self) -> PolicyConfig:
        """Refuse a rule that is dead code, rather than loading it and authorizing nothing.

        Three failures, all of them silent before this: a selector list that is empty, a risk class
        written as a glob, and a `deny` an earlier `allow` completely covers. None of them changes
        what a correct manifest means; each of them turns an operator's mistaken intent into a
        message instead of a laboratory that quietly does the opposite of what its policy says.
        """
        for rule in self.rules:
            for selector in _LIST_SELECTORS:
                if not getattr(rule, selector):
                    raise ValueError(
                        f"policy rule {rule.id!r} lists no {selector}, so it matches no request "
                        f"and can never take effect. Name the {selector} it applies to, or use "
                        f"'*' for all of them."
                    )
            for entry in rule.risk_classes:
                if entry != "*" and entry not in _DECLARED_RISK_CLASSES:
                    raise ValueError(
                        f"policy rule {rule.id!r} names risk class {entry!r}, which OpenSDL does "
                        f"not declare. Unlike capability, environments and operators, "
                        f"risk_classes is compared as a string and never globbed, so a pattern "
                        f"such as 'R*' matches no class at all and the rule silently applies to "
                        f"nothing. Use '*' for every class, or any of "
                        f"{sorted(_DECLARED_RISK_CLASSES)}."
                    )
        for allowing, denied in shadowed_deny_rules(self.rules):
            raise ValueError(
                f"policy rule {denied.id!r} can never take effect: rule {allowing.id!r} (allow, "
                f"priority {allowing.priority}) is evaluated first and matches every request "
                f"{denied.id!r} (deny, priority {denied.priority}) would match. Rules are "
                f"evaluated in ascending priority, the first match decides, and a deny does not "
                f"override an earlier allow — so this deny is dead code. Give {denied.id!r} a "
                f"priority below {allowing.priority}, or narrow {allowing.id!r}. This check "
                f"reports only a deny that one earlier allow covers in every selector: it cannot "
                f"detect a partial shadow, where an allow is broader in one selector and narrower "
                f"in another, so a manifest that loads is not proof that its deny rules fire."
            )
        return self


class DomainPackConfig(OpenSDLModel):
    name: str
    plugin: str
    config: dict[str, Any] = Field(default_factory=dict)


class TwinConfig(OpenSDLModel):
    definition: str
    viewer_root: str | None = None


class LabSpec(OpenSDLModel):
    environment: str = "simulation"
    storage: StorageConfig = Field(default_factory=StorageConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    adapters: list[AdapterConfig] = Field(default_factory=list)
    capabilities: list[CapabilityBinding] = Field(default_factory=list)
    resources: list[Resource] = Field(default_factory=list)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)
    domain_packs: list[DomainPackConfig] = Field(default_factory=list)
    twin: TwinConfig | None = None
    extensions: dict[str, Any] = Field(default_factory=dict)


class LabManifest(OpenSDLModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, validate_assignment=True)

    api_version: Literal["opensdl.dev/v0alpha1"] = Field(
        default="opensdl.dev/v0alpha1", alias="apiVersion"
    )
    kind: Literal["Laboratory"] = "Laboratory"
    metadata: LabMetadata
    spec: LabSpec

    #: Every `${provider:name}` reference `load_manifest` resolved, and the literal text it stood
    #: in for. The model carries resolved values because adapters need them; this is what lets a
    #: serializer put the reference back. A manifest built in memory has none.
    _secret_references: tuple[SecretReference, ...] = PrivateAttr(default=())

    @property
    def secret_references(self) -> tuple[SecretReference, ...]:
        return self._secret_references


def load_manifest(path: str | Path) -> LabManifest:
    """Load, resolve secret references, and validate one laboratory manifest.

    Resolution happens on the raw document, before validation, so every consumer of the model sees
    ordinary values and nothing downstream has to know a credential was named rather than written.
    Validation failures are re-raised with resolved values replaced by the references they came
    from: Pydantic reports the input it rejected, and the CLI prints an exception's message
    verbatim on stderr.
    """
    source = Path(path)
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"manifest must contain a mapping: {source}")
    try:
        resolved, references = resolve_secret_references(data)
    except ManifestSecretError as error:
        raise ManifestSecretError(f"{source}: {error}") from None
    try:
        manifest = LabManifest.model_validate(resolved)
    except ValidationError as error:
        if not references:
            raise
        raise ValueError(f"{source}: {redact(str(error), references)}") from None
    manifest._secret_references = references
    return manifest


def redacted_manifest_document(manifest: LabManifest) -> dict[str, Any]:
    """The manifest as a JSON-ready document, with every resolved reference written back.

    Use this anywhere a manifest is serialized, printed, or exported. It restores by *path*, so a
    value that merely happens to equal a secret is untouched and a reference embedded in a longer
    string is reproduced whole.
    """
    document = manifest.model_dump(mode="json", by_alias=True, exclude_none=True)
    for reference in manifest.secret_references:
        _restore(document, reference)
    return document


def _restore(document: dict[str, Any], reference: SecretReference) -> None:
    node: Any = document
    for element in reference.path[:-1]:
        try:
            node = node[element]
        except (KeyError, IndexError, TypeError) as error:  # pragma: no cover - defensive
            raise ValueError(
                f"cannot redact the secret at {format_path(reference.path)}: the serialized "
                f"manifest has no such path, so the resolved value would be emitted"
            ) from error
    node[reference.path[-1]] = reference.reference


def dump_manifest(manifest: LabManifest, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = redacted_manifest_document(manifest)
    target.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def embedded_capability_schema() -> dict[str, Any]:
    return CapabilityDefinition.model_json_schema()
