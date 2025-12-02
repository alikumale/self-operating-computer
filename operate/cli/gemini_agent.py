import argparse
import logging
import os

from operate.agents.gemini_mcp_agent import GeminiMCPAgent
from operate.models.gemini import GeminiPlanner
from operate.tools.mcp_adapter import MCPToolAdapter

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s - %(message)s",
)


FINISH_TOOL = {
    "name": "finish_task",
    "description": "Conclude the task and provide a short summary of the completed work.",
    "parameters": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "One sentence describing what was accomplished.",
            }
        },
        "required": ["summary"],
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Gemini + Windows-MCP autonomous agent locally.",
    )
    parser.add_argument("--task", required=True, help="Objective for the agent to accomplish.")
    parser.add_argument(
        "--gemini-model",
        default=os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp"),
        help="Gemini model to use for planning.",
    )
    parser.add_argument(
        "--mcp-url",
        default=None,
        help="Base URL for the Windows-MCP server (defaults to MCP_HOST/PORT envs).",
    )
    parser.add_argument(
        "--vision",
        action="store_true",
        help="Request MCP State-Tool to include screenshots.",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=12,
        help="Maximum reasoning/acting turns before stopping.",
    )
    return parser.parse_args()


def build_agent(args: argparse.Namespace) -> GeminiMCPAgent:
    mcp_adapter = MCPToolAdapter(base_url=args.mcp_url)
    tool_declarations = mcp_adapter.tool_declarations() + [FINISH_TOOL]
    planner = GeminiPlanner(tool_declarations=tool_declarations, model=args.gemini_model)
    return GeminiMCPAgent(
        objective=args.task,
        mcp_adapter=mcp_adapter,
        planner=planner,
        use_vision=args.vision,
        max_turns=args.max_turns,
    )


def main() -> None:
    args = parse_args()
    agent = build_agent(args)
    summary = agent.run()
    print("\n=== Task Summary ===")
    print(summary or "No summary returned.")


if __name__ == "__main__":
    main()
