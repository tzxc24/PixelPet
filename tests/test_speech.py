import asyncio
import io
import wave
import os
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.speech.service import SpeechService, SpeechError, AudioResult
from backend.api.audio import router


def wav(seconds=0.1):
    target = io.BytesIO()
    with wave.open(target, 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(b'\0\0' * int(seconds * 16000))
    return target.getvalue()


def run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize('data,mime,code', [(b'', 'audio/wav', 'empty_audio'), (b'x', 'text/plain', 'unsupported_audio'), (b'bad', 'audio/wav', 'invalid_audio'), (b'x' * (10 * 1024 * 1024 + 1), 'audio/wav', 'audio_too_large'), (wav(60.1), 'audio/wav', 'audio_too_long')])
def test_rejects_invalid_audio_before_asr(data, mime, code):
    service = SpeechService(SimpleNamespace())
    with pytest.raises(SpeechError) as error:
        run(service.transcribe(data, mime))
    assert error.value.code == code


def test_real_decode_and_injected_asr_metadata():
    class ASR:
        def transcribe(self, samples):
            assert len(samples) == 1600
            return {'text': '你好', 'language': 'zh'}
    service = SpeechService(SimpleNamespace(), asr=ASR())
    result = run(service.transcribe(wav(), 'audio/wav; codecs=pcm'))
    assert result['text'] == '你好'
    assert result['duration'] == pytest.approx(.1)
    assert result['sample_rate'] == 16000
    assert result['channels'] == 1


def test_missing_model_does_not_fake_transcript(monkeypatch):
    service = SpeechService(SimpleNamespace(asr_model='tiny'))
    monkeypatch.setattr(service.asr, 'transcribe', lambda audio: (_ for _ in ()).throw(SpeechError(503, 'asr_unavailable', 'Model unavailable')))
    with pytest.raises(SpeechError) as error:
        run(service.transcribe(wav(), 'audio/wav'))
    assert error.value.status == 503
    assert service.status()['browser_tts']['requires_browser'] is True


def client(service):
    app = FastAPI()
    app.state.speech = service
    app.include_router(router)
    return TestClient(app)


def test_synthesize_returns_wav_and_metadata():
    class TTS:
        def synthesize(self, text, voice, rate, volume):
            assert text == '你好'
            return AudioResult(wav(), 16000, 1, .1, provider='test')
        def voices(self):
            return [{'name': 'Test'}]
    http = client(SpeechService(SimpleNamespace(), tts=TTS()))
    response = http.post('/api/audio/synthesize', json={'text': '你好'})
    assert response.status_code == 200
    assert response.content[:4] == b'RIFF'
    assert response.headers['content-type'] == 'audio/wav'
    assert response.headers['x-audio-codec'] == 'pcm_s16le'
    assert response.headers['x-audio-sample-rate'] == '16000'
    assert http.get('/api/audio/voices').json() == [{'name': 'Test'}]


def test_api_audio_errors_and_text_validation():
    http = client(SpeechService(SimpleNamespace()))
    assert http.post('/api/audio/transcribe', files={'audio': ('bad.wav', b'', 'audio/wav')}).status_code == 422
    assert http.post('/api/audio/transcribe', files={'audio': ('bad.txt', b'abc', 'text/plain')}).status_code == 415
    for body in [{'text': '   '}, {'text': 'x', 'rate': 11}, {'text': 'x', 'volume': 101}]:
        assert http.post('/api/audio/synthesize', json=body).status_code == 422


def test_silence_no_speech_is_explicit():
    class ASR:
        def transcribe(self, samples):
            return {'text': '', 'language': 'zh'}
    with pytest.raises(SpeechError) as error:
        run(SpeechService(SimpleNamespace(), asr=ASR()).transcribe(wav(), 'audio/wav'))
    assert error.value.code == 'no_speech'


@pytest.mark.skipif(os.name != 'nt', reason='Windows SAPI integration')
def test_windows_sapi_returns_real_decodable_wav():
    service = SpeechService(SimpleNamespace())
    if not service.status()['tts']['ready']:
        pytest.skip('No Windows voice installed')
    audio = run(service.synthesize('Hello PixelPet'))
    with wave.open(io.BytesIO(audio.data)) as stream:
        assert stream.getnframes() > 100
        assert stream.getsampwidth() == 2
        assert stream.getframerate() == audio.sample_rate
        assert stream.getnchannels() == audio.channels

