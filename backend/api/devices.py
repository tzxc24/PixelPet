"""PixelPet JSON business protocol; never a native xiaozhi endpoint."""
import asyncio
import json
import re
import io
import struct
import wave
from datetime import datetime, timedelta, timezone
from backend.preferences.scheduler import parse_voice_reminder
from uuid import uuid4
from backend.speech.service import SpeechError
from backend.speech.commands import is_rest_command, is_wake_command, normalize, assistant_rest_commitment
from backend.ai.schemas import ModelReply
from backend.ai.provider import LLMError
from backend.access import access_error
import numpy as np
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from backend.events import Event

router=APIRouter()

VOICE_HEADER = struct.Struct('!16sI')
VOICE_CHUNK = 4096
VOICE_LIMIT = 16000 * 2 * 20
VOICE_RECORD_DEADLINE = 25


def device_playback_pcm(data: bytes, peak: float) -> bytes:
    """Use available PCM headroom for the desk pet's speaker."""
    peak_limit = .85
    if not 0 < peak < peak_limit:
        return data
    gain = min(2.0, peak_limit / peak)
    samples = np.frombuffer(data, dtype='<i2')
    return np.rint(samples * gain).astype('<i2').tobytes()


@router.get('/api/devices/voice/status')
async def voice_status(request: Request):
    return {'devices': [
        {'id': identity, **{key: item.get(key) for key in
         ('conversation_id', 'state', 'dialog_state', 'last_heartbeat', 'connected_at')}}
        for identity, item in getattr(request.app.state, 'voice_devices', {}).items()
    ]}


