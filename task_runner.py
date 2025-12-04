"""Simple Tkinter GUI to queue and run operate tasks sequentially with saved settings."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

DEFAULT_MODEL = os.getenv("LLM_MODEL_NAME", "google/gemini-2.5-flash")
ROOT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = ROOT_DIR / "config.json"


def get_config_path() -> Path:
    return CONFIG_PATH


def default_config() -> dict:
    return {
        "llm_model_name": DEFAULT_MODEL,
        "api_key": "",
        "voice_enabled": False,
        "delay_between_tasks_seconds": 0,
    }


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text())
            merged = default_config()
            merged.update({k: v for k, v in data.items() if k in merged})
            return merged
        except Exception:
            return default_config()
    return default_config()


def save_config(cfg: dict) -> None:
    cfg_to_save = default_config()
    cfg_to_save.update({k: v for k, v in cfg.items() if k in cfg_to_save})
    CONFIG_PATH.write_text(json.dumps(cfg_to_save, indent=2))


def build_operate_command(objective: str, model: str, voice_enabled: bool) -> list[str]:
    operate_path = shutil.which("operate")
    command: list[str]
    if operate_path:
        command = [operate_path]
    else:
        local_main = ROOT_DIR / "operate" / "main.py"
        if local_main.exists():
            command = [sys.executable, str(local_main)]
        else:
            raise FileNotFoundError(
                "Could not find the 'operate' CLI. Install it with 'pip install self-operating-computer' inside your virtual environment."
            )

    command.extend(["-m", model])
    if voice_enabled:
        command.append("--voice")
    command.extend(["--prompt", objective])
    return command


def run_task(objective: str, cfg: dict) -> None:
    model = (
        cfg.get("llm_model_name")
        or os.getenv("LLM_MODEL_NAME")
        or DEFAULT_MODEL
    )
    voice_enabled = bool(cfg.get("voice_enabled"))
    try:
        delay_seconds = int(cfg.get("delay_between_tasks_seconds") or 0)
    except (TypeError, ValueError):  # pragma: no cover - defensive default
        delay_seconds = 0

    try:
        cmd = build_operate_command(objective, model, voice_enabled)
        subprocess.run(cmd, check=True)
        if delay_seconds > 0:
            time.sleep(delay_seconds)
    except FileNotFoundError as exc:
        messagebox.showerror("Operate Task Runner", str(exc))
    except subprocess.CalledProcessError as exc:
        messagebox.showerror(
            "Operate Task Runner",
            f"operate failed with exit code {exc.returncode} while running: {objective}",
        )
    except Exception as exc:  # pragma: no cover - defensive
        messagebox.showerror("Operate Task Runner", f"Unexpected error: {exc}")


class TaskRunnerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Operate Task Runner")
        self.config = load_config()

        self.model_var = tk.StringVar(value=self.config.get("llm_model_name", DEFAULT_MODEL))
        self.api_key_var = tk.StringVar(value=self.config.get("api_key", ""))
        self.voice_var = tk.BooleanVar(value=bool(self.config.get("voice_enabled")))
        self.delay_var = tk.StringVar(
            value=str(self.config.get("delay_between_tasks_seconds", 0))
        )
        self.task_var = tk.StringVar()
        self.running = False

        self._build_widgets()

    def _build_widgets(self) -> None:
        notebook = ttk.Notebook(self.root)

        tasks_frame = ttk.Frame(notebook)
        settings_frame = ttk.Frame(notebook)

        notebook.add(tasks_frame, text="Tasks")
        notebook.add(settings_frame, text="Settings")
        notebook.pack(fill=tk.BOTH, expand=True)

        self._build_tasks_tab(tasks_frame)
        self._build_settings_tab(settings_frame)

    def _build_tasks_tab(self, frame: ttk.Frame) -> None:
        model_frame = ttk.Frame(frame)
        model_frame.pack(fill=tk.X, padx=10, pady=(10, 0))
        ttk.Label(model_frame, text="Model:").pack(side=tk.LEFT)
        ttk.Entry(model_frame, textvariable=self.model_var, width=40).pack(
            side=tk.LEFT, padx=(5, 0)
        )

        entry_frame = ttk.Frame(frame)
        entry_frame.pack(fill=tk.X, padx=10, pady=(10, 0))
        ttk.Label(entry_frame, text="Task:").pack(side=tk.LEFT)
        entry = ttk.Entry(entry_frame, textvariable=self.task_var, width=60)
        entry.pack(side=tk.LEFT, padx=(5, 0))
        entry.bind("<Return>", lambda _event: self.add_task())
        ttk.Button(entry_frame, text="Add Task", command=self.add_task).pack(
            side=tk.LEFT, padx=(5, 0)
        )

        list_frame = ttk.Frame(frame)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 0))
        ttk.Label(list_frame, text="Queued Tasks:").pack(anchor=tk.W)
        self.task_listbox = tk.Listbox(list_frame, selectmode=tk.EXTENDED, height=10)
        self.task_listbox.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.task_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.task_listbox.config(yscrollcommand=scrollbar.set)

        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(button_frame, text="Run All", command=self.run_all).pack(side=tk.LEFT)
        ttk.Button(button_frame, text="Delete Selected", command=self.delete_selected).pack(
            side=tk.LEFT, padx=(5, 0)
        )
        ttk.Button(button_frame, text="Clear All", command=self.clear_tasks).pack(
            side=tk.LEFT, padx=(5, 0)
        )

        self.status_var = tk.StringVar(value="Idle")
        ttk.Label(frame, textvariable=self.status_var, anchor="w").pack(
            fill=tk.X, padx=10, pady=(0, 10)
        )

    def _build_settings_tab(self, frame: ttk.Frame) -> None:
        content = ttk.Frame(frame, padding=10)
        content.pack(fill=tk.BOTH, expand=True)

        ttk.Label(content, text="LLM Model Name").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(content, textvariable=self.model_var, width=40).grid(
            row=0, column=1, sticky=tk.W, pady=5
        )

        ttk.Label(content, text="API Key").grid(row=1, column=0, sticky=tk.W)
        ttk.Entry(content, textvariable=self.api_key_var, width=40, show="*").grid(
            row=1, column=1, sticky=tk.W, pady=5
        )

        ttk.Checkbutton(
            content,
            text="Enable voice mode",
            variable=self.voice_var,
        ).grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=5)

        ttk.Label(content, text="Delay between tasks (seconds)").grid(
            row=3, column=0, sticky=tk.W
        )
        ttk.Entry(content, textvariable=self.delay_var, width=10).grid(
            row=3, column=1, sticky=tk.W, pady=5
        )

        ttk.Button(content, text="Save Settings", command=self.save_settings).grid(
            row=4, column=0, columnspan=2, pady=10, sticky=tk.W
        )

    def add_task(self) -> None:
        task = self.task_var.get().strip()
        if not task:
            return
        self.task_listbox.insert(tk.END, task)
        self.task_var.set("")

    def delete_selected(self) -> None:
        selected = list(self.task_listbox.curselection())
        for index in reversed(selected):
            self.task_listbox.delete(index)

    def clear_tasks(self) -> None:
        self.task_listbox.delete(0, tk.END)

    def run_all(self) -> None:
        if self.running:
            messagebox.showinfo("Operate Task Runner", "Tasks are already running.")
            return
        tasks = [self.task_listbox.get(i) for i in range(self.task_listbox.size())]
        if not tasks:
            messagebox.showinfo("Operate Task Runner", "No tasks to run.")
            return
        cfg = self._current_config()
        thread = threading.Thread(target=self._run_tasks_thread, args=(tasks, cfg), daemon=True)
        self.running = True
        thread.start()

    def _run_tasks_thread(self, tasks: list[str], cfg: dict) -> None:
        self._set_status(f"Running {len(tasks)} task(s)...")
        for idx, task in enumerate(tasks, start=1):
            self._set_status(f"[{idx}/{len(tasks)}] Running: {task}")
            run_task(task, cfg)
        self._set_status("All tasks completed.")
        self.running = False

    def _set_status(self, message: str) -> None:
        self.root.after(0, lambda: self.status_var.set(message))

    def save_settings(self) -> None:
        delay_value = self.delay_var.get().strip()
        try:
            delay_int = int(delay_value or 0)
            if delay_int < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "Operate Task Runner",
                "Delay between tasks must be a non-negative integer.",
            )
            return

        self.config.update(
            {
                "llm_model_name": self.model_var.get().strip() or DEFAULT_MODEL,
                "api_key": self.api_key_var.get().strip(),
                "voice_enabled": bool(self.voice_var.get()),
                "delay_between_tasks_seconds": delay_int,
            }
        )
        save_config(self.config)
        messagebox.showinfo("Operate Task Runner", "Settings saved.")

    def _current_config(self) -> dict:
        return {
            "llm_model_name": self.model_var.get().strip() or DEFAULT_MODEL,
            "api_key": self.api_key_var.get().strip(),
            "voice_enabled": bool(self.voice_var.get()),
            "delay_between_tasks_seconds": int(self.delay_var.get() or 0),
        }


def main() -> None:
    root = tk.Tk()
    app = TaskRunnerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
