"""Registers every tool module with the MCPServer instance.

Starting resource slice: leads, tasks (v2), calendar (v2), communication,
notes, whoami. Every other resource in specs/rest/*.json follows the same
register(mcp) pattern -- add a new tools/<resource>.py and call its register()
here.
"""

from __future__ import annotations

from mcp.server import MCPServer

from . import calendar, communication, leads, notes, tasks, whoami


def register_all(mcp: MCPServer) -> None:
    leads.register(mcp)
    tasks.register(mcp)
    calendar.register(mcp)
    communication.register(mcp)
    notes.register(mcp)
    whoami.register(mcp)
