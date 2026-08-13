"""Notes tools -- /v1.0/notes* (specs/rest/notes.json). Only version that exists."""

from __future__ import annotations

from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp_types import ToolAnnotations

from lofty_mcp.rest_client import compact, request


def register(mcp: MCPServer) -> None:
    @mcp.tool(annotations=ToolAnnotations(title="List Notes", read_only_hint=True))
    async def lofty_notes_list(ctx: Context, lead_id: int, include_system_note: bool | None = None) -> dict[str, Any]:
        """List notes for a lead (GET /v1.0/notes)."""
        client = ctx.request_context.lifespan_context.client
        params = compact(leadId=lead_id, includeSystemNote=include_system_note)
        return await request(client, "GET", "/v1.0/notes", params=params)

    @mcp.tool(annotations=ToolAnnotations(title="Get Note", read_only_hint=True))
    async def lofty_notes_get(ctx: Context, note_id: int) -> dict[str, Any]:
        """Get a note by ID (GET /v1.0/notes/{noteId})."""
        client = ctx.request_context.lifespan_context.client
        return await request(client, "GET", f"/v1.0/notes/{note_id}")

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Create Note", read_only_hint=False, destructive_hint=False, idempotent_hint=False
        )
    )
    async def lofty_notes_create(ctx: Context, lead_id: int, content: str, is_pin: bool = False) -> dict[str, Any]:
        """Create a note on a lead (POST /v1.0/notes). content is silently truncated to 2000 characters."""
        client = ctx.request_context.lifespan_context.client
        body = {"leadId": lead_id, "content": content, "isPin": is_pin}
        return await request(client, "POST", "/v1.0/notes", json=body)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Update Note", read_only_hint=False, destructive_hint=True, idempotent_hint=True
        )
    )
    async def lofty_notes_update(
        ctx: Context, note_id: int, lead_id: int, content: str, is_pin: bool | None = None
    ) -> dict[str, Any]:
        """Update a note (PUT /v1.0/notes/{noteId}). content and lead_id are required.

        is_pin defaults to preserving the note's current pinned state: the API requires
        isPin on every PUT (no partial-update semantics for it), so when is_pin isn't
        passed explicitly, this tool first GETs the note to read its existing isPin
        value rather than silently resetting it to false. Pass is_pin explicitly to
        pin/unpin as part of the same call.
        """
        client = ctx.request_context.lifespan_context.client
        if is_pin is None:
            current = await request(client, "GET", f"/v1.0/notes/{note_id}")
            is_pin = bool(current.get("isPin", False))
        body = {"leadId": lead_id, "content": content, "isPin": is_pin}
        return await request(client, "PUT", f"/v1.0/notes/{note_id}", json=body)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Delete Note", read_only_hint=False, destructive_hint=True, idempotent_hint=True
        )
    )
    async def lofty_notes_delete(ctx: Context, note_id: int) -> dict[str, Any]:
        """Delete a note (DELETE /v1.0/notes/{noteId})."""
        client = ctx.request_context.lifespan_context.client
        return await request(client, "DELETE", f"/v1.0/notes/{note_id}")
