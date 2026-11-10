"""Chat JSON/SSE and persistent session/memory management for the local owner."""
import json
from datetime import datetime,timezone

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.background import BackgroundTask

from backend.ai.provider import LLMError
from backend.ai.schemas import MemoryInput
from backend.chat.service import Busy
from backend.database.store import Missing
from backend.error_log import service_failure
from backend.release import RELEASE, VERSION

router=APIRouter(prefix="/api")


class ChatInput(BaseModel):
    model_config=ConfigDict(extra="forbid")
    message: str=Field(min_length=1,max_length=2000)
    conversation_id: str | None=Field(default=None,min_length=1,max_length=64)

    @field_validator("message")
    @classmethod
    def nonempty(cls,value):
        if not value.strip():
            raise ValueError("消息不能为空")
        return value.strip()


class MemoryPatch(BaseModel):
    model_config=ConfigDict(extra="forbid")
    content: str | None=Field(default=None,min_length=1,max_length=1000)
    importance: float | None=Field(default=None,ge=0,le=1)
    category: str | None=None
    confirmed: bool | None=None


def translate(exc):
    if isinstance(exc,Missing):
        raise HTTPException(404,str(exc))
    if isinstance(exc,Busy):
        raise HTTPException(409,str(exc))
    raise HTTPException(422,"记忆内容或分类无效，敏感信息不能保存。")


def begin(request,payload):
    try:
        return request.app.state.chat.begin(payload.message,payload.conversation_id)
    except (Missing,Busy) as exc:
        translate(exc)
    except LLMError as exc:
        raise HTTPException(exc.status, {'code':exc.code,'message':exc.message}) from None


@router.get("/status")
async def status(request:Request):
    provider=request.app.state.provider
    return {"phase":"V1","version":VERSION,"release":RELEASE,"mode":provider.mode,"model":getattr(provider,"model","offline-rules"),"thinking":getattr(provider,"thinking","disabled"),"streaming":True,"persistent_history":True}


@router.post("/chat")
async def chat(payload:ChatInput,request:Request):
    turn=begin(request,payload)
    try:
        result=None
        async for event,data in request.app.state.chat.events(turn,streaming=False):
            if event=="done":
                result=data
        return result
    except LLMError as exc:
        service_failure('llm', exc.status)
        raise HTTPException(exc.status,{"code":exc.code,"message":exc.message,"conversation_id":turn.cid}) from None


def encode(event,data):
    return f"event: {event}\ndata: {json.dumps(data,ensure_ascii=False)}\n\n"


@router.post("/chat/stream")
async def stream_chat(payload:ChatInput,request:Request):
    turn=begin(request,payload)
    service=request.app.state.chat
    async def stream():
        try:
            async for event,data in service.events(turn):
                yield encode(event,data)
        except LLMError as exc:
            service_failure('llm', exc.status)
            yield encode("error",{"code":exc.code,"message":exc.message,"conversation_id":turn.cid})
        finally:
            service.abort(turn)
    return StreamingResponse(stream(),media_type="text/event-stream",headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"},background=BackgroundTask(service.abort,turn))


@router.get("/conversations")
async def conversations(request:Request):
    return request.app.state.store.conversations()


@router.post("/conversations")
async def new_conversation(request:Request):
    return request.app.state.store.create_conversation()


@router.get("/conversations/{cid}/messages")
async def messages(cid:str,request:Request):
    try:
        return request.app.state.store.messages(cid)
    except Missing as exc:
        translate(exc)


@router.delete("/conversations/{cid}")
async def delete_conversation(cid:str,request:Request):
    return remove_conversation(cid,request,False)


@router.delete("/conversations/{cid}/messages")
async def clear_conversation(cid:str,request:Request):
    return remove_conversation(cid,request,True)


def remove_conversation(cid,request,clear):
    try:
        request.app.state.chat.require_idle(cid)
        request.app.state.store.delete_conversation(cid,clear_only=clear)
    except (Missing,Busy) as exc:
        translate(exc)
    return {"ok":True}


@router.get("/memories")
async def memories(request:Request,q:str | None=Query(default=None,max_length=2000),category:str | None=None,since:datetime | None=None):
    rows=request.app.state.store.memories(q)
    if category is not None:rows=[m for m in rows if m['category']==category]
    if since is not None:
        cutoff=since.replace(tzinfo=timezone.utc) if since.tzinfo is None else since
        rows=[m for m in rows if datetime.fromisoformat(m['updated_at'])>=cutoff]
    return rows


@router.post("/memories")
async def create_memory(payload:MemoryInput,request:Request):
    try:
        return request.app.state.store.upsert_memory(**payload.model_dump())
    except ValueError as exc:
        translate(exc)


@router.patch("/memories/{mid}")
async def update_memory(mid:int,payload:MemoryPatch,request:Request):
    current=next((m for m in request.app.state.store.memories() if m["id"]==mid),None)
    if current is None:
        raise HTTPException(404,"记忆不存在。")
    try:
        body={key:current[key] for key in ("category","content","importance")}
        if any(value is None for value in payload.model_dump(exclude_unset=True).values()):
            raise ValueError("null not allowed")
        changes=payload.model_dump(exclude_unset=True)
        confirmed=changes.pop('confirmed',None)
        body.update(changes)
        validated=MemoryInput.model_validate(body)
        return request.app.state.store.upsert_memory(**validated.model_dump(),memory_id=mid,confirmed=confirmed)
    except (ValueError,Missing) as exc:
        translate(exc)


@router.delete("/memories/{mid}")
async def delete_memory(mid:int,request:Request):
    try:
        request.app.state.store.delete_memory(mid)
    except Missing as exc:
        translate(exc)
    return {"ok":True}


@router.get("/profile")
async def profile(request:Request):
    return request.app.state.store.profile()
