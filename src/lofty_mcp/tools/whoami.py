"""Whoami diagnostic -- GET /v1.0/me (specs/rest/members.json).

Replaces the old CLI-based auth_status tool: there's no CLI and no multi-level
auth state to inspect anymore, just one API key. This is a lightweight "is the
key working" check that resolves the caller's own profile from the token.
"""

from __future__ import annotations

from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp_types import ToolAnnotations

from lofty_mcp.rest_client import request


def register(mcp: MCPServer) -> None:
    @mcp.tool(annotations=ToolAnnotations(title="Who Am I", read_only_hint=True))
    async def lofty_whoami(ctx: Context) -> dict[str, Any]:
        """Get the authenticated user's own profile (GET /v1.0/me). Useful to confirm LOFTY_API_KEY is valid."""
        client = ctx.request_context.lifespan_context.client
        return await request(client, "GET", "/v1.0/me")
