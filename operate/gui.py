"""Simple Tkinter wrapper to launch the self-operating-computer engine.

This utility keeps configuration minimal so Windows users can trigger
common tasks without relying on a terminal prompt.
"""
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from operate.main import main as operate_main

AVAILABLE_MODELS = [
    "gpt-4-with-ocr",
    "gpt-4.1-with-ocr",
    "o1-with-ocr",
    "gpt-4-with-som",
    "gemini-pro-vision",
    "claude-3",
    "llava",
    "qwen-vl",
]


class OperateGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Self-Operating Computer")
        self.root.geometry("520x260")

        self.objective_var = tk.StringVar()
        self.model_var = tk.StringVar(value=AVAILABLE_MODELS[0])
        self.verbose_var = tk.BooleanVar(value=False)

        self._build_layout()

    def _build_layout(self):
        padding = {"padx": 12, "pady": 8}

        heading = ttk.Label(
            self.root,
            text="Run the self-operating-computer",
            font=("Segoe UI", 12, "bold"),
        )
        heading.grid(row=0, column=0, columnspan=2, **padding, sticky="w")

        ttk.Label(self.root, text="Objective:").grid(
            row=1, column=0, sticky="nw", **padding
        )
        objective_entry = tk.Text(self.root, height=4, width=45)
        objective_entry.grid(row=1, column=1, sticky="we", **padding)
        objective_entry.bind("<<Modified>>", lambda _event: self._sync_objective(objective_entry))

        ttk.Label(self.root, text="Model:").grid(row=2, column=0, sticky="w", **padding)
        model_menu = ttk.Combobox(
            self.root,
            textvariable=self.model_var,
            values=AVAILABLE_MODELS,
            state="readonly",
        )
        model_menu.grid(row=2, column=1, sticky="we", **padding)

        verbose_check = ttk.Checkbutton(
            self.root,
            text="Verbose logging",
            variable=self.verbose_var,
        )
        verbose_check.grid(row=3, column=1, sticky="w", **padding)

        self.status_label = ttk.Label(self.root, text="Idle", foreground="#555")
        self.status_label.grid(row=4, column=0, columnspan=2, sticky="w", **padding)

        self.run_button = ttk.Button(self.root, text="Start", command=self._start)
        self.run_button.grid(row=5, column=1, sticky="e", **padding)

        self.root.columnconfigure(1, weight=1)

    def _sync_objective(self, widget: tk.Text):
        if widget.edit_modified():
            self.objective_var.set(widget.get("1.0", tk.END).strip())
            widget.edit_modified(False)

    def _start(self):
        objective = self.objective_var.get().strip()
        if not objective:
            messagebox.showwarning("Objective required", "Please enter what you want the agent to accomplish.")
            return

        self.run_button.config(state=tk.DISABLED)
        self.status_label.config(text="Running...", foreground="#0a5")

        thread = threading.Thread(
            target=self._run_engine,
            args=(objective, self.model_var.get(), self.verbose_var.get()),
            daemon=True,
        )
        thread.start()

    def _run_engine(self, objective: str, model: str, verbose: bool):
        try:
            operate_main(model, terminal_prompt=objective, voice_mode=False, verbose_mode=verbose)
        except Exception as exc:  # noqa: BLE001 - show any runtime errors
            messagebox.showerror("Self-Operating Computer", str(exc))
        finally:
            self.run_button.config(state=tk.NORMAL)
            self.status_label.config(text="Idle", foreground="#555")

    def run(self):
        self.root.mainloop()


def launch_gui():
    OperateGUI().run()


if __name__ == "__main__":
    launch_gui()
