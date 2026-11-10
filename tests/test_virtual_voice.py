import asyncio
import io
import json
import socket
import wave
from uuid import UUID

from fastapi.testclient import TestClient
from websockets.sync.client import connect

from backend.core.config import Settings
from backend.main import create_app
from backend.speech.service import SpeechError
from scripts.virtual_esp32_voice import HEADER, VirtualESP32Voice, pcm16_wav
from scripts.verify_v11_device_live import loopback


def test_recording_deadline_releases_session(tmp_path, monkeypatch):
    import backend.api.devices as devices
    monkeypatch.setattr(devices, 'VOICE_RECORD_DEADLINE', .05, raising=False)
    app = create_app(database_path=tmp_path / 'deadline.sqlite3', settings=Settings(llm_mode='mock'))
    with TestClient(app) as http, http.websocket_connect('/api/devices/voice/ws?device_id=deadline') as ws:
        device = VirtualESP32Voice(TestTransport(ws))
        device.hello()
        device.send('record.start')
        original = device.control('record.ready')['session_id']
        assert ws.receive_json() == {'type': 'error', 'code': 'record_timeout', 'session_id': original}
        device.send('record.start')
        assert device.control('record.ready')['session_id'] != original


def test_disabled_asr_applies_to_device_voice(tmp_path):
    app = create_app(database_path=tmp_path / 'disabled.sqlite3', settings=Settings(llm_mode='mock'))
    with TestClient(app) as http:
        http.patch('/api/pet/settings', json={'asr_provider': 'disabled'}).raise_for_status()
        with http.websocket_connect('/api/devices/voice/ws?device_id=disabled') as ws:
            device = VirtualESP32Voice(TestTransport(ws))
            device.hello()
            device.send('record.start')
            assert ws.receive_json() == {'type': 'error', 'code': 'asr_disabled'}


class TestTransport:
    __test__ = False

    def __init__(self, websocket):
        self.websocket = websocket

    def send(self, frame):
        if isinstance(frame, bytes):
            self.websocket.send_bytes(frame)
        else:
            self.websocket.send_text(frame)

    def recv(self, timeout=None):
        frame = self.websocket.receive()
        if 'bytes' in frame:
            return frame['bytes']
        if 'text' in frame:
            return frame['text']
        raise ConnectionError('WebSocket closed')


def test_virtual_voice_two_turns_use_binary_audio_and_persist_conversation(tmp_path):
    class FixtureASR:
        def transcribe(self, samples):
            assert len(samples) == 8000
            return {'text': '你还记得我在做什么吗？', 'language': 'zh'}

    app = create_app(database_path=tmp_path / 'device.sqlite3', settings=Settings(llm_mode='mock'))
    with TestClient(app) as http:
        app.state.speech.asr = FixtureASR()
        http.patch('/api/pet/settings', json={'tts_provider': 'mock'}).raise_for_status()
        http.post('/api/memories', json={'category': 'project', 'content': '主人正在开发 ESP32 AI 桌宠 PixelPet。', 'importance': .95}).raise_for_status()
        with http.websocket_connect('/api/devices/voice/ws?device_id=virtual-voice-test') as ws:
            device = VirtualESP32Voice(TestTransport(ws))
            device.hello()
            first, output = device.turn(b'\x03\x00' * 8000)
            second, _ = device.turn(b'\x03\x00' * 8000, first['conversation_id'])
        assert first['conversation_id'] == second['conversation_id']
        assert first['session_id'] != second['session_id']
        assert 'PixelPet' in first['text']
        with wave.open(io.BytesIO(pcm16_wav(output, 24000)), 'rb') as wav:
            assert wav.getnframes() > 0 and wav.getframerate() == 24000


def test_device_voice_rejects_empty_duplicate_old_and_oversized_frames(tmp_path):
    app = create_app(database_path=tmp_path / 'frames.sqlite3', settings=Settings(llm_mode='mock'))
    with TestClient(app) as http, http.websocket_connect('/api/devices/voice/ws?device_id=bad-frames') as ws:
        device = VirtualESP32Voice(TestTransport(ws))
        device.hello()
        device.send('record.start')
        old = device.control('record.ready')['session_id']
        device.send('record.stop', session_id=old)
        assert ws.receive_json()['code'] == 'empty_recording'
        device.send('record.start')
        session = device.control('record.ready')['session_id']
        current = UUID(hex=session).bytes
        ws.send_bytes(b'broken')
        assert ws.receive_json()['code'] == 'invalid_audio_frame'
        ws.send_bytes(HEADER.pack(current, 0) + b'\x01')
        assert ws.receive_json()['code'] == 'invalid_audio_frame'
        ws.send_bytes(HEADER.pack(UUID(hex=old).bytes, 0) + b'\0\0')
        assert ws.receive_json()['code'] == 'invalid_audio_sequence'
        chunk = b'\0' * 4096
        ws.send_bytes(HEADER.pack(current, 0) + chunk)
        ws.send_bytes(HEADER.pack(current, 0) + chunk)
        assert ws.receive_json()['code'] == 'invalid_audio_sequence'
        for sequence in range(1, 157):
            ws.send_bytes(HEADER.pack(current, sequence) + chunk)
        assert ws.receive_json()['code'] == 'audio_overflow'
        device.send('heartbeat')
        device.control('heartbeat')
        device.send('record.start')
        new = device.control('record.ready')['session_id']
        assert new not in (old, session)
        device.send('cancel', session_id=new)
        assert device.control('cancelled')['session_id'] == new


