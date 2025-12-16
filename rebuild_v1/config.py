import json
from pathlib import Path
from typing import Any, Dict

CONFIG_PATH = Path(__file__).parent / "config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "provider_mode": "Ollama (Local Text)",
    "ollama_host": "http://localhost:11434",
    "ollama_text_model": "llama3.2:3b",
    "ollama_vision_model": "llava:7b",
    "openrouter_api_key": "",
    "openrouter_model": "openrouter/auto",
    "openrouter_base_url": "https://openrouter.ai/api/v1",
    "llm_timeout_seconds": 600,
    "max_steps": 20,
    "delay_seconds": 0.6,
    "stop_hotkey": "ctrl+alt+s",
    "dry_run": True,
    "confirm_before_execute": True,
    "block_clicks": True,
    "block_terminal_typing": True,
}


def load_config() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
            merged = DEFAULT_CONFIG.copy()
            if isinstance(data, dict):
                merged.update(data)
            return merged
        except (json.JSONDecodeError, OSError, TypeError):
            return DEFAULT_CONFIG.copy()
    return DEFAULT_CONFIG.copy()


def save_config(config: Dict[str, Any]) -> None:
    try:
        with CONFIG_PATH.open("w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except OSError:
        # Prefer silent failure over crashing the UI when filesystem is read-only
        pass
