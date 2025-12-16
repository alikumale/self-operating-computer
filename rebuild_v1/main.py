import tempfile
import tkinter as tk
from typing import Callable, List

from automation import ActionLooper, AutomationEngine
from config import load_config
from engine_llm import LLMEngine, LLMError, parse_action_text, test_provider
from gui import AppGUI


class AppController:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.logger: Callable[[str], None] = lambda msg: None
        self.config = load_config()
        self.automation = AutomationEngine(
            dry_run=bool(self.config.get("dry_run", True)),
            stop_hotkey=str(self.config.get("stop_hotkey", "ctrl+alt+s")),
            confirm_before_execute=bool(self.config.get("confirm_before_execute", True)),
            block_clicks=bool(self.config.get("block_clicks", True)),
            block_terminal_typing=bool(self.config.get("block_terminal_typing", True)),
            root=root,
        )
        self.gui = AppGUI(
            root,
            self.run_tasks,
            self.stop,
            self.export_logger,
            self.test_llm,
            self.test_screenshot,
        )

    def export_logger(self, logger: Callable[[str], None]) -> None:
        self.logger = logger
        self.automation.set_logger(logger)

    def log(self, message: str) -> None:
        self.logger(message)

    def stop(self) -> None:
        self.automation.stop()
        self.log("Stop signal sent.")

    def _log_provider_settings(self) -> None:
        mode = str(self.config.get("provider_mode"))
        timeout = self.config.get("llm_timeout_seconds")
        if mode == "Ollama (Local Text)":
            model = self.config.get("ollama_text_model")
            host = self.config.get("ollama_host")
        elif mode == "Ollama (Local Vision)":
            model = self.config.get("ollama_vision_model")
            host = self.config.get("ollama_host")
        else:
            model = self.config.get("openrouter_model")
            host = self.config.get("openrouter_base_url")
        self.log(f"Provider: {mode} | Model: {model} | Host: {host} | Timeout: {timeout}s")

    def run_tasks(self, tasks: List[str]) -> None:
        for index, objective in enumerate(tasks, start=1):
            self.config = load_config()
            self.automation.update_settings(
                dry_run=bool(self.config.get("dry_run", True)),
                stop_hotkey=str(self.config.get("stop_hotkey", "ctrl+alt+s")),
                confirm_before_execute=bool(self.config.get("confirm_before_execute", True)),
                block_clicks=bool(self.config.get("block_clicks", True)),
                block_terminal_typing=bool(self.config.get("block_terminal_typing", True)),
            )
            llm = LLMEngine(self.config, logger=self.log)
            looper = ActionLooper(
                automation=self.automation,
                request_action=llm.request_action,
                parse_action=parse_action_text,
                max_steps=int(self.config.get("max_steps", 20)),
                delay_seconds=float(self.config.get("delay_seconds", 0.6)),
                log_callback=self.log,
            )
            self.log(f"Running task {index}/{len(tasks)}: {objective}")
            self._log_provider_settings()
            try:
                outcome = looper.run(objective)
            except LLMError as exc:
                self.log(f"LLM error: {repr(exc)}")
                break
            except Exception as exc:  # pylint: disable=broad-except
                self.log(f"Unexpected error: {repr(exc)}")
                break
            self.log(f"Task result: {outcome}")
            if self.automation.should_stop():
                self.log("Stopped before finishing all tasks.")
                break

    def test_llm(self) -> None:
        self.config = load_config()
        result = test_provider(self.config)
        self.log(result)

    def test_screenshot(self) -> None:
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                image, path = self.automation.capture_screenshot(save_path=tmp.name)
            size = f"{image.width}x{image.height}" if image else "unknown"
            self.log(f"Screenshot saved to {path} with size {size}")
        except Exception as exc:  # pylint: disable=broad-except
            self.log(f"Screenshot test failed: {repr(exc)}")


def main() -> None:
    root = tk.Tk()
    AppController(root)
    root.mainloop()


if __name__ == "__main__":
    main()
