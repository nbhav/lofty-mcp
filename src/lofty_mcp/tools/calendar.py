"""Calendar (V2) tools -- /v2.0/calendar* (specs/rest/calendar-v2-api.json). Only version that exists.

calendar_id is a composite string ("<numericId>-task" or "<numericId>-appointment")
returned by create -- not a plain integer. Must be reused as-is for update/delete/
finish/unfinish.
"""

from __future__ import annotations

from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp_types import ToolAnnotations

from lofty_mcp.rest_client import compact, request


def register(mcp: MCPServer) -> None:
    @mcp.tool(annotations=ToolAnnotations(title="List Calendar Events", read_only_hint=True))
    async def lofty_calendar_list(
        ctx: Context,
        lead_id: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
        time_zone_code: str | None = None,
        include_finished: bool | None = None,
        page: int | None = None,
        page_size: int | None = None,
        sort: str | None = None,
        desc: bool | None = None,
        source_type: str | None = None,
    ) -> dict[str, Any]:
        """List calendar entries -- Tasks and Appointments (GET /v2.0/calendar).

        At least one of start_time/end_time (ISO8601 with offset) is required.
        include_finished=true returns both finished and unfinished; false returns
        only unfinished. page_size max 500.
        """
        client = ctx.request_context.lifespan_context.client
        params = compact(
            leadId=lead_id,
            startTime=start_time,
            endTime=end_time,
            startTimeMs=start_time_ms,
            endTimeMs=end_time_ms,
            timeZoneCode=time_zone_code,
            includeFinished=include_finished,
            page=page,
            pageSize=page_size,
            sort=sort,
            desc=desc,
            sourceType=source_type,
        )
        return await request(client, "GET", "/v2.0/calendar", params=params)

    @mcp.tool(annotations=ToolAnnotations(title="Available Meetings", read_only_hint=True))
    async def lofty_calendar_available(
        ctx: Context,
        start_time: str | None = None,
        end_time: str | None = None,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
        time_zone_code: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """List available meeting slots (GET /v2.0/calendar/meetings/available).

        Provide start_time/end_time (ISO8601) or the _ms epoch-millisecond variants.
        Range must not exceed 90 days; resolved start must be later than now.
        """
        client = ctx.request_context.lifespan_context.client
        params = compact(
            startTime=start_time,
            endTime=end_time,
            startTimeMs=start_time_ms,
            endTimeMs=end_time_ms,
            timeZoneCode=time_zone_code,
            limit=limit,
        )
        return await request(client, "GET", "/v2.0/calendar/meetings/available", params=params)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Create Calendar Event", read_only_hint=False, destructive_hint=False, idempotent_hint=False
        )
    )
    async def lofty_calendar_create(
        ctx: Context,
        type: str,
        lead_id: int,
        content: str,
        time_zone_code: str,
        start_at: str | None = None,
        end_at: str | None = None,
        start_at_ms: int | None = None,
        end_at_ms: int | None = None,
        task_way: str | None = None,
        assigned_role: str | None = None,
        address: str | None = None,
    ) -> dict[str, Any]:
        """Create a calendar Task or Appointment (POST /v2.0/calendar).

        type: TASK or APPOINTMENT (case-insensitive). task_way and assigned_role
        are required when type=TASK; address is used for type=APPOINTMENT.
        start_at/end_at must be later than the current server time. The response's
        data.id is a composite string ("<id>-task"/"<id>-appointment") -- reuse it
        as-is for update/delete/finish/unfinish.
        """
        client = ctx.request_context.lifespan_context.client
        body = compact(
            type=type,
            leadId=lead_id,
            content=content,
            timeZoneCode=time_zone_code,
            startAt=start_at,
            endAt=end_at,
            startAtMs=start_at_ms,
            endAtMs=end_at_ms,
            taskWay=task_way,
            assignedRole=assigned_role,
            address=address,
        )
        return await request(client, "POST", "/v2.0/calendar", json=body)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Update Calendar Event", read_only_hint=False, destructive_hint=True, idempotent_hint=True
        )
    )
    async def lofty_calendar_update(
        ctx: Context,
        calendar_id: str,
        content: str | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
        start_at_ms: int | None = None,
        end_at_ms: int | None = None,
        time_zone_code: str | None = None,
        reminder_type: str | None = None,
        reminder_time: str | None = None,
        lead_id: int | None = None,
        address: str | None = None,
        clear_fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """Partially update a calendar Task or Appointment (PUT /v2.0/calendar/{calendarId}).

        calendar_id is the composite string from create ("<id>-task"/"<id>-appointment").
        Only supplied fields are changed -- omitting a parameter (leaving it None) leaves
        that field alone. start_at/end_at, if supplied, must be later than now.

        Since omitting a field means "unchanged", there's no way to *clear* an optional
        field just by passing None -- use clear_fields for that: a list of this tool's own
        parameter names (e.g. ["address"]) to explicitly null out in the request, even
        though that parameter wasn't otherwise supplied.
        """
        client = ctx.request_context.lifespan_context.client
        field_map = {
            "content": "content",
            "start_at": "startAt",
            "end_at": "endAt",
            "start_at_ms": "startAtMs",
            "end_at_ms": "endAtMs",
            "time_zone_code": "timeZoneCode",
            "reminder_type": "reminderType",
            "reminder_time": "reminderTime",
            "lead_id": "leadId",
            "address": "address",
        }
        body = compact(
            content=content,
            startAt=start_at,
            endAt=end_at,
            startAtMs=start_at_ms,
            endAtMs=end_at_ms,
            timeZoneCode=time_zone_code,
            reminderType=reminder_type,
            reminderTime=reminder_time,
            leadId=lead_id,
            address=address,
        )
        for field in clear_fields or []:
            body[field_map.get(field, field)] = None
        return await request(client, "PUT", f"/v2.0/calendar/{calendar_id}", json=body)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Delete Calendar Event", read_only_hint=False, destructive_hint=True, idempotent_hint=True
        )
    )
    async def lofty_calendar_delete(ctx: Context, calendar_id: str) -> dict[str, Any]:
        """Delete a calendar Task or Appointment (DELETE /v2.0/calendar/{calendarId})."""
        client = ctx.request_context.lifespan_context.client
        return await request(client, "DELETE", f"/v2.0/calendar/{calendar_id}")

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Finish Calendar Event", read_only_hint=False, destructive_hint=False, idempotent_hint=True
        )
    )
    async def lofty_calendar_finish(ctx: Context, calendar_id: str) -> dict[str, Any]:
        """Mark a calendar Task or Appointment as finished (POST /v2.0/calendar/{calendarId}/finish)."""
        client = ctx.request_context.lifespan_context.client
        return await request(client, "POST", f"/v2.0/calendar/{calendar_id}/finish")

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Unfinish Calendar Event", read_only_hint=False, destructive_hint=False, idempotent_hint=True
        )
    )
    async def lofty_calendar_unfinish(ctx: Context, calendar_id: str) -> dict[str, Any]:
        """Revert a calendar Task or Appointment to not-completed (POST /v2.0/calendar/{calendarId}/unfinish)."""
        client = ctx.request_context.lifespan_context.client
        return await request(client, "POST", f"/v2.0/calendar/{calendar_id}/unfinish")
