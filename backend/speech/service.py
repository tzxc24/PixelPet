"""Bounded in-memory audio decoding, optional CPU ASR, and Windows WAV TTS."""
import asyncio
import base64
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
import wave
from dataclasses import dataclass
from typing import Protocol

ROOT = Path(__file__).resolve().parents[2]
MAX_BYTES = 10 * 1024 * 1024
MAX_SECONDS = 60
ALLOWED_TYPES = {'audio/wav', 'audio/x-wav', 'audio/wave', 'audio/webm', 'audio/ogg', 'audio/mp4', 'audio/mpeg', 'audio/flac', 'audio/x-flac'}


class SpeechError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


@dataclass
class AudioResult:
    data: bytes
    sample_rate: int
    channels: int
    duration: float
    provider: str = 'sapi'
    codec: str = 'pcm_s16le'
    media_type: str = 'audio/wav'
    voice: str = ''
    rate_percent: int = 0
    pitch_hz: int = 0
    volume_percent: int = 0
    requested_provider: str = ''
    fallback: bool = False
    peak: float = 0
    clipped_ratio: float = 0
    cache_hit: bool = False


class ASRProvider(Protocol):
    def transcribe(self, samples) -> dict: ...


class TTSProvider(Protocol):
    def synthesize(self, text: str, voice: str | None, rate: int | None, volume: int | None) -> AudioResult: ...
    def voices(self) -> list[dict]: ...


class LocalWhisper:
    """Load only on first transcription; all model files live beneath project tmp."""
    name = 'local_whisper'

    def __init__(self, settings, *, model_name=None, beam_size=5):
        self.model_name = model_name or getattr(settings, 'asr_model', 'tiny')
        self.beam_size = beam_size
        if self.model_name not in {'tiny', 'base', 'small', 'medium', 'large-v3', 'tiny.en', 'base.en', 'small.en'}:
            raise ValueError('Unsupported ASR model name')
        self.model_dir = ROOT / 'tmp' / 'models' / ('faster-whisper-' + self.model_name)
        self.allow_download = getattr(settings, 'asr_model_download', False)
        self.model = None
        self.lock = threading.Lock()

    def status(self):
        installed = importlib.util.find_spec('faster_whisper') is not None
        downloaded = (self.model_dir / 'model.bin').is_file()
        return {'provider': self.name, 'ready': installed and (downloaded or self.model is not None), 'installed': installed, 'model': self.model_name, 'model_downloaded': downloaded, 'download_enabled': self.allow_download, 'loaded': self.model is not None, 'device': 'cpu', 'compute_type': 'int8', 'message': 'Ready for lazy CPU loading' if installed and downloaded else 'Install faster-whisper and download the model; text chat remains available.'}

    def transcribe(self, samples, *, wake=False):
        with self.lock:
            try:
                if self.model is None:
                    from faster_whisper import WhisperModel
                    if (self.model_dir / 'model.bin').is_file():
                        model_path = str(self.model_dir)
                    elif self.allow_download:
                        from faster_whisper.utils import download_model
                        self.model_dir.mkdir(parents=True, exist_ok=True)
                        model_path = download_model(self.model_name, output_dir=str(self.model_dir), cache_dir=str(ROOT / 'tmp' / 'models' / 'hub'))
                    else:
                        raise SpeechError(503, 'asr_model_missing', 'ASR model not downloaded. Enable ASR_MODEL_DOWNLOAD for the first local model download; use text chat meanwhile.')
                    self.model = WhisperModel(model_path, device='cpu', compute_type='int8', cpu_threads=min(os.cpu_count() or 2, 4), num_workers=1)
                hints={'hotwords':'你好小星 小星小星'} if wake else {}
                # The physical wake clip is already endpointed by ESP-SR. A
                # second Silero gate can discard a short, quiet proper name.
                segments, info = self.model.transcribe(samples, beam_size=self.beam_size, vad_filter=not wake, condition_on_previous_text=False, language='zh', **hints)
                words=[]
                evidence=[]
                min_logprob = None
                for segment in segments:
                    if self.beam_size != 5:
                        score = segment.avg_logprob
                        min_logprob = score if min_logprob is None else min(min_logprob, score)
                    if wake:
                        evidence.append({'logprob':round(segment.avg_logprob,3),'no_speech':round(segment.no_speech_prob,3)})
                    # Proper names can have a low token score even in real
                    # speech. Reject jointly uncertain non-speech, then let the
                    # strict command matcher decide; neither score alone is a wake.
                    if wake and segment.avg_logprob < -.9 and segment.no_speech_prob > .6:
                        continue
                    words.append(segment.text)
                if wake:
                    self.last_wake_diagnostic={'segments':evidence,'accepted_segments':len(words)}
                result = {'text': ''.join(words).strip(), 'language': info.language}
                if min_logprob is not None:
                    result['min_logprob'] = min_logprob
                return result
            except SpeechError:
                raise
            except Exception:
                raise SpeechError(503, 'asr_unavailable', 'Local ASR could not load or transcribe. Check faster-whisper installation, model download and CPU support; use text chat meanwhile.') from None


