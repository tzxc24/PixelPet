"""Replaceable TTS providers. Only reply text is sent to the selected online service."""
import asyncio
import importlib.util
import io
import math
import socket
import struct
import time
import wave
from collections import OrderedDict
from dataclasses import replace
from hashlib import sha256
from typing import Protocol

from backend.speech.service import AudioResult, SpeechError
from backend.speech.text import prepare_text, emotion_parameters
from backend.speech.conversion import convert_audio

PREVIEW_TEXT='你好呀，我是小星！今天也很开心见到你，嘿嘿，要不要陪我聊聊天？'
EDGE_VOICES=[
    {'name':'zh-CN-XiaoyiNeural','label':'晓伊 · 自然可爱女声','provider':'edge','available':True},
    {'name':'zh-CN-XiaoxiaoNeural','label':'晓晓 · 温柔自然女声','provider':'edge','available':True},
    {'name':'zh-CN-XiaomengNeural','label':'晓梦 · 当前 Edge 目录未提供','provider':'edge','available':False,'reason':'当前 Edge 在线音色目录未提供晓梦，不能试听。'},
    {'name':'zh-CN-YunxiNeural','label':'云希 · 年轻自然男声（可用备选）','provider':'edge','available':True},
]


class TTSProvider(Protocol):
    name:str
    async def generate(self,text:str,voice:str | None,parameters:dict)->bytes: ...
    def voices(self)->list[dict]: ...
    def status(self)->dict: ...


class EdgeTTSProvider:
    name='edge'
    def __init__(self):
        self.last_success=None

    def voices(self):return [dict(item) for item in EDGE_VOICES]

    def status(self):
        return {'provider':'edge','ready':importlib.util.find_spec('edge_tts') is not None,'network_required':True,'network_verified':self.last_success is not None,'last_success':self.last_success,'media_type':'audio/wav','source_codec':'mp3','emotion_styles':False}

    async def generate(self,text,voice,parameters):
        voice=voice or 'zh-CN-XiaoyiNeural'
        if voice not in {item['name'] for item in EDGE_VOICES if item['available']}:
            raise SpeechError(422,'voice_unavailable','该音色不在当前 Edge 可用目录中，请选晓伊、晓晓或云希。')
        try:
            import aiohttp
            import edge_tts
        except ImportError:
            raise SpeechError(503,'tts_dependency_missing','在线语音依赖未安装，请安装 requirements.txt 或选择离线 SAPI。') from None
        for attempt in range(2):
            try:
                data=bytearray()
                # A fresh connector belongs to each stream; edge-tts closes its session.
                async with aiohttp.TCPConnector(family=socket.AF_INET) as connector:
                    communication=edge_tts.Communicate(text,voice=voice,rate=f"{parameters['rate_percent']:+d}%",pitch=f"{parameters['pitch_hz']:+d}Hz",volume=f"{parameters['volume_percent']:+d}%",connector=connector,connect_timeout=8,receive_timeout=20)
                    async for chunk in communication.stream():
                        if chunk['type']=='audio':
                            data.extend(chunk['data'])
                            if len(data)>10*1024*1024:
                                raise SpeechError(502,'tts_audio_too_large','生成语音过长，请缩短回复。')
                if not data:raise SpeechError(502,'tts_empty_audio','在线语音返回空音频，请重试。')
                self.last_success=time.time()
                return bytes(data)
            except asyncio.CancelledError:
                raise
            except SpeechError:
                raise
            except (aiohttp.ClientError,asyncio.TimeoutError,OSError):
                if attempt==0:
                    await asyncio.sleep(.4)
                    continue
                raise SpeechError(503,'tts_network','在线声音暂时无法连接，请重试或切换离线 SAPI。') from None
            except Exception:
                raise SpeechError(503,'tts_unavailable','在线声音生成失败，请重试；未使用系统声音冒充此音色。') from None


class SAPIProvider:
    name='sapi'
    def __init__(self,engine):self.engine=engine
    def voices(self):
        return [dict(item,provider='sapi',available=True,label=item.get('name','Windows voice')) for item in self.engine.voices()]
    def status(self):return self.engine.status() if hasattr(self.engine,'status') else {'provider':'sapi','ready':True}
    async def generate(self,text,voice,parameters):
        result=await asyncio.to_thread(self.engine.synthesize,text,voice,round(parameters['rate_percent']/10),100+parameters['volume_percent'])
        return result.data


class MockTTSProvider:
    """Produces a clearly labelled fixture tone, never pretend natural speech."""
    name='mock'
    def voices(self):return [{'name':'mock-tone','label':'Mock 测试提示音（不是人声）','available':True,'provider':'mock'}]
    def status(self):return {'provider':'mock','ready':True,'natural_speech':False}
    async def generate(self,text,voice,parameters):
        output=io.BytesIO()
        with wave.open(output,'wb') as stream:
            stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(24000)
            stream.writeframes(b''.join(struct.pack('<h',int(2000*math.sin(2*math.pi*440*i/24000))) for i in range(6000)))
        return output.getvalue()


