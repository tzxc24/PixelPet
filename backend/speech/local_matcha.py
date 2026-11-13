"""Server-local Chinese synthesis for the ESP32 fast voice path."""
import asyncio
import io
import threading
import wave

import numpy as np

from backend.core.config import ROOT
from backend.speech.service import SpeechError


class LocalMatchaTTS:
    name = 'local_matcha'
    filenames = ('model-steps-3.onnx', 'vocos-22khz-univ.onnx', 'tokens.txt',
                 'lexicon.txt', 'phone.fst', 'date.fst', 'number.fst')

    def __init__(self, directory=None):
        self.directory = directory or ROOT / 'tmp/models/matcha-icefall-zh-baker'
        self._engine = None
        self._lock = threading.Lock()

    def voices(self):
        return [{'name': 'matcha-zh-baker', 'label': '离线中文女声',
                 'provider': self.name, 'available': self.status()['ready']}]

    def status(self):
        return {'provider': self.name, 'ready': self._engine is not None,
                'network_required': False}

    def warmup(self):
        with self._lock:
            if self._engine is not None:
                return
            try:
                import sherpa_onnx
                files = {name: str(self.directory / name) for name in self.filenames}
                if not all((self.directory / name).is_file() for name in files):
                    raise ValueError('Missing Matcha model files')
                matcha = sherpa_onnx.OfflineTtsMatchaModelConfig(
                    acoustic_model=files['model-steps-3.onnx'],
                    vocoder=files['vocos-22khz-univ.onnx'],
                    tokens=files['tokens.txt'], lexicon=files['lexicon.txt'])
                config = sherpa_onnx.OfflineTtsConfig(
                    model=sherpa_onnx.OfflineTtsModelConfig(
                        matcha=matcha, num_threads=1, provider='cpu'),
                    rule_fsts=','.join(files[name] for name in self.filenames[-3:]),
                    max_num_sentences=2)
                if not config.validate():
                    raise ValueError('Invalid Matcha configuration')
                self._engine = sherpa_onnx.OfflineTts(config)
            except (ImportError, OSError, RuntimeError, ValueError) as exc:
                raise SpeechError(503, 'tts_local_unavailable', '离线中文语音未就绪。') from exc

    def _generate(self, text, parameters):
        self.warmup()
        speed = 1 + parameters['rate_percent'] / 100
        try:
            with self._lock:
                audio = self._engine.generate(text, sid=0, speed=speed)
            samples = np.asarray(audio.samples, dtype=np.float32)
            if samples.ndim != 1 or not 0 < samples.size <= audio.sample_rate * 120 or not np.isfinite(samples).all():
                raise ValueError('Invalid Matcha audio')
            peak = float(np.max(np.abs(samples)))
            if peak == 0:
                raise ValueError('Silent Matcha audio')
            gain = min(1.0, .95 / peak) * (100 + parameters['volume_percent']) / 100
            pcm = np.rint(samples * (32767 * gain)).astype('<i2').tobytes()
            output = io.BytesIO()
            with wave.open(output, 'wb') as wav:
                wav.setparams((1, 2, audio.sample_rate, 0, 'NONE', 'not compressed'))
                wav.writeframes(pcm)
            return output.getvalue()
        except (RuntimeError, TypeError, ValueError) as exc:
            raise SpeechError(503, 'tts_local_failed', '离线中文语音暂时无法生成。') from exc

    async def generate(self, text, voice, parameters):
        return await asyncio.to_thread(self._generate, text, parameters)
