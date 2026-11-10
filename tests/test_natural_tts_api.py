"""Natural voice endpoint metadata, persistence and strict preview behavior."""
import asyncio
from fastapi.testclient import TestClient
import pytest
from backend.core.config import Settings
from backend.main import create_app
from backend.speech.service import SpeechError
from tests.test_natural_tts import FixtureProvider


def test_default_voice_and_persisted_switch(tmp_path):
    path=tmp_path/'voice.db'
    for iteration in range(2):
        app=create_app(database_path=path,settings=Settings(llm_mode='mock'))
        with TestClient(app) as client:
            app.state.speech.natural.providers['edge']=FixtureProvider()
            prefs=client.get('/api/pet/settings').json()
            assert prefs['tts_provider']=='edge'
            if iteration==0:
                assert prefs['voice']=='zh-CN-XiaoyiNeural' and prefs['pitch_hz']==0
                assert prefs['rate']==1 and prefs['volume']==1
                assert client.patch('/api/pet/settings',json={'voice':'zh-CN-XiaoxiaoNeural','rate':1.05,'volume':.8}).status_code==200
            else:assert prefs['voice']=='zh-CN-XiaoxiaoNeural' and prefs['rate']==1.05
            saved=client.post('/api/audio/synthesize',json={'text':'使用已保存的声音'})
            assert saved.headers['x-audio-voice']=='zh-CN-XiaoxiaoNeural'
            assert saved.headers['x-audio-rate-percent']=='5' and saved.headers['x-audio-volume-percent']=='-20'
            result=client.post('/api/audio/synthesize',json={'text':'你好！','provider':'edge','voice':'zh-CN-XiaoxiaoNeural','rate_percent':5,'volume_percent':-20})
            assert result.status_code==200,result.text
            assert result.headers['x-audio-voice']=='zh-CN-XiaoxiaoNeural'
            assert result.headers['x-audio-rate-percent']=='5' and result.headers['x-audio-volume-percent']=='-20'
            assert result.headers['x-audio-sample-rate']=='24000' and result.headers['x-audio-channels']=='1'
            assert result.headers['x-audio-fallback']=='none'
            device=client.post('/api/audio/synthesize',json={'text':'你好！','provider':'mock','output_format':'device_pcm','sample_rate':16000})
            assert device.status_code==200 and device.headers['content-type']=='application/octet-stream'
            assert device.headers['x-audio-codec']=='pcm_s16le'
            assert client.get('/voice-test').status_code==200
            assert 'zh-CN-XiaomengNeural' in str(client.get('/api/audio/voices?provider=edge').json())


def test_strict_preview_failure_does_not_masquerade(tmp_path):
    class Broken(FixtureProvider):
        async def generate(self,*args):raise SpeechError(503,'tts_network','在线声音暂时不可用')
    app=create_app(database_path=tmp_path/'error.db',settings=Settings(llm_mode='mock'))
    with TestClient(app) as client:
        app.state.speech.natural.providers['edge']=Broken()
        response=client.post('/api/audio/synthesize',json={'text':'试听','provider':'edge','allow_fallback':False})
        assert response.status_code==503 and response.json()['detail']['code']=='tts_network'
        app.state.speech.natural.providers['edge']=FixtureProvider()
        assert client.post('/api/audio/synthesize',json={'text':'重试','provider':'edge'}).status_code==200


def test_disconnected_client_cancels_generation():
    from backend.api.audio import generate_until_disconnect
    from fastapi import HTTPException
    class Disconnected:
        async def is_disconnected(self):return True
    async def scenario():
        cancelled=asyncio.Event()
        async def waiting():
            try:await asyncio.sleep(30)
            finally:cancelled.set()
        with pytest.raises(HTTPException) as error:
            await generate_until_disconnect(Disconnected(),waiting())
        assert error.value.status_code==499 and cancelled.is_set()
    asyncio.run(scenario())
