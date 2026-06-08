from __future__ import annotations

import httpx

from ..exceptions import (
    AuthenticationError,
    AuthorizationError,
    PermanentIntegrationError,
    RateLimitError,
    TransientIntegrationError,
)


def raise_for_http_response(response: httpx.Response, *, provider: str) -> None:
    if response.is_success:
        return
    status = response.status_code
    detail = response.text[:300]
    message = f"{provider} HTTP {status}: {detail}"
    if status == 429:
        raise RateLimitError(message)
    if status >= 500:
        raise TransientIntegrationError(message)
    if status == 401:
        raise AuthenticationError(message)
    if status == 403:
        raise AuthorizationError(message)
    raise PermanentIntegrationError(message)
