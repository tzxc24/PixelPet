"""Minimal OpenAI-compatible Chat Completions SSE adapter; no vendor SDK dependency."""
import asyncio
import json
from typing import AsyncIterator, Protocol
from urllib.parse import urlsplit

import httpx


class LLMError(Exception):
    def __init__(self, code="provider_unavailable", message="小星暂时联系不上模型服务，请检查配置或稍后再试。", status=502):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


class LLMProvider(Protocol):
    mode: str
    def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]: ...
    async def complete(self, messages: list[dict[str, str]]) -> str: ...
    async def close(self): ...


class OpenAICompatibleProvider:
    mode = "openai"

    def __init__(self, settings, transport=None):
        base = settings.llm_base_url.rstrip("/")
        parsed = urlsplit(base)
        if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username or parsed.query or parsed.fragment:
            raise ValueError("LLM_BASE_URL must be an HTTP(S) base URL without credentials, query or fragment")
        if not settings.llm_model.strip() or not settings.llm_api_key.get_secret_value().strip():
            raise ValueError("LLM_MODEL and LLM_API_KEY are required in openai mode")
        self.url = base + "/chat/completions"
        self.model = settings.llm_model
        self.timeout = settings.llm_timeout
        self.client = httpx.AsyncClient(
            headers={"Authorization": "Bearer " + settings.llm_api_key.get_secret_value()},
            timeout=httpx.Timeout(self.timeout), transport=transport,
            follow_redirects=False,
        )

    async def stream(self, messages):
        async def consume():
            # Bounded queue would add unnecessary buffering: the generator streams directly.
            async with self.client.stream("POST", self.url, json={
                "model": self.model, "messages": messages, "stream": True,
            }) as response:
                if response.status_code != 200:
                    raise LLMError()
                total = 0
                complete = False
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if raw == "[DONE]":
                        return
                    if not raw:
                        continue
                    data = json.loads(raw)
                    if not isinstance(data, dict):
                        raise LLMError("invalid_response", "模型返回格式异常，请重试。")
                    if "error" in data:
                        raise LLMError()
                    choices = data.get("choices", [])
                    if not choices:
                        continue
                    reason=choices[0].get("finish_reason")
                    if reason is not None:
                        if reason != "stop":
                            raise LLMError("incomplete_response", "模型回复没有完整结束，请重试。")
                        complete=True
                    part = choices[0].get("delta", {}).get("content")
                    if part is None:
                        continue
                    if not isinstance(part, str):
                        raise LLMError("invalid_response", "模型返回格式异常，请重试。")
                    total += len(part)
                    if total > 24000:
                        raise LLMError("invalid_response", "模型回复过长，请重试。")
                    yield part
                if not complete:
                    raise LLMError("incomplete_response", "模型回复连接中断，请重试。")
        try:
            async for part in consume():
                yield part
        except (httpx.TimeoutException, asyncio.TimeoutError):
            raise LLMError("timeout", "小星等模型等得有点久，这条消息已保存，请稍后再试。", 504) from None
        except LLMError:
            raise
        except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError, AttributeError):
            raise LLMError() from None

    async def close(self):
        await self.client.aclose()

    async def complete(self, messages):
        return "".join([part async for part in self.stream(messages)])


def make_provider(settings):
    from backend.ai.mock import MockProvider
    mode = settings.llm_mode
    key=settings.deepseek_api_key if settings.llm_provider=="deepseek" else settings.llm_api_key
    if mode == "mock" or (mode == "auto" and not key.get_secret_value().strip()):
        return MockProvider()
    if settings.llm_provider=="deepseek":
        from backend.ai.deepseek import DeepSeekProvider
        return DeepSeekProvider(settings)
    return OpenAICompatibleProvider(settings)
