"""Persist user turns, retrieve bounded memories and validate streamed model replies."""
import asyncio
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from backend.ai.provider import LLMError
from backend.ai.schemas import ModelReply
from backend.core.config import ROOT
from backend.memory.logic import extract, grounded


def animation_for(emotion, action):
    emotional={"happy":"HAPPY","shy":"SHY","sad":"IDLE","angry":"ANNOYED","curious":"LISTENING","thinking":"THINKING","sleepy":"SLEEP","surprised":"SURPRISED"}
    return emotional.get(emotion, {"jump":"HAPPY","listen":"LISTENING","think":"THINKING","speak":"SPEAKING","sleep":"SLEEP","shake":"SURPRISED"}.get(action,"IDLE"))


def partial_reply(raw):
    """Decode only complete JSON string codepoints, including fragmented escapes."""
    match=re.search(r'"reply"\s*:\s*"',raw)
    if match is None:
        return ""
    encoded=""
    escaped=False
    for char in raw[match.end():]:
        if char=='"' and not escaped:
            break
        encoded+=char
        if char=='\\' and not escaped:
            escaped=True
        else:
            escaped=False
    for end in range(len(encoded),max(-1,len(encoded)-13),-1):
        try:
            value=json.loads('"'+encoded[:end]+'"')
            value.encode("utf-8")  # Do not emit an unpaired UTF-16 surrogate.
            return value
        except (ValueError,UnicodeEncodeError):
            continue
    return ""


@dataclass
class Turn:
    cid: str
    mid: int
    message: str
    prompt: list
    active: bool = True


class Busy(Exception):
    pass


