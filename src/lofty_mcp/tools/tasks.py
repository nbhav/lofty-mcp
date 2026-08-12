"""Tasks & appointments (V2) tools -- /v2.0/tasks* (specs/rest/tasks-appointments-v2.json).

V2 chosen over /v1.0/tasks* because it's a strict superset (adds finish/
unfinish and my-tasks); see specs/rest/index.json "versionDecisions".
"""

from __future__ import annotations

from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp_types import ToolAnnotations

from lofty_mcp.rest_client import compact, request


def register(mcp: MCPServer) -> None:
    @mcp.tool(annotations=ToolAnnotations(title="List Tasks", read_only_hint=True))
    async def lofty_tasks_list(ctx: Context, lead_id: int) -> dict[str, Any]:
        """List all tasks and appointments attached to a lead (GET /v2.0/tasks)."""
        client = ctx.request_context.lifespan_context.client
        return await request(client, "GET", "/v2.0/tasks", params=compact(leadId=lead_id))

    @mcp.tool(annotations=ToolAnnotations(title="Get Task", read_only_hint=True))
    async def lofty_tasks_get(ctx: Context, task_id: int) -> dict[str, Any]:
        """Get a single task or appointment by ID (GET /v2.0/tasks/{taskId})."""
        client = ctx.request_context.lifespan_context.client
        return await request(client, "GET", f"/v2.0/tasks/{task_id}")

    @mcp.tool(annotations=ToolAnnotations(title="My Tasks", read_only_hint=True))
    async def lofty_tasks_my_tasks(
        ctx: Context,
        user_id: int | None = None,
        current_id: int | None = None,
        limit: int | None = None,
        time_zone_code: str | None = None,
    ) -> dict[str, Any]:
        """List tasks assigned to a user, sorted by startTime descending (GET /v2.0/tasks/my-tasks).

        Defaults to the authenticated user if user_id is omitted. Cursor pagination:
        pass the last returned item's id as current_id to fetch the next page. limit is 1-100 (default 10).
        """
        client = ctx.request_context.lifespan_context.client
        params = compact(userId=user_id, currentId=current_id, limit=limit, timeZoneCode=time_zone_code)
        return await request(client, "GET", "/v2.0/tasks/my-tasks", params=params)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Create Task", read_only_hint=False, destructive_hint=False, idempotent_hint=False
        )
    )
    async def lofty_tasks_create(
        ctx: Context,
        lead_id: int,
        type: str,
        content: str | None = None,
        assigned_role: str | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
        time_zone_code: str | None = None,
        address: str | None = None,
    ) -> dict[str, Any]:
        """Create a task or appointment on a lead (POST /v2.0/tasks).

        type is required: Other, Call, Email, Text, or Appointment. start_at/end_at
        are ISO8601 with offset, e.g. '2026-03-01T15:00:00-08:00'. address is for
        Appointment-type entries. Response contains the new entry's ID under 'taskId'.
        """
        client = ctx.request_context.lifespan_context.client
        body = compact(
            leadId=lead_id,
            type=type,
            content=content,
            assignedRole=assigned_role,
            startAt=start_at,
            endAt=end_at,
            timeZoneCode=time_zone_code,
            address=address,
        )
        return await request(client, "POST", "/v2.0/tasks", json=body)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Update Task", read_only_hint=False, destructive_hint=True, idempotent_hint=True
        )
    )
    async def lofty_tasks_update(
        ctx: Context,
        task_id: int,
        content: str | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
        time_zone_code: str | None = None,
        address: str | None = None,
    ) -> dict[str, Any]:
        """Partially update a task or appointment (PUT /v2.0/tasks/{taskId}).

        At least one of content/start_at/end_at/address must be supplied. Use
        lofty_tasks_finish/lofty_tasks_unfinish for completion state, not this.
        """
        client = ctx.request_context.lifespan_context.client
        body = compact(content=content, startAt=start_at, endAt=end_at, timeZoneCode=time_zone_code, address=address)
        return await request(client, "PUT", f"/v2.0/tasks/{task_id}", json=body)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Delete Task", read_only_hint=False, destructive_hint=True, idempotent_hint=True
        )
    )
    async def lofty_tasks_delete(ctx: Context, task_id: int) -> dict[str, Any]:
        """Delete a task or appointment (DELETE /v2.0/tasks/{taskId})."""
        client = ctx.request_context.lifespan_context.client
        return await request(client, "DELETE", f"/v2.0/tasks/{task_id}")

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Finish Task", read_only_hint=False, destructive_hint=False, idempotent_hint=True
        )
    )
    async def lofty_tasks_finish(ctx: Context, task_id: int) -> dict[str, Any]:
        """Mark a task or appointment as completed (POST /v2.0/tasks/{taskId}/finish).

        Smart-plan tasks can't be finished this way (TASK_IS_SMARTPLAN error).
        """
        client = ctx.request_context.lifespan_context.client
        return await request(client, "POST", f"/v2.0/tasks/{task_id}/finish")

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Unfinish Task", read_only_hint=False, destructive_hint=False, idempotent_hint=True
        )
    )
    async def lofty_tasks_unfinish(ctx: Context, task_id: int) -> dict[str, Any]:
        """Revert a task or appointment to not-completed (POST /v2.0/tasks/{taskId}/unfinish)."""
        client = ctx.request_context.lifespan_context.client
        return await request(client, "POST", f"/v2.0/tasks/{task_id}/unfinish")
