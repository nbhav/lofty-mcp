IMAGE           := lofty-mcp:py
SERVER_NAME     := lofty
MCP_JSON        := .mcp.json
ENV_FILE        := $(CURDIR)/.env
HTTP_PORT       := 8000
HTTP_CONTAINER  := lofty-mcp-http
TUNNEL_LOG      := .cloudflared-tunnel.log
TUNNEL_PID      := .cloudflared-tunnel.pid

# Picks up TUNNEL_NAME/TUNNEL_HOSTNAME (and anything else) from .env if present, so the
# persistent-tunnel targets below don't need them repeated on the command line every
# time. `-include` (not `include`) so a missing .env doesn't hard-fail targets that
# don't need it. Command-line `make target VAR=...` still overrides whatever .env sets.
-include .env

# Defaults for the persistent (named) tunnel + Cloudflare Access OAuth workflow --
# see `make help`'s tunnel-* entries. TUNNEL_HOSTNAME has no default: it's specific to
# a Cloudflare zone you own, so it must come from .env or the command line.
TUNNEL_NAME          ?= lofty-mcp
TUNNEL_HOSTNAME      ?=
CLOUDFLARED_CONFIG   := $(CURDIR)/.cloudflared/config.yml
PERSISTENT_TUNNEL_LOG := .cloudflared-persistent-tunnel.log
PERSISTENT_TUNNEL_PID := .cloudflared-persistent-tunnel.pid

.PHONY: help build up down status test clean http-up http-down http-status \
	tunnel-login tunnel-create http-up-persistent http-down-persistent http-status-persistent

help:
	@echo "make build       - docker build the lofty-mcp image"
	@echo "make up          - build the image and register it in $(MCP_JSON) for Claude Code (stdio)"
	@echo "make down        - remove it from $(MCP_JSON) and stop/remove any running containers"
	@echo "make status      - show whether the image exists and whether it's registered"
	@echo "make test        - run scripts/mcp_test_harness.py against the image (real API calls)"
	@echo "make clean       - remove the built image"
	@echo "make http-up     - run the server in HTTP mode + a cloudflared quick tunnel, for Cowork"
	@echo "make http-down   - stop the HTTP container and the tunnel"
	@echo "make http-status - show the HTTP container and tunnel URL, if running"
	@echo ""
	@echo "Persistent tunnel (fixed hostname, Cloudflare Access OAuth-capable) -- see README.md:"
	@echo "make tunnel-login          - one-time: authorize cloudflared against your Cloudflare account"
	@echo "make tunnel-create         - create/reuse the named tunnel and route TUNNEL_HOSTNAME (from .env) to it"
	@echo "make http-up-persistent    - run the server + the named tunnel at TUNNEL_HOSTNAME"
	@echo "make http-down-persistent  - stop the HTTP container and the named tunnel"
	@echo "make http-status-persistent - show the HTTP container and named tunnel status"

build:
	docker build -t $(IMAGE) .

# Registers this server in the project's .mcp.json so Claude Code picks it up
# (project-scoped MCP config -- see https://docs.claude.com/en/docs/claude-code/mcp).
# Each session spawns `docker run -i --rm ...` fresh and Docker tears it down
# on exit (--rm), so there's no long-lived container to separately manage.
up: build
	@command -v jq >/dev/null 2>&1 || { echo "jq is required (brew install jq)" >&2; exit 1; }
	@test -f "$(ENV_FILE)" || { echo "Error: $(ENV_FILE) not found -- create it with LOFTY_API_KEY=<your key> first." >&2; exit 1; }
	@entry=$$(jq -n --arg envfile "$(ENV_FILE)" --arg image "$(IMAGE)" \
		'{command: "docker", args: ["run", "-i", "--rm", "--env-file", $$envfile, $$image]}'); \
	if [ -f "$(MCP_JSON)" ]; then \
		jq --argjson entry "$$entry" '.mcpServers["$(SERVER_NAME)"] = $$entry' "$(MCP_JSON)" > "$(MCP_JSON).tmp" && mv "$(MCP_JSON).tmp" "$(MCP_JSON)"; \
	else \
		jq -n --argjson entry "$$entry" '{mcpServers: {"$(SERVER_NAME)": $$entry}}' > "$(MCP_JSON)"; \
	fi
	@echo "Registered '$(SERVER_NAME)' in $(MCP_JSON). Restart Claude Code (or run /mcp) to pick it up."

