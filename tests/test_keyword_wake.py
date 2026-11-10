import numpy as np
import pytest

from backend.speech.keyword_wake import LocalKeywordWake
from backend.speech.service import SpeechError


class Stream:
    def __init__(self): self.frames=[]
    def accept_waveform(self,rate,samples):
        assert rate==16000
        self.frames.append(samples.copy())


class Detector:
    def __init__(self,keyword=''):
        self.keyword=keyword;self.streams=[]
    def create_stream(self):
        stream=Stream();self.streams.append(stream);return stream
    def is_ready(self,stream): return len(stream.frames)>0
    def decode_stream(self,stream): stream.frames.clear()
    def get_result(self,stream): return self.keyword


def test_keyword_wake_detects_only_configured_terms_and_resets_each_clip():
    detector=Detector('你好小心')
    wake=LocalKeywordWake(engine=detector)
    assert wake.transcribe(np.ones(16000,dtype=np.float32)*.01)['text']=='你好小心'
    wake.transcribe(np.zeros(16000,dtype=np.float32))
    assert len(detector.streams)==2
    detector.keyword='其他对话'
    assert wake.transcribe(np.zeros(16000,dtype=np.float32))['text']==''


def test_missing_keyword_model_fails_locally_without_fallback_or_download(tmp_path):
    wake=LocalKeywordWake(manifest_path=tmp_path/'missing.json')
    assert not wake.status()['ready']
    with pytest.raises(SpeechError) as exc:
        wake.transcribe(np.zeros(16000,dtype=np.float32))
    assert exc.value.code=='wake_model_missing'


@pytest.mark.parametrize('samples',[np.zeros((2,160)),np.array([float('nan')]),np.zeros(320001)])
def test_invalid_keyword_audio_is_rejected(samples):
    with pytest.raises(SpeechError):
        LocalKeywordWake(engine=Detector()).transcribe(samples)


def test_wake_service_cannot_select_cloud_asr_even_when_requested():
    import asyncio
    import io
    import wave
    from backend.core.config import Settings
    from backend.speech.service import SpeechService
    class Forbidden:
        def transcribe(self,*args,**kwargs):raise AssertionError('Standby must not reach cloud or general ASR')
    service=SpeechService(Settings(),asr=Forbidden())
    service.baidu_asr=Forbidden()
    service.wake_detector=LocalKeywordWake(engine=Detector('你好小心'))
    output=io.BytesIO()
    with wave.open(output,'wb') as wav:
        wav.setparams((1,2,16000,0,'NONE','not compressed'));wav.writeframes(b'\0\0'*16000)
    result=asyncio.run(service.transcribe(output.getvalue(),'audio/wav',provider='baidu_asr',wake=True))
    assert result['provider']=='local_keyword_spotter'
    assert result['text']=='你好小心'
