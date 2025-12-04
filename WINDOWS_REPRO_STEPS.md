# Windows Reproduction Steps (Python 3.11 recommended)

Follow these PowerShell commands on Windows 10/11 for a clean setup:

```powershell
# 1) Clone the repository
 git clone https://github.com/alikumale/self-operating-computer.git
 cd self-operating-computer

# 2) Create and activate a Python 3.11 virtual environment
 py -3.11 -m venv .venv
 .\.venv\Scripts\Activate.ps1  # or .\.venv\Scripts\activate

# 3) Upgrade pip and install dependencies
 python -m pip install --upgrade pip
 pip install -r requirements.txt
 # If you need the console script directly, also run:
 # pip install self-operating-computer

# 4) Configure your model/key and run
 # Launch the GUI to save settings (model, API key, voice, delay) into config.json
 python task_runner.py

# Optional: use the convenience script
 # .\scripts\setup_windows.ps1

# 5) Quick checks
 operate --help
 python task_runner.py
```

Notes:
- Settings (including API key and model) are stored locally in `config.json`, which is git-ignored.
- The GUI requires a display; running it in a headless shell will raise a Tkinter display error.
- The project is tested with Python 3.11; versions 3.10–3.12 should work. Older/newer versions will show a warning only.
