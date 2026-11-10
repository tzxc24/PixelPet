"""Offline phoneme keyword spotting; never sends or retains standby speech."""
import hashlib
import importlib.util
import json
import threading
from pathlib import Path

import numpy as np

from backend.core.config import ROOT
from backend.speech.service import SpeechError

KEYWORDS = frozenset(('你好小星','你好小心','小星小星'))


class LocalKeywordWake:
    name='local_keyword_spotter'

    def __init__(self,manifest_path=None,engine=None):
        self.manifest_path=Path(manifest_path or ROOT/'config/wake_model.json')
        self.engine=engine
        self.lock=threading.Lock()
        self.last_wake_diagnostic=None

    def files(self):
        manifest=json.loads(self.manifest_path.read_text(encoding='utf-8'))
        directory=(ROOT/manifest['directory']).resolve()
        if not directory.is_relative_to((ROOT/'tmp/models').resolve()):
            raise ValueError('Wake models must be under project tmp/models')
        return directory,manifest['sha256']

    def status(self):
        ready=self.engine is not None
        if not ready:
            try:
                directory,files=self.files()
                ready=bool(files) and all((directory/name).is_file() for name in files)
                ready=ready and importlib.util.find_spec('sherpa_onnx') is not None
            except (OSError,ValueError,KeyError,TypeError):
                ready=False
        return {'provider':self.name,'ready':ready,'network_required':False,
                'keywords':sorted(KEYWORDS),'device':'PC CPU','recordings_retained':False,
                'message':'离线关键词检测' if ready else '请安装依赖并运行 scripts/setup_wake_model.py'}

    def load(self):
        if self.engine is not None:return
        try:
            directory,files=self.files()
            for name,digest in files.items():
                path=(directory/name).resolve()
                if not path.is_relative_to(directory) or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
                    raise ValueError('Wake model digest mismatch')
            import sherpa_onnx
            def model(prefix):
                return str(directory/next(name for name in files if name.startswith(prefix)))
            self.engine=sherpa_onnx.KeywordSpotter(
                tokens=model('tokens'),encoder=model('encoder'),decoder=model('decoder'),
                joiner=model('joiner'),keywords_file=str(ROOT/'config/wake_keywords.txt'),
                num_threads=2,provider='cpu',keywords_score=1.0,keywords_threshold=.3)
        except (OSError,ValueError,KeyError,TypeError,ImportError,StopIteration,RuntimeError):
            raise SpeechError(503,'wake_model_missing','离线唤醒模型不可用，请运行 scripts/setup_wake_model.py；不会将待机声音转发云端。') from None

    def transcribe(self,samples):
        samples=np.asarray(samples,dtype=np.float32)
        if samples.ndim!=1 or not 0<len(samples)<=320000 or not np.isfinite(samples).all():
            raise SpeechError(422,'invalid_wake_audio','唤醒输入必须是 20 秒以内的单声道 16kHz 音频。')
        with self.lock:
            self.load()
            stream=self.engine.create_stream()
            keyword=''
            # Fresh stream for each bounded clip. Never carry background content
            # between turns; padding flushes the final short keyword's frames.
            for chunk in (samples,np.zeros(8000,dtype=np.float32)):
                stream.accept_waveform(16000,chunk)
                while self.engine.is_ready(stream):
                    self.engine.decode_stream(stream)
                    result=self.engine.get_result(stream)
                    if result in KEYWORDS:
                        keyword=result
                        break
                if keyword:break
            self.last_wake_diagnostic={'matched':bool(keyword),'provider':self.name}
            return {'text':keyword,'language':'zh'}
