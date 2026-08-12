"""Leads tools -- GET/POST/PUT/DELETE /v1.0/leads* (specs/rest/leads.json).

Create/update bodies (LeadRequest/EditLeadRequest) have 30-50 fields including
nested `property`/`inquiry` objects -- too large to hand-expand into typed
parameters usefully. Those tools accept a raw `body: dict` matching the Lofty
schema instead; docstrings list the fields used most often and point at
specs/rest/leads.json / specs/openapi.json#/components/schemas/LeadRequest
for the rest.

Every tool carries MCP ToolAnnotations (read_only_hint/destructive_hint/
idempotent_hint) so a client can decide what to auto-approve vs. confirm --
these are hints, not enforcement (see mcp_types.ToolAnnotations docstring).
"""

from __future__ import annotations

from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp_types import ToolAnnotations

from lofty_mcp.rest_client import compact, request


def register(mcp: MCPServer) -> None:
    @mcp.tool(annotations=ToolAnnotations(title="List Leads", read_only_hint=True))
    async def lofty_leads_list(
        ctx: Context,
        stage: str | None = None,
        source: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        assigned_user_id: int | None = None,
        contacted: bool | None = None,
        segments: str | None = None,
        all_tags: str | None = None,
        any_tags: str | None = None,
        group_ids: int | None = None,
        offset: int | None = None,
        limit: int | None = None,
        sort: str | None = None,
        desc: bool | None = None,
        key: str | None = None,
        scroll_id: str | None = None,
    ) -> dict[str, Any]:
        """Search/list Lofty leads (GET /v1.0/leads).

        limit must be 1-100 (400 LIMIT_NOT_VALID otherwise). Use offset for
        offset-based paging or scroll_id (from a prior response) for cursor
        paging. key searches by name/phone/email. sort accepts values like
        LastContact, LastActivity, CreateTime, Score, etc.
        """
        client = ctx.request_context.lifespan_context.client
        params = compact(
            stage=stage,
            source=source,
            phone=phone,
            email=email,
            assignedUserId=assigned_user_id,
            contacted=contacted,
            segments=segments,
            allTags=all_tags,
            anyTags=any_tags,
            groupIds=group_ids,
            offset=offset,
            limit=limit,
            sort=sort,
            desc=desc,
            key=key,
            scrollId=scroll_id,
        )
        return await request(client, "GET", "/v1.0/leads", params=params)

    @mcp.tool(annotations=ToolAnnotations(title="Get Lead", read_only_hint=True))
    async def lofty_leads_get(ctx: Context, lead_id: int, with_trash: bool | None = None) -> dict[str, Any]:
        """Get a single Lofty lead by ID (GET /v1.0/leads/{leadId}). 404 LEAD_NOT_EXIST if inaccessible."""
        client = ctx.request_context.lifespan_context.client
        return await request(
            client, "GET", f"/v1.0/leads/{lead_id}", params=compact(withTrash=with_trash)
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Create Lead", read_only_hint=False, destructive_hint=False, idempotent_hint=False
        )
    )
    async def lofty_leads_create(ctx: Context, body: dict[str, Any]) -> dict[str, Any]:
        """Create a Lofty lead (POST /v1.0/leads).

        body is a LeadRequest object. Required: firstName. Commonly used fields:
        lastName, emails (list), phones (list), source, stage, assignedUserId
        (skips automatic routing if set), tags/tagsAdd (list), property (dict:
        streetAddress/city/state/zipCode/... -- at least one required if the
        property block is present at all), inquiry (dict: priceMin/priceMax/
        propertyType/locations/...), leadTypes (list of int: Seller=1, Buyer=2,
        Renter=5, Investor=6, Other=-1). Full schema:
        specs/openapi.json#/components/schemas/LeadRequest.
        """
        client = ctx.request_context.lifespan_context.client
        return await request(client, "POST", "/v1.0/leads", json=body)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Update Lead", read_only_hint=False, destructive_hint=True, idempotent_hint=True
        )
    )
    async def lofty_leads_update(ctx: Context, lead_id: int, body: dict[str, Any]) -> dict[str, Any]:
        """Update a Lofty lead (PUT /v1.0/leads/{leadId}).

        body is an EditLeadRequest object (same shape as create's LeadRequest,
        no required fields -- only send what you want to change). Full schema:
        specs/openapi.json#/components/schemas/EditLeadRequest.
        """
        client = ctx.request_context.lifespan_context.client
        return await request(client, "PUT", f"/v1.0/leads/{lead_id}", json=body)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Delete Lead", read_only_hint=False, destructive_hint=True, idempotent_hint=True
        )
    )
    async def lofty_leads_delete(ctx: Context, lead_id: int, reason: str) -> dict[str, Any]:
        """Move a Lofty lead to trash (DELETE /v1.0/leads/{leadId}). reason is required and audit-logged."""
        client = ctx.request_context.lifespan_context.client
        return await request(client, "DELETE", f"/v1.0/leads/{lead_id}", params=compact(reason=reason))

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Assign Lead", read_only_hint=False, destructive_hint=False, idempotent_hint=True
        )
    )
    async def lofty_leads_assign(ctx: Context, lead_id: int, assignee_user_ids: list[int]) -> dict[str, Any]:
        """Assign a Lofty lead to one or more agents (POST /v1.0/leads/{leadId}/assignment)."""
        client = ctx.request_context.lifespan_context.client
        return await request(client, "POST", f"/v1.0/leads/{lead_id}/assignment", json=assignee_user_ids)

    @mcp.tool(annotations=ToolAnnotations(title="Lead Activities", read_only_hint=True))
    async def lofty_leads_activities(ctx: Context, lead_id: int, cur_page: int | None = None) -> dict[str, Any]:
        """Get a lead's site-tracked activities: browse/search/favorite/showing/submission
        (GET /v1.0/leads/{leadId}/activities). Fixed page size of 100; cur_page is 0-indexed.
        """
        client = ctx.request_context.lifespan_context.client
        return await request(
            client, "GET", f"/v1.0/leads/{lead_id}/activities", params=compact(curPage=cur_page)
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Add Lead Activity", read_only_hint=False, destructive_hint=False, idempotent_hint=False
        )
    )
    async def lofty_leads_add_activity(ctx: Context, lead_id: int, body: dict[str, Any]) -> dict[str, Any]:
        """Log engagement activity against a lead (POST /v1.0/leads/{leadId}/activity).

        body is a LeadActivity object. The OpenAPI spec marks created, link,
        picture, text, and type as all required, though not every field is
        meaningful for every activity type -- pass an empty string for ones
        that don't apply. type: Search/Browse/Favorite/... (see
        specs/openapi.json#/components/schemas/LeadActivity for the full enum
        and per-type field meaning). created is epoch milliseconds.
        """
        client = ctx.request_context.lifespan_context.client
        return await request(client, "POST", f"/v1.0/leads/{lead_id}/activity", json=body)
