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
    """Policy denied an execution request."""


class ResourceBusyError(OpenSDLError):
    """One or more required resources could not be leased."""


class WorkflowExecutionError(OpenSDLError):
    """A workflow could not complete successfully."""
