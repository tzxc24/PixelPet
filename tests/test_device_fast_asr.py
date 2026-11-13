import asyncio

import pytest

from backend.core.config import Settings
from backend.speech.service import SpeechService
from scripts.virtual_esp32_voice import pcm16_wav


@pytest.mark.parametrize('score, expected, base_calls', [
    (-.3, 'quick', 0), (-.9, 'checked', 1), (None, 'checked', 1),
])
def test_device_uses_tiny_only_when_transcript_is_confident(score, expected, base_calls):
    class Engine:
        def __init__(self, text, score=None):
            self.text, self.score, self.calls = text, score, 0

        def transcribe(self, samples):
            self.calls += 1
            result = {'text': self.text, 'language': 'zh'}
            if self.score is not None:
                result['min_logprob'] = self.score
            return result

    primary = Engine('checked')
    tiny = Engine('quick', score)
    service = SpeechService(Settings(), asr=primary)
    service.fast_asr = tiny
    audio = pcm16_wav(b'\x01\x00' * 8000, 16000)
    result = asyncio.run(service.transcribe_device(audio, 'audio/wav'))
    assert result['text'] == expected and 'min_logprob' not in result
    assert tiny.calls == 1 and primary.calls == base_calls


@pytest.mark.parametrize('local_fails, voice, pitch, expected', [
    (False, 'zh-CN-XiaoyiNeural', 0, ['local_matcha']),
    (True, 'zh-CN-XiaoyiNeural', 0, ['local_matcha', 'edge']),
    (False, 'zh-CN-YunxiNeural', 0, ['edge']),
    (False, 'zh-CN-XiaoyiNeural', 3, ['edge']),
])
def test_device_offline_synthesis_falls_back_and_respects_custom_voice(local_fails, voice, pitch, expected):
    from backend.speech.service import SpeechError

    service = SpeechService(Settings())
    service.device_local_tts = True
    calls = []

    async def synthesize(text, *, provider, **options):
        calls.append(provider)
        if provider == 'local_matcha' and local_fails:
            raise SpeechError(503, 'tts_local_unavailable', 'fixture')
        return provider

    service.natural.synthesize = synthesize
    result = asyncio.run(service.synthesize_device('你好', provider='edge', voice=voice, pitch_hz=pitch))
    assert calls == expected
    assert result == expected[-1]
