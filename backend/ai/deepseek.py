"""DeepSeek through the official OpenAI SDK, with thinking explicitly configured."""
import httpx
from openai import AsyncOpenAI, APIError, APIStatusError, APITimeoutError

from backend.ai.provider import LLMError


class DeepSeekProvider:
    mode="deepseek"
    plain_text_fallback=True

    def __init__(self,settings,transport=None):
        if not settings.deepseek_api_key.get_secret_value().strip():
            raise ValueError("DEEPSEEK_API_KEY is required for DeepSeek")
        self.model=settings.llm_model or "deepseek-flash"
        self.thinking=settings.llm_thinking
        kwargs={}
        if transport is not None:
            kwargs["http_client"]=httpx.AsyncClient(transport=transport)
        self.client=AsyncOpenAI(api_key=settings.deepseek_api_key.get_secret_value(),base_url=settings.llm_base_url or "https://api.deepseek.com",timeout=settings.llm_timeout,max_retries=0,**kwargs)

    def arguments(self,messages,stream):
        return {"model":self.model,"messages":messages,"stream":stream,"response_format":{"type":"json_object"},"extra_body":{"thinking":{"type":self.thinking}},"max_tokens":2048}

    @staticmethod
    def fail(exc):
        if isinstance(exc,(APITimeoutError,httpx.TimeoutException)):
            return LLMError("timeout","DeepSeek 回复超时，消息已保存，请稍后重试。",504)
        if isinstance(exc,APIStatusError):
            code=exc.status_code
            if code in (400,413,422) and any(word in str(exc.body).lower() for word in ('context_length','context length','maximum context','too many tokens')):
                return LLMError('context_limit','完整聊天历史超过 DeepSeek 的上下文容量。本条消息已保存，未自动裁剪旧记录。请先导出整理历史后重试。',413)
            if code==401:
                return LLMError("authentication","DeepSeek 密钥验证失败，请检查本机 .env 配置。")
            if code==402:
                return LLMError("balance","DeepSeek 账户余额不足，请检查账户。")
            if code==429:
                return LLMError("rate_limit","DeepSeek 请求较多，请稍后再试。")
            if code in (400,404,422):
                return LLMError("configuration","DeepSeek 请求配置不被接受，请检查模型名称与参数。")
        return LLMError("provider_unavailable","小星暂时联系不上 DeepSeek，请稍后再试。")

    async def complete(self,messages):
        try:
            response=await self.client.chat.completions.create(**self.arguments(messages,False))
            choice=response.choices[0]
            if choice.finish_reason!="stop":
                raise LLMError("incomplete_response","DeepSeek 的回复没有完整结束，请重试。")
            return choice.message.content or ""
        except LLMError:
            raise
        except (APIError,httpx.HTTPError,ValueError,TypeError,IndexError,AttributeError) as exc:
            raise self.fail(exc) from None

    async def stream(self,messages):
        response=None
        try:
            response=await self.client.chat.completions.create(**self.arguments(messages,True))
            complete=False
            async for chunk in response:
                if not chunk.choices:
                    continue
                choice=chunk.choices[0]
                if choice.finish_reason is not None:
                    if choice.finish_reason!="stop":
                        raise LLMError("incomplete_response","DeepSeek 的回复没有完整结束，请重试。")
                    complete=True
                if choice.delta.content:
                    yield choice.delta.content
            if not complete:
                raise LLMError("incomplete_response","DeepSeek 回复连接中断，请重试。")
        except LLMError:
            raise
        except (APIError,httpx.HTTPError,ValueError,TypeError,IndexError,AttributeError) as exc:
            raise self.fail(exc) from None
        finally:
            if response is not None:
                await response.close()

    async def close(self):
        await self.client.close()
