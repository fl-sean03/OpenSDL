from __future__ import annotations

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
        return (
            fnmatch(capability.id, self.capability)
            and any(fnmatch(environment, pattern) for pattern in self.environments)
            and any(fnmatch(operator_id, pattern) for pattern in self.operators)
            and any(pattern == "*" or pattern == capability.risk_class.value for pattern in self.risk_classes)
        )


class PolicyDecision(OpenSDLModel):
    effect: AuthorizationEffect
    allowed: bool
    reason: str
    rule_id: str | None = None
    policy_version: str


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

    def evaluate(
        self,
        capability: CapabilityDefinition,
        operator_id: str,
        environment: str,
    ) -> PolicyDecision:
        for rule in self.rules:
            if rule.matches(capability, operator_id, environment):
                return PolicyDecision(
                    effect=rule.effect,
                    allowed=rule.effect == AuthorizationEffect.ALLOW,
                    reason=rule.reason or f"matched policy rule {rule.id}",
                    rule_id=rule.id,
                    policy_version=self.version,
                )
        return PolicyDecision(
            effect=self.default_effect,
            allowed=self.default_effect == AuthorizationEffect.ALLOW,
            reason="default policy effect",
            policy_version=self.version,
        )
