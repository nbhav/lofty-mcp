# specs/

## `openapi.json`

Lofty's full OpenAPI spec, downloaded from
`https://developer.lofty.com/openapi/openapi.json` and saved here so it never needs
re-fetching. 102 operations across 27 tags. This is the authoritative source for every
endpoint path, parameter, and request/response schema used by this project.

## `rest/*.json`

One file per OpenAPI tag (resource), mechanically generated from `openapi.json` by
[`scripts/generate_rest_specs.py`](../scripts/generate_rest_specs.py) — regenerate with:

```
python scripts/generate_rest_specs.py
```

Each file lists that resource's operations (method, path, summary, parameters,
request body ref), with the `Authorization` header parameter stripped out — it's
injected by `src/lofty_mcp/rest_client.py`, never a tool-facing argument.

Start with **`rest/index.json`** — it's hand-maintained (not overwritten by the
generator) and holds the facts that matter most before touching any tool code:

- **`authCorrection`** — every operation's own doc says `Authorization: Bearer
  [access_token]`. That's wrong for this project's credential. The real, verified
  scheme is `Authorization: token <key>`. Sending Bearer gets a real rejection from
  Lofty's server (`400 200058 "User in token does not exist."`), not a client bug.
- **`versionDecisions`** — several resources exist at both `/v1.0/...` and `/v2.0/...`
  (tasks, communication). `index.json` records which version this project uses per
  resource and why, so new tools don't silently pick the wrong one.
- **`resources`** — implemented vs. pending, with the target implementation file for
  each.

See the root [`DESIGN.md`](../DESIGN.md) for why this project calls the REST API
directly instead of wrapping `lofty-cli`.
