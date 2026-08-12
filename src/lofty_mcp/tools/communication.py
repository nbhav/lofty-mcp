"""Communication tools -- mixed v1/v2 (specs/rest/communication.json, communication-v2.json).

Version choices (see specs/rest/index.json "versionDecisions"):
- send-sms / send-email: v1, only version.
- call history: /v1.0/communication/call/v2 -- same param shape as v1, but its own
  description says it covers "additional event types not covered by the v1 variant".
- email/text history: plain v1, no v2 variant exists.
- agent-communication search: GET /v2.0/communication/agent (cursor-paged, query
  params) instead of POST /v1.0/agent/communication (JSON body) -- cleaner fit for
  a search-style tool.
"""

from __future__ import annotations

from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp_types import ToolAnnotations

from lofty_mcp.rest_client import compact, request


def register(mcp: MCPServer) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Send SMS", read_only_hint=False, destructive_hint=False, idempotent_hint=False
        )
    )
    async def lofty_communication_send_sms(
        ctx: Context,
        lead_id: int,
        content: str,
        phone_number: str | None = None,
        phone_code: str | None = None,
    ) -> dict[str, Any]:
        """Send an SMS to a lead from the caller's virtual number (POST /v1.0/message/sms/send).

        phone_number+phone_code select a specific phone on the lead; if omitted, the
        lead's primary phone is used. Caller must have an active virtual number.
        """
        client = ctx.request_context.lifespan_context.client
        body = compact(leadId=lead_id, content=content, phoneNumber=phone_number, phoneCode=phone_code)
        return await request(client, "POST", "/v1.0/message/sms/send", json=body)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Send Email", read_only_hint=False, destructive_hint=False, idempotent_hint=False
        )
    )
    async def lofty_communication_send_email(
        ctx: Context,
        lead_id: int,
        subject: str,
        content: str,
        to_email: str | None = None,
    ) -> dict[str, Any]:
        """Send an email to a lead (POST /v1.0/message/email/send).

        to_email selects a specific email on the lead; if omitted or not found, the
        lead's primary email is used.
        """
        client = ctx.request_context.lifespan_context.client
        body = compact(leadId=lead_id, subject=subject, content=content, toEmail=to_email)
        return await request(client, "POST", "/v1.0/message/email/send", json=body)

    @mcp.tool(annotations=ToolAnnotations(title="Call History", read_only_hint=True))
    async def lofty_communication_calls(
        ctx: Context,
        lead_id: int,
        offset: int | None = None,
        limit: int | None = None,
        current_id: int | None = None,
    ) -> dict[str, Any]:
        """Search a lead's call history (GET /v1.0/communication/call/v2).

        Uses the v2-flavored endpoint (still under the /v1.0 path) since it covers
        additional event types beyond plain v1. current_id pages from a prior result.
        """
        client = ctx.request_context.lifespan_context.client
        params = compact(leadId=lead_id, offset=offset, limit=limit, currentId=current_id)
        return await request(client, "GET", "/v1.0/communication/call/v2", params=params)

    @mcp.tool(annotations=ToolAnnotations(title="Email History", read_only_hint=True))
    async def lofty_communication_emails(
        ctx: Context,
        lead_id: int,
        offset: int | None = None,
        limit: int | None = None,
        current_id: int | None = None,
    ) -> dict[str, Any]:
        """Search a lead's email history (GET /v1.0/communication/email)."""
        client = ctx.request_context.lifespan_context.client
        params = compact(leadId=lead_id, offset=offset, limit=limit, currentId=current_id)
        return await request(client, "GET", "/v1.0/communication/email", params=params)

    @mcp.tool(annotations=ToolAnnotations(title="SMS History", read_only_hint=True))
    async def lofty_communication_texts(
        ctx: Context,
        lead_id: int,
        offset: int | None = None,
        limit: int | None = None,
        current_id: int | None = None,
    ) -> dict[str, Any]:
        """Search a lead's SMS history (GET /v1.0/communication/text)."""
        client = ctx.request_context.lifespan_context.client
        params = compact(leadId=lead_id, offset=offset, limit=limit, currentId=current_id)
        return await request(client, "GET", "/v1.0/communication/text", params=params)

    @mcp.tool(annotations=ToolAnnotations(title="Search Agent Communications", read_only_hint=True))
    async def lofty_communication_agent_communication(
        ctx: Context,
        start_time: int,
        end_time: int,
        type: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        team_view: bool | None = None,
    ) -> dict[str, Any]:
        """Search communication timeline entries for the caller (GET /v2.0/communication/agent).

        start_time/end_time are epoch milliseconds; the window may span up to 90
        days. type: CALL, TEXT, EMAIL, or ALL. team_view=true includes the team's
        communications (requires ACCESS_ALL_TEAM_LEADS permission). Cursor-paged:
        pass a prior response's cursor to continue.
        """
        client = ctx.request_context.lifespan_context.client
        params = compact(
            type=type, startTime=start_time, endTime=end_time, limit=limit, cursor=cursor, teamView=team_view
        )
        return await request(client, "GET", "/v2.0/communication/agent", params=params)
