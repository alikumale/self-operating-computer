import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import google.generativeai as genai
from google.protobuf.json_format import MessageToDict


@dataclass
class ToolCall:
    name: str
    arguments: Dict[str, Any]


class GeminiPlanner:
    """Lightweight Gemini planner that emits MCP tool calls."""

    def __init__(
        self,
        tool_declarations: Sequence[Dict[str, Any]],
        model: str = "gemini-2.0-flash-exp",
        api_key: Optional[str] = None,
    ) -> None:
        self.tool_declarations = list(tool_declarations)
        genai.configure(api_key=api_key or os.getenv("GOOGLE_API_KEY"))
        self.model = genai.GenerativeModel(
            model,
            tools=[{"function_declarations": self.tool_declarations}],
        )

    def build_prompt(
        self, objective: str, state: str, history: Sequence[Dict[str, Any]]
    ) -> str:
        """Return a compact planning prompt for Gemini."""

        history_lines = []
        for item in history:
            history_lines.append(
                f"- tool={item['tool']} args={json.dumps(item['args'])} -> {item['result']}"
            )

        history_block = "\n".join(history_lines) if history_lines else "(none yet)"
        prompt = f"""
You are an autonomous desktop operator. You have Windows-MCP tools that can interact with the local Windows desktop.

Goal: {objective}
Current state (from MCP):
{state}

Completed actions:
{history_block}

Rules:
- Prefer a single best MCP tool call per turn.
- Do not invent tools. Only use the provided functions.
- When the task is complete, call finish_task with a short summary.
"""
        return prompt.strip()

    def propose_actions(
        self, objective: str, state: str, history: Sequence[Dict[str, Any]]
    ) -> List[ToolCall]:
        prompt = self.build_prompt(objective, state, history)
        response = self.model.generate_content(
            [prompt],
            tool_config={"function_calling_config": {"mode": "ANY"}},
        )

        content = None
        if getattr(response, "candidates", None):
            content = response.candidates[0].content
        parts = getattr(content, "parts", []) if content else []

        tool_calls: List[ToolCall] = []
        for part in parts:
            function_call = getattr(part, "function_call", None)
            if not function_call:
                continue
            args = self._parse_args(function_call.args)
            tool_calls.append(ToolCall(name=function_call.name, arguments=args))

        # Fallback: allow JSON text payloads when function calling is disabled
        if not tool_calls and getattr(response, "text", None):
            try:
                fallback = json.loads(response.text)
                if isinstance(fallback, dict) and "tool" in fallback:
                    tool_calls.append(
                        ToolCall(
                            name=fallback.get("tool", ""),
                            arguments=fallback.get("arguments", {}),
                        )
                    )
            except Exception:  # noqa: BLE001
                pass

        return tool_calls

    @staticmethod
    def _parse_args(args: Any) -> Dict[str, Any]:
        try:
            return MessageToDict(args)
        except Exception:  # noqa: BLE001
            try:
                return dict(args)
            except Exception:  # noqa: BLE001
                return {}
