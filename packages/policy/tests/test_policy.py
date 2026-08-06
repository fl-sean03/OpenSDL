"""Tests for the authorization boundary.

`PolicyRule.matches` joins four conditions with `and` inside a single `return`, so statement and
branch coverage reach 100% from one allow/deny pair while most of the boundary stays unexercised.
These tests constrain the behaviour instead of the line count: every selector on its own, the
precedence rules an operator has to reason about, and the fields a decision carries into the audit
record.

Precedence, asserted below because none of it is obvious and all of it is load-bearing:

* Rules are evaluated in ascending `priority`. **A lower number is evaluated first.**
* **The first matching rule wins and evaluation stops.** There is no second pass.
* **`DENY` does not override `ALLOW`.** A broad allow at priority 10 beats a narrow deny at
  priority 20, so a deny rule only takes effect if it sorts ahead of every allow that also matches.
* Rules with equal priority are evaluated in declaration order.
* When nothing matches, `default_effect` decides, and it defaults to `deny`.
"""

import pytest

from opensdl_core import AuthorizationEffect, CapabilityDefinition, ExecutorType, RiskClass
from opensdl_policy import PolicyEngine, PolicyRule


def capability(
    capability_id: str = "sim.mix",
    risk_class: RiskClass = RiskClass.R1,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        id=capability_id,
        name="Mix",
        executor_type=ExecutorType.SIMULATOR,
        input_schema={},
        output_schema={},
        risk_class=risk_class,
    )


def allow(rule_id: str, **selectors: object) -> PolicyRule:
    return PolicyRule(id=rule_id, effect=AuthorizationEffect.ALLOW, **selectors)  # type: ignore[arg-type]


def deny(rule_id: str, **selectors: object) -> PolicyRule:
    return PolicyRule(id=rule_id, effect=AuthorizationEffect.DENY, **selectors)  # type: ignore[arg-type]


def test_capability_pattern_selects_by_glob() -> None:
    engine = PolicyEngine(rules=[allow("allow-sim", capability="sim.*")])

    assert engine.evaluate(capability("sim.mix"), "software/test", "simulation").allowed
    assert not engine.evaluate(capability("instrument.mix"), "software/test", "simulation").allowed


def test_environment_selector_admits_only_the_listed_environments() -> None:
    engine = PolicyEngine(rules=[allow("allow-sim", environments=["simulation", "staging-*"])])

    assert engine.evaluate(capability(), "software/test", "simulation").allowed
    assert engine.evaluate(capability(), "software/test", "staging-eu").allowed
    assert not engine.evaluate(capability(), "software/test", "live").allowed


def test_operator_selector_matches_a_glob_and_rejects_everyone_else() -> None:
    engine = PolicyEngine(rules=[allow("allow-software", operators=["software/*"])])

    assert engine.evaluate(capability(), "software/agent-7", "simulation").allowed
    assert not engine.evaluate(capability(), "human/alice", "simulation").allowed
    # The prefix has to be a path segment: `software` alone is not `software/...`.
    assert not engine.evaluate(capability(), "software", "simulation").allowed


def test_risk_class_selector_admits_only_the_listed_classes() -> None:
    engine = PolicyEngine(rules=[allow("allow-low-risk", risk_classes=["R0", "R1"])])

    assert engine.evaluate(capability(risk_class=RiskClass.R0), "software/test", "sim").allowed
    assert engine.evaluate(capability(risk_class=RiskClass.R1), "software/test", "sim").allowed
    assert not engine.evaluate(capability(risk_class=RiskClass.R2), "software/test", "sim").allowed


def test_risk_class_selector_is_an_exact_match_and_not_a_glob() -> None:
    """Unlike every other selector, `risk_classes` compares strings.

    `R*` looks like the wildcard the other three selectors accept and matches nothing. A rule
    written that way silently authorizes no capability at all.
    """
    engine = PolicyEngine(rules=[allow("looks-like-a-wildcard", risk_classes=["R*"])])

    for risk_class in RiskClass:
        assert not engine.evaluate(
            capability(risk_class=risk_class), "software/test", "sim"
        ).allowed

    assert (
        PolicyEngine(rules=[allow("real-wildcard", risk_classes=["*"])])
        .evaluate(capability(risk_class=RiskClass.R4), "software/test", "sim")
        .allowed
    )


