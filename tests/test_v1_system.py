"""Voice API, real SQLite restart, and mock model/TTS through normal HTTP routes."""
import io
import json
import wave

from fastapi.testclient import TestClient
import pytest

from backend.core.config import Settings
from backend.main import create_app
from tests.test_speech import wav


@pytest.mark.parametrize(('statement', 'question'), [
    ('请记住：我正在开发 ESP32 AI 桌宠 PixelPet。', '你还记得我在做什么吗？'),
    ('請記住：我正在開發 ESP32 AI 桌寵 PixelPet。', '你還記得我在做什麼嗎？'),
])
def test_mock_voice_turn_recalls_memory_after_restart(tmp_path, statement, question):
    database = tmp_path / 'system.sqlite3'
    settings = Settings(llm_mode='mock')
    with TestClient(create_app(database_path=database, settings=settings)) as client:
        saved = client.post('/api/chat', json={'message': statement})
        assert saved.status_code == 200
        earlier_id = saved.json()['conversation_id']

    class FixtureASR:
        def transcribe(self, samples):
            assert len(samples) == 1600
            return {'text': question, 'language': 'zh'}

    app = create_app(database_path=database, settings=settings)
    with TestClient(app) as client:
        app.state.speech.asr = FixtureASR()
        audio = client.post('/api/audio/transcribe', files={'audio': ('input.wav', wav(), 'audio/wav')})
        assert audio.status_code == 200
        response = client.post('/api/chat/stream', json={'message': audio.json()['text']})
        assert response.status_code == 200
        blocks = response.text.strip().split('\n\n')
        assert any(block.startswith('event: delta\n') for block in blocks)
        assert blocks[-1].startswith('event: done\n')
        reply = json.loads(blocks[-1].split('\ndata: ', 1)[1])
        assert reply['mode'] == 'mock' and reply['conversation_id'] != earlier_id
        assert 'PixelPet' in reply['reply'] and reply['emotion'] == 'curious'
        speech = client.post('/api/audio/synthesize', json={'text': reply['reply'], 'provider': 'mock', 'emotion': reply['emotion']})
        assert speech.status_code == 200 and speech.headers['x-audio-provider'] == 'mock'
        with wave.open(io.BytesIO(speech.content), 'rb') as generated:
            assert generated.getframerate() == 24000 and generated.getnframes() > 0
        assert client.post('/api/audio/transcribe', files={'audio': ('empty.wav', b'', 'audio/wav')}).status_code == 422
        assert client.post('/api/audio/synthesize', json={'text': '测试', 'provider': 'edge', 'voice': 'invalid'}).status_code == 422
        metrics = client.get('/api/diagnostics').json()
        assert metrics['audio_requests']['asr_failures'] == 1
        assert metrics['audio_requests']['tts_failures'] == 1
        assert metrics['llm']['timings']['llm_total_ms'] >= 0


def test_traditional_sensitive_voice_statement_is_not_remembered(tmp_path):
    settings = Settings(llm_mode='mock')
    with TestClient(create_app(database_path=tmp_path / 'sensitive.sqlite3', settings=settings)) as client:
        assert client.post('/api/chat', json={'message': '請記住：我的驗證碼是 123456。'}).status_code == 200
        assert client.get('/api/memories').json() == []
