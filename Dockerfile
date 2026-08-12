# No external CLI binary needed (unlike the earlier lofty-cli-wrapping design) --
# this server calls https://api.lofty.com directly over HTTP, so plain Python covers it.
FROM python:3.12-slim
WORKDIR /app

COPY pyproject.toml .
COPY src ./src
RUN pip install --no-cache-dir .

# Server speaks MCP over stdio: run with `docker run -i`.
# Requires LOFTY_API_KEY at `docker run` time (-e or --env-file), not baked into the image.
ENTRYPOINT ["python", "-m", "lofty_mcp.server"]
