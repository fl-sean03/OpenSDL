# Safety boundary

OpenSDL provides software contracts and reference infrastructure for laboratory automation and scientific computation. It is not a safety instrumented system, emergency-stop circuit, safety PLC, machine-guarding design, chemical compatibility determination, process hazard analysis, operating procedure, or compliance certification.

## Fundamental rule

No probabilistic model or general software operator should be the only mechanism preventing injury, release, fire, explosion, equipment damage, environmental harm, or loss of containment.

Physical deployments remain responsible for, as applicable:

1. inherently safer materials, scales, and conditions;
2. containment, ventilation, shielding, guarding, and segregation;
3. safety-rated interlocks and emergency stops;
4. edge controllers enforcing hard equipment limits;
5. watchdogs and known safe-state behavior;
6. validated operating procedures and trained personnel;
7. incident response and regulatory compliance.

OpenSDL begins above those controls. Its policy and authority mechanisms are additional layers, not replacements.

## Capability operating domain

Every physical capability should document permitted materials, quantities, temperature, pressure, energy, force, speed, approved fixtures, required sensors, calibration state, prohibited combinations, and failure behavior. Requests outside the validated operating domain are denied or escalated by the deployment.

## Proposal, authorization, execution, verification

A physical operation should preserve distinct records for:

- requested intent;
- schema and state validation;
- authorization;
- command dispatch;
- physical acknowledgement;
- postcondition verification;
- reconciliation or incident response.

An API success response is not by itself proof that a physical action occurred.

## Failure behavior

Operational adapters must define communication loss, timeout, retry safety, cancellation, abort, park or safe state, cleanup, and manual handoff. Database rollback cannot reverse a physical action.

## Reference profile

The included examples are simulator-only. No included adapter is qualified for hazardous or production equipment.
