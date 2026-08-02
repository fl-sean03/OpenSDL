from opensdl_core import CapabilityDefinition, ExecutorType, RiskClass
from opensdl_policy import PolicyEngine, PolicyRule


def test_specific_allow_rule() -> None:
    capability = CapabilityDefinition(id="sim.mix", name="Mix", executor_type=ExecutorType.SIMULATOR, input_schema={}, output_schema={}, risk_class=RiskClass.R1)
    engine = PolicyEngine(rules=[PolicyRule(id="allow-sim", effect="allow", capability="sim.*", environments=["simulation"])])
    assert engine.evaluate(capability, "software/test", "simulation").allowed
    assert not engine.evaluate(capability, "software/test", "live").allowed
