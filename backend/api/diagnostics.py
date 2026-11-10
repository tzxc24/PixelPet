"""Readiness and bounded metadata only; no credentials, audio or message contents."""
from datetime import datetime,timezone
from fastapi import APIRouter,Request
from pydantic import BaseModel,ConfigDict

from backend.api.audio import status as audio_status
from backend.release import RELEASE, VERSION

router=APIRouter(prefix='/api')


class EffectConfig(BaseModel):
    model_config=ConfigDict(extra='forbid')
    quiet_mode:bool


@router.patch('/events/configure')
async def configure(payload:EffectConfig,request:Request):
    request.app.state.pet_engine.configure(payload.model_dump())
    return {'ok':True}


@router.get('/diagnostics')
async def diagnostics(request:Request):
    state=request.app.state
    return {'version':VERSION,'release':RELEASE,'time_utc':datetime.now(timezone.utc).isoformat(),
            'llm':{'provider':state.provider.mode,'model':getattr(state.provider,'model','offline-rules'),
                   'active_conversations':len(state.chat.active),'timings':getattr(state.chat,'last_timing',{}),
                   'failures':state.chat.failures},
            'context':getattr(state.chat,'last_context',{'mode':'all_stored_sessions','truncated':False}),
            'speech':await audio_status(request),
            'audio_requests':dict(state.speech.request_metrics),'tts_cache':state.speech.natural.cache_status(),
            'voice_devices':getattr(state,'voice_devices',{}),
            'pet':state.pet_engine.snapshot(),'devices':state.devices.status(),
            'events':state.event_bus.history()[-40:],'recordings_retained':False,
            'hardware':'HW_PENDING','xiaozhi_native_compatible':False}
