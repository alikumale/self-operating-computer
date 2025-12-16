import base64
import io
import json
from typing import Callable, Dict, List, Optional

import requests
from openai import OpenAI


class LLMError(Exception):
    """Raised when the language model call fails."""


def _first_json_object(text: str) -> Optional[Dict[str, object]]:
    decoder = json.JSONDecoder()
    idx = text.find("{")
    while idx != -1:
        try:
            obj, _ = decoder.raw_decode(text[idx:])
            if isinstance(obj, dict):
                if idx > 0:
                    # leading noise; still return first valid object
                    return obj
                return obj
        except json.JSONDecodeError:
            pass
        idx = text.find("{", idx + 1)
    return None


def parse_action_text(text: str, logger: Optional[Callable[[str], None]] = None) -> Optional[Dict[str, object]]:
    """Parse first JSON object describing an action. Logs when multiple objects are present."""
    try:
        data = json.loads(text)
        extra_text = None
    except json.JSONDecodeError:
        data = _first_json_object(text)
        extra_text = text
    else:
        if isinstance(text, str) and text.strip().endswith("}"):
            extra_text = None
        else:
            extra_text = text

    if data is None:
        return None

    if extra_text and logger:
        logger("Model returned extra text; using first JSON object only.")

    if not isinstance(data, dict):
        return None
    action_type = data.get("type")
    if action_type not in {"click", "type", "hotkey", "wait", "done"}:
        return None
    if action_type == "click":
        if isinstance(data.get("x"), int) and isinstance(data.get("y"), int):
            return {"type": "click", "x": data["x"], "y": data["y"]}
    elif action_type == "type":
        if isinstance(data.get("text"), str):
            return {"type": "type", "text": data["text"]}
    elif action_type == "hotkey":
        keys = data.get("keys")
        if isinstance(keys, str):
            keys = [keys]
        if isinstance(keys, list):
            normalized = []
            for key in keys:
                if isinstance(key, str) and "+" in key:
                    normalized.extend(part.strip() for part in key.split("+") if part.strip())
                elif isinstance(key, str):
                    normalized.append(key)
            if normalized:
                return {"type": "hotkey", "keys": normalized}
    elif action_type == "wait":
        seconds = data.get("seconds")
        if isinstance(seconds, (int, float)):
            return {"type": "wait", "seconds": float(seconds)}
    elif action_type == "done":
        reason = data.get("reason")
        if isinstance(reason, str):
            return {"type": "done", "reason": reason}
    return None


