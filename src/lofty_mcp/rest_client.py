"""Thin REST client for the Lofty API: base URL, auth header, error mapping.

No refresh/retry logic. LOFTY_API_KEY is a personal-access token (Lofty CRM ->
Settings -> Integrations -> API) with a documented "configurable expiration"
and no refresh flow -- unlike an OAuth access/refresh token pair. On a bad-token
response we raise a clear message telling the caller to regenerate the key,
rather than retrying.

Auth scheme: verified empirically against the real API (see
specs/rest/index.json "authCorrection") that this credential must be sent as
`Authorization: token <key>`, NOT `Authorization: Bearer <key>` -- despite
every operation in specs/openapi.json documenting Bearer. Bearer returns
HTTP 400 {"code":200058,"message":"User in token does not exist."} for this
credential type. Since a bad/expired token can plausibly surface as either a
bare 401 or that same 400+200058 shape, `_is_bad_token_error()` treats both as
the same condition rather than special-casing 401 alone.
"""

from __future__ import annotations

from typing import Any

import httpx

BASE_URL = "https://api.lofty.com"

# Lofty's "this credential is bad" signal isn't consistently one status code: an
# unrecognized/expired personal-access token can come back as a bare 401, but the
# empirically-observed wrong-auth-scheme case (see specs/rest/index.json
# "authCorrection") is actually HTTP 400 with this application-level error code.
# Treat both as the same "regenerate your key" condition rather than only 401,
# so the helpful message doesn't silently fail to fire for the documented case.
_BAD_TOKEN_ERROR_CODE = 200058


class LoftyApiError(Exception):
    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f"Lofty API error {status_code}: {body}")


def _is_bad_token_error(response: httpx.Response) -> bool:
    if response.status_code == 401:
        return True
    if response.status_code != 400:
        return False
    try:
        body = response.json()
    except ValueError:
        return False
    return isinstance(body, dict) and body.get("code") == _BAD_TOKEN_ERROR_CODE


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
    if _is_bad_token_error(response):
        raise LoftyApiError(
            response.status_code,
            "Authentication failed. This API key has no refresh mechanism -- "
            "regenerate it in the Lofty CRM under Settings -> Integrations -> API "
            "and update LOFTY_API_KEY.",
        )
    if response.is_error:
        raise LoftyApiError(response.status_code, response.text)
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError as exc:
        # A 2xx response with a non-JSON body (proxy/WAF/maintenance page in front
        # of api.lofty.com) shouldn't surface as a raw JSONDecodeError -- wrap it
        # in the same error type every other failure path produces.
        raise LoftyApiError(response.status_code, response.text) from exc
