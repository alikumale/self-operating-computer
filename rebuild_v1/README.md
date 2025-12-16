A minimal Windows-friendly rewrite that runs a decide-and-act loop with a local Ollama model (no API keys required). Phase B wiring for OpenRouter is also in place.

## Features
- Tkinter GUI with Tasks, Settings, and Logs tabs
- Provider modes: Ollama Text, Ollama Vision, OpenRouter API
- Safety toggles: Dry Run (default ON), Confirm Before Execute, Block Clicks, Block Terminal Typing, STOP hotkey/button
- Loop: screenshot → LLM JSON action → validate → (optionally) execute via `pyautogui`
- Config persisted to `rebuild_v1/config.json`

## Requirements
- Python 3.11 on Windows
- [Ollama](https://ollama.com) running locally (default host `http://localhost:11434`)
- Optional: OpenRouter API key for Phase B

Install Python packages:

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r rebuild_v1/requirements.txt
```

## Running the app
```bash
python -m rebuild_v1.main
```
If Tkinter fails to start in a headless environment, run on a local desktop session.

## Recommended modes
- **Local Text**: fastest, safest with clicks blocked by default. Ideal when you want conservative hotkeys/typing.
- **Local Vision**: needs a vision model; may be slower on some PCs. Increase timeout (600s+) if the model is large.
- **OpenRouter API**: highest accuracy if you have an API key.

Pull the default Ollama models before running:
```bash
ollama pull llama3.2:3b
ollama pull llava:7b
```

## Using Ollama (Phase A)
1. Start Ollama: `ollama serve`
2. Pick "Ollama (Local Text)" or "Ollama (Local Vision)" in Settings and adjust models/host if needed.
3. Vision mode sends the latest screenshot as base64 to the model.

The app checks connectivity to Ollama and shows a friendly message if the server or model is unavailable.

## Safety controls
- **Dry Run**: enabled by default; shows actions without executing.
- **Confirm Before Execute**: prompts before any real action; terminal windows require double-confirm for typing/hotkeys.
- **Block Clicks**: skips click actions and asks the model again.
- **Block Typing In Terminals**: prevents destructive commands unless you confirm twice.
- **STOP hotkey**: `Ctrl+Alt+S` (configurable) registered via the `keyboard` library.
- **STOP button**: halts the current loop.
- **Max steps**, **delay**, **timeout** configurable in Settings.

## OpenRouter (Phase B)
A provider dropdown exists; if "OpenRouter (API)" is chosen, set your API key, model, and base URL in Settings. Requests use the OpenAI-compatible SDK.

## Notes
- Screenshots use Pillow's `ImageGrab`; ensure a visible desktop session.
- Avoid sharing `config.json`—it is gitignored and may contain sensitive keys.