class LLMEngine:
    def __init__(self, config: Dict[str, object], logger: Optional[Callable[[str], None]] = None):
        self.config = config
        self.logger = logger or (lambda _msg: None)

    def _raise(self, provider_mode: str, endpoint: str, model: str, exc: Exception) -> LLMError:
        return LLMError(
            f"[{provider_mode}] call to {endpoint} with model '{model}' failed: {repr(exc)}"
        )

    def _ollama_chat(
        self,
        messages: List[Dict[str, object]],
        model: str,
        host: str,
        timeout: float,
        provider_mode: str,
    ) -> str:
        try:
            health = requests.get(f"{host}/api/tags", timeout=5)
        except requests.RequestException as exc:
            raise self._raise(provider_mode, f"{host}/api/tags", model, exc) from exc

        if health.status_code != 200:
            raise LLMError(
                f"[{provider_mode}] Ollama responded with status {health.status_code}; is it running?"
            )

        payload = {"model": model, "messages": messages, "stream": False}
        try:
            response = requests.post(
                f"{host}/api/chat", json=payload, timeout=timeout, stream=False
            )
        except requests.RequestException as exc:
            raise self._raise(provider_mode, f"{host}/api/chat", model, exc) from exc

        if response.status_code == 404:
            raise LLMError(
                f"[{provider_mode}] Model '{model}' not found. Install with: ollama pull {model}"
            )
        if response.status_code >= 400:
            raise LLMError(
                f"[{provider_mode}] Ollama returned {response.status_code}: {response.text}"
            )

        try:
            data = response.json()
        except ValueError as exc:  # pragma: no cover - defensive
            raise self._raise(provider_mode, f"{host}/api/chat", model, exc) from exc

        message = data.get("message", {})
        content = message.get("content")
        if not content:
            raise LLMError(f"[{provider_mode}] Ollama returned an empty response.")
        return content

    def _openrouter_chat(
        self, messages: List[Dict[str, object]], model: str, base_url: str, api_key: str, timeout: float
    ) -> str:
        if not api_key:
            raise LLMError("[OpenRouter (API)] Missing API key in settings.")

        client = OpenAI(api_key=api_key, base_url=base_url)
        try:
            chat = client.chat.completions.create(
                model=model,
                messages=messages,
                stream=False,
                timeout=timeout,
            )
        except Exception as exc:  # pylint: disable=broad-except
            raise LLMError(
                f"[OpenRouter (API)] call to {base_url} with model '{model}' failed: {repr(exc)}"
            ) from exc

        try:
            content = chat.choices[0].message.content
        except (AttributeError, IndexError):  # pragma: no cover - defensive
            content = None
        if not content:
            raise LLMError("[OpenRouter (API)] returned an empty response.")
        return content

    def request_action(
        self,
        objective: str,
        screenshot_note: str,
        screenshot_bytes: Optional[bytes] = None,
        screen_size: Optional[str] = None,
    ) -> str:
        provider_mode = str(self.config.get("provider_mode", "Ollama (Local Text)"))
        timeout = float(self.config.get("llm_timeout_seconds", 600))
        common_schema = (
            "Allowed actions as ONE JSON object: "
            '{"type":"click","x":int,"y":int} | '
            '{"type":"type","text":str} | '
            '{"type":"hotkey","keys":[str,...]} | '
            '{"type":"wait","seconds":float} | '
            '{"type":"done","reason":str}.'
        )
        examples = (
            "Examples: {\"type\":\"hotkey\",\"keys\":[\"win\"]} | "
            "{\"type\":\"type\",\"text\":\"notepad\"} | "
            "{\"type\":\"click\",\"x\":120,\"y\":220} | "
            "{\"type\":\"wait\",\"seconds\":1.0} | "
            "{\"type\":\"done\",\"reason\":\"finished\"}."
        )
        safe_text_rules = (
            "In text-only mode avoid free clicking. Prefer hotkeys, typing, waits, Win search, "
            "Ctrl+L for address bar, then type and Enter. OUTPUT JSON ONLY."
        )
        vision_rules = (
            "You may click visible elements, but still prefer reliable hotkeys and typing when possible. "
            "OUTPUT JSON ONLY."
        )
        user_block = (
            f"Objective: {objective}\n"
            f"Latest screenshot info: {screenshot_note}\n"
            f"Screen size: {screen_size or 'unknown'}\n"
            "Reply with exactly one JSON object."
        )

        messages: List[Dict[str, object]] = [
            {
                "role": "system",
                "content": (
                    "You are controlling a computer. Decide the single next action. "
                    + common_schema
                    + " "
                    + examples
                ),
            }
        ]

        if provider_mode == "Ollama (Local Text)":
            messages.append({"role": "user", "content": safe_text_rules})
            messages.append({"role": "user", "content": user_block})
            return self._ollama_chat(
                messages,
                model=str(self.config.get("ollama_text_model", "llama3.2:3b")),
                host=str(self.config.get("ollama_host", "http://localhost:11434")),
                timeout=timeout,
                provider_mode=provider_mode,
            )

        if provider_mode == "Ollama (Local Vision)":
            if screenshot_bytes is None:
                raise LLMError("Vision mode requires screenshot bytes.")
            b64_image = base64.b64encode(screenshot_bytes).decode("utf-8")
            messages.append({"role": "user", "content": vision_rules})
            messages.append(
                {
                    "role": "user",
                    "content": user_block,
                    "images": [b64_image],
                }
            )
            try:
                return self._ollama_chat(
                    messages,
                    model=str(self.config.get("ollama_vision_model", "llava:7b")),
                    host=str(self.config.get("ollama_host", "http://localhost:11434")),
                    timeout=timeout,
                    provider_mode=provider_mode,
                )
            except LLMError as exc:
                if "images" in str(exc).lower():
                    self.logger(
                        "The selected Ollama model may not support images. Try pulling llava:7b and set it in settings."
                    )
                raise

        if provider_mode == "OpenRouter (API)":
            messages.append({"role": "user", "content": safe_text_rules})
            messages.append({"role": "user", "content": user_block})
            return self._openrouter_chat(
                messages,
                model=str(self.config.get("openrouter_model", "openrouter/auto")),
                base_url=str(self.config.get("openrouter_base_url", "https://openrouter.ai/api/v1")),
                api_key=str(self.config.get("openrouter_api_key", "")),
                timeout=timeout,
            )

        raise LLMError(f"Unsupported provider mode: {provider_mode}")


def test_provider(config: Dict[str, object]) -> str:
    engine = LLMEngine(config)
    provider_mode = str(config.get("provider_mode", "Ollama (Local Text)"))
    timeout = float(config.get("llm_timeout_seconds", 600))
    if provider_mode.startswith("Ollama"):
        host = str(config.get("ollama_host", "http://localhost:11434"))
        model = (
            str(config.get("ollama_text_model", "llama3.2:3b"))
            if provider_mode == "Ollama (Local Text)"
            else str(config.get("ollama_vision_model", "llava:7b"))
        )
        try:
            tags = requests.get(f"{host}/api/tags", timeout=5)
            tags.raise_for_status()
        except Exception as exc:  # pylint: disable=broad-except
            return f"Ollama connectivity failed: {repr(exc)}"

        payload_messages: List[Dict[str, object]] = [
            {
                "role": "user",
                "content": "Reply OK",
            }
        ]
        if provider_mode == "Ollama (Local Vision)":
            img = io.BytesIO()
            from PIL import Image  # lazy import to avoid overhead if unused

            Image.new("RGB", (2, 2), color="black").save(img, format="PNG")
            img_bytes = img.getvalue()
            payload_messages[0]["images"] = [base64.b64encode(img_bytes).decode("utf-8")]
        try:
            reply = engine._ollama_chat(  # pylint: disable=protected-access
                payload_messages, model=model, host=host, timeout=timeout, provider_mode=provider_mode
            )
        except Exception as exc:  # pylint: disable=broad-except
            return f"Ollama chat failed: {repr(exc)}"
        return f"Ollama test succeeded: {reply}" if reply else "Ollama test returned empty response."

    if provider_mode == "OpenRouter (API)":
        try:
            reply = engine._openrouter_chat(  # pylint: disable=protected-access
                messages=[{"role": "user", "content": "Reply OK"}],
                model=str(config.get("openrouter_model", "openrouter/auto")),
                base_url=str(config.get("openrouter_base_url", "https://openrouter.ai/api/v1")),
                api_key=str(config.get("openrouter_api_key", "")),
                timeout=timeout,
            )
        except Exception as exc:  # pylint: disable=broad-except
            return f"OpenRouter test failed: {repr(exc)}"
        return f"OpenRouter test succeeded: {reply}" if reply else "OpenRouter test returned empty response."

    return f"Unsupported provider mode: {provider_mode}"
