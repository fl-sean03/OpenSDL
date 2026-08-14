"""What a benchmark task asks, and what a result says.

The claim this package makes is that "did the agent operate the laboratory correctly" is a query
rather than an opinion. Every check below is answered from records the framework already keeps: a
run either reached `completed`, policy either refused something or did not, an attestation either
carries a basis or does not. Nothing here asks a model to judge another model's work.

That is not a criticism of judge-based grading, which exists because most tasks have no ground
truth to check against. This domain has one, and using a judge where a database will answer would
be slower, dearer, and less repeatable.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

from opensdl_core import OpenSDLModel, utc_now
from pydantic import Field


class CheckKind(StrEnum):
    """The questions a task may ask of the laboratory it was run against.

    Deliberately a closed set. A task that needs a question not on this list is asking for
    something the evidence store cannot answer, and the honest response is to add the record that
    would answer it rather than to reach for a judge.
    """

    #: At least `count` runs reached `completed`.
    RUNS_COMPLETED = "runs_completed"
    #: At most `count` runs ended `failed`. Zero is the usual expectation.
    RUNS_FAILED_AT_MOST = "runs_failed_at_most"
    #: No run is still waiting on a person. A task is not finished if it left one stranded.
    NO_RUN_AWAITING_INTERVENTION = "no_run_awaiting_intervention"
    #: The named capability executed at least `count` times.
    CAPABILITY_EXECUTED = "capability_executed"
    #: The named capability never executed. This is how a task states a boundary.
    CAPABILITY_NEVER_EXECUTED = "capability_never_executed"
    #: Policy refused the agent at least `count` times. For tasks that ask an agent to probe.
    POLICY_DENIED_AT_LEAST = "policy_denied_at_least"
    #: Policy never refused the agent. For tasks that ask it to work within what it was granted.
    POLICY_NEVER_DENIED = "policy_never_denied"
    #: Every attestation recorded carries a non-empty basis.
    ATTESTATIONS_CARRY_A_BASIS = "attestations_carry_a_basis"
    #: An event of this type was recorded at least `count` times.
    EVENT_RECORDED = "event_recorded"


class Check(OpenSDLModel):
    """One question, and what counts as the right answer."""

    kind: CheckKind
    #: What this check is for, in the words a failing report should use.
    description: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    #: How much of the task's score this check carries. Tasks normalise, so these are relative.
    weight: float = Field(default=1.0, gt=0)


class BenchmarkTask(OpenSDLModel):
    """One thing an agent is asked to do, and how the result is decided.

    `prompt` is given to the agent verbatim and to every agent identically. Following Artificial
    Analysis, it is zero-shot: no worked example is attached, because an example of the answer
    measures how well a model copies rather than whether it can operate a laboratory.
    """

    id: str = Field(min_length=1)
    #: Grouped for the weighted index, in the way an evaluation suite groups its components.
    category: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    #: The directory holding the laboratory this task runs against, relative to the suite file.
    #: Only consulted when a suite resolves its tasks; a caller driving `attempt_task` directly
    #: hands over the directory itself, and this stays at its default unread.
    laboratory: str = Field(default=".", min_length=1)
    #: The manifest inside that directory, relative to its root. The agent is handed the copied
    #: laboratory, so this is the path it would open, not a path on this machine.
    manifest: str = Field(min_length=1)
    #: Where that laboratory keeps its records, relative to the same directory. Stated rather than
    #: read out of the manifest: this package may not import the manifest schema, and a grader that
    #: guessed the path would open an empty database and report a confident nothing.
    store: str = Field(default=".opensdl/opensdl.db", min_length=1)
    checks: list[Check] = Field(min_length=1)
    #: What a competent operator would need. Reported beside the result rather than enforced, so a
    #: model that takes ten times as long is visible as such instead of being failed.
    reference_seconds: float | None = Field(default=None, gt=0)


class BenchmarkSuite(OpenSDLModel):
    """Every task a model is asked, and how the headline number is weighted.

    A suite is data rather than code so that the thing being compared across models is a file
    anyone can read and diff. A result quoted against "the OpenSDL benchmark" means nothing unless
    the suite it came from is pinned, which is what `version` is for: changing a task changes what
    the number means, and a number that changed because the questions changed is not a measurement.
    """

    name: str = Field(min_length=1)
    #: Bumped whenever a task is added, removed, or reworded. Scores are comparable within a
    #: version and are not comparable across one.
    version: str = Field(min_length=1)
    description: str = ""
    #: Category weights for the headline index. Categories absent here weigh nothing, so a suite
    #: that states weights states all of them; stating none weighs every category equally.
    weights: dict[str, float] = Field(default_factory=dict)
    tasks: list[BenchmarkTask] = Field(min_length=1)
    #: The directory task paths resolve against, set by the loader from where the file was found
    #: rather than read out of it. A suite that could name its own root could point at anything on
    #: the machine that ran it, and the file is written by whoever supplies the tasks.
    root: Path = Field(default=Path())

    def source_for(self, task: BenchmarkTask) -> Path:
        """The laboratory directory this task runs against."""

        return (self.root / task.laboratory).resolve()


class CheckOutcome(OpenSDLModel):
    """One question and the answer the records gave."""

    kind: CheckKind
    description: str
    passed: bool
    #: What was found, in enough detail to argue with. A bare `false` is not a finding.
    detail: str
    weight: float


class TaskAttempt(OpenSDLModel):
    """One agent, one task, one go at it.

    `error` is for the attempt failing to happen — a transport error, a crash. It is distinct from
    the checks failing, which is the agent being wrong, and the two are not scored the same way:
    an attempt that never ran is retried, and an attempt that ran badly is a result.
    """

    task_id: str
    repeat: int = Field(ge=1)
    outcomes: list[CheckOutcome] = Field(default_factory=list)
    seconds: float = Field(ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    #: Priced from the provider's own token counts rather than a local tokenizer, because the
    #: provider's count is what the bill is computed from.
    cost_usd: float = Field(default=0.0, ge=0)
    error: str | None = None

    @property
    def passed(self) -> bool:
        """Every check held. Partial credit lives in `score`, not here."""

        return self.error is None and bool(self.outcomes) and all(o.passed for o in self.outcomes)

    @property
    def score(self) -> float:
        """The weighted fraction of checks that held, between zero and one."""

        if self.error is not None or not self.outcomes:
            return 0.0
        total = sum(outcome.weight for outcome in self.outcomes)
        held = sum(outcome.weight for outcome in self.outcomes if outcome.passed)
        return held / total if total else 0.0


class TaskScore(OpenSDLModel):
    """What a set of attempts at one task establishes.

    `pass_at_1` is the share of attempts that got everything right first time, which is the
    convention the field settled on and the number that compares to published results. `mean_score`
    sits beside it because a suite where a model gets four of five checks every time and a suite
    where it gets none are both `pass_at_1` of zero, and those are not the same laboratory.
    """

    task_id: str
    category: str
    attempts: list[TaskAttempt]

    @property
    def repeats(self) -> int:
        return len(self.attempts)

    @property
    def pass_at_1(self) -> float:
        return (
            sum(1 for a in self.attempts if a.passed) / len(self.attempts) if self.attempts else 0.0
        )

    @property
    def mean_score(self) -> float:
        return sum(a.score for a in self.attempts) / len(self.attempts) if self.attempts else 0.0

    @property
    def mean_seconds(self) -> float:
        return sum(a.seconds for a in self.attempts) / len(self.attempts) if self.attempts else 0.0

    @property
    def cost_usd(self) -> float:
        return sum(a.cost_usd for a in self.attempts)


class BenchmarkReport(OpenSDLModel):
    """One model against the whole suite.

    Score, cost and time are reported together and never separately. A model that scores two points
    higher for eight times the money is a different answer to "which should this laboratory use"
    than the score alone suggests.
    """

    model: str
    scores: list[TaskScore]
    #: What was asked, so a quoted number carries its own questions. A score without the suite and
    #: version behind it cannot be compared with anything, including a later run of "the same"
    #: benchmark.
    suite: str = ""
    suite_version: str = ""
    #: Carried from the suite so that re-weighting a published result is a deliberate argument
    #: rather than something that happens by leaving an argument off.
    weights: dict[str, float] = Field(default_factory=dict)
    generated_at: Any = Field(default_factory=utc_now)

    @property
    def categories(self) -> dict[str, float]:
        """Mean `pass_at_1` within each category."""

        grouped: dict[str, list[float]] = {}
        for score in self.scores:
            grouped.setdefault(score.category, []).append(score.pass_at_1)
        return {name: sum(values) / len(values) for name, values in grouped.items()}

    def index(self, weights: dict[str, float] | None = None) -> float:
        """One number, weighted by category.

        Unweighted, this is the mean over categories rather than over tasks, so adding three easy
        tasks to one category cannot lift the headline figure. Passing `weights` re-weights a
        recorded result, which is a thing worth doing and worth doing on purpose: a laboratory that
        cares more about restraint than throughput is entitled to say so and say it out loud.
        """
        categories = self.categories
        if not categories:
            return 0.0
        weights = self.weights if weights is None else weights
        if not weights:
            return sum(categories.values()) / len(categories)
        total = sum(weights.get(name, 0.0) for name in categories)
        if total <= 0:
            return 0.0
        return sum(categories[name] * weights.get(name, 0.0) for name in categories) / total

    @property
    def cost_usd(self) -> float:
        return sum(score.cost_usd for score in self.scores)

    @property
    def seconds(self) -> float:
        return sum(a.seconds for score in self.scores for a in score.attempts)
