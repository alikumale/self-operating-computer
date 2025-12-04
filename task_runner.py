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
        model = self.model_var.get().strip() or DEFAULT_MODEL
        thread = threading.Thread(target=self._run_tasks_thread, args=(tasks, model), daemon=True)
        self.running = True
        thread.start()

    def _run_tasks_thread(self, tasks: list[str], model: str) -> None:
        self._set_status(f"Running {len(tasks)} task(s)...")
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


def main() -> None:
    root = tk.Tk()
    app = TaskRunnerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
