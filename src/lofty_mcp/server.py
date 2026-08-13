"""Entrypoint: MCPServer over stdio or Streamable HTTP, lifespan-injected httpx client,
LOFTY_API_KEY auth.

Run (stdio, default -- for Claude Code's .mcp.json): python -m lofty_mcp.server
Run (HTTP, for remote connectors like Cowork): MCP_TRANSPORT=http python -m lofty_mcp.server

HTTP mode binds 0.0.0.0 so it's reachable from outside the container (map the port
with `docker run -p`). By itself it has no auth beyond LOFTY_API_KEY being baked
into the container's env -- anyone who can reach the port/tunnel URL (e.g. the
`make http-up` cloudflared tunnel) can call every tool, including destructive ones.
Set MCP_HTTP_AUTH_TOKEN to require `Authorization: Bearer <token>` on every HTTP
request; without it, startup prints a loud warning and runs unauthenticated (only
appropriate for a throwaway local-machine + tunnel test, never anything trusted).
"""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

import httpx
from dotenv import load_dotenv
from mcp.server import MCPServer

from lofty_mcp.rest_client import make_client
from lofty_mcp.tools import register_all

load_dotenv()

try:
    __version__ = _pkg_version("lofty-mcp")
except PackageNotFoundError:  # running from source without an installed distribution
    __version__ = "0.0.0-dev"


@dataclass
class AppContext:
    client: httpx.AsyncClient


@asynccontextmanager
async def lifespan(server: MCPServer) -> AsyncIterator[AppContext]:
    api_key = os.environ.get("LOFTY_API_KEY")
    if not api_key:
        print(
            "LOFTY_API_KEY must be set (Lofty CRM -> Settings -> Integrations -> API).",
            file=sys.stderr,
        )
        raise RuntimeError("LOFTY_API_KEY is not set")
    client = make_client(api_key)
    try:
        yield AppContext(client=client)
    finally:
        await client.aclose()


mcp = MCPServer("lofty-mcp", version=__version__, lifespan=lifespan)
register_all(mcp)


class _BearerAuthMiddleware:
    """Minimal shared-secret gate for HTTP mode.

    Not OAuth -- just requires `Authorization: Bearer <token>` to match
    MCP_HTTP_AUTH_TOKEN on every HTTP request before it reaches the MCP app, so a
    tunnel URL alone (e.g. the random *.trycloudflare.com host `make http-up`
    hands out) isn't enough on its own to call tools against the live Lofty CRM.
    """

    def __init__(self, app, token: str) -> None:
        self.app = app
        self._expected = f"Bearer {token}"

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        got = headers.get(b"authorization", b"").decode("latin-1")
        if got != self._expected:
            from starlette.responses import PlainTextResponse

            await PlainTextResponse("Unauthorized", status_code=401)(scope, receive, send)
            return
        await self.app(scope, receive, send)


def _run_http(host: str, port: int) -> None:
    import anyio
    import uvicorn

    auth_token = os.environ.get("MCP_HTTP_AUTH_TOKEN")
    if not auth_token:
        print(
            "WARNING: MCP_TRANSPORT=http is starting with NO authentication beyond "
            "LOFTY_API_KEY baked into the environment. Anyone who can reach this port "
            "-- or a tunnel URL pointed at it, e.g. via `make http-up` -- can call "
            "every tool against the live Lofty CRM, including destructive ones like "
            "lofty_leads_delete. Set MCP_HTTP_AUTH_TOKEN to require a bearer token on "
            "every request before exposing this anywhere less trusted.",
            file=sys.stderr,
        )

    app = mcp.streamable_http_app(host=host)
    if auth_token:
        app = _BearerAuthMiddleware(app, auth_token)

    config = uvicorn.Config(app, host=host, port=port, log_level=mcp.settings.log_level.lower())
    anyio.run(uvicorn.Server(config).serve)


if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "http":
        host = os.environ.get("MCP_HTTP_HOST", "0.0.0.0")
        port = int(os.environ.get("MCP_HTTP_PORT", "8000"))
        _run_http(host, port)
    else:
        mcp.run()