down:
	@command -v jq >/dev/null 2>&1 || { echo "jq is required (brew install jq)" >&2; exit 1; }
	@if [ -f "$(MCP_JSON)" ]; then \
		jq 'del(.mcpServers["$(SERVER_NAME)"])' "$(MCP_JSON)" > "$(MCP_JSON).tmp" && mv "$(MCP_JSON).tmp" "$(MCP_JSON)"; \
		echo "Removed '$(SERVER_NAME)' from $(MCP_JSON)."; \
	else \
		echo "$(MCP_JSON) does not exist -- nothing to remove."; \
	fi
	@running=$$(docker ps -aq --filter ancestor=$(IMAGE)); \
	if [ -n "$$running" ]; then \
		docker rm -f $$running >/dev/null; \
		echo "Stopped and removed lingering $(IMAGE) container(s)."; \
	fi

status:
	@docker image inspect $(IMAGE) >/dev/null 2>&1 && echo "image: built ($(IMAGE))" || echo "image: not built"
	@if [ -f "$(MCP_JSON)" ] && command -v jq >/dev/null 2>&1 && jq -e '.mcpServers["$(SERVER_NAME)"]' "$(MCP_JSON)" >/dev/null 2>&1; then \
		echo "registered: yes ($(MCP_JSON))"; \
	else \
		echo "registered: no"; \
	fi

test: build
	docker run --rm -i --env-file "$(ENV_FILE)" --entrypoint python \
		-v "$(CURDIR)":/app -w /app $(IMAGE) scripts/mcp_test_harness.py

clean:
	docker rmi $(IMAGE) 2>/dev/null || true

# Streamable HTTP mode for remote connectors (e.g. Cowork's "Remote MCP server URL").
# No auth of its own beyond LOFTY_API_KEY in the container's env -- see the warning
# in src/lofty_mcp/server.py. cloudflared's quick tunnel needs no account/signup,
# but hands out a random *.trycloudflare.com URL each run.
http-up: build
	@command -v cloudflared >/dev/null 2>&1 || { echo "cloudflared is required (brew install cloudflare/cloudflare/cloudflared)" >&2; exit 1; }
	@test -f "$(ENV_FILE)" || { echo "Error: $(ENV_FILE) not found -- create it with LOFTY_API_KEY=<your key> first." >&2; exit 1; }
	@docker rm -f $(HTTP_CONTAINER) >/dev/null 2>&1 || true
	docker run -d --rm --name $(HTTP_CONTAINER) -p $(HTTP_PORT):8000 \
		--env-file "$(ENV_FILE)" -e MCP_TRANSPORT=http $(IMAGE) >/dev/null
	@echo "Container listening on http://localhost:$(HTTP_PORT)/mcp"
	@echo "Starting cloudflared quick tunnel..."
	@rm -f "$(TUNNEL_LOG)"
	@nohup cloudflared tunnel --url http://localhost:$(HTTP_PORT) > "$(TUNNEL_LOG)" 2>&1 & echo $$! > "$(TUNNEL_PID)"
	@for i in 1 2 3 4 5 6 7 8 9 10; do \
		url=$$(grep -o 'https://[a-zA-Z0-9.-]*\.trycloudflare\.com' "$(TUNNEL_LOG)" 2>/dev/null | head -1); \
		if [ -n "$$url" ]; then \
			echo "Tunnel URL: $$url/mcp"; \
			echo "Paste that into Cowork's 'Remote MCP server URL' field."; \
			exit 0; \
		fi; \
		sleep 1; \
	done; \
	echo "Tunnel URL not found yet after 10s -- check $(TUNNEL_LOG) or run 'make http-status'." >&2; \
	exit 1

