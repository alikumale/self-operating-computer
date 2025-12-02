# Local Gemini-Based Automation Strategy

This plan outlines how to combine the capabilities of `CursorTouch/Windows-MCP` and `OthersideAI/self-operating-computer` into a single Python application that can run locally and autonomously carry out desktop tasks on your commands.

## Goals
- Replace the default LLM endpoints with Gemini models for planning and tool-selection.
- Reuse the Windows MCP control layer for direct OS interactions (e.g., keyboard/mouse, window focus, file operations).
- Leverage the self-operating-computer task loop for multi-step reasoning, progress tracking, and retries.
- Keep everything runnable locally with minimal setup commands.

## High-Level Architecture
1. **Controller (self-operating-computer core):**
   - Use the existing `operate` package to orchestrate tasks and maintain the agent loop.
   - Extend the task loop to emit MCP-compatible tool calls when actions are required.

2. **Tooling Layer (Windows-MCP):**
   - Import the Windows MCP tool registry and map the key actions (mouse, keyboard, window focus, filesystem) into the `operate` tool schema.
   - Add a thin adapter that translates agent tool calls into MCP RPCs.

3. **Model Client (Gemini):**
   - Introduce a Gemini client (via the Google Generative AI Python SDK) that implements the `operate.models` interfaces.
   - Support function/tool calling by translating the `Gemini` function call format into the existing `FunctionCall` objects used by the task loop.

4. **Configuration & Startup:**
   - Single `config.yaml` or `.env` to specify Gemini API key, model version, and MCP server address/port.
   - Provide a `python -m operate.gemini_agent --task "<instruction>"` entrypoint that starts the loop and connects to MCP.

## Implementation Steps
- **Model Adapter:**
  - Add `operate/models/gemini.py` implementing `LLM` interface with `complete` and `chat` methods.
  - Handle streaming and function calling; map MCP tool schemas into Gemini function specs.

- **Tool Adapter:**
  - Create `operate/tools/mcp_adapter.py` that loads available MCP actions from `windows-mcp` and exposes them via the `operate.tools.registry`.
  - Ensure safety checks for file paths and window targets before executing actions.

- **CLI Entrypoint:**
  - New script `operate/cli/gemini_agent.py` to parse user task descriptions, load config, and start the agent loop with Gemini + MCP adapters.

- **Local Run Example:**
  ```bash
  pip install -r requirements.txt
  pip install google-generativeai  # Gemini SDK
  # Start MCP server (from Windows-MCP) separately, then run:
  python -m operate.cli.gemini_agent --task "Organize my downloads folder"
  ```

## Safety & Reliability
- Require explicit confirmation before destructive actions (delete/move outside user directories).
- Log all tool calls and results to a local file for auditing.
- Add timeouts and retries for MCP RPC calls; surface failures to the agent loop for replanning.

## Next Steps
- Pull the latest `windows-mcp` repo and expose its actions over a local TCP port.
- Implement the Gemini adapter and CLI scaffold described above.
- Add tests for the tool adapters and function-call mapping to ensure compatibility.

## Implementation Notes
- Added a Gemini MCP agent at `operate/cli/gemini_agent.py` that calls Windows-MCP over HTTP.
- The MCP tool bridge lives in `operate/tools/mcp_adapter.py` and exposes the server's tools to Gemini.
- A dedicated agent loop (`operate/agents/gemini_mcp_agent.py`) tracks history and stops when Gemini calls `finish_task`.
- See `README_GEMINI_MCP.md` for setup and run instructions.
