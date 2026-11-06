"""Minimal OpenAI-compatible client for Agnes AI (agnes-2.5-flash)."""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional

import requests


class LLMError(RuntimeError):
    pass


def _extract_json(text: str) -> Any:
    """Pull the first JSON array/object out of a model reply."""
    if not text:
        raise LLMError("empty reply")
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    cleaned = cleaned.replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    # scan for the first balanced { } or [ ] — whichever appears first in the text
    found = [(cleaned.find(op), op, cl) for op, cl in (("[", "]"), ("{", "}")) if cleaned.find(op) >= 0]
    for start, opener, closer in sorted(found):
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(cleaned)):
            ch = cleaned[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(cleaned[start : i + 1])
                    except Exception:
                        break
    raise LLMError(f"no JSON found in reply: {text[:160]}")


class AgnesLLM:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://apihub.agnes-ai.com/v1",
        model: str = "agnes-2.5-flash",
        temperature: float = 0.2,
        timeout: int = 120,
    ) -> None:
        self.api_key = api_key or os.environ.get("AGNES_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def chat(self, messages: List[Dict[str, str]], max_tokens: int = 3000, json_mode: bool = False) -> str:
        if not self.enabled:
            raise LLMError("AGNES_API_KEY not set")
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        last_err: Optional[Exception] = None
        for attempt in range(4):
            try:
                resp = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=self.timeout,
                )
                if resp.status_code in (408, 409, 429, 500, 502, 503, 504) and attempt < 3:
                    time.sleep(2 * (attempt + 1))
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
