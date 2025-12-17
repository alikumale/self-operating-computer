import base64
import io
import json
from typing import Callable, Dict, List, Optional

import requests
from openai import OpenAI


class LLMError(Exception):
    """Raised when the language model call fails."""


def _clean_json_response(text: str) -> str:
    cleaned = text.strip()
    fence_start = cleaned.find("```")
    if fence_start != -1:
        fence_end = cleaned.find("```", fence_start + 3)
        if fence_end != -1:
            cleaned = cleaned[fence_start + 3 : fence_end]
    cleaned = cleaned.strip()
    if cleaned.lower().startswith("json"):
        cleaned = cleaned[4:].strip()

    brace_start = cleaned.find("{")
    if brace_start != -1:
        brace_depth = 0
        end_idx = None
        for idx, ch in enumerate(cleaned[brace_start:], start=brace_start):
            if ch == "{":
                brace_depth += 1
            elif ch == "}":
                brace_depth -= 1
                if brace_depth == 0:
                    end_idx = idx
                    break
        if end_idx is not None:
            cleaned = cleaned[brace_start : end_idx + 1]
        else:
            cleaned = cleaned[brace_start:]
    return cleaned


def parse_action_text(text: str, logger: Optional[Callable[[str], None]] = None) -> Optional[Dict[str, object]]:
    """Parse first JSON object describing an action with markdown-tolerant cleaning."""
    cleaned = _clean_json_response(text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        if logger:
            logger(f"Failed to parse model response (raw first 500): {text[:500]}")
            logger(f"Cleaned string: {cleaned}")
            logger(f"Parse error: {repr(exc)}")
        return None

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
            health = requests.get(f"{host}/api/tags", timeout=timeout)
        except requests.ReadTimeout as exc:  # type: ignore[attr-defined]
            raise LLMError(
                "Ollama timed out: increase timeout or use a smaller model. "
                f"Details: {repr(exc)}"
            ) from exc
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
        except requests.ReadTimeout as exc:  # type: ignore[attr-defined]
            raise LLMError(
                "Ollama timed out: increase timeout or use a smaller model. "
                f"Details: {repr(exc)}"
            ) from exc
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
        retry_count: int = 0,
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
        json_only_rules = (
            "Output EXACTLY ONE JSON object. DO NOT wrap output in markdown or backticks. "
            "DO NOT include explanations or extra text. Markdown-wrapped JSON will be rejected. "
            "Output raw JSON only."
        )
        safe_text_rules = (
            "In text-only mode avoid free clicking. Prefer hotkeys, typing, waits, Win search, "
            "Ctrl+L for address bar, then type and Enter. Output raw JSON only."
        )
        vision_rules = (
            "You may click visible elements, but still prefer reliable hotkeys and typing when possible. "
            "Output raw JSON only."
        )
        screen_info = (
            f"The virtual screen resolution is {screen_size or 'unknown'} pixels. "
            "Coordinates must be within this range. Do not assume a single monitor."
        )
        retry_warning = (
            "Previous response had invalid JSON. Respond with raw JSON only, no markdown."
            if retry_count > 0
            else ""
        )
        user_block = (
            f"Objective: {objective}\n"
            f"Latest screenshot info: {screenshot_note}\n"
            f"Screen size: {screen_size or 'unknown'}\n"
            f"{screen_info}\n"
            "Allowed actions must use integers for x and y. Prefer hotkey/type/wait over click; "
            "only click when necessary. Reply with exactly one JSON object."
        )

        messages: List[Dict[str, object]] = [
            {
                "role": "system",
                "content": (
                    "You are controlling a computer. Decide the single next action. "
                    + common_schema
                    + " "
                    + examples
                    + " "
                    + json_only_rules
                ),
            }
        ]

        if provider_mode == "Ollama (Local Text)":
            messages.append({"role": "user", "content": safe_text_rules})
            if retry_warning:
                messages.append({"role": "user", "content": retry_warning})
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
            if retry_warning:
                messages.append({"role": "user", "content": retry_warning})
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
            if retry_warning:
                messages.append({"role": "user", "content": retry_warning})
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
            tags = requests.get(f"{host}/api/tags", timeout=timeout)
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
