"""Regenerate specs/rest/*.json from specs/openapi.json.

One-off/rerunnable codegen: groups the 102 operations in the Lofty OpenAPI spec by their
first tag and writes one summary file per resource, stripping the `Authorization` header
parameter (it's injected by rest_client.py, never a tool-facing argument) and keeping just
what's needed to write/verify a tool handler quickly.

Run: python scripts/generate_rest_specs.py
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OPENAPI_PATH = REPO_ROOT / "specs" / "openapi.json"
OUT_DIR = REPO_ROOT / "specs" / "rest"


def slugify(tag: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", tag.lower()).strip("-")
    return slug


def summarize_parameter(param: dict) -> dict:
    schema = param.get("schema", {})
    return {
        "name": param["name"],
        "in": param["in"],
        "required": param.get("required", False),
        "type": schema.get("type"),
        "format": schema.get("format"),
        "description": param.get("description"),
    }


def summarize_request_body(request_body: dict | None) -> dict | None:
    if not request_body:
        return None
    content = request_body.get("content", {})
    json_content = content.get("application/json", {})
    schema = json_content.get("schema", {})
    return {
        "required": request_body.get("required", False),
        "schemaRef": schema.get("$ref"),
        "inlineType": schema.get("type") if "$ref" not in schema else None,
    }


def summarize_operation(method: str, path: str, op: dict) -> dict:
    params = [
        summarize_parameter(p)
        for p in op.get("parameters", [])
        if not (p["in"] == "header" and p["name"] == "Authorization")
    ]
    return {
        "operationId": op.get("operationId"),
        "method": method.upper(),
        "path": path,
        "summary": op.get("summary"),
        "description": op.get("description"),
        "parameters": params,
        "requestBody": summarize_request_body(op.get("requestBody")),
    }


def main() -> None:
    spec = json.loads(OPENAPI_PATH.read_text())
    resources: dict[str, dict] = {}

    for path, methods in spec.get("paths", {}).items():
        for method, op in methods.items():
            tags = op.get("tags") or ["untagged"]
            tag = tags[0]
            slug = slugify(tag)
            resources.setdefault(slug, {"tag": tag, "operations": []})
            resources[slug]["operations"].append(summarize_operation(method, path, op))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for slug, data in sorted(resources.items()):
        data["operations"].sort(key=lambda o: (o["path"], o["method"]))
        out = {
            "resource": slug,
            "tag": data["tag"],
            "sourceSpec": "specs/openapi.json",
            "authNote": (
                "Every operation's OpenAPI doc says 'Authorization: Bearer [access_token]' — "
                "that is WRONG for the personal-access API key this project uses. Empirically "
                "confirmed working: 'Authorization: token <key>'. Bearer returns HTTP 400 "
                "{\"code\":200058,\"message\":\"User in token does not exist.\"}. See "
                "specs/rest/index.json."
            ),
            "operationCount": len(data["operations"]),
            "operations": data["operations"],
        }
        (OUT_DIR / f"{slug}.json").write_text(json.dumps(out, indent=2) + "\n")

    print(f"Wrote {len(resources)} resource spec files to {OUT_DIR}")


if __name__ == "__main__":
    main()
