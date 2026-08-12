# lofty-mcp

An MCP server that gives Claude tools to work with a [Lofty](https://www.lofty.com) CRM
account — leads, tasks/appointments, calendar, communications, and notes — by calling
Lofty's REST API directly.

## Why REST, not `lofty-cli`

This project started as a wrapper around Lofty's official CLI (`@loftyai/lofty-cli`), on
the reasoning that the CLI would save us from reimplementing OAuth and from handling
64-bit lead/task IDs ourselves. That design was abandoned after hitting a real,
irreconcilable credential mismatch — documented here so it isn't rediscovered the hard
way:

- The only credential available for this project is a Lofty **personal-access API key**
  (generated in the CRM under **Settings → Integrations → API**).
- That credential authenticates over HTTP as `Authorization: token <key>` — confirmed
  empirically against `https://api.lofty.com` (`GET /v1.0/leads` → `200 OK` with real
  data).
- `lofty-cli` only speaks OAuth **Bearer** tokens. Every one of its auth methods (Direct
  Token, Token URL, Browser OAuth, Client Credentials) ends in an `Authorization: Bearer
  <token>` header. Feeding it the API key produces a real rejection from Lofty's own
  server: `Error 400: {"code":200058,"message":"User in token does not exist."}` — not a
  config problem, a protocol mismatch. The same request succeeds instantly with
  `Authorization: token <key>` instead of `Bearer`.
- Getting a CLI-compatible credential would mean either running a full browser OAuth
  flow to mint an access/refresh token pair, or registering an OAuth app in Lofty's
  Developer Portal for the Client Credentials flow — neither of which was available.

Given the working credential is REST-only, wrapping the CLI was never going to work, so
the server now calls `https://api.lofty.com` directly (see
[`src/lofty_mcp/rest_client.py`](src/lofty_mcp/rest_client.py)). This turned out to be a
simplification, not just a workaround:

- **No token refresh logic.** A personal-access API key doesn't expire on the
  short-lived OAuth cycle an access/refresh pair does — there's nothing to refresh. If
  it does stop working, the fix is regenerating it in the CRM, not a retry loop (see
  `LoftyApiError` in `rest_client.py`).
- **No 64-bit ID precision handling.** Lofty's lead/task IDs are 64-bit integers, which
  is a real hazard in JavaScript (`Number` loses precision above 2^53). Python's `int`
  is arbitrary-precision, so this was a genuine source of care in an earlier
  TypeScript/CLI prototype and simply isn't a concern here.
- **Full, authoritative API surface for free.** Lofty publishes a complete OpenAPI spec
  (`specs/openapi.json`, 102 operations across 27 resources) — a far more reliable
  source than scraping the CLI's `--help` text and prose docs, which is what the earlier
  prototype had to do. `specs/rest/*.json` is generated straight from it (see
  [`specs/README.md`](specs/README.md)).

## Authentication

Single env var: `LOFTY_API_KEY`, sent as `Authorization: token <key>`. Get it from the
Lofty CRM under **Settings → Integrations → API**. Put it in a `.env` file at the repo
root (not committed — see `.gitignore`):

```
LOFTY_API_KEY=your-key-here
```

If it stops working, calls fail with a clear `LoftyApiError` pointing back at that same
settings page — there is no refresh path, so regenerating the key is the fix.

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
```

Every tool carries [MCP `ToolAnnotations`](https://modelcontextprotocol.io)
(`readOnlyHint`/`destructiveHint`/`idempotentHint`) — reads are marked read-only,
creates/sends are marked non-idempotent, updates/deletes are marked destructive — so a
well-behaved client can decide what to auto-approve vs. confirm. These are hints, not
enforcement: nothing in this server itself blocks a destructive call.

## Setup

Requires Docker. Everything — build, run, test — happens inside containers; nothing
from this project's dependency stack is installed on the host.

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

```
make http-up         # runs the server in Streamable HTTP mode + a cloudflared quick tunnel
make http-down        # tears both down
```

Remote connectors (Anthropic's Cowork "Add custom connector" dialog, or anything else
that talks to an MCP server over HTTP rather than spawning a local process) need a real
HTTPS URL, since they run in the cloud and can't spawn processes on your machine. `make
http-up` runs the server bound to `0.0.0.0:8000` and fronts it with `cloudflared tunnel
--url` (no account needed, but the URL is random and changes every run).

### ⚠️ This has no authentication — do not leave it running

The HTTP endpoint accepts requests from **anyone who has the URL**. There is currently
no bearer token, no OAuth, nothing checking who's calling — only `LOFTY_API_KEY` baked
into the container's own environment. Whoever holds the tunnel URL can call every tool
in this server against the real Lofty account, including sends (SMS/email) and deletes.

This is acceptable for the way `make http-up` is meant to be used: a short-lived local
test, torn down with `make http-down` right after. It is **not** acceptable as a
standing deployment. The "Add custom connector" dialog itself has `OAuth Client ID` /
`OAuth Client Secret` fields for exactly this reason — before this server is exposed
anywhere longer-lived than a quick local tunnel, it needs an actual authorization layer
in front of the Streamable HTTP endpoint. Two ways to get there, roughly in order of
effort:

1. **A bearer token gate.** Cheapest option: require a shared secret in an
   `Authorization` header on every request to `/mcp`, checked in an ASGI middleware
   before it reaches the MCP app. Not OAuth, but closes the "anyone with the URL" hole.
2. **A real OAuth 2.1 authorization server**, per the
   [MCP Authorization spec](https://modelcontextprotocol.io/specification/latest/basic/authorization).
   This is what the Cowork dialog's OAuth fields expect: the MCP server acts as an
   OAuth *resource server*, validating bearer tokens issued by a separate *authorization
   server* (self-hosted, or a hosted provider like Auth0/WorkOS/Stytch). This is the
   correct answer for anything beyond solo local testing, but it's a genuinely separate
   piece of infrastructure — an OAuth server, client registration, token issuance and
   validation — not a config flag. Nothing in this repo implements it yet.

Also worth knowing: `run_streamable_http_async`'s DNS-rebinding protection
(`transport_security`) is left at the SDK's default, which is **disabled** unless
explicitly configured (see `src/lofty_mcp/server.py`) — another gap that matters once
this is reachable from anywhere untrusted.

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
