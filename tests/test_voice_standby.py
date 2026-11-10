from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from backend.core.config import Settings
from backend.main import create_app
from backend.speech.commands import is_rest_command, is_wake_command, assistant_rest_commitment
from scripts.virtual_esp32_voice import HEADER, VirtualESP32Voice
from tests.test_virtual_voice import TestTransport


@pytest.mark.parametrize('text', ['休息吧', '小星，休息吧。', '小心休息吧', '小星你先休息吧',
    '小型休息吧！', '小心休息吧，学校这么讲道理的呢？'])
def test_rest_commands(text):
    assert is_rest_command(text)


@pytest.mark.parametrize('text', ['你好小星！', '你好，小心。', '你好小新', '你好小辛', '小星小星'])
def test_wake_commands(text):
    assert is_wake_command(text)


@pytest.mark.parametrize('text', ['为什么要说休息吧', '我想知道你好小星的意思', '你好', '我想休息吧', '小心地走路',
    '如果我说小心休息吧，你会做什么', '不要休息吧', '他说小型休息吧是什么意思'])
def test_discussion_is_not_a_device_command(text):
    assert not is_rest_command(text)
    assert not is_wake_command(text)


@pytest.mark.parametrize('text', ['好，那我先睡一小会儿，你也别太累啦～','好，我乖乖休息～','我先休息啦。'])
def test_assistant_rest_promises_require_device_standby(text):
    assert assistant_rest_commitment(text)


@pytest.mark.parametrize('text', ['我不休息，陪你聊。','你先休息吧。','我先休息可以吗？','故事里他说我先休息。'])
def test_non_promises_are_not_sleep_actions(text):
    assert not assistant_rest_commitment(text)


@pytest.mark.parametrize('structured', [True, False])
def test_model_rest_agreement_executes_standby(tmp_path, structured):
    import json
    app=create_app(database_path=tmp_path/'promise.sqlite3',settings=Settings(llm_mode='mock'))
    async def transcribe(*args, **kwargs):
        return {'text':'你先歇着，我晚点找你。','elapsed_ms':1}
    async def answer(*args):
        result={'reply':'好，那我先睡一小会儿，你也别太累啦～','emotion':'sleepy','action':'sleep','memories':[]}
        if structured:result['dialog_state']='standby'
        return json.dumps(result)
    with TestClient(app) as http:
        app.state.speech.transcribe=transcribe
        app.state.provider.complete=answer
        http.patch('/api/pet/settings',json={'tts_provider':'mock'}).raise_for_status()
        with http.websocket_connect('/api/devices/voice/ws?device_id=promise-test') as ws:
            d=VirtualESP32Voice(TestTransport(ws));d.hello();upload(d,ws)
            assert d.control('dialog.state')['dialog_state']=='standby'
            start=d.control('playback.start')
            assert start['dialog_state']=='standby'
            drain(ws,start)


def upload(device, ws, purpose='conversation', conversation=None):
    device.send('record.start', purpose=purpose, **({'conversation_id': conversation} if conversation else {}))
    sid = device.control('record.ready')['session_id']
    ws.send_bytes(HEADER.pack(UUID(hex=sid).bytes, 0) + b'\x03\x00' * 1600)
    device.send('record.stop', session_id=sid)
    device.control('thinking')
    return sid


def drain(ws, start):
    size = 0
    while True:
        packet = ws.receive()
        if 'bytes' in packet:
            size += len(packet['bytes']) - HEADER.size
        else:
            import json
            assert json.loads(packet['text'])['type'] == 'playback.end'
            assert size == start['byte_count']
            return


def test_standby_forces_local_asr_and_discards_non_wake_text(tmp_path):
    app = create_app(database_path=tmp_path/'wake.sqlite3', settings=Settings(llm_mode='mock'))
    calls = []
    async def transcribe(data, media, *, provider=None, wake=False):
        calls.append(provider)
        assert wake
        return {'text': '今天的天气很好', 'elapsed_ms': 1}
    with TestClient(app) as http:
        app.state.speech.transcribe = transcribe
        http.patch('/api/pet/settings', json={'asr_provider': 'baidu_asr'}).raise_for_status()
        with http.websocket_connect('/api/devices/voice/ws?device_id=wake-test') as ws:
            device = VirtualESP32Voice(TestTransport(ws)); device.hello()
            sid = upload(device, ws, 'wake')
            assert device.control('wake.result') == {'type': 'wake.result', 'session_id': sid, 'dialog_state': 'standby'}
        assert calls == ['local_keyword_spotter']
        assert http.get('/api/conversations').json() == []


def test_rest_and_wake_keep_conversation_without_llm(tmp_path):
    app = create_app(database_path=tmp_path/'commands.sqlite3', settings=Settings(llm_mode='mock'))
    phrases = iter(['小星休息吧', '你好小星'])
    calls = []
    async def transcribe(data, media, *, provider=None, wake=False):
        calls.append(provider)
        assert wake == (provider == 'local_keyword_spotter')
        return {'text': next(phrases), 'elapsed_ms': 1}
    async def reject(*args, **kwargs):
        raise AssertionError('Control commands must not call LLM')
    with TestClient(app) as http:
        app.state.speech.transcribe = transcribe
        app.state.provider.complete = reject
        http.patch('/api/pet/settings', json={'tts_provider':'mock'}).raise_for_status()
        with http.websocket_connect('/api/devices/voice/ws?device_id=commands-test') as ws:
            device = VirtualESP32Voice(TestTransport(ws)); device.hello()
            upload(device, ws)
            state = device.control('dialog.state'); assert state['dialog_state'] == 'standby'
            start = device.control('playback.start'); assert start['dialog_state'] == 'standby'
            cid = start['conversation_id']; drain(ws, start)
            upload(device, ws, 'wake', cid)
            assert device.control('dialog.state')['dialog_state'] == 'active'
            start = device.control('playback.start'); assert start['conversation_id'] == cid
            drain(ws, start)
        assert calls == [None, 'local_keyword_spotter']
        assert len(http.get('/api/conversations/'+cid+'/messages').json()) == 2