class WindowsSAPI:
    name = 'sapi'

    def __init__(self, timeout=120):
        self.timeout = timeout
        self.executable = shutil.which('powershell.exe') if os.name == 'nt' else None
        self._voices = None
        self._voice_check = 0

    def _invoke(self, payload):
        if not self.executable:
            raise SpeechError(503, 'tts_unavailable', 'Windows PowerShell and System.Speech are required for backend WAV synthesis. Browser speechSynthesis is a separate option.')
        try:
            result = subprocess.run([self.executable, '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(ROOT / 'scripts' / 'sapi_synthesize.ps1')], input=json.dumps(payload, ensure_ascii=True).encode('ascii'), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=self.timeout, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), cwd=ROOT)
            if result.returncode:
                raise SpeechError(503, 'tts_unavailable', 'Windows SAPI synthesis unavailable; check installed Windows voices.')
            return json.loads(result.stdout.decode('utf-8-sig'))
        except subprocess.TimeoutExpired:
            raise SpeechError(504, 'tts_timeout', 'Windows speech synthesis timed out.') from None
        except (OSError, ValueError):
            raise SpeechError(503, 'tts_unavailable', 'Windows speech process could not return valid audio.') from None

    def voices(self):
        if self._voices is None or time.monotonic() - self._voice_check > 60:
            self._voices = self._invoke({'mode': 'voices'})
            self._voice_check = time.monotonic()
        return self._voices

    def status(self):
        try:
            voices = self.voices()
            return {'provider': self.name, 'ready': bool(voices), 'voices': len(voices), 'media_type': 'audio/wav', 'codec': 'pcm_s16le', 'message': 'Windows SAPI voices detected' if voices else 'No Windows SAPI voices installed'}
        except SpeechError as exc:
            return {'provider': self.name, 'ready': False, 'message': exc.message}

    def synthesize(self, text, voice=None, rate=None, volume=None):
        if voice and voice not in {item['name'] for item in self.voices()}:
            raise SpeechError(422, 'unknown_voice', 'Requested Windows voice is not installed.')
        output = self._invoke({'mode': 'synthesize', 'text': text, 'voice': voice, 'rate': rate if rate is not None else 0, 'volume': volume if volume is not None else 80})
        try:
            data = base64.b64decode(output['audio'], validate=True)
            with wave.open(io.BytesIO(data)) as stream:
                if stream.getsampwidth() != 2 or stream.getnframes() == 0:
                    raise ValueError('invalid PCM')
                return AudioResult(data, stream.getframerate(), stream.getnchannels(), stream.getnframes() / stream.getframerate())
        except (KeyError, ValueError, wave.Error):
            raise SpeechError(503, 'invalid_tts_audio', 'Windows speech engine returned invalid WAV audio.') from None


def decode_audio(data):
    try:
        import av
        import numpy as np
    except ImportError:
        raise SpeechError(503, 'decoder_unavailable', 'Install faster-whisper (including PyAV) for local audio decoding.') from None
    try:
        frames, count = [], 0
        with av.open(io.BytesIO(data)) as container:
            if not container.streams.audio:
                raise ValueError('no audio stream')
            stream = container.streams.audio[0]
            resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)
            for frame in container.decode(stream):
                for converted in resampler.resample(frame):
                    count += converted.samples
                    if count > MAX_SECONDS * 16000:
                        raise SpeechError(422, 'audio_too_long', 'Audio must be at most 60 seconds.')
                    frames.append(converted.to_ndarray().reshape(-1))
            for converted in resampler.resample(None):
                count += converted.samples
                if count > MAX_SECONDS * 16000:
                    raise SpeechError(422, 'audio_too_long', 'Audio must be at most 60 seconds.')
                frames.append(converted.to_ndarray().reshape(-1))
        if count == 0:
            raise ValueError('empty stream')
        return np.concatenate(frames).astype(np.float32) / 32768.0, count / 16000
    except SpeechError:
        raise
    except Exception:
        raise SpeechError(422, 'invalid_audio', 'Audio could not be decoded into playable samples.') from None


class SpeechService:
    def __init__(self, settings, asr: ASRProvider | None = None, tts: TTSProvider | None = None):
        self.asr = asr if asr is not None else LocalWhisper(settings)
        self.fast_asr = None
        if asr is None and getattr(settings, 'device_fast_asr', False) and self.asr.model_name != 'tiny':
            self.fast_asr = LocalWhisper(settings, model_name='tiny', beam_size=3)
        from backend.speech.baidu_asr import BaiduASR
        self.baidu_asr = BaiduASR(settings)
        from backend.speech.keyword_wake import LocalKeywordWake
        self.wake_detector = LocalKeywordWake()
        self.preferences = None
        self.timeout = getattr(settings, 'speech_timeout', 120)
        self.tts = tts if tts is not None else WindowsSAPI(self.timeout)
        from backend.speech.providers import NaturalTTSService
        self.device_local_tts = getattr(settings, 'device_local_tts', False)
        providers = {}
        if self.device_local_tts:
            from backend.speech.local_matcha import LocalMatchaTTS
            providers['local_matcha'] = LocalMatchaTTS()
        self.natural=NaturalTTSService(self.tts,providers=providers,timeout=min(self.timeout,45))
        self._asr_busy = False
        self.request_metrics = dict(asr_failures=0, tts_failures=0, asr_last_ms=None, tts_last_ms=None)

    def selected_asr(self, provider=None):
        if provider is None and self.preferences is not None:
            provider = self.preferences.get().asr_provider
        if provider == 'disabled':
            raise SpeechError(503, 'asr_disabled', '语音识别已关闭。')
        return self.baidu_asr if provider == 'baidu_asr' else self.asr

    def status(self):
        try:
            selected = self.selected_asr()
            asr = selected.status() if hasattr(selected, 'status') else {'provider': 'injected', 'ready': True}
        except SpeechError:
            asr = {'provider': 'disabled', 'ready': False}
        return {'asr': asr, 'wake':self.wake_detector.status(), 'tts': self.tts.status() if hasattr(self.tts, 'status') else {'provider': 'injected', 'ready': True}, 'browser_tts': {'requires_browser': True, 'server_audio': False, 'message': 'Browser must detect speechSynthesis and available voices.'}, 'max_bytes': MAX_BYTES, 'max_duration_seconds': MAX_SECONDS, 'timeout_seconds': self.timeout, 'recordings_retained': False}

    async def transcribe_device(self, data, content_type):
        if self.fast_asr is not None:
            return await self.transcribe(data, content_type, fast=True)
        return await self.transcribe(data, content_type)

    def _fast_result(self, samples):
        try:
            result = self.fast_asr.transcribe(samples)
        except SpeechError:
            return None
        score = result.pop('min_logprob', float('-inf'))
        if result['text'].strip() and score >= -.65:
            return result
        return None

    async def transcribe(self, data, content_type, *, provider=None, wake=False, fast=False):
        if len(data) > MAX_BYTES:
            raise SpeechError(413, 'audio_too_large', 'Audio upload exceeds 10 MB.')
        if not data:
            raise SpeechError(422, 'empty_audio', 'Audio recording is empty.')
        if (content_type or '').split(';')[0].strip().lower() not in ALLOWED_TYPES:
            raise SpeechError(415, 'unsupported_audio', 'Unsupported audio media type.')
        if self._asr_busy:
            raise SpeechError(409, 'asr_busy', 'A recording is already being transcribed.')
        selected = self.wake_detector if wake else self.selected_asr(provider)
        self._asr_busy = True
        started = time.monotonic()
        def work():
            try:
                samples, duration = decode_audio(data)
                engine = selected
                result = self._fast_result(samples) if fast and self.fast_asr is not None and selected is self.asr and not wake else None
                if result is not None:
                    engine = self.fast_asr
                else:
                    result = selected.transcribe(samples, wake=True) if wake and isinstance(selected,LocalWhisper) else selected.transcribe(samples)
                if not result['text'].strip():
                    raise SpeechError(422, 'no_speech', 'No speech was recognized. Try again or use text chat.')
                return {**result, 'duration': round(duration, 4), 'provider': getattr(engine, 'name', 'injected'), 'model': getattr(engine, 'model_name', None), 'sample_rate': 16000, 'channels': 1, 'codec': 'pcm_f32le', 'input_media_type': content_type, 'input_size_bytes': len(data), 'elapsed_ms': round((time.monotonic() - started) * 1000)}
            finally:
                # A timeout cannot cancel native CPU inference; keep admission closed until it exits.
                self._asr_busy = False
        try:
            return await asyncio.wait_for(asyncio.to_thread(work), self.timeout)
        except asyncio.TimeoutError:
            raise SpeechError(504, 'asr_timeout', 'Local transcription timed out; use text chat or a smaller model.') from None

    async def warm_device_tts(self):
        if self.device_local_tts:
            try:
                await asyncio.to_thread(self.natural.provider('local_matcha').warmup)
            except SpeechError:
                self.device_local_tts = False

    async def synthesize_device(self, text, **options):
        if (self.device_local_tts and options.get('provider') == 'edge'
                and options.get('voice') in (None, 'zh-CN-XiaoyiNeural')
                and not options.get('pitch_hz')):
            try:
                return await self.natural.synthesize(text, **(options | {'provider': 'local_matcha', 'voice': 'matcha-zh-baker'}))
            except SpeechError:
                pass  # Keep the configured Edge voice as the fallback.
        return await self.natural.synthesize(text, **options)

    async def synthesize(self, text, voice=None, rate=None, volume=None):
        if not text.strip() or len(text) > 2000 or rate is not None and not -10 <= rate <= 10 or volume is not None and not 0 <= volume <= 100:
            raise SpeechError(422, 'invalid_speech_request', 'Text, rate or volume is outside supported limits.')
        return await asyncio.to_thread(self.tts.synthesize, text.strip(), voice, rate, volume)

    async def voices(self):
        return await asyncio.to_thread(self.tts.voices)
