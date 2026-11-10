from types import SimpleNamespace

import numpy as np

from backend.core.config import Settings
from backend.speech.service import LocalWhisper


def test_short_wake_phrase_uses_decoder_without_second_vad_gate():
    calls=[]
    class Model:
        def transcribe(self,samples,**kwargs):
            calls.append(kwargs)
            return iter([SimpleNamespace(text='你好小星',avg_logprob=-.2,no_speech_prob=.05)]),SimpleNamespace(language='zh')
    asr=LocalWhisper(Settings());asr.model=Model()
    assert asr.transcribe(np.zeros(32000),wake=True)['text']=='你好小星'
    assert calls[-1]['vad_filter'] is False
    asr.transcribe(np.zeros(32000))
    assert calls[-1]['vad_filter'] is True


def test_uncertain_wake_text_is_not_accepted():
    class Model:
        def transcribe(self,*args,**kwargs):
            return iter([SimpleNamespace(text='你好小星',avg_logprob=-1.8,no_speech_prob=.9)]),SimpleNamespace(language='zh')
    asr=LocalWhisper(Settings());asr.model=Model()
    assert asr.transcribe(np.zeros(32000),wake=True)['text']==''


def test_proper_name_low_text_score_is_kept_when_speech_probability_is_high():
    class Model:
        def transcribe(self,*args,**kwargs):
            return iter([SimpleNamespace(text='你好小心',avg_logprob=-1.939,no_speech_prob=.113)]),SimpleNamespace(language='zh')
    asr=LocalWhisper(Settings());asr.model=Model()
    assert asr.transcribe(np.zeros(32000),wake=True)['text']=='你好小心'