http-down:
	@docker rm -f $(HTTP_CONTAINER) >/dev/null 2>&1 && echo "Stopped $(HTTP_CONTAINER)." || echo "$(HTTP_CONTAINER) was not running."
	@if [ -f "$(TUNNEL_PID)" ]; then \
		kill $$(cat "$(TUNNEL_PID)") 2>/dev/null && echo "Stopped cloudflared tunnel." || true; \
		rm -f "$(TUNNEL_PID)"; \
	fi
	@rm -f "$(TUNNEL_LOG)"

http-status:
	@docker ps --filter name=$(HTTP_CONTAINER) --format '{{.Names}}: {{.Status}}' | grep -q . \
		&& docker ps --filter name=$(HTTP_CONTAINER) --format 'container: {{.Status}}' \
		|| echo "container: not running"
	@if [ -f "$(TUNNEL_LOG)" ]; then \
		url=$$(grep -o 'https://[a-zA-Z0-9.-]*\.trycloudflare\.com' "$(TUNNEL_LOG)" | head -1); \
		if [ -n "$$url" ]; then echo "tunnel: $$url/mcp"; else echo "tunnel: starting..."; fi; \
	else \
		echo "tunnel: not running"; \
	fi

# --- Persistent (named) tunnel, for a fixed hostname you can put behind Cloudflare
# Access (Zero Trust) for real OAuth login -- unlike the quick tunnel above, which is
# random-hostname and stateless. TUNNEL_NAME/TUNNEL_HOSTNAME come from .env (or the
# command line); see README.md "Connecting to a remote client" for the one-time
# Cloudflare-side setup (adding a domain, running tunnel-login, configuring Access).

# One-time: opens a browser to authorize cloudflared against your Cloudflare account
# and writes ~/.cloudflared/cert.pem. Needed once per machine before tunnel-create.
tunnel-login:
	@command -v cloudflared >/dev/null 2>&1 || { echo "cloudflared is required (brew install cloudflare/cloudflare/cloudflared)" >&2; exit 1; }
	cloudflared tunnel login
	@echo "Logged in. Next: set TUNNEL_HOSTNAME in $(ENV_FILE) and run 'make tunnel-create'."

# Creates the named tunnel (reusing it if it already exists), routes TUNNEL_HOSTNAME's
# DNS to it, and writes $(CLOUDFLARED_CONFIG) pointing at this machine's local HTTP
# port. Safe to re-run.
tunnel-create:
	@command -v cloudflared >/dev/null 2>&1 || { echo "cloudflared is required (brew install cloudflare/cloudflare/cloudflared)" >&2; exit 1; }
	@command -v jq >/dev/null 2>&1 || { echo "jq is required (brew install jq)" >&2; exit 1; }
	@test -n "$(TUNNEL_HOSTNAME)" || { echo "Error: TUNNEL_HOSTNAME is not set -- add TUNNEL_HOSTNAME=lofty-mcp.yourdomain.com to $(ENV_FILE), or pass it on the command line." >&2; exit 1; }
	@cloudflared tunnel list --output json 2>/dev/null | jq -e --arg name "$(TUNNEL_NAME)" '.[] | select(.name == $$name)' >/dev/null 2>&1 \
		|| cloudflared tunnel create $(TUNNEL_NAME)
	@tunnel_id=$$(cloudflared tunnel list --output json | jq -r --arg name "$(TUNNEL_NAME)" '.[] | select(.name == $$name) | .id'); \
	if [ -z "$$tunnel_id" ]; then echo "Error: could not find tunnel '$(TUNNEL_NAME)' after creating it." >&2; exit 1; fi; \
	mkdir -p "$(CURDIR)/.cloudflared"; \
	printf 'tunnel: %s\ncredentials-file: %s/.cloudflared/%s.json\ningress:\n  - hostname: %s\n    service: http://localhost:$(HTTP_PORT)\n  - service: http_status:404\n' \
		"$$tunnel_id" "$$HOME" "$$tunnel_id" "$(TUNNEL_HOSTNAME)" > "$(CLOUDFLARED_CONFIG)"; \
	echo "Wrote $(CLOUDFLARED_CONFIG) for tunnel '$(TUNNEL_NAME)' ($$tunnel_id)"
	cloudflared tunnel route dns $(TUNNEL_NAME) $(TUNNEL_HOSTNAME)
	@echo ""
	@echo "Tunnel '$(TUNNEL_NAME)' is routed to https://$(TUNNEL_HOSTNAME)"
	@echo "Next: in the Cloudflare Zero Trust dashboard, add an Access application for"
	@echo "that hostname with an OAuth identity provider, then run 'make http-up-persistent'."