def test_every_selector_must_match_for_a_rule_to_apply() -> None:
    rule = allow(
        "narrow",
        capability="sim.*",
        environments=["simulation"],
        operators=["software/*"],
        risk_classes=["R1"],
    )
    engine = PolicyEngine(rules=[rule])

    assert engine.evaluate(capability("sim.mix"), "software/test", "simulation").allowed
    assert not engine.evaluate(capability("robot.mix"), "software/test", "simulation").allowed
    assert not engine.evaluate(capability("sim.mix"), "software/test", "live").allowed
    assert not engine.evaluate(capability("sim.mix"), "human/alice", "simulation").allowed
    assert not engine.evaluate(
        capability("sim.mix", RiskClass.R3), "software/test", "simulation"
    ).allowed


def test_an_explicit_deny_rule_returns_a_deny_decision_rather_than_falling_through() -> None:
    """The deny branch has to return, not merely fail to match.

    With `default_effect="allow"` a fall-through would report allowed, so this distinguishes a
    real `DENY` return from the absence of a match.
    """
    engine = PolicyEngine(
        rules=[deny("deny-live", environments=["live"], reason="live work needs an operator")],
        default_effect="allow",
    )

    decision = engine.evaluate(capability(), "software/test", "live")

    assert decision.effect is AuthorizationEffect.DENY
    assert not decision.allowed
    assert decision.rule_id == "deny-live"
    assert decision.reason == "live work needs an operator"

    unmatched = engine.evaluate(capability(), "software/test", "simulation")
    assert unmatched.allowed
    assert unmatched.rule_id is None


def test_the_lowest_priority_number_is_evaluated_first() -> None:
    rules = [
        deny("deny-everything", priority=50),
        allow("allow-simulation", environments=["simulation"], priority=10),
    ]

    decision = PolicyEngine(rules=rules).evaluate(capability(), "software/test", "simulation")

    assert decision.allowed
    assert decision.rule_id == "allow-simulation"
    # Declaration order is irrelevant; only `priority` decides.
    assert (
        PolicyEngine(rules=list(reversed(rules)))
        .evaluate(capability(), "software/test", "simulation")
        .rule_id
        == "allow-simulation"
    )


def test_a_deny_rule_does_not_override_a_broader_allow_that_sorts_ahead_of_it() -> None:
    """The trap an operator falls into when adding a deny rule.

    Many authorization engines evaluate deny-overrides. This one does not: it takes the first
    match in priority order. A narrow `DENY` written after a broad `ALLOW` is dead code, and
    nothing reports that. The deny only binds once it sorts ahead of the allow.
    """
    broad_allow = allow("allow-all-simulation", capability="*", priority=10)
    narrow_deny = deny("deny-hazardous", capability="sim.hazardous", priority=20)

    ineffective = PolicyEngine(rules=[broad_allow, narrow_deny])
    decision = ineffective.evaluate(capability("sim.hazardous"), "software/test", "simulation")
    assert decision.allowed, "a later deny does not override an earlier allow"
    assert decision.rule_id == "allow-all-simulation"

    effective = PolicyEngine(
        rules=[broad_allow, deny("deny-hazardous", capability="sim.hazardous", priority=5)]
    )
    blocked = effective.evaluate(capability("sim.hazardous"), "software/test", "simulation")
    assert not blocked.allowed
    assert blocked.rule_id == "deny-hazardous"


def test_rules_of_equal_priority_are_evaluated_in_declaration_order() -> None:
    first = allow("first", priority=10)
    second = deny("second", priority=10)

    assert (
        PolicyEngine(rules=[first, second])
        .evaluate(capability(), "software/test", "simulation")
        .rule_id
        == "first"
    )
    assert (
        PolicyEngine(rules=[second, first])
        .evaluate(capability(), "software/test", "simulation")
        .rule_id
        == "second"
    )


@pytest.mark.parametrize(
    ("default_effect", "allowed"),
    [("deny", False), ("allow", True)],
)
def test_the_default_effect_decides_when_no_rule_matches(
    default_effect: str, allowed: bool
) -> None:
    engine = PolicyEngine(
        rules=[allow("allow-live", environments=["live"])],
        default_effect=default_effect,  # type: ignore[arg-type]
    )

    decision = engine.evaluate(capability(), "software/test", "simulation")

    assert decision.allowed is allowed
    assert decision.effect is AuthorizationEffect(default_effect)
    assert decision.rule_id is None
    assert decision.reason == "default policy effect"


