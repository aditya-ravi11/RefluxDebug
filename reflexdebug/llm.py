"""LLM client wrapper with token and cost accounting, plus a scripted offline stand-in."""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from typing import Any

from .config import Settings

# USD per 1M tokens (input, output). Used for cost estimates only.
PRICING = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4.1": (2.00, 8.00),
    "text-embedding-3-small": (0.02, 0.0),
    "scripted": (0.0, 0.0),
    "text-embedding-3-large": (0.13, 0.0),
}


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ChatResult:
    content: str
    tool_calls: list[ToolCall]
    message: dict  # assistant message ready to append to the conversation
    finish_reason: str = "stop"  # "length" means the reply was cut off at max_tokens


@dataclass
class Usage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    embedding_tokens: int = 0
    cost_usd: float = 0.0

    def add(self, model: str, prompt: int, completion: int) -> None:
        self.calls += 1
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        pin, pout = PRICING.get(model, PRICING["gpt-4o-mini"])
        self.cost_usd += prompt / 1e6 * pin + completion / 1e6 * pout

    def add_embedding(self, model: str, tokens: int) -> None:
        self.embedding_tokens += tokens
        self.cost_usd += tokens / 1e6 * PRICING.get(model, (0.02, 0))[0]

    def as_dict(self) -> dict:
        return {
            "llm_calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "embedding_tokens": self.embedding_tokens,
            "cost_usd": round(self.cost_usd, 6),
        }


class LLM:
    """Thin wrapper over the OpenAI Chat Completions API."""

    def __init__(self, settings: Settings | None = None, model: str | None = None) -> None:
        self.settings = settings or Settings()
        self.settings.require_key()
        from openai import OpenAI

        self.client = OpenAI(api_key=self.settings.api_key, timeout=90.0, max_retries=2)
        self.model = model or self.settings.model
        self.usage = Usage()
        self.max_calls = self.settings.max_llm_calls

    def reset_usage(self, max_calls: int | None = None) -> None:
        self.usage = Usage()
        self.max_calls = max_calls or self.settings.max_llm_calls

    @property
    def calls_left(self) -> int:
        return self.max_calls - self.usage.calls

    def _supports_temperature(self) -> bool:
        return not (self.model.startswith("o") or self.model.startswith("gpt-5"))

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        json_mode: bool = False,
        temperature: float | None = None,
        max_tokens: int = 4096,
    ) -> ChatResult:
        if self.usage.calls >= self.max_calls:
            raise BudgetExceeded(f"LLM call budget of {self.max_calls} exhausted")
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages, "max_tokens": max_tokens}
        if self._supports_temperature():
            kwargs["temperature"] = self.settings.temperature if temperature is None else temperature
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
            kwargs["parallel_tool_calls"] = False
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        last_err: Exception | None = None
        for attempt in range(4):
            try:
                resp = self.client.chat.completions.create(**kwargs)
                break
            except Exception as err:  # network hiccups, rate limits
                last_err = err
                time.sleep(2 ** attempt)
        else:
            raise RuntimeError(f"OpenAI request failed after retries: {last_err}")

        if resp.usage:
            self.usage.add(self.model, resp.usage.prompt_tokens, resp.usage.completion_tokens)
        else:
            self.usage.add(self.model, 0, 0)
        msg = resp.choices[0].message
        calls = []
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_raw": tc.function.arguments}
            calls.append(ToolCall(tc.id, tc.function.name, args))
        message: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            message["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ]
        return ChatResult(msg.content or "", calls, message, getattr(resp.choices[0], "finish_reason", None) or "stop")

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = self.client.embeddings.create(model=self.settings.embedding_model, input=texts)
        if resp.usage:
            self.usage.add_embedding(self.settings.embedding_model, resp.usage.total_tokens)
        return [d.embedding for d in resp.data]


@dataclass
class ScriptedLLM:
    """Offline LLM used for tests and the no-key demo.

    ``script`` is a list of responses consumed in order. Each item is either a plain string
    (assistant text / JSON) or a dict ``{"content": str, "tool": (name, args)}``. An item may
    also be a callable taking the message list and returning one of those forms.
    """

    script: list[Any]
    model: str = "scripted"
    usage: Usage = field(default_factory=Usage)
    max_calls: int = 1000
    _i: int = 0

    def reset_usage(self, max_calls: int | None = None) -> None:
        self.usage = Usage()
        self.max_calls = max_calls or self.max_calls

    @property
    def calls_left(self) -> int:
        return self.max_calls - self.usage.calls

    def chat(self, messages, tools=None, json_mode=False, temperature=None, max_tokens=4096) -> ChatResult:
        if self.usage.calls >= self.max_calls:
            raise BudgetExceeded("scripted budget exhausted")
        if self._i >= len(self.script):
            item: Any = {"content": "Nothing left to try.", "tool": ("finish", {"summary": "script ended"})} if tools else "{}"
        else:
            item = self.script[self._i]
            self._i += 1
        if callable(item):
            item = item(messages)
        prompt_tokens = sum(len(str(m.get("content", ""))) for m in messages) // 4
        if isinstance(item, str):
            self.usage.add(self.model, prompt_tokens, len(item) // 4)
            return ChatResult(item, [], {"role": "assistant", "content": item})
        content = item.get("content", "")
        calls = []
        message: dict[str, Any] = {"role": "assistant", "content": content}
        if item.get("tool"):
            name, args = item["tool"]
            call_id = f"call_{self.usage.calls}"
            calls.append(ToolCall(call_id, name, args))
            message["tool_calls"] = [
                {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
            ]
        self.usage.add(self.model, prompt_tokens, (len(content) + len(json.dumps(item.get("tool")))) // 4)
        return ChatResult(content, calls, message)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [hashed_embedding(t) for t in texts]


def hashed_embedding(text: str, dim: int = 256) -> list[float]:
    """Deterministic bag-of-words embedding used offline and as a fallback."""
    vec = [0.0] * dim
    for token in text.lower().split():
        token = "".join(ch for ch in token if ch.isalnum())
        if not token:
            continue
        h = int(hashlib.md5(token.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]

