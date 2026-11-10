"""Settings, local reminders, and owner memory governance."""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy import delete
from sqlalchemy.orm import Session

from backend.database.models import Memory
from backend.database.store import OWNER
from backend.preferences import PetPreferences, ReminderInput

router = APIRouter(prefix='/api')


@router.get('/pet/settings', response_model=PetPreferences)
def settings(request: Request):
    return request.app.state.preferences.get()


@router.patch('/pet/settings', response_model=PetPreferences)
async def update_settings(request: Request, payload: dict = Body(...)):
    if getattr(request.app.state,'chat',None) and request.app.state.chat.active:
        raise HTTPException(409,'请在小星回复结束后修改设置。')
    try:
        snapshot = request.app.state.preferences.update(payload)
    except ValidationError as exc:
        raise HTTPException(422, detail=exc.errors(include_context=False)) from None
    engine = getattr(request.app.state, 'pet_engine', None)
    if engine is not None:
        engine.configure(snapshot.model_dump())
    provider=getattr(request.app.state,'provider',None)
    if provider is not None and hasattr(provider,'model'):
        provider.model=snapshot.llm_model
    return snapshot


@router.get('/reminders')
def reminders(request: Request):
    return request.app.state.scheduler.list()


@router.post('/reminders', status_code=201)
def create_reminder(payload: ReminderInput, request: Request):
    try:
        return request.app.state.scheduler.create(payload.text, payload.due_at)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.delete('/reminders/{reminder_id}')
def delete_reminder(reminder_id: str, request: Request):
    if not request.app.state.scheduler.delete(reminder_id):
        raise HTTPException(404, '提醒不存在。')
    return {'deleted': True}


@router.get('/notifications/poll')
def poll_notifications(request: Request):
    return request.app.state.scheduler.poll()


@router.get('/memories/export')
def export_memories(request: Request):
    store = request.app.state.store
    payload = {'version': 1, 'exported_at': datetime.now(timezone.utc).isoformat(), 'profile': store.profile(), 'memories': store.memories()}
    return Response(json.dumps(payload, ensure_ascii=False, indent=2), media_type='application/json', headers={'Content-Disposition': 'attachment; filename="pixelpet-memories.json"'})


@router.delete('/memories')
async def clear_memories(request: Request):
    # Async route deliberately has no await between active check and transaction;
    # chat claims turns on this same event loop, preventing clear/begin races.
    chat = getattr(request.app.state, 'chat', None)
    if chat is not None and chat.active:
        raise HTTPException(409, '小星正在回复，请等回复结束后再清空记忆。')
    store = request.app.state.store
    with Session(store.engine) as session, session.begin():
        store.ensure_owner(session)
        session.execute(delete(Memory).where(Memory.user_id == OWNER))
        store.sync_profile(session)
    return {'deleted': True}
