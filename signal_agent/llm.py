"""Клиент к внутренним моделям Qwen через OpenAI-совместимый API (vLLM).

Только стандартная библиотека: внутренний контур, никаких внешних SDK и ключей.
Интерфейс ChatModel.chat() возвращает сообщение ассистента в формате OpenAI:
{"role": "assistant", "content": str | None, "tool_calls": [...] | None}.
"""
from __future__ import annotations

import base64
import json
import time
import urllib.request
from typing import Any, Protocol


class ChatModel(Protocol):
    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
             json_mode: bool = False, temperature: float = 0.0) -> dict[str, Any]: ...


class LLMError(RuntimeError):
    pass


def _post(url: str, payload: dict[str, Any], timeout: float, headers: dict[str, str] | None = None,
          retries: int = 2) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # сеть внутреннего контура: короткий экспоненциальный повтор
            last = exc
            time.sleep(2 ** attempt)
    raise LLMError(f"{url}: {last}")


class OpenAICompatChat:
    """Qwen 3.8 за vLLM: /v1/chat/completions с поддержкой tools."""

    def __init__(self, base_url: str, model: str, timeout_s: float = 120, api_key: str | None = None):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.timeout = timeout_s
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    def chat(self, messages, tools=None, json_mode=False, temperature=0.0):
        payload: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": temperature}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        resp = _post(self.url, payload, self.timeout, self.headers)
        msg = resp["choices"][0]["message"]
        return {"role": "assistant", "content": msg.get("content"), "tool_calls": msg.get("tool_calls")}


class QwenASR:
    """Qwen-ASR: OpenAI-совместимый /v1/audio/transcriptions (multipart)."""

    def __init__(self, base_url: str, model: str, timeout_s: float = 300):
        self.url = base_url.rstrip("/") + "/audio/transcriptions"
        self.model, self.timeout = model, timeout_s

    def transcribe(self, audio_path: str) -> str:
        boundary = "----signal" + str(int(time.time() * 1000))
        with open(audio_path, "rb") as f:
            audio = f.read()
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n{self.model}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\nru\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"call.wav\"\r\n"
            f"Content-Type: audio/wav\r\n\r\n"
        ).encode() + audio + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(self.url, data=body, method="POST",
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))["text"]


class QwenVL:
    """Qwen-VL: картинка-вложение → текст ошибки и описание экрана."""

    def __init__(self, base_url: str, model: str, prompt: str, timeout_s: float = 60):
        self.chat_model = OpenAICompatChat(base_url, model, timeout_s)
        self.prompt = prompt

    def describe(self, image_path: str) -> str:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        messages = [{"role": "user", "content": [
            {"type": "text", "text": self.prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ]}]
        return self.chat_model.chat(messages)["content"] or ""
