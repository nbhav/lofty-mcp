# Design decisions

This document is the "why" behind this project's shape — history, tradeoffs, and things
that would otherwise get silently rediscovered or reverted. For what the project does
and how to run it, see [`README.md`](README.md).

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

## The auth scheme is empirically-verified, not spec-verified

`specs/openapi.json` documents `Authorization: Bearer [access_token]` on every single
operation. That's wrong for the credential this project actually has. The real, working
scheme (`Authorization: token <key>`) was found by testing directly against
`https://api.lofty.com`, not by reading docs — see `specs/rest/index.json`'s
`authCorrection` for the full empirical record, including the exact rejection body
Bearer produces (`400 {"code":200058,"message":"User in token does not exist."}`).

Because the failure mode for a *wrong scheme* is that specific 400+200058 shape, and
it's plausible an *expired/revoked* key produces the same shape (both are "this token
doesn't resolve to a user" from Lofty's point of view), `rest_client.py`'s
`_is_bad_token_error()` treats both a bare 401 and that specific 400 as the same
"regenerate your key" condition, rather than trusting either status code alone.

## HTTP-mode security posture

Streamable HTTP mode binds `0.0.0.0` so it's reachable from outside the container. Three
layers exist today, each a deliberate tradeoff rather than a finished security model:

1. **`LOFTY_API_KEY`**, baked into the container's environment — this authenticates the
   *server* to Lofty's API. It says nothing about who's allowed to call *this* server.
2. **`MCP_HTTP_AUTH_TOKEN`** (optional) — a shared-secret bearer check implemented as a
   thin ASGI middleware in `server.py`, wrapping the Starlette app the `mcp` SDK builds
   via `streamable_http_app()`, ahead of `uvicorn.Server`. This is the cheapest closeable
   gap: no OAuth, no client registration, just "does the `Authorization` header match".
   It's deliberately *not* built on the `mcp` package's `auth`/`token_verifier`/
   `AuthSettings` machinery, which models a full OAuth 2.1 resource server (issuer URL,
   protected-resource metadata, scopes) — appropriate for a real multi-tenant deployment,
   not for a single-operator personal-access-key server.
3. **Cloudflare Access** (recommended for anything beyond solo local testing) — real
   OAuth login (Google/GitHub/Okta/etc.) enforced at Cloudflare's edge, in front of a
   *named* tunnel with a fixed hostname (as opposed to the quick tunnel's random,
   throwaway URL). Unauthenticated requests never reach the container. This is the
   answer to what the Cowork "Add custom connector" dialog's `OAuth Client ID`/`OAuth
   Client Secret` fields are asking for, without this project needing to implement an
   OAuth authorization server itself.

Two gaps worth knowing about even with the above in place:

- `run_streamable_http_async`'s DNS-rebinding protection (`transport_security`) is left
  at the SDK's default, which is **disabled** unless explicitly configured
  (`mcp/server/transport_security.py`: `TransportSecuritySettings(
  enable_dns_rebinding_protection=False)` is the fallback when nothing is passed). The
  quick tunnel's random `*.trycloudflare.com` hostname changing every run is part of why
  this hasn't been tightened — a fixed `allowed_hosts` list doesn't fit that workflow.
  The persistent-tunnel path (fixed hostname) is a more natural fit for turning this on
  if it's ever wired up.
- The `MCP_HTTP_AUTH_TOKEN` check is a flat string compare on every request, not a
  constant-time comparison — a timing side-channel in theory, low real-world risk given
  this isn't meant to be internet-facing without Access in front of it too.

## Why `lofty_notes_update` fetches before it writes

The Lofty notes API requires `content`, `leadId`, and `isPin` on every `PUT` — there's
no partial-update semantics for `isPin` specifically. A tool signature that defaults
`is_pin` to `False` would silently unpin a note on every content-only edit. Rather than
make `is_pin` required (forcing every caller to know and repeat the current pin state
just to fix a typo), `lofty_notes_update` treats "not passed" as "preserve current
state": it does a `GET` first when `is_pin` is omitted, reads the existing value, and
only then sends the `PUT`. Costs an extra round-trip on the common case; the alternative
(silent data loss on unrelated edits) was worse.

## Why `clear_fields` instead of `None` meaning "clear"

`rest_client.compact()` drops every `None`-valued argument before building a request
body, which is what makes optional tool parameters like `lofty_calendar_update`'s
`address` mean "leave unchanged" when omitted. That's the right default for a
partial-update tool — but it also means `None` can never mean "set this to null" through
the same mechanism. Rather than overload `None` with two meanings (which would make
"leave unchanged" impossible to express instead), `lofty_calendar_update` and
`lofty_tasks_update` take a separate `clear_fields: list[str] | None` parameter: names
in that list get explicitly nulled in the request body regardless of what the
correspondingly-named parameter was passed. Slightly more to explain in the docstring;
keeps both operations expressible.