def test_an_engine_with_no_rules_denies_by_default() -> None:
    decision = PolicyEngine().evaluate(capability(), "software/test", "simulation")

    assert not decision.allowed
    assert decision.effect is AuthorizationEffect.DENY
    assert decision.policy_version == "built-in/v0alpha1"


def test_a_decision_carries_the_matched_rule_and_the_policy_version_into_the_record() -> None:
    engine = PolicyEngine(rules=[allow("allow-sim")], version="site/2026-08")

    decision = engine.evaluate(capability(), "software/test", "simulation")

    assert decision.rule_id == "allow-sim"
    assert decision.policy_version == "site/2026-08"
    # A rule without a reason still explains itself by naming the rule that decided.
    assert decision.reason == "matched policy rule allow-sim"


# --- Verifiable policy evidence -------------------------------------------------------------
#
# `policy_version` is a free-form label an operator writes in the manifest. It is bound to nothing,
# so every rule in a laboratory can change while the recorded evidence stays byte-identical. The
# digest below is the content half of that record: it is computed from the effective ruleset the
# engine actually evaluates, so a decision recorded before a rule change cannot be confused with one
# recorded after it. The version stays in the record as the operator's claim; the digest is the part
# that can be checked.


def test_a_decision_carries_a_digest_of_the_ruleset_that_decided_it() -> None:
    engine = PolicyEngine(rules=[allow("allow-sim")], version="site/2026-08")

    decision = engine.evaluate(capability(), "software/test", "simulation")

    assert decision.policy_digest == engine.digest
    assert decision.policy_digest.startswith("sha256:")
    assert len(decision.policy_digest) == len("sha256:") + 64


def test_the_default_effect_decision_carries_the_same_digest() -> None:
    """A denial by default is evidence too, and has to identify the ruleset that produced it."""
    engine = PolicyEngine(rules=[allow("allow-live", environments=["live"])])

    decision = engine.evaluate(capability(), "software/test", "simulation")

    assert decision.rule_id is None
    assert decision.policy_digest == engine.digest


def test_changing_a_rule_changes_the_digest_while_the_version_stays_constant() -> None:
    """The failure this exists to catch.

    An operator edits a rule and leaves `spec.policy.version` alone — the normal case, since
    nothing requires the version to move. Before the digest, the two `PolicyEvaluated` events were
    indistinguishable.
    """
    before = PolicyEngine(rules=[allow("allow-sim", capability="sim.*")], version="site/2026-08")
    after = PolicyEngine(rules=[allow("allow-sim", capability="*")], version="site/2026-08")

    first = before.evaluate(capability(), "software/test", "simulation")
    second = after.evaluate(capability(), "software/test", "simulation")

    assert first.policy_version == second.policy_version
    assert first.policy_digest != second.policy_digest


def test_the_digest_covers_the_default_effect_and_rule_order() -> None:
    """Everything that decides an outcome is in the digest, not only the rule bodies."""
    rules = [allow("allow-live", environments=["live"])]

    assert (
        PolicyEngine(rules=rules, default_effect="deny").digest
        != PolicyEngine(rules=rules, default_effect="allow").digest
    )

    first = allow("first", priority=10)
    second = deny("second", priority=10)
    assert (
        PolicyEngine(rules=[first, second]).digest != PolicyEngine(rules=[second, first]).digest
    ), "equal-priority rules are evaluated in declaration order, so order is content"


def test_the_digest_is_stable_across_engines_and_ignores_the_version_label() -> None:
    """Two deployments running the same rules produce comparable evidence.

    The digest answers exactly one question — did the rules change? — so the free-form version
    label is deliberately outside it. A laboratory that renames its policy version has not changed
    what the policy does, and two laboratories running identical rules can be compared directly.
    """
    rules = [allow("allow-sim", capability="sim.*"), deny("deny-live", environments=["live"])]

    assert (
        PolicyEngine(rules=rules, version="site/a").digest
        == PolicyEngine(rules=list(rules), version="site/b").digest
    )
    # Priority sorting is applied before hashing, so a reordered declaration of the same effective
    # ruleset is the same ruleset.
    ordered = [allow("a", priority=10), deny("b", priority=20)]
    assert PolicyEngine(rules=ordered).digest == PolicyEngine(rules=list(reversed(ordered))).digest
