from __future__ import annotations

import hashlib
import json
from fnmatch import fnmatch
from typing import Literal

from pydantic import Field

from opensdl_core import AuthorizationEffect, CapabilityDefinition, OpenSDLModel


class PolicyRule(OpenSDLModel):
    id: str
    effect: AuthorizationEffect
    capability: str = "*"
    environments: list[str] = Field(default_factory=lambda: ["*"])
    operators: list[str] = Field(default_factory=lambda: ["*"])
    risk_classes: list[str] = Field(default_factory=lambda: ["*"])
    reason: str = ""
    priority: int = 100

    def matches(self, capability: CapabilityDefinition, operator_id: str, environment: str) -> bool:
        """Whether this rule decides this request. Four selectors, all of which must admit it.

        Three of them glob. `risk_classes` compares strings, so `R*` matches no class at all —
        the asymmetry `test_risk_class_selector_is_an_exact_match_and_not_a_glob` pins.

        One thing outside this distribution depends on the semantics here. `opensdl_schemas`
        refuses to load a manifest whose `deny` rule an earlier `allow` covers completely, because
        such a rule can never reach this method: evaluation takes the first match in priority order
        and a deny does not override an earlier allow. That analysis cannot import this package —
        the boundary in `scripts/check-boundaries.py` forbids it — so it reimplements what "covers"
        means and `packages/schemas/tests/test_manifest_policy.py` holds the two together by
        evaluating every pair it reports against this engine. Changing what this method matches
        will fail there, which is the intended place to find out.
        """
        return (
            fnmatch(capability.id, self.capability)
            and any(fnmatch(environment, pattern) for pattern in self.environments)
            and any(fnmatch(operator_id, pattern) for pattern in self.operators)
            and any(
                pattern == "*" or pattern == capability.risk_class.value
                for pattern in self.risk_classes
            )
        )


class PolicyDecision(OpenSDLModel):
    """One authorization outcome, recorded verbatim in the durable `PolicyEvaluated` event.

    `policy_version` is the operator's claim: a free-form string copied from the manifest that is
    bound to no rule content. `policy_digest` is the checkable half — a digest of the effective
    ruleset that produced this decision, so two recorded decisions can be compared without trusting
    the label.
    """

    effect: AuthorizationEffect
    allowed: bool
    reason: str
    rule_id: str | None = None
    policy_version: str
    policy_digest: str


class PolicyEngine:
    def __init__(
        self,
        rules: list[PolicyRule] | None = None,
        default_effect: Literal["allow", "deny"] = "deny",
        version: str = "built-in/v0alpha1",
    ) -> None:
        self.rules = sorted(rules or [], key=lambda rule: rule.priority)
        self.default_effect = AuthorizationEffect(default_effect)
        self.version = version

    @property
    def digest(self) -> str:
        """`sha256:` digest of the effective ruleset, over canonical JSON.

        Computed from `self.rules` on every read rather than cached at construction, so an engine
        whose rules were replaced after construction cannot stamp a stale digest onto a decision.
        The cost is one small hash per authorization, alongside a database write and an adapter
        call.

        Everything that can change an outcome is inside the digest: every rule field, the order the
        rules are evaluated in, and the default effect. The free-form `version` label is outside it,
        so the digest answers exactly one question — did the rules change? — and identical rules
        compare equal across laboratories that label their policy differently.
        """
        canonical = json.dumps(
            {
                "defaultEffect": self.default_effect.value,
                "rules": [rule.model_dump(mode="json", by_alias=True) for rule in self.rules],
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(canonical).hexdigest()}"

    def evaluate(
        self,
        capability: CapabilityDefinition,
        operator_id: str,
        environment: str,
    ) -> PolicyDecision:
        digest = self.digest
        for rule in self.rules:
            if rule.matches(capability, operator_id, environment):
                return PolicyDecision(
                    effect=rule.effect,
                    allowed=rule.effect == AuthorizationEffect.ALLOW,
                    reason=rule.reason or f"matched policy rule {rule.id}",
                    rule_id=rule.id,
                    policy_version=self.version,
                    policy_digest=digest,
                )
        return PolicyDecision(
            effect=self.default_effect,
            allowed=self.default_effect == AuthorizationEffect.ALLOW,
            reason="default policy effect",
            policy_version=self.version,
            policy_digest=digest,
        )
