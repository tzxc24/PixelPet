"""Audio upload and actual backend WAV responses; no raw recording retention."""
import asyncio
import time
from typing import Literal
from urllib.parse import quote
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.speech.service import MAX_BYTES, SpeechError
from backend.ai.schemas import Emotion
from backend.error_log import service_failure

router = APIRouter(prefix='/api/audio', tags=['audio'])


class SynthesizeInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(min_length=1, max_length=2000)
    voice: str | None = Field(default=None, max_length=200)
    rate: int | None = Field(default=None, ge=-10, le=10)
    volume: int | None = Field(default=None, ge=0, le=100)
    provider: Literal['edge','sapi','mock','azure','custom'] | None=None
    rate_percent: int=Field(default=0,ge=-20,le=20)
    pitch_hz: int=Field(default=0,ge=-12,le=12)
    volume_percent: int=Field(default=0,ge=-100,le=0)
    emotion: Emotion='normal'
    output_format: Literal['pc','device_pcm','device_wav']='pc'
    sample_rate: Literal[16000,24000] | None=None
    allow_fallback: bool=False

    @field_validator('text')
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError('Speech text cannot be empty')
        return value.strip()


def failure(exc):
    raise HTTPException(exc.status, {'code': exc.code, 'message': exc.message}) from None


async def generate_until_disconnect(request, generation):
    """Abort the online stream when the browser stops or replaces a reply."""
    task=asyncio.create_task(generation)
    try:
        while True:
            done,_=await asyncio.wait({task},timeout=.1)
            if done:return await task
            if await request.is_disconnected():
                raise HTTPException(499,{'code':'audio_cancelled','message':'语音任务已取消。'})
    finally:
        if not task.done():task.cancel()
        await asyncio.gather(task,return_exceptions=True)


@router.get('/status')
async def status(request: Request):
    service=request.app.state.speech
    result=await asyncio.to_thread(service.status)
    preferences=getattr(request.app.state,'preferences',None)
    selected=preferences.get().tts_provider if preferences is not None else 'sapi'
    if selected!='browser':
        result['tts']=await asyncio.to_thread(service.natural.provider(selected).status)
    else:result['tts']={'provider':'browser','ready':False,'requires_browser':True}
    result['selected_tts_provider']=selected
    result['preview_text']='你好呀，我是小星！今天也很开心见到你，嘿嘿，要不要陪我聊聊天？'
    return result


@router.get('/voices')
async def voices(request: Request,provider:Literal['edge','sapi','mock','azure','custom'] | None=None):
    try:
        preferences=getattr(request.app.state,'preferences',None)
        selected=provider or (preferences.get().tts_provider if preferences is not None else None)
        if selected and selected!='browser':return await request.app.state.speech.natural.voices(selected)
        return await request.app.state.speech.voices()
    except SpeechError as exc:
        failure(exc)


@router.post('/transcribe')
async def transcribe(request: Request, audio: UploadFile = File(...), duration_ms: float | None = Form(default=None, ge=0), sample_rate: int | None = Form(default=None, ge=1, le=384000), channels: int | None = Form(default=None, ge=1, le=32), purpose: Literal['conversation','wake'] = Form(default='conversation')):
    metrics = request.app.state.speech.request_metrics
    started = time.monotonic()
    try:
        preferences=getattr(request.app.state,'preferences',None)
        if preferences is not None and preferences.get().asr_provider=='disabled':
            raise SpeechError(503,'asr_disabled','本地语音识别已在设置中关闭，请使用文字或重新开启。')
        data = await audio.read(MAX_BYTES + 1)
        if purpose == 'wake':
            result = await request.app.state.speech.transcribe(data, audio.content_type, provider='local_whisper')
        else:
            result = await request.app.state.speech.transcribe(data, audio.content_type)
        result['client_metadata'] = {'duration_ms': duration_ms, 'sample_rate': sample_rate, 'channels': channels}
        return result
    except SpeechError as exc:
        metrics['asr_failures'] += 1
        service_failure('asr', exc.status)
        failure(exc)
    finally:
        metrics['asr_last_ms'] = round((time.monotonic()-started)*1000)
        await audio.close()


@router.post('/synthesize')
async def synthesize(payload: SynthesizeInput, request: Request):
    metrics = request.app.state.speech.request_metrics
    started = time.monotonic()
    try:
        service=request.app.state.speech
        preferences=getattr(request.app.state,'preferences',None)
        saved=preferences.get() if preferences is not None else None
        selected=payload.provider or (saved.tts_provider if saved is not None else None)
        if selected is None:
            audio=await service.synthesize(payload.text,payload.voice,payload.rate,payload.volume)
        else:
            if selected=='browser':raise SpeechError(409,'browser_tts_only','浏览器声音不能由后端生成，请选择 Edge 或 SAPI。')
            rate=payload.rate_percent if 'rate_percent' in payload.model_fields_set or payload.rate is None else payload.rate*10
            volume=payload.volume_percent if 'volume_percent' in payload.model_fields_set or payload.volume is None else payload.volume-100
            voice=payload.voice;pitch=payload.pitch_hz
            if saved is not None:
                if not {'rate','rate_percent'} & payload.model_fields_set:rate=round((saved.rate-1)*100)
                if not {'volume','volume_percent'} & payload.model_fields_set:volume=round((saved.volume-1)*100)
                if 'pitch_hz' not in payload.model_fields_set:pitch=saved.pitch_hz
                if 'voice' not in payload.model_fields_set and selected==saved.tts_provider:voice=saved.voice
            audio=await generate_until_disconnect(request,service.natural.synthesize(payload.text,provider=selected,voice=voice,rate_percent=rate,pitch_hz=pitch,volume_percent=volume,emotion=payload.emotion,output_format=payload.output_format,sample_rate=payload.sample_rate,allow_fallback=payload.allow_fallback))
        return Response(audio.data, media_type=audio.media_type, headers={'X-Audio-Sample-Rate': str(audio.sample_rate), 'X-Audio-Channels': str(audio.channels), 'X-Audio-Codec': audio.codec, 'X-Audio-Duration': str(round(audio.duration, 4)), 'X-Audio-Provider': audio.provider, 'X-Audio-Voice':quote(audio.voice),'X-Audio-Rate-Percent':str(audio.rate_percent),'X-Audio-Pitch-Hz':str(audio.pitch_hz),'X-Audio-Volume-Percent':str(audio.volume_percent),'X-Audio-Fallback':'sapi' if audio.fallback else 'none','X-Audio-Requested-Provider':audio.requested_provider,'X-Audio-Fallback-Reason':'edge_unavailable' if audio.fallback else '','X-Audio-Peak':str(audio.peak),'X-Audio-Clipped-Ratio':str(audio.clipped_ratio),'X-Audio-Size-Bytes': str(len(audio.data)), 'X-Audio-Synthesis-Ms':str(round((time.monotonic()-started)*1000)), 'X-Audio-Cache': 'hit' if audio.cache_hit else 'miss', 'Cache-Control': 'no-store'})
    except SpeechError as exc:
        metrics['tts_failures'] += 1
        service_failure('tts', exc.status)
        failure(exc)
    finally:
        metrics['tts_last_ms'] = round((time.monotonic()-started)*1000)
