"""Entrypoint: MCPServer over stdio or Streamable HTTP, lifespan-injected httpx client,
LOFTY_API_KEY auth.

Run (stdio, default -- for Claude Code's .mcp.json): python -m lofty_mcp.server
Run (HTTP, for remote connectors like Cowork): MCP_TRANSPORT=http python -m lofty_mcp.server

HTTP mode binds 0.0.0.0 so it's reachable from outside the container (map the port
with `docker run -p`). It has no auth of its own beyond LOFTY_API_KEY being baked
into the container's env -- anyone who can reach the port/tunnel URL can call every
tool. Fine for local-machine + tunnel testing; add a real auth layer (e.g. a bearer
token checked in front of the ASGI app, or transport_security allowed_hosts/origins)
before exposing this anywhere less trusted.
"""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from dotenv import load_dotenv
from mcp.server import MCPServer

from lofty_mcp.rest_client import make_client
from lofty_mcp.tools import register_all

load_dotenv()


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


mcp = MCPServer("lofty-mcp", lifespan=lifespan)
register_all(mcp)


if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "http":
        host = os.environ.get("MCP_HTTP_HOST", "0.0.0.0")
        port = int(os.environ.get("MCP_HTTP_PORT", "8000"))
        mcp.run(transport="streamable-http", host=host, port=port)
    else:
        mcp.run()
