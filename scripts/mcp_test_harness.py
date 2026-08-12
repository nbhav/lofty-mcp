"""Reliable stdio request/response harness for smoke-testing the MCP server.

Spawns `python -m lofty_mcp.server` as a subprocess and drives it with threaded
stdout/stderr readers + per-request timeouts, avoiding the premature-EOF issue
that plain shell `< input.jsonl` piping hits once a tool call involves a real
network round trip (the process can be torn down before the async response
lands). Meant to run *inside* the project's Docker image, e.g.:

  docker run --rm -i --env-file .env --entrypoint python \\
    -v "$(pwd)":/app -w /app lofty-mcp:py scripts/mcp_test_harness.py
"""

import json
import queue
import subprocess
import sys
import threading

REQUESTS = [
    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "harness", "version": "0.0.1"}}},
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "lofty_leads_list", "arguments": {"limit": 1}}},
    {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "lofty_whoami", "arguments": {}}},
]


def reader(stream, q):
    for line in iter(stream.readline, ""):
        q.put(line)


def main() -> None:
    proc = subprocess.Popen(
        [sys.executable, "-u", "-m", "lofty_mcp.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    out_q: "queue.Queue[str]" = queue.Queue()
    err_q: "queue.Queue[str]" = queue.Queue()
    threading.Thread(target=reader, args=(proc.stdout, out_q), daemon=True).start()
    threading.Thread(target=reader, args=(proc.stderr, err_q), daemon=True).start()

    for req in REQUESTS:
        line = json.dumps(req)
        proc.stdin.write(line + "\n")
        proc.stdin.flush()
        print(f">>> sent: {line}")
        try:
            resp = out_q.get(timeout=20)
            print(f"<<< recv: {resp.strip()}")
        except queue.Empty:
            print("<<< TIMEOUT waiting for response")

    proc.stdin.close()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()

    print("--- remaining stderr ---")
    while not err_q.empty():
        print(err_q.get_nowait().rstrip())
    print(f"exit code: {proc.returncode}")


if __name__ == "__main__":
    main()
