# Windows Reproduction Steps

Follow these PowerShell commands to reproduce the local setup:

```powershell
# 1) Clone the repository
 git clone https://github.com/alikumale/self-operating-computer.git
 cd self-operating-computer
 # Or skip cloning and install the published wheel:
 # pip install self-operating-computer

# 2) Create and activate a virtual environment
 py -3 -m venv .venv
 .\.venv\Scripts\Activate.ps1

# 3) Install the package and dependencies (Python-only install)
 pip install .

# 4) Add your OpenRouter/OpenAI settings (creates .env)
 copy .env.example .env
# Edit .env and set OPENROUTER_API_KEY, OPENAI_BASE_URL, and LLM_MODEL_NAME as needed

# 5) Smoke-test the CLI (headless-safe) or run a simple objective
 python -m operate.cli.gemini_agent --help
# Example headless-safe run using the configured LLM model name
 operate -m $env:LLM_MODEL_NAME --objective "Say hello and then exit."

# 6) Launch the task runner GUI
#   The first launch prompts you to set a password; later launches ask for it.
#   Settings (model, API key, voice, delays, startup preference) are stored in config.json (ignored by git).
 python task_runner.py
```

> Note: The `operate` CLI requires access to a GUI/Display because it imports `pyautogui`. In a headless shell you can still verify the install with the Gemini MCP helper command above.
