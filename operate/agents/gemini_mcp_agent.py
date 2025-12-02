import json
import logging
from typing import Any, Dict, List, Sequence

from operate.models.gemini import GeminiPlanner, ToolCall
from operate.tools.mcp_adapter import MCPCallError, MCPToolAdapter

logger = logging.getLogger(__name__)


class GeminiMCPAgent:
    def __init__(
        self,
        objective: str,
        mcp_adapter: MCPToolAdapter,
        planner: GeminiPlanner,
        use_vision: bool = False,
        max_turns: int = 12,
    ) -> None:
        self.objective = objective
        self.mcp_adapter = mcp_adapter
        self.planner = planner
        self.use_vision = use_vision
        self.max_turns = max_turns
        self.history: List[Dict[str, Any]] = []

    def run(self) -> str:
        """Run the Gemini + MCP loop until completion or turn limit."""

        for turn in range(self.max_turns):
            state = self.mcp_adapter.get_state(use_vision=self.use_vision)
            tool_calls = self._next_actions(state)

            if not tool_calls:
                logger.info("No tool calls returned; stopping early.")
                break

            for call in tool_calls:
                if call.name == "finish_task":
                    return call.arguments.get("summary", "")

                result = self._invoke_tool(call)
                self._record_history(call, result)

        return "Reached max turns or no further actions were provided."

    def _next_actions(self, state: str) -> Sequence[ToolCall]:
        try:
            return self.planner.propose_actions(self.objective, state, self.history)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Gemini planner failed", exc_info=exc)
            return []

    def _invoke_tool(self, call: ToolCall) -> Any:
        try:
            return self.mcp_adapter.invoke(call.name, call.arguments)
        except MCPCallError as exc:
            logger.error("MCP call failed: %s", exc)
            return f"MCP call failed: {exc}"

    def _record_history(self, call: ToolCall, result: Any) -> None:
        serialized_result = result
        try:
            if isinstance(result, (dict, list)):
                serialized_result = json.dumps(result)
        except Exception:  # noqa: BLE001
            pass

        self.history.append(
            {
                "tool": call.name,
                "args": call.arguments,
                "result": serialized_result,
            }
        )