class ChatService:
    def __init__(self,store,provider,settings):
        self.store,self.provider,self.settings=store,provider,settings
        path=settings.character_path
        if not path.is_absolute():
            path=ROOT/path
        character=json.loads(path.read_text(encoding="utf-8-sig"))
        self.system="\n".join(character[key] for key in ("persona","rules","output"))
        self.active=set()
        self.failures=0

    def require_idle(self,cid):
        if cid in self.active:
            raise Busy("小星正在回复这段对话，请等回复结束后再操作。")

    def begin(self,message,cid=None,*,spoken=False):
        if cid is None:
            cid=self.store.create_conversation()["id"]
        self.require_idle(cid)
        # No await between checking and claiming: atomic on the service's event loop.
        self.active.add(cid)
        mid=None
        try:
            mid=self.store.begin_message(cid,message)
            context=self.store.full_context(mid)
            for fact in extract(message):
                self.store.upsert_memory(**fact,source=f"user:{cid}:{mid}")
            memories=self.store.memories(message)
            data=[{"category":m["category"],"content":m["content"]} for m in memories]
            identity=''
            if getattr(self,'preferences',None) is not None:
                preferences=self.preferences.get()
                identity='\n当前名字与性格设置（仅描述角色）：'+json.dumps({'name':preferences.name,'personality':preferences.personality},ensure_ascii=False)
            voice_style = ("\n当前为实时语音对话。先直接回应主人的问题，再讲清楚必要的背景、原因、步骤或例子。内容的长短由问题和主人的要求决定，讲到意思完整为止。主人要听故事、睡前故事、童话或寓言时，完整讲述。没指定篇目时，优先选一则中国寓言（如守株待兔、刻舟求剑、井底之蛙、狐假虎威），同一段对话尽量不重复。用自然中文讲一则完整的故事，有人物、起因、经过和结局，加入适量对话和具体细节；睡前语气温和，可以用一句话自然收尾。指定了篇目或长度就按主人的要求讲。" if spoken else "")
            prompt=[{"role":"system","content":self.system+identity+voice_style+"\n\nMEMORY_DATA:"+json.dumps(data,ensure_ascii=False)}]+context+[{"role":"user","content":message}]
            if sum(len(item['content']) for item in prompt)>self.settings.llm_history_max_chars:
                raise LLMError('history_too_large','完整历史超过本机发送上限，本条消息已保存；未裁剪历史，也未发送模型。请先导出整理历史，或调整 LLM_HISTORY_MAX_CHARS。',413)
            self.last_context={'mode':'all_stored_sessions','history_messages':len(context),
                               'characters':sum(len(item['content']) for item in prompt),'truncated':False}
            return Turn(cid,mid,message,prompt)
        except Exception:
            if mid is not None:
                self.store.fail_message(mid)
            self.active.discard(cid)
            raise

    def abort(self,turn):
        if turn.active:
            try:
                self.store.fail_message(turn.mid)
            finally:
                self.active.discard(turn.cid)
                turn.active=False

    def clock_reply(self, message):
        query = re.sub(r'[\s，。？！、,.?!]+', '', message)
        if not re.fullmatch(r'(?:小[星心])?(?:请问|你知道)?(?:现在|此刻)?(?:是)?(?:几点(?:钟)?|什么时间)(?:了|吗)?', query):
            return None
        preferences = self.preferences.get() if getattr(self, 'preferences', None) else None
        now = datetime.now(ZoneInfo(preferences.time_zone if preferences else 'Asia/Shanghai'))
        hour = f'{now.hour}点'
        if preferences and preferences.time_format == '12':
            hour = ('上午' if now.hour < 12 else '下午') + f'{now.hour % 12 or 12}点'
        minute = f'{now.minute:02d}分' if now.minute else '整'
        return ModelReply(reply=f'现在是{hour}{minute}。', emotion='normal', action='speak')

    async def events(self,turn,streaming=True):
        raw,emitted="",""
        started=time.monotonic();first_token=None
        clock_reply = self.clock_reply(turn.message)
        async def once():
            if clock_reply is not None:
                yield clock_reply.model_dump_json()
            else:
                yield await self.provider.complete(turn.prompt)
        use_once = clock_reply is not None or (not streaming and hasattr(self.provider, 'complete'))
        iterator = (once() if use_once else self.provider.stream(turn.prompt)).__aiter__()
        deadline=time.monotonic()+self.settings.llm_timeout
        try:
            yield "meta",{"conversation_id":turn.cid,"mode":self.provider.mode}
            while True:
                try:
                    part=await asyncio.wait_for(iterator.__anext__(),timeout=max(.001,deadline-time.monotonic()))
                except StopAsyncIteration:
                    break
                if first_token is None:first_token=round((time.monotonic()-started)*1000)
                raw+=part
                if len(raw)>24000:
                    raise LLMError("invalid_response","模型回复过长，请重试。")
                decoded=partial_reply(raw)
                if len(decoded)>6000:
                    raise LLMError("invalid_response","模型回复过长，请重试。")
                if decoded.startswith(emitted) and len(decoded)>len(emitted):
                    yield "delta",{"text":decoded[len(emitted):]}
                    emitted=decoded
            clean=re.sub(r"^```(?:json)?\s*|\s*```$","",raw.strip())
            fallback=False
            try:
                result=ModelReply.model_validate_json(clean)
            except ValidationError:
                if not getattr(self.provider,"plain_text_fallback",False):
                    raise
                try:
                    data=json.loads(clean)
                    text=data.get("reply","") if isinstance(data,dict) else ""
                except ValueError:
                    text=partial_reply(clean) if clean.startswith(("{","[")) else clean
                if not isinstance(text,str) or not text.strip():
                    raise LLMError("invalid_response","模型返回空白或无法解析，请重试。")
                result=ModelReply(reply=text[:6000],emotion="normal",action="idle")
                fallback=True
            # Candidate memories are facts only when grounded in this user turn.
            for memory in result.memories:
                if memory.importance>=.7 and grounded(memory.content,turn.message):
                    self.store.upsert_memory(**memory.model_dump(),source=f"model:{turn.cid}:{turn.mid}")
            message_id=self.store.finish_message(turn.cid,turn.mid,result,self.provider.mode)
            self.last_timing={'llm_first_token_ms':first_token,'llm_total_ms':round((time.monotonic()-started)*1000)}
            engine=getattr(self,'pet_engine',None)
            if engine is not None:
                from backend.events import Event
                engine.handle_event(Event(type='pet.emotion',device_id='browser-pixelpet',payload={'emotion':result.emotion,'state':animation_for(result.emotion,result.action)}))
            yield "done",{"conversation_id":turn.cid,"message_id":message_id,"reply":result.reply,"emotion":result.emotion,"action":result.action,"dialog_state":result.dialog_state,"state":animation_for(result.emotion,result.action),"mode":self.provider.mode,"fallback":fallback,'timings':self.last_timing}
        except (asyncio.TimeoutError,TimeoutError):
            self.failures+=1
            raise LLMError("timeout","小星等模型等得有点久，这条消息已保存，请稍后再试。",504) from None
        except (ValidationError,ValueError,TypeError):
            self.failures+=1
            raise LLMError("invalid_response","模型返回格式异常，这条消息已保存，请重试。") from None
        except LLMError:
            self.failures+=1
            raise
        finally:
            try:
                await iterator.aclose()
            finally:
                self.abort(turn)
