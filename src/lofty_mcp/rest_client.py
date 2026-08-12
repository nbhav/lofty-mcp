"""Thin REST client for the Lofty API: base URL, auth header, error mapping.

No refresh/retry logic. LOFTY_API_KEY is a personal-access token (Lofty CRM ->
Settings -> Integrations -> API) with a documented "configurable expiration"
and no refresh flow -- unlike an OAuth access/refresh token pair. On 401 we
raise a clear message telling the caller to regenerate the key, rather than
retrying.

Auth scheme: verified empirically against the real API (see
specs/rest/index.json "authCorrection") that this credential must be sent as
`Authorization: token <key>`, NOT `Authorization: Bearer <key>` -- despite
every operation in specs/openapi.json documenting Bearer. Bearer returns
HTTP 400 {"code":200058,"message":"User in token does not exist."} for this
credential type.
"""

from __future__ import annotations

from typing import Any

import httpx

BASE_URL = "https://api.lofty.com"


class LoftyApiError(Exception):
    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f"Lofty API error {status_code}: {body}")


def make_client(api_key: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=BASE_URL,
        headers={"Authorization": f"token {api_key}"},
        timeout=30.0,
    )


def compact(**kwargs: Any) -> dict[str, Any]:
    """Drop None-valued kwargs, for building query-param or JSON-body dicts from optional tool args."""
    return {k: v for k, v in kwargs.items() if v is not None}


async def request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | list[Any] | None = None,
) -> Any:
    """Make a request and return the parsed JSON body (or {} for empty responses).

    Lead/task/calendar IDs from Lofty are 64-bit integers. Python's `int` is
    arbitrary-precision and this parses via the stdlib `json` module under the
    hood, so unlike a JS implementation there's no precision loss to guard
    against here -- IDs pass through as ordinary Python ints.
    """
    response = await client.request(method, path, params=params, json=json)
    if response.status_code == 401:
        raise LoftyApiError(
            401,
            "Authentication failed. This API key has no refresh mechanism -- "
            "regenerate it in the Lofty CRM under Settings -> Integrations -> API "
            "and update LOFTY_API_KEY.",
        )
    if response.is_error:
        raise LoftyApiError(response.status_code, response.text)
    if not response.content:
        return {}
    return response.json()
