import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

DEFAULT_MCP_PORT = 8000


class MCPCallError(RuntimeError):
    """Raised when the MCP server cannot process a request."""


@dataclass
class MCPToolCall:
    name: str
    arguments: Dict[str, Any]


class MCPToolAdapter:
    """Thin HTTP adapter for the Windows-MCP server.

    The Windows-MCP server can run in `streamable-http` mode with `uv run main.py --transport streamable-http`.
    This adapter forwards tool calls over HTTP. If the server exposes a different path, update the `call_paths`
    list to match your deployment.
    """

    def __init__(self, base_url: Optional[str] = None, timeout: int = 30) -> None:
        host = os.getenv("MCP_HOST", "localhost")
        port = os.getenv("MCP_PORT", str(DEFAULT_MCP_PORT))
        scheme = os.getenv("MCP_SCHEME", "http")
        self.base_url = (base_url or f"{scheme}://{host}:{port}").rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def tool_declarations(self) -> List[Dict[str, Any]]:
        """Return the MCP tool schemas for LLM function calling."""

        return [
            {
                "name": "State-Tool",
                "description": "Capture the current desktop state (optionally with screenshot).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "use_vision": {
                            "type": "boolean",
                            "description": "Return a screenshot in addition to UI tree and metadata.",
                        }
                    },
                },
            },
            {
                "name": "App-Tool",
                "description": "Launch, resize, or switch between Windows applications.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "mode": {
                            "type": "string",
                            "enum": ["launch", "resize", "switch"],
                            "description": "Type of application control to perform.",
                        },
                        "name": {
                            "type": "string",
                            "description": "Application name when launching or switching.",
                        },
                        "window_loc": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Top-left window coordinate [x, y] when resizing.",
                        },
                        "window_size": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Window size [width, height] when resizing.",
                        },
                    },
                },
            },
            {
                "name": "Click-Tool",
                "description": "Click on UI elements at given coordinates.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "loc": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Pixel coordinates [x, y] to click.",
                        },
                        "button": {
                            "type": "string",
                            "enum": ["left", "right", "middle"],
                            "description": "Mouse button to use.",
                        },
                        "clicks": {
                            "type": "integer",
                            "description": "Number of clicks (1–3).",
                        },
                    },
                },
            },
            {
                "name": "Move-Tool",
                "description": "Move the mouse pointer without clicking.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to_loc": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Destination coordinates [x, y].",
                        }
                    },
                },
            },
            {
                "name": "Drag-Tool",
                "description": "Drag from the current cursor position to a destination.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to_loc": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Destination coordinates [x, y].",
                        }
                    },
                },
            },
            {
                "name": "Type-Tool",
                "description": "Type text into a focused field or a coordinate.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "loc": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Optional coordinates [x, y] to click before typing.",
                        },
                        "text": {"type": "string", "description": "Text to type."},
                        "clear": {
                            "type": "boolean",
                            "description": "Clear existing text before typing.",
                        },
                        "press_enter": {
                            "type": "boolean",
                            "description": "Press Enter after typing.",
                        },
                    },
                },
            },
            {
                "name": "Shortcut-Tool",
                "description": "Trigger keyboard shortcuts like ctrl+c or alt+tab.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "shortcut": {
                            "type": "string",
                            "description": "Shortcut string, e.g., 'ctrl+c' or 'win+r'.",
                        }
                    },
                },
            },
            {
                "name": "Scroll-Tool",
                "description": "Scroll vertically or horizontally.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "loc": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Optional coordinates [x, y] to scroll at.",
                        },
                        "type": {
                            "type": "string",
                            "enum": ["horizontal", "vertical"],
                            "description": "Scroll orientation.",
                        },
                        "direction": {
                            "type": "string",
                            "enum": ["up", "down", "left", "right"],
                            "description": "Scroll direction.",
                        },
                        "wheel_times": {
                            "type": "integer",
                            "description": "Wheel steps to scroll (roughly 3–5 lines per step).",
                        },
                    },
                },
            },
            {
                "name": "Wait-Tool",
                "description": "Pause execution for a few seconds.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "duration": {
                            "type": "integer",
                            "description": "Duration in seconds to wait.",
                        }
                    },
                },
            },
            {
                "name": "Powershell-Tool",
                "description": "Execute a PowerShell command and return output.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "PowerShell command to run.",
                        }
                    },
                },
            },
            {
                "name": "Scrape-Tool",
                "description": "Scrape webpage content to markdown via the MCP server.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "Full URL including protocol to scrape.",
                        }
                    },
                },
            },
        ]

    def get_state(self, use_vision: bool = False) -> str:
        response = self.invoke("State-Tool", {"use_vision": use_vision})
        if isinstance(response, str):
            return response
        return json.dumps(response)

    def invoke(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        payload = {"name": name, "arguments": arguments or {}}
        call_paths = ["/call", f"/tools/{name}"]

        for path in call_paths:
            url = f"{self.base_url}{path}"
            try:
                response = self.session.post(url, json=payload if path.endswith("call") else arguments, timeout=self.timeout)
                if response.ok:
                    return self._parse_response(response)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue

        message = f"Failed to call MCP tool {name} via {self.base_url}"
        if "last_error" in locals():
            message = f"{message}: {last_error}"
        raise MCPCallError(message)

    @staticmethod
    def _parse_response(response: requests.Response) -> Any:
        try:
            return response.json()
        except Exception:  # noqa: BLE001
            return response.text
