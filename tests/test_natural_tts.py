"""Natural TTS contracts use generated fixture WAVs; never cloud calls in pytest."""
import asyncio
import io
import wave
from types import SimpleNamespace

import pytest

from backend.speech.providers import NaturalTTSService, MockTTSProvider, EdgeTTSProvider
from backend.speech.service import SpeechError, WindowsSAPI


def wav():
    stream=io.BytesIO()
    with wave.open(stream,'wb') as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(24000);audio.writeframes(b'\0\0'*2400)
    return stream.getvalue()


class FixtureProvider:
    name='edge'
    calls=[]
    async def generate(self,text,voice,parameters):
        self.calls.append((text,voice,parameters));return wav()
    def voices(self):return EdgeTTSProvider().voices()
    def status(self):return {'provider':'edge','ready':True}


@pytest.mark.parametrize('voice',['zh-CN-XiaoyiNeural','zh-CN-XiaoxiaoNeural','zh-CN-YunxiNeural'])
def test_voice_switch_parameters_and_pcm(voice):
    service=NaturalTTSService(WindowsSAPI(),providers={'edge':FixtureProvider()})
    result=asyncio.run(service.synthesize('**你好！** 我是小星。',provider='edge',voice=voice,emotion='happy'))
    assert result.provider=='edge' and result.voice==voice
    assert result.sample_rate==24000 and result.channels==1 and result.codec=='pcm_s16le'
    text,chosen,parameters=FixtureProvider.calls[-1]
    assert '*' not in text and chosen==voice and parameters['rate_percent']==4
    assert parameters['pitch_hz']==0 and parameters['volume_percent']==0


def test_unavailable_voice_not_masqueraded():
    service=NaturalTTSService(WindowsSAPI())
    with pytest.raises(SpeechError) as error:
        asyncio.run(service.synthesize('你好',provider='edge',voice='zh-CN-XiaomengNeural'))
    assert error.value.code=='voice_unavailable'


def test_network_failure_has_explicit_offline_fallback():
    class Broken(FixtureProvider):
        async def generate(self,*args):raise SpeechError(503,'tts_network','test offline')
    class Offline:
        def synthesize(self,*args):
            from backend.speech.service import AudioResult
            return AudioResult(wav(),24000,1,.1)
        def voices(self):return []
    service=NaturalTTSService(Offline(),providers={'edge':Broken()})
    with pytest.raises(SpeechError):asyncio.run(service.synthesize('你好',provider='edge',allow_fallback=False))
    result=asyncio.run(service.synthesize('你好',provider='edge',allow_fallback=True))
    assert result.provider=='sapi' and result.fallback is True and result.requested_provider=='edge'


def test_mock_generates_valid_audio_and_device_format():
    service=NaturalTTSService(WindowsSAPI())
    result=asyncio.run(service.synthesize('测试',provider='mock',output_format='device_pcm',sample_rate=16000))
    assert result.media_type=='application/octet-stream' and result.sample_rate==16000
    assert result.channels==1 and len(result.data)>100 and not result.data.startswith(b'RIFF')


def test_provider_cancellation_propagates():
    class Waiting(FixtureProvider):
        async def generate(self,*args):await asyncio.sleep(30)
    async def scenario():
        service=NaturalTTSService(WindowsSAPI(),providers={'edge':Waiting()})
        task=asyncio.create_task(service.synthesize('取消',provider='edge'))
        await asyncio.sleep(.01);task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
    asyncio.run(scenario())


def test_fallback_timeout_is_a_friendly_error():
    class Broken(FixtureProvider):
        async def generate(self,*args):raise SpeechError(503,'tts_network','offline')
    class Waiting(FixtureProvider):
        async def generate(self,*args):await asyncio.sleep(30)
    service=NaturalTTSService(WindowsSAPI(),providers={'edge':Broken(),'sapi':Waiting()},timeout=.01)
    with pytest.raises(SpeechError) as error:
        asyncio.run(service.synthesize('你好',allow_fallback=True))
    assert error.value.status==504 and error.value.code=='tts_timeout'