@router.websocket('/api/devices/voice/ws')
async def voice_socket(ws: WebSocket):
    app = ws.app.state
    device = ws.query_params.get('device_id', '')
    if (access_error(ws.scope, app.access_token, app.allowed_hosts) is not None
            or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,80}', device)):
        await ws.close(code=1008)
        return
    active = getattr(app, 'voice_devices', None)
    if active is None:
        active = app.voice_devices = {}
    if device in active or len(active) >= 16:
        await ws.close(code=1008)
        return
    metrics = active[device] = dict(state='connected', uploaded=0, downloaded=0,
                                    rejected_frames=0, last_error=None, recording_bytes=0,
                                    connected_at=datetime.now(timezone.utc).isoformat())
    session = None
    conversation = None
    purpose = 'conversation'
    recording = bytearray()
    sequence = 0
    worker = None
    welcomed = False
    supports_reminders = False
    offered_reminder = None
    played_reminder = None
    record_deadline = None
    clock = asyncio.get_running_loop().time

    async def reply(kind, **fields):
        if kind == 'error':
            metrics['last_error'] = fields.get('code')
        await ws.send_json(dict(type=kind, **fields))

    async def synthesize(text, emotion):
        prefs = app.preferences.get()
        provider = prefs.tts_provider if prefs.tts_provider != 'browser' else 'edge'
        return await app.speech.synthesize_device(
            text, provider=provider, voice=prefs.voice if provider == prefs.tts_provider else None,
            emotion=emotion, rate_percent=round((prefs.rate-1)*100),
            volume_percent=round((prefs.volume-1)*100), pitch_hz=prefs.pitch_hz,
            output_format='device_pcm', sample_rate=24000)

    async def send_audio(session_id, audio, **fields):
        playback = device_playback_pcm(audio.data, audio.peak)
        await reply('playback.start', session_id=session_id, sample_rate=audio.sample_rate,
                    channels=audio.channels, format=audio.codec, byte_count=len(playback), **fields)
        identity = bytes.fromhex(session_id)
        for index, offset in enumerate(range(0, len(playback), VOICE_CHUNK)):
            chunk = playback[offset:offset+VOICE_CHUNK]
            await ws.send_bytes(VOICE_HEADER.pack(identity, index) + chunk)
            metrics['downloaded'] += len(chunk)
        await reply('playback.end', session_id=session_id)

    async def process(session_id, samples, conversation_id, purpose):
        turn = None
        loop = asyncio.get_running_loop()
        started = loop.time()
        try:
            if app.preferences.get().asr_provider == 'disabled':
                await reply('error', code='asr_disabled', session_id=session_id)
                return
            output = io.BytesIO()
            with wave.open(output, 'wb') as wav:
                wav.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
                wav.writeframes(samples)
            if purpose == 'wake':
                try:
                    transcript = await app.speech.transcribe(output.getvalue(), 'audio/wav', provider='local_keyword_spotter', wake=True)
                except SpeechError as exc:
                    if exc.code != 'no_speech':
                        raise
                    metrics['wake_check'] = {'result':'no_keyword','provider':'local_keyword_spotter'}
                    await reply('wake.result', session_id=session_id, dialog_state='standby')
                    return
            else:
                transcript = await app.speech.transcribe_device(output.getvalue(), 'audio/wav')
            metrics['asr_ms'] = transcript.get('elapsed_ms')
            metrics['asr_model'] = transcript.get('model')
            dialog_state = 'active'
            cid = conversation_id
            if purpose == 'wake':
                phrase=normalize(transcript['text'])
                metrics['wake_check'] = {
                    'result':'matched' if is_wake_command(phrase) else 'phrase_mismatch',
                    'characters':len(phrase),
                    'greeting':any(word in phrase for word in ('你好','您好')),
                    'name_variant':next((name for name in ('小星','小心','小新','小辛') if name in phrase),None),
                }
                if not is_wake_command(transcript['text']):
                    await reply('wake.result', session_id=session_id, dialog_state='standby')
                    return
                result = {'reply': '我在，想聊什么？', 'emotion': 'happy'}
                metrics['dialog_state'] = 'active'
                await reply('dialog.state', session_id=session_id, dialog_state='active')
            else:
                turn = app.chat.begin(transcript['text'], conversation_id, spoken=True)
                cid = turn.cid
                metrics['conversation_id'] = cid
                result = None
                reminder = parse_voice_reminder(transcript['text']) if supports_reminders else None
                if reminder is not None:
                    minutes, content = reminder
                    if not 1 <= minutes <= 1440:
                        text = '请说一个一到一千四百四十分钟之间的时间。'
                    else:
                        due = datetime.now(timezone.utc) + timedelta(minutes=minutes)
                        try:
                            app.scheduler.create(content or '时间到了。', due, device_id=device)
                            text = f'好，{minutes}分钟后提醒你。'
                        except ValueError:
                            text = '提醒没有设好，提醒列表已满。'
                    result = {'reply': text, 'emotion': 'normal'}
                    app.store.finish_message(turn.cid, turn.mid, ModelReply(**result, action='speak'), 'device_control')
                    app.chat.active.discard(turn.cid)
                    turn.active = False
                elif is_rest_command(transcript['text']):
                    dialog_state = 'standby'
                    metrics['dialog_state'] = 'standby'
                    result = {'reply': '好，我先休息啦。想聊天时叫我“你好小星”。', 'emotion': 'sleepy'}
                    app.store.finish_message(turn.cid, turn.mid,
                        ModelReply(**result, action='sleep'), 'device_control')
                    await reply('dialog.state', session_id=session_id, dialog_state='standby')
                else:
                    async for kind, item in app.chat.events(turn, streaming=False):
                        if kind == 'done':
                            result = item
            if result is None:
                await reply('error', code='no_reply', session_id=session_id)
                return
            if purpose != 'wake' and dialog_state != 'standby' and (
                    result.get('dialog_state') == 'standby' or assistant_rest_commitment(result['reply'])):
                dialog_state='standby'
                metrics['dialog_state']='standby'
                await reply('dialog.state', session_id=session_id, dialog_state='standby')
            metrics.update(result.get('timings', {}))
            tts_started = loop.time()
            for attempt in range(2):
                try:
                    audio = await synthesize(result['reply'], result['emotion'])
                    break
                except SpeechError as exc:
                    if attempt or exc.code not in ('tts_network', 'tts_timeout'):
                        raise
                    metrics['tts_retries'] = metrics.get('tts_retries', 0) + 1
                    await asyncio.sleep(1)
            metrics.update(state='sending', tts_ms=round((loop.time()-tts_started)*1000),
                           reply_ms=round((loop.time()-started)*1000))
            metrics['tts_provider'] = audio.provider
            await send_audio(session_id, audio, conversation_id=cid, dialog_state=dialog_state,
                             emotion=result['emotion'], text=result['reply'][:500],
                             timings={key: value for key, value in metrics.items() if key.endswith('_ms')})
        except (SpeechError, LLMError) as exc:
            await reply('error', code=exc.code, session_id=session_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            await reply('error', code='voice_turn_failed', session_id=session_id)
        finally:
            if turn is not None:
                app.chat.abort(turn)
            metrics['state'] = 'idle'

    async def bounded_turn(session_id, samples, conversation_id, purpose):
        try:
            await asyncio.wait_for(process(session_id, samples, conversation_id, purpose), timeout=90)
        except asyncio.TimeoutError:
            await reply('error', code='turn_timeout', session_id=session_id)

    try:
        await ws.accept()
        while True:
            if worker is not None and worker.done():
                await worker
                worker = None
                session = None
            timeout = 100 if worker else 45
            recording_timeout = record_deadline is not None
            if record_deadline is not None:
                timeout = min(timeout, max(0, record_deadline - clock()))
            try:
                frame = await asyncio.wait_for(ws.receive(), timeout=timeout)
            except asyncio.TimeoutError:
                if not recording_timeout:
                    raise
                await reply('error', code='record_timeout', session_id=session)
                session = record_deadline = None
                recording.clear()
                metrics.update(state='idle', recording_bytes=0)
                continue
            if frame['type'] == 'websocket.disconnect':
                break
            if worker is not None and worker.done():
                await worker
                worker = None
                session = None
            if frame.get('bytes') is not None:
                data = frame['bytes']
                size = len(data) - VOICE_HEADER.size
                if not session or worker or not 0 < size <= VOICE_CHUNK or size % 2:
                    metrics['rejected_frames'] += 1
                    await reply('error', code='invalid_audio_frame')
                    continue
                identity, index = VOICE_HEADER.unpack_from(data)
                if identity.hex() != session or index != sequence:
                    metrics['rejected_frames'] += 1
                    await reply('error', code='invalid_audio_sequence')
                    continue
                if len(recording) + size > VOICE_LIMIT:
                    session = None
                    record_deadline = None
                    recording.clear()
                    metrics['recording_bytes'] = 0
                    metrics['state'] = 'idle'
                    await reply('error', code='audio_overflow')
                    continue
                recording.extend(data[VOICE_HEADER.size:])
                metrics['uploaded'] += size
                metrics['recording_bytes'] = len(recording)
                sequence += 1
                continue
            try:
                raw = frame.get('text', '')
                msg = json.loads(raw) if len(raw) <= 4096 else None
                kind = msg.get('type') if isinstance(msg, dict) else None
            except (ValueError, RecursionError):
                kind = None
            if kind == 'hello' and not welcomed:
                welcomed = True
                supports_reminders = msg.get('reminders') is True
                firmware = msg.get('firmware_version')
                if isinstance(firmware, str) and re.fullmatch(r'[\w.+-]{1,40}', firmware, re.ASCII):
                    metrics['firmware_version'] = firmware
                metrics['state'] = 'idle'
                await reply('hello', version=1, protocol='pixelpet-pcm-v1', sample_rate=16000,
                            channels=1, format='pcm_s16le', max_record_seconds=20)
            elif welcomed and kind == 'heartbeat':
                metrics['last_heartbeat'] = datetime.now(timezone.utc).isoformat()
                await reply('heartbeat')
            elif welcomed and supports_reminders and kind == 'reminder.poll' and session is None:
                item = app.scheduler.next_device_reminder(device)
                offered_reminder = item['id'] if item else None
                if item:
                    await reply('reminder.ready', session_id=offered_reminder)
                else:
                    await reply('reminder.none')
            elif welcomed and supports_reminders and kind == 'reminder.play' and session is None:
                item = app.scheduler.next_device_reminder(device)
                if not item or not offered_reminder or offered_reminder != item['id'] or msg.get('session_id') != offered_reminder:
                    await reply('reminder.none')
                    continue
                text = '提醒你，' + item['text']
                try:
                    audio = await asyncio.wait_for(synthesize(text, 'normal'), timeout=20)
                    await send_audio(offered_reminder, audio)
                    played_reminder = offered_reminder
                except (SpeechError, asyncio.TimeoutError):
                    await reply('reminder.none')
            elif welcomed and supports_reminders and kind == 'reminder.ack' and played_reminder and msg.get('session_id') == played_reminder:
                app.scheduler.ack_device_reminder(device, played_reminder)
                offered_reminder = played_reminder = None
                await reply('reminder.ack')
            elif welcomed and kind == 'record.start' and session is None:
                if app.preferences.get().asr_provider == 'disabled':
                    await reply('error', code='asr_disabled')
                    continue
                purpose = msg.get('purpose', 'conversation')
                if purpose not in ('conversation', 'wake'):
                    await reply('error', code='invalid_record_purpose')
                    continue
                metrics['dialog_state'] = 'standby' if purpose == 'wake' else 'active'
                conversation = msg.get('conversation_id')
                if conversation is not None and (not isinstance(conversation, str) or len(conversation) > 64):
                    await reply('error', code='invalid_conversation')
                    continue
                session = uuid4().hex
                record_deadline = clock() + VOICE_RECORD_DEADLINE
                recording.clear()
                metrics['recording_bytes'] = 0
                sequence = 0
                metrics['state'] = 'recording'
                await reply('record.ready', session_id=session)
            elif welcomed and kind == 'record.stop' and session and msg.get('session_id') == session and not worker:
                record_deadline = None
                if not recording:
                    session = None
                    metrics['state'] = 'idle'
                    await reply('error', code='empty_recording')
                    continue
                await reply('thinking', session_id=session)
                metrics['state'] = 'thinking'
                worker = asyncio.create_task(bounded_turn(session, bytes(recording), conversation, purpose))
                recording.clear()
                metrics['recording_bytes'] = 0
            elif welcomed and kind == 'cancel' and session and msg.get('session_id') == session:
                record_deadline = None
                if worker:
                    worker.cancel()
                    await asyncio.gather(worker, return_exceptions=True)
                    worker = None
                await reply('cancelled', session_id=session)
                session = None
                recording.clear()
                metrics['recording_bytes'] = 0
                metrics['state'] = 'idle'
            else:
                await reply('error', code='invalid_voice_state')
    except asyncio.TimeoutError:
        await ws.close(code=1001, reason='voice timeout')
    except WebSocketDisconnect:
        pass
    finally:
        if worker:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
        active.pop(device, None)

DEVICE_EVENTS = {
    'TOUCH_START': 'touch.touch_down',
    'TOUCH_END': 'touch.touch_up',
    'TOUCH_SHORT': 'touch.tap',
    'TOUCH_DOUBLE': 'touch.double_tap',
    'TOUCH_LONG': 'touch.long_press',
    'RECORD_START': 'audio.record_start',
    'RECORD_STOP': 'audio.record_stop',
    'AUDIO_PLAY_START': 'audio.speak_start',
    'AUDIO_PLAY_END': 'audio.speak_end',
    'HAPTIC_SHORT': 'haptic.pattern',
    'HAPTIC_DOUBLE': 'haptic.pattern',
    'DISPLAY_EMOTION': 'pet.emotion',
}
EMOTION_STATE = {
    'normal': 'IDLE', 'happy': 'HAPPY', 'shy': 'SHY', 'sad': 'IDLE',
    'angry': 'ANNOYED', 'curious': 'SURPRISED', 'thinking': 'THINKING',
    'sleepy': 'SLEEP', 'surprised': 'SURPRISED',
}


def device_event(message, device_id):
    kind = message['type']
    payload = message.get('payload', {})
    if kind in ('HAPTIC_SHORT', 'HAPTIC_DOUBLE'):
        payload = {**payload, 'name': 'short' if kind == 'HAPTIC_SHORT' else 'double'}
    elif kind == 'DISPLAY_EMOTION':
        emotion = payload.get('emotion')
        if not isinstance(emotion, str) or emotion not in EMOTION_STATE:
            raise ValueError('unknown emotion')
        payload = {**payload, 'state': EMOTION_STATE[emotion]}
    return Event.model_validate({
        **{key: value for key, value in message.items() if key != 'seq'},
        'device_id': device_id, 'type': DEVICE_EVENTS.get(kind, kind), 'payload': payload,
    })

@router.get('/api/devices')
def devices(request:Request):
    request.app.state.devices.expire()
    return {'devices':request.app.state.devices.status(),'esp32':'HW_PENDING','protocol':'pixelpet-business-v1'}

@router.get('/api/events/status')
def event_status(request:Request):
    return {'events':request.app.state.event_bus.history(),'total':request.app.state.event_bus.count,'pet':request.app.state.pet_engine.snapshot()}

@router.post('/api/events')
def post_event(event:Event,request:Request):
    effects=request.app.state.pet_engine.handle_event(event)
    return {'event_id':event.event_id,'effects':effects,'pet':request.app.state.pet_engine.snapshot()}

@router.websocket('/api/devices/ws')
async def device_socket(ws:WebSocket):
    if access_error(ws.scope,getattr(ws.app.state,'access_token',''),getattr(ws.app.state,'allowed_hosts',None)) is not None:
        await ws.close(code=1008); return
    device_id=ws.query_params.get('device_id','mock-001')
    if not re.fullmatch(r'[a-zA-Z0-9_.-]{1,80}',device_id):
        await ws.close(code=1008); return
    service=ws.app.state.devices
    generation = service.connect(device_id)
    if generation is None:
        await ws.close(code=1008, reason='device id already connected')
        return
    hello=False
    expected_seq = None
    loop = asyncio.get_running_loop()
    deadline = loop.time() + service.heartbeat_timeout
    try:
        await ws.accept()
        await ws.send_json({
            'version': 1, 'type': 'device.connected', 'device_id': device_id,
            'protocol': 'pixelpet-business-v1', 'reconnect_count': generation - 1,
            'heartbeat_timeout': service.heartbeat_timeout,
        })
        while True:
            frame=await asyncio.wait_for(ws.receive(),timeout=deadline - loop.time())
            if frame['type']=='websocket.disconnect': break
            if 'text' not in frame:
                await ws.close(code=1003,reason='business JSON only'); break
            raw=frame['text']
            if len(raw.encode())>16384:
                await ws.close(code=1009); break
            correlation = {}
            try:
                msg=json.loads(raw)
                if not isinstance(msg,dict) or type(msg.get('version')) is not int or msg['version']!=1:
                    raise ValueError('version required')
                kind=msg.get('type')
                if not isinstance(kind, str) or not isinstance(msg.get('payload', {}), dict):
                    raise ValueError('invalid frame')
                seq = msg.get('seq')
                if type(seq) is int and 1 <= seq <= 2147483647:
                    correlation = {'seq': seq}
                if not hello and kind != 'hello':
                    raise ValueError('hello required')
                first_sequenced_hello = not hello and 'seq' in msg
                if expected_seq is not None or first_sequenced_hello:
                    required = expected_seq if expected_seq is not None else 1
                    if not correlation or seq != required:
                        await ws.send_json({
                            'version': 1, 'type': 'error', **correlation,
                            'payload': {'code': 'invalid_sequence', 'expected_seq': required},
                        })
                        continue
                    expected_seq = required + 1
                effects=[]
                event = None if kind in ('hello','heartbeat','response') else device_event(msg, device_id)
                service.heartbeat(device_id, generation=generation,
                                  kind=msg.get('payload', {}).get('client') if kind=='hello' else None)
                if event is not None:
                    effects=ws.app.state.pet_engine.handle_event(event)
                hello = True
                deadline = loop.time() + service.heartbeat_timeout
                await ws.send_json({'version':1,'type':'ack',**correlation,'payload':{'received':kind},'effects':effects,'pet':ws.app.state.pet_engine.snapshot()})
            except (ValueError,ValidationError,TypeError,RecursionError):
                await ws.send_json({'version':1,'type':'error',**correlation,'payload':{'code':'invalid_event'}})
    except asyncio.TimeoutError:
        await ws.close(code=1001,reason='heartbeat timeout')
    except WebSocketDisconnect:
        pass
    finally:
        service.disconnect(device_id, generation=generation)
