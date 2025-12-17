import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

import keyboard
import pyautogui
import tkinter as tk
from PIL import ImageGrab
from tkinter import messagebox

pyautogui.FAILSAFE = False


@dataclass
class ActionResult:
    action: Dict[str, object]
    executed: bool
    error: Optional[str] = None


class AutomationEngine:
    def __init__(
        self,
        dry_run: bool = True,
        stop_hotkey: str = "ctrl+alt+s",
        confirm_before_execute: bool = True,
        block_clicks: bool = True,
        block_terminal_typing: bool = True,
        root: Optional[tk.Tk] = None,
    ):
        self.dry_run = dry_run
        self.stop_hotkey = stop_hotkey
        self.confirm_before_execute = confirm_before_execute
        self.block_clicks = block_clicks
        self.block_terminal_typing = block_terminal_typing
        self._stop_flag = threading.Event()
        self._hotkey_registered = False
        self.log_callback: Callable[[str], None] = lambda _msg: None
        self.root = root
        self.screen_size: Optional[Tuple[int, int]] = None

    def set_logger(self, logger: Callable[[str], None]) -> None:
        self.log_callback = logger

    def update_settings(
        self,
        *,
        dry_run: Optional[bool] = None,
        stop_hotkey: Optional[str] = None,
        confirm_before_execute: Optional[bool] = None,
        block_clicks: Optional[bool] = None,
        block_terminal_typing: Optional[bool] = None,
    ) -> None:
        if dry_run is not None:
            self.dry_run = dry_run
        if stop_hotkey is not None:
            self.stop_hotkey = stop_hotkey
        if confirm_before_execute is not None:
            self.confirm_before_execute = confirm_before_execute
        if block_clicks is not None:
            self.block_clicks = block_clicks
        if block_terminal_typing is not None:
            self.block_terminal_typing = block_terminal_typing

    def register_stop_hotkey(self) -> None:
        if self._hotkey_registered:
            return
        try:
            keyboard.add_hotkey(self.stop_hotkey, self.stop)
            self._hotkey_registered = True
        except keyboard.KeyboardException:
            # Keyboard may need elevated privileges; ignore if unavailable
            pass

    def stop(self) -> None:
        self._stop_flag.set()

    def reset_stop(self) -> None:
        self._stop_flag.clear()

    def should_stop(self) -> bool:
        return self._stop_flag.is_set()

    def set_screen_size(self, size: Tuple[int, int]) -> None:
        self.screen_size = size

    def capture_screenshot(self, save_path: Optional[str] = None):
        image = ImageGrab.grab()
        path = save_path
        if save_path:
            image.save(save_path)
        return image, path

    def validate_action(
        self, action: Dict[str, object], screen_size: Optional[Tuple[int, int]]
    ) -> Tuple[bool, Optional[str], bool]:
        action_type = action.get("type")
        if action_type == "click":
            if self.block_clicks:
                return False, "Clicks are blocked by safety settings.", True
            if screen_size:
                width, height = screen_size
                x, y = int(action.get("x", -1)), int(action.get("y", -1))
                if x < 0 or y < 0 or x >= width or y >= height:
                    return False, "Click coordinates out of bounds.", True
        return True, None, False

    def _confirm_action(self, description: str, double_confirm: bool = False) -> bool:
        if self.root is None:
            return True
        proceed = messagebox.askyesno("Confirm Action", description)
        if not proceed:
            return False
        if double_confirm:
            proceed = messagebox.askyesno(
                "Confirm Again", f"Are you absolutely sure? {description}"
            )
        return proceed

    def _active_window_title(self) -> str:
        try:
            win = pyautogui.getActiveWindow()
            if win and getattr(win, "title", None):
                return str(win.title)
        except Exception:  # pylint: disable=broad-except
            pass
        try:
            title = pyautogui.getActiveWindowTitle()
            if title:
                return str(title)
        except Exception:  # pylint: disable=broad-except
            pass
        return ""

    def _is_terminal_window(self) -> bool:
        title = self._active_window_title().lower()
        for keyword in ["powershell", "command prompt", "cmd", "terminal", "bash", "zsh"]:
            if keyword in title:
                return True
        return False

    def execute_action(self, action: Dict[str, object]) -> ActionResult:
        if self.dry_run:
            return ActionResult(action=action, executed=False, error=None)

        action_type = action.get("type")
        description = f"Execute action: {action}"

        if self.confirm_before_execute:
            if not self._confirm_action(description):
                return ActionResult(action=action, executed=False, error="User cancelled action")

        if action_type in {"type", "hotkey"} and self.block_terminal_typing and self._is_terminal_window():
            if not self._confirm_action(
                "Action targets a terminal-like window. Confirm twice to proceed.", double_confirm=True
            ):
                return ActionResult(action=action, executed=False, error="Blocked in terminal window")

        try:
            if action_type == "click":
                pyautogui.click(x=int(action["x"]), y=int(action["y"]))
            elif action_type == "type":
                pyautogui.typewrite(str(action["text"]))
            elif action_type == "hotkey":
                keys = [str(k) for k in action.get("keys", [])]
                pyautogui.hotkey(*keys)
            elif action_type == "wait":
                time.sleep(float(action.get("seconds", 0)))
            elif action_type == "done":
                pass
            else:
                return ActionResult(action=action, executed=False, error="Unknown action type")
            return ActionResult(action=action, executed=True, error=None)
        except Exception as exc:  # pylint: disable=broad-except
            return ActionResult(action=action, executed=False, error=str(exc))


