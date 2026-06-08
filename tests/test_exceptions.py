from __future__ import annotations

from ebay_workflows.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    EbayWorkflowsError,
    PermanentIntegrationError,
    RateLimitError,
    TransientIntegrationError,
)
from ebay_workflows.integrations.http_errors import raise_for_http_response
from ebay_workflows.workflow_errors import error_category_for


def test_error_category_for_typed_exception() -> None:
    assert error_category_for(AuthenticationError("bad token")) == "AuthenticationError"
    assert error_category_for(ConfigurationError("missing key")) == "ConfigurationError"
    assert error_category_for(RateLimitError("slow down")) == "RateLimitError"
    assert error_category_for(TransientIntegrationError("timeout")) == "TransientIntegrationError"


def test_raise_for_http_response_maps_status_codes() -> None:
    import httpx

    response_429 = httpx.Response(429, request=httpx.Request("GET", "https://example.com"))
    response_503 = httpx.Response(503, request=httpx.Request("GET", "https://example.com"))
    response_401 = httpx.Response(401, request=httpx.Request("GET", "https://example.com"))
    response_403 = httpx.Response(403, request=httpx.Request("GET", "https://example.com"))
    response_404 = httpx.Response(404, request=httpx.Request("GET", "https://example.com"))

    for exc_type, response in (
        (RateLimitError, response_429),
        (TransientIntegrationError, response_503),
        (AuthenticationError, response_401),
        (AuthorizationError, response_403),
        (PermanentIntegrationError, response_404),
    ):
        try:
            raise_for_http_response(response, provider="Test")
        except exc_type:
            pass
        else:
            raise AssertionError(f"expected {exc_type.__name__}")


def test_ebay_workflows_error_message() -> None:
    err = EbayWorkflowsError("boom")
    assert str(err) == "boom"
    assert err.message == "boom"
