import asyncio

import pytest

from backend.speech.providers import EdgeTTSProvider, NaturalTTSService
from backend.speech.service import SpeechError, WindowsSAPI
from tests.test_natural_tts import FixtureProvider


def test_edge_disconnect_recovery_and_cache_isolation():
    class Network(FixtureProvider):
        offline = True
        calls = []

        async def generate(self, *args):
            if self.offline:
                raise SpeechError(503, 'tts_network', 'offline')
            return await super().generate(*args)

    async def scenario():
        network = Network()
        service = NaturalTTSService(WindowsSAPI(), providers={'edge': network})
        with pytest.raises(SpeechError):
            await service.synthesize('你好小星。')
        network.offline = False
        first = await service.synthesize('你好小星。')
        network.offline = True
        cached = await service.synthesize('你好小星。')
        assert not first.cache_hit and cached.cache_hit and cached.data == first.data
        assert cached.provider == 'edge' and not cached.fallback
        for change in ({'emotion': 'happy'}, {'voice': 'zh-CN-XiaoxiaoNeural'}, {'sample_rate': 16000}, {'output_format': 'device_pcm'}):
            with pytest.raises(SpeechError):
                await service.synthesize('你好小星。', **change)
        assert service.cache_status()['hits'] == 1

    asyncio.run(scenario())


def test_edge_retries_once_and_recovers(monkeypatch):
    import edge_tts

    class Connection:
        calls = 0
        offline = True

        def __init__(self, *args, **kwargs):
            pass

        async def stream(self):
            Connection.calls += 1
            if Connection.offline or Connection.calls == 3:
                raise ConnectionResetError('injected network reset')
            yield {'type': 'audio', 'data': b'provider payload'}

    monkeypatch.setattr(edge_tts, 'Communicate', Connection)
    async def scenario():
        provider = EdgeTTSProvider()
        parameters = dict(rate_percent=0, pitch_hz=0, volume_percent=0)
        with pytest.raises(SpeechError) as error:
            await provider.generate('网络断开', None, parameters)
        assert error.value.code == 'tts_network' and Connection.calls == 2
        Connection.offline = False
        assert await provider.generate('网络恢复', None, parameters) == b'provider payload'
        assert Connection.calls == 4 and provider.status()['network_verified']

    asyncio.run(scenario())
