from __future__ import annotations


class EbayWorkflowsError(Exception):
    """Base error with a stable category for logs and error_json."""

    category: str = "WorkflowExecutionError"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ConfigurationError(EbayWorkflowsError):
    category = "ConfigurationError"


class AuthenticationError(EbayWorkflowsError):
    category = "AuthenticationError"


class AuthorizationError(EbayWorkflowsError):
    category = "AuthorizationError"


class RateLimitError(EbayWorkflowsError):
    category = "RateLimitError"


class TransientIntegrationError(EbayWorkflowsError):
    category = "TransientIntegrationError"


class PermanentIntegrationError(EbayWorkflowsError):
    category = "PermanentIntegrationError"


class DataValidationError(EbayWorkflowsError):
    category = "DataValidationError"


class DataSourceError(EbayWorkflowsError):
    category = "DataSourceError"


class WorkflowExecutionError(EbayWorkflowsError):
    category = "WorkflowExecutionError"