class UnconfiguredProvider:
    def status(self):return {'provider':self.name,'ready':False,'configured':False}
    def voices(self):return []
    async def generate(self,*args):
        raise SpeechError(503,'tts_not_configured','该语音服务尚未配置，不会自动启用付费接口。')


class AzureSpeechProvider(UnconfiguredProvider):
    """Reserved adapter slot; no Azure dependency or paid request is enabled."""
    name='azure'


class CustomTTSProvider(UnconfiguredProvider):
    """Reserved server-side adapter slot, never a frontend-controlled remote URL."""
    name='custom'


class NaturalTTSService:
    cache_max_bytes = 12 * 1024 * 1024
    cache_max_entries = 24
    cache_ttl = 300

    def __init__(self,legacy_tts,providers=None,timeout=45):
        self.providers={'edge':EdgeTTSProvider(),'sapi':SAPIProvider(legacy_tts),'mock':MockTTSProvider(),'azure':AzureSpeechProvider(),'custom':CustomTTSProvider()}
        self.providers.update(providers or {})
        self.timeout=timeout
        self._cache = OrderedDict()
        self._cache_bytes = self._cache_hits = self._cache_misses = 0

    def _evict(self, key):
        _, audio = self._cache.pop(key)
        self._cache_bytes -= len(audio.data)

    def _expire_cache(self):
        now = time.monotonic()
        for key, (expires, _) in list(self._cache.items()):
            if expires <= now:
                self._evict(key)

    def cache_status(self):
        self._expire_cache()
        return dict(entries=len(self._cache), bytes=self._cache_bytes,
                    hits=self._cache_hits, misses=self._cache_misses)

    def _cache_result(self, key, result):
        if len(result.data) > self.cache_max_bytes:
            return
        if key in self._cache:
            self._evict(key)
        self._cache[key] = (time.monotonic() + self.cache_ttl, result)
        self._cache_bytes += len(result.data)
        while len(self._cache) > self.cache_max_entries or self._cache_bytes > self.cache_max_bytes:
            self._evict(next(iter(self._cache)))

    def provider(self,name):
        if name not in self.providers:
            raise SpeechError(422,'unknown_tts_provider','不支持的语音服务。')
        return self.providers[name]

    async def voices(self,name='edge'):
        return await asyncio.to_thread(self.provider(name).voices)

    async def synthesize(self,text,provider='edge',voice=None,rate_percent=0,pitch_hz=0,volume_percent=0,emotion='normal',output_format='pc',sample_rate=None,allow_fallback=False):
        try:
            text=prepare_text(text)
            parameters=emotion_parameters(emotion,rate_percent,pitch_hz,volume_percent)
        except ValueError:
            raise SpeechError(422,'invalid_speech_text','没有可朗读的文字，或语音参数无效。') from None
        if provider=='edge':
            voice=voice or 'zh-CN-XiaoyiNeural'
            if voice not in {item['name'] for item in EDGE_VOICES if item['available']}:
                raise SpeechError(422,'voice_unavailable','该音色当前无法使用；晓梦未出现在 Edge 目录中，请选择可用音色。')
        target={'pc':'pc','device_pcm':'device','device_wav':'device_wav'}.get(output_format)
        if target is None:raise SpeechError(422,'invalid_audio_format','不支持的音频格式。')
        selected=self.provider(provider);requested=provider;fallback=False
        cache_key = None
        if provider == 'edge':
            self._expire_cache()
            cache_key = (sha256(text.encode()).digest(), voice, tuple(sorted(parameters.items())), target, sample_rate or 24000)
            if cache_key in self._cache:
                self._cache_hits += 1
                self._cache.move_to_end(cache_key)
                return replace(self._cache[cache_key][1], cache_hit=True)
            self._cache_misses += 1
        if provider=='sapi':parameters={**parameters,'pitch_hz':0}
        try:
            raw=await asyncio.wait_for(selected.generate(text,voice,parameters),self.timeout)
        except (asyncio.TimeoutError,SpeechError) as exc:
            if not allow_fallback or provider!='edge' or isinstance(exc,SpeechError) and exc.status==422:
                if isinstance(exc,SpeechError):raise
                raise SpeechError(504,'tts_timeout','在线语音超时，请重试或选择离线声音。') from None
            provider='sapi';voice=None;fallback=True;parameters={**parameters,'pitch_hz':0}
            try:
                raw=await asyncio.wait_for(self.provider('sapi').generate(text,None,parameters),self.timeout)
            except asyncio.TimeoutError:
                raise SpeechError(504,'tts_timeout','离线语音也未能及时生成，请重试。') from None
        try:
            converted=await asyncio.to_thread(convert_audio,raw,target,sample_rate)
        except ValueError:
            raise SpeechError(502,'invalid_tts_audio','语音解码或格式转换失败，请重试。') from None
        if converted['clipped_ratio']>.02:
            raise SpeechError(502,'tts_clipping','语音存在明显饱和，已停止播放，请降低音量或更换音色。')
        result = AudioResult(**converted,provider=provider,voice=voice or 'system-default',requested_provider=requested,fallback=fallback,**parameters)
        if cache_key is not None and not fallback:
            self._cache_result(cache_key, result)
        return result
