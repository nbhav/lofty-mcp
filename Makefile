IMAGE           := lofty-mcp:py
SERVER_NAME     := lofty
MCP_JSON        := .mcp.json
ENV_FILE        := $(CURDIR)/.env
HTTP_PORT       := 8000
HTTP_CONTAINER  := lofty-mcp-http
TUNNEL_LOG      := .cloudflared-tunnel.log
TUNNEL_PID      := .cloudflared-tunnel.pid

.PHONY: help build up down status test clean http-up http-down http-status

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
	echo "Tunnel URL not found yet after 10s -- check $(TUNNEL_LOG) or run 'make http-status'."

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

.DEFAULT_GOAL := help
