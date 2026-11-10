from fastapi.testclient import TestClient

from backend.core.config import Settings
from backend.main import create_app
from scripts.virtual_esp32_voice import VirtualESP32Voice
from tests.test_virtual_voice import TestTransport


def test_each_voice_turn_is_history_and_explicit_fact_is_long_term_memory(tmp_path):
    path=tmp_path/'voice-memory.sqlite3'
    app=create_app(database_path=path,settings=Settings(llm_mode='mock'))
    phrases=iter(['请记住，我喜欢画水彩画。','你好，小星。'])
    async def transcribe(*args, **kwargs):
        return {'text':next(phrases),'elapsed_ms':1}
    with TestClient(app) as http:
        app.state.speech.transcribe=transcribe
        http.patch('/api/pet/settings',json={'tts_provider':'mock'}).raise_for_status()
        with http.websocket_connect('/api/devices/voice/ws?device_id=voice-memory') as ws:
            device=VirtualESP32Voice(TestTransport(ws));device.hello()
            first,_=device.turn(b'\x03\x00'*1600)
            device.turn(b'\x03\x00'*1600,first['conversation_id'])
        cid=first['conversation_id']
        assert len(http.get('/api/conversations/'+cid+'/messages').json())==4
        assert '水彩画' in http.get('/api/memories').text
    restarted=create_app(database_path=path,settings=Settings(llm_mode='mock'))
    with TestClient(restarted) as http:
        assert len(http.get('/api/conversations/'+cid+'/messages').json())==4
        assert '水彩画' in http.get('/api/memories').text