class ActionLooper:
    def __init__(
        self,
        automation: AutomationEngine,
        request_action: Callable[..., str],
        parse_action: Callable[[str, Optional[Callable[[str], None]]], Optional[Dict[str, object]]],
        max_steps: int,
        delay_seconds: float,
        log_callback: Callable[[str], None],
    ):
        self.automation = automation
        self.request_action = request_action
        self.parse_action = parse_action
        self.max_steps = max_steps
        self.delay_seconds = delay_seconds
        self.log_callback = log_callback

    def run(self, objective: str) -> str:
        self.automation.reset_stop()
        self.automation.register_stop_hotkey()
        screen = pyautogui.size()
        self.automation.set_screen_size((screen.width, screen.height))
        self.log_callback(f"Screen size detected: {screen.width}x{screen.height}")

        for step in range(1, self.max_steps + 1):
            if self.automation.should_stop():
                return "Stopped by user"

            try:
                image, _ = self.automation.capture_screenshot()
                screenshot_note = f"screenshot captured ({image.width}x{image.height})"
                self.log_callback(f"Screenshot captured for step {step}: {image.width}x{image.height}")
            except Exception as exc:  # pylint: disable=broad-except
                screenshot_note = f"screenshot failed: {exc}"
                self.log_callback(f"Screenshot failed: {exc}")
                image = None

            screenshot_bytes = None
            if image:
                try:
                    from io import BytesIO

                    buffer = BytesIO()
                    image.save(buffer, format="PNG")
                    screenshot_bytes = buffer.getvalue()
                except Exception as exc:  # pylint: disable=broad-except
                    self.log_callback(f"Failed to serialize screenshot: {exc}")

            retries = 0
            action_data: Optional[Dict[str, object]] = None
            reask_guard = 0
            while retries < 3 and not self.automation.should_stop():
                raw = self.request_action(
                    objective,
                    screenshot_note=screenshot_note,
                    screenshot_bytes=screenshot_bytes,
                    screen_size=f"{screen.width}x{screen.height}",
                    retry_count=retries,
                )
                self.log_callback(f"Raw model response: {raw}")
                action_data = self.parse_action(raw, self.log_callback)
                if action_data is None:
                    retries += 1
                    self.log_callback("Model returned invalid JSON. Retrying...")
                    continue

                valid, reason, reask = self.automation.validate_action(action_data, (screen.width, screen.height))
                if not valid:
                    self.log_callback(reason or "Action rejected")
                    if reask:
                        reask_guard += 1
                        if reask_guard >= 3:
                            return "Action rejected repeatedly"
                        continue
                break

            if action_data is None:
                return "Failed to parse action after retries"

            result = self.automation.execute_action(action_data)
            executed_text = "executed" if result.executed else "dry-run"
            self.log_callback(f"Action step {step}: {action_data} ({executed_text})")
            if result.error:
                self.log_callback(f"Action error: {result.error}")
                if result.error.startswith("User cancelled"):
                    return "User cancelled action"

            if action_data.get("type") == "done":
                return str(action_data.get("reason", "Done"))

            if self.automation.should_stop():
                return "Stopped by user"
            time.sleep(self.delay_seconds)
        return "Reached max steps"
