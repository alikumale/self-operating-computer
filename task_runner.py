"""Tkinter task runner with settings, password protection, and OpenRouter-friendly config."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

ROOT_DIR = Path(__file__).resolve().parent
CONFIG_FILENAME = "config.json"
DEFAULT_MODEL_NAME = "google/gemini-2.5-flash"
MAX_PASSWORD_ATTEMPTS = 3


def get_config_path() -> Path:
    """Return the path to the config file."""

    return ROOT_DIR / CONFIG_FILENAME


def default_config() -> dict:
    """Provide default settings for the task runner."""

    return {
        "llm_model_name": DEFAULT_MODEL_NAME,
        "api_key": "",
        "voice_enabled": False,
        "delay_between_tasks_seconds": 0,
        "start_with_windows": False,
        "password_salt": "",
        "password_hash": "",
    }


def load_config() -> dict:
    """Load config.json if present; otherwise return defaults."""

    cfg = default_config()
    path = get_config_path()
    if not path.exists():
        return cfg

    try:
        with path.open("r", encoding="utf-8") as fh:
            loaded = json.load(fh)
        if isinstance(loaded, dict):
            cfg.update({k: loaded.get(k, v) for k, v in cfg.items()})
    except Exception:
        # If anything goes wrong loading the config, fall back to defaults.
        return cfg

    return cfg


def save_config(cfg: dict) -> None:
    """Write the config dictionary back to disk."""

    path = get_config_path()
    with path.open("w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)


def hash_password(password: str, salt: str) -> str:
    """Hash a password with the provided salt using SHA-256."""

    return hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    """Verify a password against the expected hash."""

    return hash_password(password, salt) == expected_hash


def ensure_password_set(root: tk.Tk, config: dict) -> bool:
    """Prompt to set or verify a password before showing the app."""

    if not config.get("password_hash"):
        while True:
            pw1 = simpledialog.askstring("Set Password", "Create a password:", show="*", parent=root)
            if pw1 is None:
                return False
            pw2 = simpledialog.askstring("Set Password", "Confirm password:", show="*", parent=root)
            if pw2 is None:
                return False
            if pw1 != pw2:
                messagebox.showerror("Password", "Passwords do not match. Please try again.", parent=root)
                continue
            salt = secrets.token_hex(16)
            config["password_salt"] = salt
            config["password_hash"] = hash_password(pw1, salt)
            save_config(config)
            return True

    for _ in range(MAX_PASSWORD_ATTEMPTS):
        entered = simpledialog.askstring("Password Required", "Enter password:", show="*", parent=root)
        if entered is None:
            return False
        if verify_password(entered, config.get("password_salt", ""), config.get("password_hash", "")):
            return True
        messagebox.showerror("Password", "Incorrect password. Please try again.", parent=root)

    messagebox.showerror("Password", "Maximum attempts reached. Exiting.", parent=root)
    return False


def get_effective_model(config: dict) -> str:
    """Choose the model from config or environment."""

    return config.get("llm_model_name") or os.getenv("LLM_MODEL_NAME") or DEFAULT_MODEL_NAME


def get_effective_api_key(config: dict) -> str:
    """Choose the API key from config or environment."""

    return config.get("api_key") or os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY") or ""


def build_operate_command(objective: str, model: str, config: dict, base_command: list[str] | None = None) -> list[str]:
    """Construct the operate CLI command with fallbacks and flags."""

    if base_command:
        command = list(base_command)
    else:
        found = shutil.which("operate")
        if found:
            command = [found]
        else:
            local_script = ROOT_DIR / "operate" / "operate.py"
            if local_script.exists():
                command = [sys.executable, str(local_script)]
            else:
                raise FileNotFoundError(
                    "Could not find the 'operate' CLI. Ensure it is installed in your virtual environment."
                )

    command.extend(["-m", model, "--objective", objective])
    if config.get("voice_enabled"):
        command.append("--voice")
    return command


def run_task(task: str, config: dict, model_name: str | None = None, base_command: list[str] | None = None) -> None:
    """Run a single task using the operate CLI."""

    model = model_name.strip() if model_name and model_name.strip() else get_effective_model(config)
    command = build_operate_command(task, model, config, base_command=base_command)
    env = os.environ.copy()
    api_key = get_effective_api_key(config)
    if api_key:
        env.setdefault("OPENAI_API_KEY", api_key)
        env.setdefault("OPENROUTER_API_KEY", api_key)
    subprocess.run(command, check=True, env=env)


def update_windows_startup(config: dict) -> None:
    """Create or remove a startup shortcut on Windows based on config."""

    if not sys.platform.startswith("win"):
        return

    appdata = os.getenv("APPDATA")
    if not appdata:
        return

    startup_dir = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    bat_path = startup_dir / "OperateTaskRunner.bat"

    if config.get("start_with_windows"):
        lines = [
            "@echo off",
            "REM Adjust python executable if needed.",
            f'cd /d "{ROOT_DIR}"',
            "REM Activate virtual environment if present",
            "if exist \".venv\\Scripts\\activate.bat\" call \".venv\\Scripts\\activate.bat\"",
            "python task_runner.py",
        ]
        try:
            startup_dir.mkdir(parents=True, exist_ok=True)
            bat_path.write_text("\n".join(lines), encoding="utf-8")
        except Exception:
            messagebox.showwarning(
                "Startup",
                "Could not update Windows startup configuration.",
            )
    else:
        if bat_path.exists():
            try:
                bat_path.unlink()
            except Exception:
                messagebox.showwarning(
                    "Startup",
                    "Could not remove Windows startup configuration.",
                )


class TaskRunnerApp:
    def __init__(self, root: tk.Tk, config: dict):
        self.root = root
        self.config = config
        self.root.title("Operate Task Runner")

        self.model_var = tk.StringVar(value=get_effective_model(config))
        self.task_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Idle")

        self.settings_model_var = tk.StringVar(value=config.get("llm_model_name", DEFAULT_MODEL_NAME))
        self.settings_api_key_var = tk.StringVar(value=config.get("api_key", ""))
        self.voice_var = tk.BooleanVar(value=bool(config.get("voice_enabled")))
        self.delay_var = tk.StringVar(value=str(config.get("delay_between_tasks_seconds", 0)))
        self.start_with_windows_var = tk.BooleanVar(value=bool(config.get("start_with_windows")))

"""Simple Tkinter GUI to queue and run operate tasks sequentially."""
import os
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox

DEFAULT_MODEL = os.getenv("LLM_MODEL_NAME", "google/gemini-2.5-flash")


def run_task(task: str, model_name: str | None = None, base_command: list[str] | None = None) -> None:
    """Run a single task using the operate CLI.

    Parameters
    ----------
    task: str
        The objective to pass to operate.
    model_name: str | None
        Model override; falls back to DEFAULT_MODEL if missing.
    base_command: list[str] | None
        Override the base command for testing (defaults to ["operate"]).
    """

    model = model_name.strip() if model_name and model_name.strip() else DEFAULT_MODEL
    command = list(base_command) if base_command else ["operate"]
    command.extend(["-m", model, "--objective", task])
    subprocess.run(command, check=True)


class TaskRunnerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Operate Task Runner")

        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        self.task_var = tk.StringVar()
        self.running = False

        self._build_widgets()

    def _build_widgets(self) -> None:
        notebook = ttk.Notebook(self.root)
        tasks_tab = ttk.Frame(notebook)
        settings_tab = ttk.Frame(notebook)
        notebook.add(tasks_tab, text="Tasks")
        notebook.add(settings_tab, text="Settings")
        notebook.pack(fill=tk.BOTH, expand=True)

        self._build_tasks_tab(tasks_tab)
        self._build_settings_tab(settings_tab)

        tk.Label(self.root, textvariable=self.status_var, anchor="w").pack(fill=tk.X, padx=10, pady=(0, 10))

    def _build_tasks_tab(self, parent: ttk.Frame) -> None:
        model_frame = ttk.Frame(parent)
        model_frame.pack(fill=tk.X, padx=10, pady=(10, 0))
        ttk.Label(model_frame, text="Model:").pack(side=tk.LEFT)
        ttk.Entry(model_frame, textvariable=self.model_var, width=40).pack(side=tk.LEFT, padx=(5, 0))

        entry_frame = ttk.Frame(parent)
        entry_frame.pack(fill=tk.X, padx=10, pady=(10, 0))
        ttk.Label(entry_frame, text="Task:").pack(side=tk.LEFT)
        entry = ttk.Entry(entry_frame, textvariable=self.task_var, width=60)
        entry.pack(side=tk.LEFT, padx=(5, 0))
        entry.bind("<Return>", lambda _event: self.add_task())
        ttk.Button(entry_frame, text="Add Task", command=self.add_task).pack(side=tk.LEFT, padx=(5, 0))

        list_frame = ttk.Frame(parent)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 0))
        ttk.Label(list_frame, text="Queued Tasks:").pack(anchor=tk.W)
        self.task_listbox = tk.Listbox(list_frame, selectmode=tk.EXTENDED, height=10)
        self.task_listbox.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.task_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.task_listbox.config(yscrollcommand=scrollbar.set)

        button_frame = ttk.Frame(parent)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(button_frame, text="Run All", command=self.run_all).pack(side=tk.LEFT)
        ttk.Button(button_frame, text="Delete Selected", command=self.delete_selected).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(button_frame, text="Clear", command=self.clear_tasks).pack(side=tk.LEFT, padx=(5, 0))

    def _build_settings_tab(self, parent: ttk.Frame) -> None:
        container = ttk.Frame(parent)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        ttk.Label(container, text="LLM Model Name").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(container, textvariable=self.settings_model_var, width=40).grid(row=0, column=1, sticky=tk.W)

        ttk.Label(container, text="API Key").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(container, textvariable=self.settings_api_key_var, width=40, show="*").grid(row=1, column=1, sticky=tk.W)

        voice_check = ttk.Checkbutton(container, text="Enable voice mode", variable=self.voice_var)
        voice_check.grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=2)

        ttk.Label(container, text="Delay between tasks (seconds)").grid(row=3, column=0, sticky=tk.W, pady=2)
        ttk.Entry(container, textvariable=self.delay_var, width=10).grid(row=3, column=1, sticky=tk.W)

        start_check = ttk.Checkbutton(
            container,
            text="Start this app automatically with Windows",
            variable=self.start_with_windows_var,
        )
        start_check.grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=2)

        save_button = ttk.Button(container, text="Save Settings", command=self.save_settings)
        save_button.grid(row=5, column=0, columnspan=2, pady=(8, 0), sticky=tk.W)
        model_frame = tk.Frame(self.root)
        model_frame.pack(fill=tk.X, padx=10, pady=(10, 0))
        tk.Label(model_frame, text="Model:").pack(side=tk.LEFT)
        tk.Entry(model_frame, textvariable=self.model_var, width=40).pack(side=tk.LEFT, padx=(5, 0))

        entry_frame = tk.Frame(self.root)
        entry_frame.pack(fill=tk.X, padx=10, pady=(10, 0))
        tk.Label(entry_frame, text="Task:").pack(side=tk.LEFT)
        entry = tk.Entry(entry_frame, textvariable=self.task_var, width=60)
        entry.pack(side=tk.LEFT, padx=(5, 0))
        entry.bind("<Return>", lambda _event: self.add_task())
        tk.Button(entry_frame, text="Add Task", command=self.add_task).pack(side=tk.LEFT, padx=(5, 0))

        list_frame = tk.Frame(self.root)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 0))
        tk.Label(list_frame, text="Queued Tasks:").pack(anchor=tk.W)
        self.task_listbox = tk.Listbox(list_frame, selectmode=tk.EXTENDED, height=10)
        self.task_listbox.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.task_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.task_listbox.config(yscrollcommand=scrollbar.set)

        button_frame = tk.Frame(self.root)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        tk.Button(button_frame, text="Run All", command=self.run_all).pack(side=tk.LEFT)
        tk.Button(button_frame, text="Delete Selected", command=self.delete_selected).pack(side=tk.LEFT, padx=(5, 0))
        tk.Button(button_frame, text="Clear", command=self.clear_tasks).pack(side=tk.LEFT, padx=(5, 0))

        self.status_var = tk.StringVar(value="Idle")
        tk.Label(self.root, textvariable=self.status_var, anchor="w").pack(fill=tk.X, padx=10, pady=(0, 10))

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
        model = self.model_var.get().strip() or get_effective_model(self.config)
        model = self.model_var.get().strip() or DEFAULT_MODEL
        thread = threading.Thread(target=self._run_tasks_thread, args=(tasks, model), daemon=True)
        self.running = True
        thread.start()

    def _run_tasks_thread(self, tasks: list[str], model: str) -> None:
        self._set_status(f"Running {len(tasks)} task(s)...")
        try:
            for idx, task in enumerate(tasks, start=1):
                self._set_status(f"[{idx}/{len(tasks)}] Running: {task}")
                try:
                    run_task(task, self.config, model_name=model)
                except FileNotFoundError as exc:
                    self._set_status(f"operate not found: {exc}")
                    self._notify_error(str(exc))
                    break
                except subprocess.CalledProcessError as exc:
                    self._set_status(f"Failed on task: {task}")
                    self._notify_error(f"Task failed with exit code {exc.returncode}: {task}")
                    break
                except Exception as exc:  # pragma: no cover - defensive
                    self._set_status(f"Error on task: {task}")
                    self._notify_error(f"Unexpected error: {exc}")
                    break
                delay = 0
                try:
                    delay = int(self.config.get("delay_between_tasks_seconds", 0))
                except Exception:
                    delay = 0
                if delay > 0 and idx < len(tasks):
                    time.sleep(delay)
            else:
                self._set_status("All tasks completed.")
        finally:
            self.running = False

    def _set_status(self, message: str) -> None:
        self.root.after(0, self.status_var.set, message)
        for idx, task in enumerate(tasks, start=1):
            self._set_status(f"[{idx}/{len(tasks)}] Running: {task}")
            try:
                run_task(task, model)
            except subprocess.CalledProcessError as exc:
                self._set_status(f"Failed on task: {task}")
                self._notify_error(f"Task failed with exit code {exc.returncode}: {task}")
                break
            except Exception as exc:  # pragma: no cover - defensive
                self._set_status(f"Error on task: {task}")
                self._notify_error(f"Unexpected error: {exc}")
                break
        else:
            self._set_status("All tasks completed.")
        self.running = False

    def _set_status(self, message: str) -> None:
        self.status_var.set(message)

    def _notify_error(self, message: str) -> None:
        self.root.after(0, lambda: messagebox.showerror("Operate Task Runner", message))

    def save_settings(self) -> None:
        model_value = self.settings_model_var.get().strip() or DEFAULT_MODEL_NAME
        api_key_value = self.settings_api_key_var.get().strip()
        try:
            delay_value = int(self.delay_var.get())
            if delay_value < 0:
                delay_value = 0
        except ValueError:
            delay_value = 0

        self.config.update(
            {
                "llm_model_name": model_value,
                "api_key": api_key_value,
                "voice_enabled": bool(self.voice_var.get()),
                "delay_between_tasks_seconds": delay_value,
                "start_with_windows": bool(self.start_with_windows_var.get()),
            }
        )

        save_config(self.config)
        update_windows_startup(self.config)
        self.model_var.set(model_value)
        messagebox.showinfo("Settings", "Settings saved.")


def main() -> None:
    root = tk.Tk()
    root.withdraw()

    config = load_config()
    if not ensure_password_set(root, config):
        root.destroy()
        return

    update_windows_startup(config)

    root.deiconify()
    app = TaskRunnerApp(root, config)

def main() -> None:
    root = tk.Tk()
    app = TaskRunnerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