# Runs the server in HTTP mode + the named tunnel (fixed hostname, survives restarts).
# If you've put Cloudflare Access in front of TUNNEL_HOSTNAME, requests now require a
# real OAuth login before they ever reach this container.
http-up-persistent: build
	@command -v cloudflared >/dev/null 2>&1 || { echo "cloudflared is required (brew install cloudflare/cloudflare/cloudflared)" >&2; exit 1; }
	@test -f "$(ENV_FILE)" || { echo "Error: $(ENV_FILE) not found -- create it with LOFTY_API_KEY=<your key> first." >&2; exit 1; }
	@test -n "$(TUNNEL_HOSTNAME)" || { echo "Error: TUNNEL_HOSTNAME is not set -- add it to $(ENV_FILE) first." >&2; exit 1; }
	@test -f "$(CLOUDFLARED_CONFIG)" || { echo "Error: $(CLOUDFLARED_CONFIG) not found -- run 'make tunnel-create' first." >&2; exit 1; }
	@docker rm -f $(HTTP_CONTAINER) >/dev/null 2>&1 || true
	docker run -d --rm --name $(HTTP_CONTAINER) -p $(HTTP_PORT):8000 \
		--env-file "$(ENV_FILE)" -e MCP_TRANSPORT=http $(IMAGE) >/dev/null
	@echo "Container listening on http://localhost:$(HTTP_PORT)/mcp"
	@rm -f "$(PERSISTENT_TUNNEL_LOG)"
	@nohup cloudflared tunnel --config "$(CLOUDFLARED_CONFIG)" run $(TUNNEL_NAME) > "$(PERSISTENT_TUNNEL_LOG)" 2>&1 & echo $$! > "$(PERSISTENT_TUNNEL_PID)"
	@sleep 2
	@echo "Persistent tunnel URL: https://$(TUNNEL_HOSTNAME)/mcp"
	@echo "(check $(PERSISTENT_TUNNEL_LOG) if connections aren't showing up within a few seconds)"

http-down-persistent:
	@docker rm -f $(HTTP_CONTAINER) >/dev/null 2>&1 && echo "Stopped $(HTTP_CONTAINER)." || echo "$(HTTP_CONTAINER) was not running."
	@if [ -f "$(PERSISTENT_TUNNEL_PID)" ]; then \
		kill $$(cat "$(PERSISTENT_TUNNEL_PID)") 2>/dev/null && echo "Stopped persistent cloudflared tunnel." || true; \
		rm -f "$(PERSISTENT_TUNNEL_PID)"; \
	fi
	@rm -f "$(PERSISTENT_TUNNEL_LOG)"

http-status-persistent:
	@docker ps --filter name=$(HTTP_CONTAINER) --format '{{.Names}}: {{.Status}}' | grep -q . \
		&& docker ps --filter name=$(HTTP_CONTAINER) --format 'container: {{.Status}}' \
		|| echo "container: not running"
	@if [ -n "$(TUNNEL_HOSTNAME)" ] && [ -f "$(PERSISTENT_TUNNEL_PID)" ]; then \
		echo "tunnel: https://$(TUNNEL_HOSTNAME)/mcp (persistent, tunnel '$(TUNNEL_NAME)')"; \
	elif [ -z "$(TUNNEL_HOSTNAME)" ]; then \
		echo "tunnel: TUNNEL_HOSTNAME not set in $(ENV_FILE)"; \
	else \
		echo "tunnel: not running"; \
	fi

.DEFAULT_GOAL := help
