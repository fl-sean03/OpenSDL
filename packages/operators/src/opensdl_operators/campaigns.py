"""Starting a campaign from outside Python.

A campaign was reachable only by writing bespoke `asyncio` code against `CampaignRunner`, so the
headline closed-loop feature could not be started by an operator, an agent, or a remote client.
This module is the smallest thing that changes that honestly.

It is deliberately not a method on `OperatorGateway`, and deliberately not a tool or an HTTP route.
The gateway is the surface a read-only laboratory serves, and `ReadOnlyGateway` closes exactly one
method on it; a second write path there would be inherited open. And a campaign runs for hours or
days: `POST /runs` already awaits an entire workflow inside its request handler, which is why
`RunState.QUEUED` is unreachable and the SDK's thirty-second timeout cannot submit a real run.
Repeating that for something that runs for days would be worse, not better.

So starting a campaign runs in the foreground of whichever process asked for it — today that is
`opensdl campaign start` — and stopping it means stopping that process. Reading a campaign back is
a different question with a different answer, and that half is on the gateway, in the tool
catalogue, on the HTTP API and in the SDK.
"""

from __future__ import annotations

from typing import Any

from collections.abc import Sequence

from opensdl_capabilities import PluginManager, enforce_plugin_allowlist, plugin_allowlist
from opensdl_core import WorkflowDefinition
from opensdl_runtime import (
    CampaignReader,
    CampaignRecord,
    CampaignRunner,
    CandidateConstraint,
    Objective,
    OutcomeConstraint,
    ReferenceRuntime,
    SearchSpace,
)
from opensdl_storage import RepositoryStore


class CampaignLauncher:
    """Runs one campaign in the calling process and returns the record of what it did."""

    def __init__(
        self,
        runtime: ReferenceRuntime,
        repositories: RepositoryStore,
        *,
        plugins: PluginManager | None = None,
    ) -> None:
        self.runtime = runtime
        self.repositories = repositories
        self.plugins = plugins or PluginManager()

    def load_optimizer(self, plugin: str, config: dict[str, Any] | None = None) -> Any:
        """Resolve an optimizer plugin, subject to the deployment's allowlist.

        An optimizer is code this process imports and then lets choose what the laboratory does
        next, so it is authorized by the same allowlist as an adapter rather than trusted because
        it was named on a command line.
        """
        enforce_plugin_allowlist([plugin], plugin_allowlist())
        return self.plugins.load_optimizer(plugin, config or {})

    async def run(
        self,
        workflow: WorkflowDefinition,
        *,
        environment: str,
        operator_id: str,
        optimizer: str,
        optimizer_config: dict[str, Any] | None = None,
        base_inputs: dict[str, Any] | None = None,
        score_output: str = "score",
        max_iterations: int = 10,
        minimize: bool = True,
        target_score: float | None = None,
        max_consecutive_failures: int = 3,
        max_duration_seconds: float | None = None,
        iteration_id_input: str | None = None,
        campaign_id: str | None = None,
        objectives: Sequence[Objective] | None = None,
        search_space: SearchSpace | None = None,
        candidate_constraints: Sequence[CandidateConstraint] = (),
        outcome_constraints: Sequence[OutcomeConstraint] = (),
        batch_size: int = 1,
        max_parallel_runs: int = 1,
    ) -> CampaignRecord:
        """Run a campaign to a stopping rule and return the record projected from its events.

        `environment` is the laboratory's, not the caller's: policy is evaluated against it and
        every run records it, so a campaign that stated its own would write a false provenance
        record. `operator_id` names who is accountable for an unattended loop.

        The arguments from `base_inputs` to `iteration_id_input` mirror `CampaignRunner.run`, which
        mirrors `opensdl_core.CampaignDefinition`. `optimizer_config` has no field on that
        definition, so a stored campaign definition cannot yet configure its own optimizer; that
        gap is the reason this takes arguments rather than a definition file. The declared problem
        and the throughput arguments below `campaign_id` have no field on it either, and are passed
        straight through so that starting a campaign from outside Python is not the surface that
        loses them.
        """
        loaded = self.load_optimizer(optimizer, optimizer_config)
        result = await CampaignRunner(self.runtime, self.repositories).run(
            workflow,
            loaded,
            environment=environment,
            operator_id=operator_id,
            base_inputs=base_inputs,
            score_output=score_output,
            max_iterations=max_iterations,
            minimize=minimize,
            target_score=target_score,
            max_consecutive_failures=max_consecutive_failures,
            max_duration_seconds=max_duration_seconds,
            iteration_id_input=iteration_id_input,
            campaign_id=campaign_id,
            objectives=objectives,
            search_space=search_space,
            candidate_constraints=candidate_constraints,
            outcome_constraints=outcome_constraints,
            batch_size=batch_size,
            max_parallel_runs=max_parallel_runs,
        )
        return CampaignReader(self.repositories).get(result.campaign_id)
