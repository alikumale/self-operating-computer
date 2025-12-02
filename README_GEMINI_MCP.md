# Gemini + Windows-MCP Agent

This repository now includes a lightweight Gemini planner that can drive the [Windows-MCP](https://github.com/CursorTouch/Windows-MCP) tool server. The agent runs locally and issues MCP tool calls over HTTP.

## Prerequisites
- A running Windows-MCP server (recommended transport: `streamable-http`):
  ```bash
  uv --directory <path-to-windows-mcp> run main.py --transport streamable-http --host 0.0.0.0 --port 8000
  ```
- `GOOGLE_API_KEY` exported in your environment.
- `pip install -r requirements.txt` so the `google-generativeai` client is available.

## Quickstart
Run the new CLI entrypoint from the repo root:
```bash
python -m operate.cli.gemini_agent --task "Organize my downloads folder" \
  --gemini-model gemini-2.0-flash-exp \
  --mcp-url http://localhost:8000 \
  --vision
```

Flags:
- `--task` (required): The objective you want the agent to accomplish.
- `--gemini-model`: Override the Gemini model (defaults to `gemini-2.0-flash-exp`).
- `--mcp-url`: Optional base URL for the MCP server; falls back to `MCP_HOST`/`MCP_PORT` env vars.
- `--vision`: Ask Windows-MCP's `State-Tool` to include screenshots.
- `--max-turns`: Limit the reasoning loop (defaults to 12 turns).

## What happens at runtime?
1. The agent calls the MCP `State-Tool` each turn to collect context.
2. Gemini proposes a single MCP tool call using function calling.
3. The adapter invokes the MCP tool over HTTP and logs the result.
4. When Gemini returns `finish_task`, the loop stops and prints the summary.

If your MCP deployment uses a different HTTP path, update `call_paths` in `operate/tools/mcp_adapter.py` to match your server.