def test_cancel_busy_voice_turn_and_resume_after_tts_failure(tmp_path):
    app = create_app(database_path=tmp_path / 'recovery.sqlite3', settings=Settings(llm_mode='mock'))
    with TestClient(app) as http:
        initial_synthesis = app.state.speech.natural.synthesize

        async def slow_asr(*args):
            await asyncio.sleep(10)

        async def ok_asr(*args):
            return {'text': '你好', 'elapsed_ms': 0}

        async def broken_tts(*args, **kwargs):
            raise SpeechError(503, 'tts_network', 'injected fault')

        app.state.speech.transcribe = slow_asr
        http.patch('/api/pet/settings', json={'tts_provider': 'mock'}).raise_for_status()
        with http.websocket_connect('/api/devices/voice/ws?device_id=recovery') as ws:
            device = VirtualESP32Voice(TestTransport(ws))
            device.hello()

            def start_turn():
                device.send('record.start')
                session = device.control('record.ready')['session_id']
                ws.send_bytes(HEADER.pack(UUID(hex=session).bytes, 0) + b'\0\0')
                device.send('record.stop', session_id=session)
                device.control('thinking')
                return session

            session = start_turn()
            device.send('cancel', session_id=session)
            assert device.control('cancelled')['session_id'] == session
            app.state.speech.transcribe = ok_asr
            app.state.speech.natural.synthesize = broken_tts
            failed = start_turn()
            error = ws.receive_json()
            assert error['session_id'] == failed and error['code'] == 'tts_network'
            app.state.speech.natural.synthesize = initial_synthesis
            reply, pcm = device.turn(b'\x03\x00' * 8000)
            assert reply['session_id'] not in (failed, session) and pcm


def test_device_tcp_disconnect_and_restart_reject_old_session(tmp_path):
    database = tmp_path / 'restart.sqlite3'
    settings = Settings(llm_mode='mock', access_token='')
    endpoint = '/api/devices/voice/ws?device_id=restart-test'
    with loopback(create_app(database_path=database, settings=settings)) as port:
        with connect(f'ws://127.0.0.1:{port}{endpoint}', proxy=None) as ws:
            device = VirtualESP32Voice(ws)
            device.hello()
            device.send('record.start')
            old = device.control('record.ready')['session_id']
            ws.socket.shutdown(socket.SHUT_RDWR)
    with loopback(create_app(database_path=database, settings=settings)) as port:
        with connect(f'ws://127.0.0.1:{port}{endpoint}', proxy=None) as ws:
            device = VirtualESP32Voice(ws)
            device.hello()
            device.send('record.start')
            current = device.control('record.ready')['session_id']
            assert current != old
            ws.send(HEADER.pack(UUID(hex=old).bytes, 0) + b'\0\0')
            assert json.loads(ws.recv(timeout=3))['code'] == 'invalid_audio_sequence'
            device.send('cancel', session_id=current)
            assert device.control('cancelled')['session_id'] == current


def test_voice_reconnect_after_partial_upload_and_playback(tmp_path):
    app = create_app(database_path=tmp_path / 'reconnect.sqlite3', settings=Settings(llm_mode='mock'))

    async def transcribe(*args):
        return {'text': '你好', 'elapsed_ms': 0}

    path = '/api/devices/voice/ws?device_id=reconnect'
    pcm = b'\x03\x00' * 8000
    with TestClient(app) as http:
        app.state.speech.transcribe = transcribe
        http.patch('/api/pet/settings', json={'tts_provider': 'mock'}).raise_for_status()
        sessions = []
        for phase in ('upload', 'playback'):
            with http.websocket_connect(path) as ws:
                device = VirtualESP32Voice(TestTransport(ws))
                device.hello()
                device.send('record.start')
                session = device.control('record.ready')['session_id']
                sessions.append(session)
                for seq, offset in enumerate(range(0, len(pcm), 4096)):
                    ws.send_bytes(HEADER.pack(UUID(hex=session).bytes, seq) + pcm[offset:offset + 4096])
                    if phase == 'upload':
                        break
                if phase == 'playback':
                    device.send('record.stop', session_id=session)
                    device.control('thinking')
                    assert device.control('playback.start')['session_id'] == session
                    assert ws.receive_bytes()[:16] == UUID(hex=session).bytes
        with http.websocket_connect(path) as ws:
            device = VirtualESP32Voice(TestTransport(ws))
            device.hello()
            reply, output = device.turn(pcm)
        assert reply['session_id'] not in sessions
        assert len(set(sessions)) == 2
        assert output


def test_transient_device_tts_failure_retries_same_reply_without_duplicate_messages(tmp_path):
    app = create_app(database_path=tmp_path / 'tts-retry.sqlite3', settings=Settings(llm_mode='mock'))
    calls = []

    async def transcribe(*args):
        return {'text': '你好小星', 'elapsed_ms': 0}

    with TestClient(app) as http:
        app.state.speech.transcribe = transcribe
        http.patch('/api/pet/settings', json={'tts_provider': 'mock'}).raise_for_status()
        original = app.state.speech.natural.synthesize

        async def temporary_failure(text, **kwargs):
            calls.append(text)
            if len(calls) == 1:
                raise SpeechError(503, 'tts_network', 'injected transient reset')
            return await original(text, **kwargs)

        app.state.speech.natural.synthesize = temporary_failure
        with http.websocket_connect('/api/devices/voice/ws?device_id=tts-retry') as ws:
            device = VirtualESP32Voice(TestTransport(ws))
            device.hello()
            reply, pcm = device.turn(b'\x03\x00' * 8000)
        assert pcm and len(calls) == 2 and calls[0] == calls[1]
        messages = http.get('/api/conversations/' + reply['conversation_id'] + '/messages').json()
        assert [message['role'] for message in messages] == ['user', 'assistant']
