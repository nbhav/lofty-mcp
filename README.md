# lofty-mcp

An MCP server that gives Claude tools to work with a [Lofty](https://www.lofty.com) CRM
account — leads, tasks/appointments, calendar, communications, and notes — by calling
Lofty's REST API directly.

For the reasoning behind how this project is built (why REST instead of `lofty-cli`,
the auth-scheme quirk, the HTTP-mode security tradeoffs), see [`DESIGN.md`](DESIGN.md).
This document is about what the project does and how to run it.

## Concepts

- **MCP (Model Context Protocol)** is the protocol Claude uses to discover and call
  tools exposed by an external server. This project *is* one such server: it doesn't
  talk to Claude directly, it registers **tools** (e.g. `lofty_leads_list`,
  `lofty_notes_create`) that a client (Claude Code, Cowork, etc.) can call on your
  behalf.
- **One tool module per Lofty resource.** `src/lofty_mcp/tools/` has one file per
  resource — `leads.py`, `tasks.py`, `calendar.py`, `communication.py`, `notes.py`,
  `whoami.py` — each registering the MCP tools for that resource's REST endpoints.
  35 tools total today; see `specs/rest/index.json` for what's implemented vs. pending.
- **Tool annotations.** Every tool carries
  [MCP `ToolAnnotations`](https://modelcontextprotocol.io)
  (`readOnlyHint`/`destructiveHint`/`idempotentHint`) — reads are marked read-only,
  creates/sends are non-idempotent, updates/deletes are destructive — so a well-behaved
  client can decide what to auto-approve vs. confirm with you. These are hints, not
  enforcement: nothing in the server itself blocks a destructive call.
- **Two transports, two use cases:**
  - **stdio** (default) — Claude Code spawns the server as a local subprocess per
    session. This is how you'd normally use it day to day.
  - **Streamable HTTP** — the server runs as a long-lived process bound to a port,
    for remote clients (e.g. Cowork's "Add custom connector") that can't spawn a
    process on your machine. Needs a real HTTPS URL in front of it; see
    "Connecting to a remote client" below.
- **Auth is a single API key**, not OAuth. `LOFTY_API_KEY` is a personal-access token
  from the Lofty CRM, sent as `Authorization: token <key>` on every request. There's no
  refresh flow — if it stops working, you regenerate it in the CRM.

## Initial setup

You need:

1. **Docker.** Everything — build, run, test — happens inside containers; nothing from
   this project's Python dependency stack is installed on your host. Install
   [Docker Desktop](https://www.docker.com/products/docker-desktop/) (macOS/Windows) or
   Docker Engine (Linux), and confirm it's running with `docker info`.
2. **A Lofty API key.** In the Lofty CRM, go to **Settings → Integrations → API** and
   generate a personal-access key.
3. **`jq`**, used by several `Makefile` targets to edit JSON config in place:
   `brew install jq` (macOS) or your distro's package manager.
4. *(Only if you'll use HTTP mode / remote connectors)* **`cloudflared`**:
   `brew install cloudflare/cloudflare/cloudflared`.

Then create a `.env` file at the repo root (already in `.gitignore` — never commit it):

```
LOFTY_API_KEY=your-key-here
```

If the key stops working, tool calls fail with a clear `LoftyApiError` pointing back at
Settings → Integrations → API — there's no refresh path, so regenerating the key is
always the fix.

## Project layout

```
src/lofty_mcp/
  server.py         entrypoint: MCPServer, lifespan-injected httpx client, transport selection
  rest_client.py     HTTP client: base URL, auth header, error mapping
  tools/             one module per resource (leads, tasks, calendar, communication, notes, whoami)
specs/
  openapi.json        Lofty's full OpenAPI spec (source of truth)
  rest/*.json          generated per-resource summaries (see specs/README.md)
scripts/
  generate_rest_specs.py   regenerates specs/rest/*.json from specs/openapi.json
  mcp_test_harness.py       reliable stdio request/response harness for smoke-testing
Dockerfile             plain python:3.12-slim, no CLI binary needed
Makefile               build/run/register/teardown commands (see below)
DESIGN.md              why the project is built this way (not how to run it)
```

## Building and testing

```
make help          # list all commands
make build          # docker build the image
make test           # run scripts/mcp_test_harness.py against it (real API calls)
```

## Connecting to Claude Code

```
make up             # builds the image, registers it in .mcp.json
```

This writes a `lofty` entry into the project's `.mcp.json`
(`command: docker, args: [run, -i, --rm, --env-file, <path>, lofty-mcp:py]`). Claude
Code auto-detects project-scoped `.mcp.json` files — restart the session (or run `/mcp`)
and approve the new server when prompted. `make down` removes the entry.

Each session spawns a fresh `docker run -i --rm` process over stdio; Docker tears it
down automatically when the session ends, so there's no separate container lifecycle to
manage here.

## Connecting to a remote client (e.g. Cowork)

Remote connectors need a real HTTPS URL, since they run in the cloud and can't spawn
processes on your machine. There are two ways to get one, depending on how long-lived
and trusted the deployment needs to be.

### Quick tunnel — short-lived local testing

```
make http-up         # runs the server in HTTP mode + a cloudflared quick tunnel
make http-down        # tears both down
```

`make http-up` binds the server to `0.0.0.0:8000` and fronts it with `cloudflared
tunnel --url` — no Cloudflare account needed, but the URL is random and changes every
run. By default this has **no authentication beyond `LOFTY_API_KEY`** baked into the
container: anyone with the tunnel URL can call every tool, including sends and deletes.

To close that gap for a quick tunnel session, set a shared secret before starting it:

```
MCP_HTTP_AUTH_TOKEN=some-long-random-string make http-up
```

With `MCP_HTTP_AUTH_TOKEN` set, every request must include
`Authorization: Bearer <that token>` or the server returns 401 before the request
reaches any tool. Without it, the server prints a loud warning on startup and runs
unauthenticated — fine for a few minutes of local testing torn down right after, not
for anything left running.

### Persistent tunnel — fixed hostname, Cloudflare Access OAuth

For anything longer-lived, use a **named tunnel** at a hostname you control, and put
[Cloudflare Access](https://developers.cloudflare.com/cloudflare-one/policies/access/)
in front of it for real OAuth login (Google, GitHub, Okta, etc.) — unauthenticated
requests never reach your machine at all.

One-time setup, requires a domain added to your Cloudflare account:

```
make tunnel-login     # opens a browser, authorizes cloudflared against your account (once per machine)
```

Add to `.env`:

```
TUNNEL_HOSTNAME=lofty-mcp.yourdomain.com
TUNNEL_NAME=lofty-mcp        # optional, defaults to lofty-mcp
```

Then:

```
make tunnel-create    # creates (or reuses) the named tunnel, routes TUNNEL_HOSTNAME's DNS to it
```

In the [Cloudflare Zero Trust dashboard](https://one.dash.cloudflare.com/) → Access →
Applications, add a Self-hosted application for `TUNNEL_HOSTNAME`, pick an identity
provider under Settings → Authentication, and add a policy allowing the people who
should have access. Then:

```
make http-up-persistent     # runs the server + the named tunnel at TUNNEL_HOSTNAME
make http-down-persistent   # tears both down
make http-status-persistent # check what's running
```

Once Access is configured, `MCP_HTTP_AUTH_TOKEN` (above) is still worth setting as
defense-in-depth at the application layer, but Access is what actually stops
unauthenticated traffic from reaching the container.

## Adding a new tool

Every resource in `specs/rest/*.json` not yet wired up (see `specs/rest/index.json`'s
`resources` list for what's implemented vs. pending) follows the same pattern as the
existing ones:

1. Read the resource's spec file for exact paths/params (or `specs/openapi.json`
   directly for full request/response schemas).
2. Add `src/lofty_mcp/tools/<resource>.py` with a `register(mcp)` function, one
   `@mcp.tool(annotations=ToolAnnotations(...))`-decorated function per operation,
   calling `rest_client.request()`.
3. Register it in `src/lofty_mcp/tools/__init__.py`.
4. `make test` to confirm it works against the real API.
