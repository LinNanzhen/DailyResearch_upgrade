"""Minimal OpenAI-compatible client (Agnes / OpenCode Go / any compatible gateway)."""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional

import requests


class LLMError(RuntimeError):
    pass


def _decode_many(text: str) -> list:
    """Decode concatenated / newline-delimited JSON values in one string."""
    dec = json.JSONDecoder()
    out: list = []
    idx = 0
    length = len(text)
    while idx < length:
        while idx < length and text[idx] in " \t\r\n,`":
            idx += 1
        if idx >= length:
            break
        try:
            value, end = dec.raw_decode(text, idx)
        except ValueError:
            nxt = min([p for p in (text.find("{", idx + 1), text.find("[", idx + 1)) if p != -1] or [length])
            if nxt <= idx:
                break
            idx = nxt
            continue
        out.append(value)
        idx = end
    return out


def _extract_json(text: str) -> Any:
    """Pull JSON out of a model reply: array, object, JSONL or concatenated."""
    if not text:
        raise LLMError("empty reply")
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    cleaned = cleaned.replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    values = _decode_many(cleaned)
    if len(values) == 1:
        return values[0]
    if values and all(isinstance(v, list) for v in values):
        return [item for group in values for item in group]
    if values:
        return values
    raise LLMError(f"no JSON found in reply: {text[:160]}")


class AgnesLLM:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://apihub.agnes-ai.com/v1",
        model: str = "agnes-2.5-flash",
        temperature: float = 0.2,
        timeout: int = 120,
        user_agent: str = "daily-dental-digest/1.0",
        session_id: str = "",
    ) -> None:
        self.api_key = api_key or os.environ.get("AGNES_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self.user_agent = user_agent
        self.session_id = session_id or os.urandom(8).hex()
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def chat(self, messages: List[Dict[str, str]], max_tokens: int = 3000, json_mode: bool = False) -> str:
        if not self.enabled:
            raise LLMError("no API key for this client")
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            # Agnes caps output at 4096 even for 2.5-flash; larger values are a 400.
            "max_tokens": min(int(max_tokens), 4096),
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        last_err: Optional[Exception] = None
        for attempt in range(5):
            try:
                resp = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                    timeout=self.timeout,
                )
                if resp.status_code in (408, 409, 429, 500, 502, 503, 504) and attempt < 4:
                    # Agnes returns 503 "request queue is full" during peak hours:
                    # back off patiently instead of burning the batch.
                    wait = 10 * (attempt + 1) if resp.status_code == 429 else 5 * (attempt + 1) ** 1.5
                    time.sleep(wait)
                    continue
                if resp.status_code >= 400:
                    raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                data = resp.json()
                usage = data.get("usage") or {}
                self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
                self.completion_tokens += int(usage.get("completion_tokens") or 0)
                self.calls += 1
                choices = data.get("choices") or []
                if not choices:
                    raise LLMError(f"no choices: {json.dumps(data)[:200]}")
                msg = choices[0].get("message") or {}
                content = msg.get("content")
                if isinstance(content, list):  # some providers return parts
                    content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
                return content or ""
            except (requests.RequestException, LLMError, ValueError) as exc:
                last_err = exc
                if attempt < 3:
                    time.sleep(2 * (attempt + 1))
        raise LLMError(f"request failed: {last_err}")

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }
        # OpenCode Go asks clients to send a stable session id so it can route
        # and cache properly (see opencode.ai/docs/console/go#where-can-i-use-it).
        if "opencode.ai" in self.base_url:
            headers["x-opencode-session"] = self.session_id
        return headers

    def chat_json(self, messages: List[Dict[str, str]], max_tokens: int = 3000) -> Any:
        raw = self.chat(messages, max_tokens=max_tokens, json_mode=False)
        try:
            return _extract_json(raw)
        except LLMError:
            repair = messages + [
                {"role": "assistant", "content": raw[:1500]},
                {"role": "user", "content": "上面的输出不是合法 JSON。只输出合法 JSON（不要 markdown、不要解释），保持相同字段。"},
            ]
            raw2 = self.chat(repair, max_tokens=max_tokens)
            return _extract_json(raw2)

    def usage(self) -> Dict[str, int]:
        return {"calls": self.calls, "prompt_tokens": self.prompt_tokens, "completion_tokens": self.completion_tokens}
