"""A policy rule that can never fire is refused when the manifest is loaded.

Evaluation is unchanged and deliberately so: rules are sorted by ascending priority, the first
match wins, and **a `deny` does not override an earlier `allow`**. `packages/policy/tests/test_policy.py`
asserts that, including a test named for the trap it creates — an operator who adds
`deny: sim.hazardous` at priority 20 to a manifest already carrying `allow: "*"` at priority 10 gets
no error, no warning and no effect. Changing the semantics would silently change what every existing
manifest means. Refusing the dead rule at load time does not.

What is asserted here is both directions of that refusal:

* a `deny` an earlier `allow` covers **in every selector** is refused, naming both rules;
* a `deny` that is narrower in one dimension and broader in another is **not** refused, because it
  can still fire and refusing it would take a working laboratory offline.

The analysis is deliberately incomplete. It proves shadowing for one allow at a time and for the
glob forms it can reason about; anything else is left to load. The last test in this file pins the
one property that makes the incompleteness safe: every pair the analysis reports really is dead
under the engine that will evaluate it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from opensdl_core import AuthorizationEffect, CapabilityDefinition, ExecutorType, RiskClass
from opensdl_policy import PolicyEngine, PolicyRule
from opensdl_schemas import LabManifest, load_manifest
from opensdl_schemas.manifest import PolicyRuleSpec, shadowed_deny_rules

REPOSITORY_ROOT = Path(__file__).parents[3]


def manifest(*rules: dict[str, Any], default_effect: str = "deny") -> LabManifest:
    return LabManifest.model_validate(
        {
            "apiVersion": "opensdl.dev/v0alpha1",
            "kind": "Laboratory",
            "metadata": {"name": "policy-lab", "owner": "test"},
            "spec": {
                "policy": {
                    "default_effect": default_effect,
                    "version": "test/v1",
                    "rules": list(rules),
                }
            },
        }
    )


def allow(rule_id: str, **selectors: Any) -> dict[str, Any]:
    return {"id": rule_id, "effect": "allow", **selectors}


def deny(rule_id: str, **selectors: Any) -> dict[str, Any]:
    return {"id": rule_id, "effect": "deny", **selectors}


def refusal(*rules: dict[str, Any]) -> str:
    with pytest.raises(ValidationError) as raised:
        manifest(*rules)
    return str(raised.value)


# --- A dead deny is refused --------------------------------------------------------------------


def test_the_canonical_trap_is_refused_and_both_rules_are_named() -> None:
    """`allow: "*"` at 10 and `deny: sim.hazardous` at 20 — the configuration D7 is about."""
    message = refusal(
        allow("allow-everything", capability="*", priority=10),
        deny("deny-hazardous", capability="sim.hazardous", priority=20),
    )

    assert "deny-hazardous" in message
    assert "allow-everything" in message
    # The operator needs to be told the fix, not only the fault.
    assert "priority" in message


def test_a_deny_narrower_in_every_selector_is_refused() -> None:
    message = refusal(
        allow(
            "allow-broad",
            capability="sim.*",
            environments=["*"],
            operators=["*"],
            risk_classes=["*"],
            priority=10,
        ),
        deny(
            "deny-narrow",
            capability="sim.hazardous",
            environments=["live"],
            operators=["human/alice"],
            risk_classes=["R4"],
            priority=20,
        ),
    )

    assert "deny-narrow" in message and "allow-broad" in message


def test_a_deny_of_equal_priority_declared_after_an_allow_is_refused() -> None:
    """Equal priorities are evaluated in declaration order, so this deny is dead too."""
    message = refusal(
        allow("allow-first", capability="*", priority=10),
        deny("deny-second", capability="sim.hazardous", priority=10),
    )

    assert "deny-second" in message and "allow-first" in message


def test_a_deny_whose_glob_sits_inside_the_allow_glob_is_refused() -> None:
    message = refusal(
        allow("allow-sim", capability="sim.*", priority=10),
        deny("deny-hazardous-family", capability="sim.haz*", priority=20),
    )

    assert "deny-hazardous-family" in message and "allow-sim" in message


def test_the_refusal_says_what_it_cannot_detect() -> None:
    """A partial shadow is not detectable this way, and the operator has to know that."""
    message = refusal(
        allow("allow-everything", capability="*", priority=10),
        deny("deny-hazardous", capability="sim.hazardous", priority=20),
    )

    assert "cannot" in message.lower()


# --- A live deny is not refused ----------------------------------------------------------------
#
# Every configuration below carries a deny that can still fire. Refusing one of these would take a
# laboratory offline over a rule that works, which is the expensive direction of a false positive.


def test_a_deny_that_sorts_ahead_of_the_allow_loads() -> None:
    loaded = manifest(
        deny("deny-hazardous", capability="sim.hazardous", priority=5),
        allow("allow-everything", capability="*", priority=10),
    )

    assert [rule.id for rule in loaded.spec.policy.rules] == ["deny-hazardous", "allow-everything"]


def test_a_deny_of_equal_priority_declared_before_the_allow_loads() -> None:
    assert manifest(
        deny("deny-first", capability="sim.hazardous", priority=10),
        allow("allow-second", capability="*", priority=10),
    )


def test_a_deny_broader_in_environment_than_the_allow_loads() -> None:
    """The allow only covers `simulation`; the deny still binds everywhere else."""
    assert manifest(
        allow("allow-simulation", capability="*", environments=["simulation"], priority=10),
        deny("deny-hazardous", capability="sim.hazardous", environments=["*"], priority=20),
    )


def test_a_deny_broader_in_operator_than_the_allow_loads() -> None:
    assert manifest(
        allow("allow-software", capability="*", operators=["software/*"], priority=10),
        deny("deny-hazardous", capability="sim.hazardous", operators=["*"], priority=20),
    )


def test_a_deny_naming_a_risk_class_the_allow_omits_loads() -> None:
    assert manifest(
        allow("allow-low-risk", capability="*", risk_classes=["R0", "R1"], priority=10),
        deny("deny-hazardous", capability="sim.hazardous", risk_classes=["R4"], priority=20),
    )


def test_a_deny_whose_capability_glob_is_not_provably_covered_loads() -> None:
    """`*.hazardous` reaches capabilities `sim.*` does not, and proving otherwise is not attempted."""
    assert manifest(
        allow("allow-sim", capability="sim.*", priority=10),
        deny("deny-hazardous", capability="*.hazardous", priority=20),
    )


def test_a_deny_broader_than_the_allow_in_capability_loads() -> None:
    assert manifest(
        allow("allow-one", capability="sim.mix", priority=10),
        deny("deny-family", capability="sim.*", priority=20),
    )


def test_two_allows_that_only_jointly_cover_a_deny_load() -> None:
    """Documented incompleteness: coverage is proved one allow at a time.

    Together these two allows leave the deny dead. Neither does on its own, and a union analysis
    over globs is not something this check attempts. Missing the case is the safe direction.
    """
    assert manifest(
        allow("allow-r0", capability="*", risk_classes=["R0", "R1", "R2"], priority=10),
        allow("allow-r3", capability="*", risk_classes=["R3", "R4"], priority=11),
        deny("deny-hazardous", capability="sim.hazardous", priority=20),
    )


def test_a_deny_shadowed_by_an_earlier_deny_loads() -> None:
    """Redundant, but not the trap: the request is denied either way."""
    assert manifest(
        deny("deny-everything", capability="*", priority=10),
        deny("deny-hazardous", capability="sim.hazardous", priority=20),
    )


def test_an_allow_shadowed_by_an_earlier_allow_loads() -> None:
    assert manifest(
        allow("allow-everything", capability="*", priority=10),
        allow("allow-sim", capability="sim.*", priority=20),
    )


def test_every_shipped_manifest_still_loads() -> None:
    """The reference laboratories ship a policy block, and `make example` runs one of them."""
    for relative in (
        "examples/simulated-color-mixing/opensdl.yaml",
        "examples/computation-only/opensdl.yaml",
        "examples/digital-twin-surrogate/opensdl.yaml",
    ):
        assert load_manifest(REPOSITORY_ROOT / relative)


# --- A selector that matches nothing -------------------------------------------------------------


def test_a_risk_class_written_as_a_glob_is_refused() -> None:
    """`risk_classes` is the only selector that compares strings rather than globbing.

    `R*` reads as the wildcard the other three selectors accept, matches no risk class, and
    silently authorizes nothing at all.
    """
    message = refusal(allow("looks-like-a-wildcard", risk_classes=["R*"], priority=10))

    assert "R*" in message
    assert "looks-like-a-wildcard" in message
    assert "R0" in message, "the error has to list what is accepted"


def test_an_unknown_risk_class_is_refused() -> None:
    message = refusal(allow("typo", risk_classes=["R1 "], priority=10))

    assert "typo" in message


@pytest.mark.parametrize("selector", ["environments", "operators", "risk_classes"])
def test_an_empty_selector_list_is_refused(selector: str) -> None:
    message = refusal(allow("matches-nothing", **{selector: []}, priority=10))

    assert "matches-nothing" in message
    assert selector in message


def test_the_wildcard_and_the_declared_risk_classes_are_accepted() -> None:
    assert manifest(allow("wildcard", risk_classes=["*"], priority=10))
    assert manifest(allow("declared", risk_classes=[value for value in RiskClass], priority=10))


# --- The analysis agrees with the engine that will evaluate it -----------------------------------


def capability(capability_id: str, risk_class: RiskClass) -> CapabilityDefinition:
    return CapabilityDefinition(
        id=capability_id,
        name="probe",
        executor_type=ExecutorType.SIMULATOR,
        input_schema={},
        output_schema={},
        risk_class=risk_class,
    )


CAPABILITY_IDS = ("sim.mix", "sim.hazardous", "sim.haz", "sim.hazardous.inner", "robot.mix", "x")
OPERATORS = ("software/agent-7", "human/alice", "software", "operator/showcase")
ENVIRONMENTS = ("simulation", "live", "staging-eu", "physical")

SELECTORS: tuple[dict[str, Any], ...] = (
    {},
    {"capability": "*"},
    {"capability": "sim.*"},
    {"capability": "sim.haz*"},
    {"capability": "sim.hazardous"},
    {"capability": "*.hazardous"},
    {"capability": "sim.?azardous"},
    {"environments": ["simulation"]},
    {"environments": ["simulation", "staging-*"]},
    {"operators": ["software/*"]},
    {"operators": ["human/alice"]},
    {"risk_classes": ["R0", "R1"]},
    {"risk_classes": ["R4"]},
    {"capability": "sim.*", "environments": ["simulation"], "risk_classes": ["R0", "R1"]},
    {"capability": "sim.hazardous", "operators": ["human/alice"], "risk_classes": ["R4"]},
)


def engine_rule(spec: PolicyRuleSpec) -> PolicyRule:
    return PolicyRule.model_validate(spec.model_dump(mode="json"))


def test_every_pair_the_analysis_refuses_is_dead_under_the_engine() -> None:
    """The property that makes an incomplete analysis safe: no false positive, ever.

    This is the check that keeps `manifest.py` honest about `PolicyRule.matches`. The two live in
    different distributions — `opensdl_schemas` must not import `opensdl_policy` — so nothing but
    this comparison stops the manifest's idea of "covers" drifting from the engine's idea of
    "matches". Every selector combination above is paired with every other, and every pair the
    analysis calls shadowed is evaluated against the real engine over the whole sampled request
    space. A single request the deny wins is a false positive, and a false positive refuses a
    laboratory's entire configuration.
    """
    reported = 0
    for first in SELECTORS:
        for second in SELECTORS:
            rules = [
                PolicyRuleSpec.model_validate({"id": "a", "effect": "allow", **first}),
                PolicyRuleSpec.model_validate({"id": "d", "effect": "deny", **second}),
            ]
            if not shadowed_deny_rules(rules):
                continue
            reported += 1
            engine = PolicyEngine(rules=[engine_rule(rule) for rule in rules])
            for capability_id in CAPABILITY_IDS:
                for risk_class in RiskClass:
                    for operator in OPERATORS:
                        for environment in ENVIRONMENTS:
                            decision = engine.evaluate(
                                capability(capability_id, risk_class), operator, environment
                            )
                            assert decision.rule_id != "d", (
                                f"{second} was reported dead behind {first} and decided "
                                f"{capability_id}/{risk_class}/{operator}/{environment}"
                            )

    assert reported > 20, "the corpus has to actually exercise the analysis"


def test_the_analysis_reports_the_pair_in_evaluation_order() -> None:
    """The reported pair is (shadowing allow, dead deny), whatever order they were declared in."""
    rules = [
        PolicyRuleSpec(id="deny-late", effect="deny", capability="sim.hazardous", priority=20),
        PolicyRuleSpec(id="allow-early", effect="allow", capability="*", priority=10),
    ]

    assert [(a.id, d.id) for a, d in shadowed_deny_rules(rules)] == [("allow-early", "deny-late")]


def test_the_engine_semantics_this_analysis_assumes_are_unchanged() -> None:
    """If evaluation ever becomes deny-overrides, this whole check becomes wrong, not merely stale.

    A shadowed deny would then be live and refusing it would be a defect. This assertion is the
    tripwire: it fails on the day the semantics change, in the file that depends on them.
    """
    engine = PolicyEngine(
        rules=[
            PolicyRule(id="allow-everything", effect=AuthorizationEffect.ALLOW, priority=10),
            PolicyRule(
                id="deny-hazardous",
                effect=AuthorizationEffect.DENY,
                capability="sim.hazardous",
                priority=20,
            ),
        ]
    )

    decision = engine.evaluate(capability("sim.hazardous", RiskClass.R4), "human/alice", "live")

    assert decision.allowed and decision.rule_id == "allow-everything"
