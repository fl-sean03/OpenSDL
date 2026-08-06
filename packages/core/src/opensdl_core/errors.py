from __future__ import annotations


class OpenSDLError(Exception):
    """Base error for public OpenSDL failures."""


class ValidationError(OpenSDLError):
    """A contract or configuration is invalid."""


class LifecycleError(OpenSDLError):
    """A requested state transition is invalid."""


class CapabilityNotFoundError(OpenSDLError):
    """No registered adapter exposes the requested capability."""


class ExecutionDeniedError(OpenSDLError):
    """Policy denied an execution request.

    Carries the decision that refused it. Which rule fired, and under which policy revision,
    is the operator's own configuration rather than adapter-supplied text, so an interface
    can report it without leaking anything a caller did not already own. Without it a denial
    is indistinguishable from any other refusal and the operator cannot find the rule.
    """

    def __init__(self, message: str, *, decision: object | None = None) -> None:
        super().__init__(message)
        self.decision = decision


class ResourceBusyError(OpenSDLError):
    """One or more required resources could not be leased."""


class WorkflowExecutionError(OpenSDLError):
    """A workflow could not complete successfully."""
