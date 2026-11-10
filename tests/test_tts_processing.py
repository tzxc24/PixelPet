import io
import wave

import av
import numpy as np
import pytest


def test_text_keeps_facts_without_markdown_or_decoration():
    from backend.speech.text import prepare_text
    result = prepare_text('# 温度报告\n\n**温度**为 -3.5°C，电压 3.3V，不要关机。😊\n[说明](https://example.com) ![图](x.png)')
    assert '-3.5°C，电压 3.3V，不要关机。' in result
    assert '说明' in result
    assert not any(item in result for item in ['#', '**', 'https', '😊', 'x.png'])
    assert '温度报告。' in result


def test_text_skips_code_and_bounds_at_sentence():
    from backend.speech.text import prepare_text
    assert prepare_text('执行方法：\n```python\nprint(123)\n```') == '执行方法：代码内容请查看屏幕。'
    assert prepare_text('第一句。第二句太长了。', max_chars=6) == '第一句。'


def test_text_removes_urls_without_swallowing_adjacent_facts():
    from backend.speech.text import prepare_text
    assert prepare_text('详情 https://example.com。电池剩余 25%，不要关机。') == '详情 。电池剩余 25%，不要关机。'
    assert prepare_text('## 报告 ##\n- 温度 -3.5°C。') == '报告。温度 -3.5°C。'


def test_text_refuses_to_cut_a_number_or_unbroken_fact():
    from backend.speech.text import prepare_text
    with pytest.raises(ValueError):
        prepare_text('1234567890', max_chars=5)
    assert prepare_text('温度正常，电池剩余1234567890。', max_chars=10) == '温度正常。'


@pytest.mark.parametrize('text', ['', '  ', '😊✨', '![图](image.png)', '---'])
def test_text_rejects_unspeakable(text):
    from backend.speech.text import prepare_text
    with pytest.raises(ValueError):
        prepare_text(text)


def test_emotion_adjustments_are_mild_and_bounded():
    from backend.speech.text import emotion_parameters
    expected = {'normal': 0, 'happy': 4, 'shy': -3, 'sad': -5, 'curious': 1, 'sleepy': -7, 'surprised': 5, 'angry': 0, 'thinking': 0}
    for emotion, rate in expected.items():
        assert emotion_parameters(emotion) == dict(rate_percent=rate, pitch_hz=0, volume_percent=0)
    assert emotion_parameters('happy', 100, 99, 20) == dict(rate_percent=20, pitch_hz=12, volume_percent=0)
    assert emotion_parameters('sad', -100, -99, -200) == dict(rate_percent=-20, pitch_hz=-12, volume_percent=-100)


def make_wav(sample_rate=48000, seconds=0.25, stereo=True, clipped=False):
    count = round(sample_rate * seconds)
    values = (np.sin(np.arange(count) * 2 * np.pi * 440 / sample_rate) * 12000).astype('<i2')
    if clipped:
        values[:] = 32767
    if stereo:
        values = np.column_stack([values, values])
    output = io.BytesIO()
    with wave.open(output, 'wb') as writer:
        writer.setnchannels(2 if stereo else 1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(values.tobytes())
    return output.getvalue()


@pytest.mark.parametrize('target,rate', [('pc', 24000), ('device', 24000), ('device_wav', 16000)])
def test_audio_resamples_without_changing_duration_or_pitch(target, rate):
    from backend.speech.conversion import convert_audio
    result = convert_audio(make_wav(), target=target, sample_rate=rate)
    assert result['sample_rate'] == rate
    assert result['channels'] == 1
    assert result['duration'] == pytest.approx(0.25, abs=1/rate)
    assert result['codec'] == 'pcm_s16le'
    if target == 'device':
        assert result['media_type'] == 'application/octet-stream'
        pcm = result['data']
    else:
        assert result['media_type'] == 'audio/wav'
        with wave.open(io.BytesIO(result['data']), 'rb') as reader:
            assert (reader.getnchannels(), reader.getsampwidth(), reader.getframerate(), reader.getnframes()) == (1, 2, rate, rate // 4)
            pcm = reader.readframes(reader.getnframes())
    samples = np.frombuffer(pcm, dtype='<i2')
    assert len(samples) == rate // 4
    spectrum = np.abs(np.fft.rfft(samples))
    assert np.fft.rfftfreq(len(samples), 1/rate)[spectrum.argmax()] == pytest.approx(440, abs=4)
    assert 0 < result['peak'] < 1
    assert result['clipped_ratio'] == 0


def test_audio_reports_clipping_and_decodes_mp3():
    from backend.speech.conversion import convert_audio
    clipped = convert_audio(make_wav(stereo=False, clipped=True))
    assert clipped['clipped_ratio'] > 0.9
    assert clipped['peak'] > 0.99
    output = io.BytesIO()
    with av.open(output, 'w', format='mp3') as container:
        stream = container.add_stream('mp3', rate=24000)
        stream.layout = 'mono'
        samples = np.zeros((1, 6000), dtype=np.float32)
        frame = av.AudioFrame.from_ndarray(samples, format='fltp', layout='mono')
        frame.sample_rate = 24000
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    result = convert_audio(output.getvalue(), target='device')
    assert result['duration'] == pytest.approx(0.25, abs=0.01)


@pytest.mark.parametrize('payload,kwargs', [(b'', {}), (b'invalid', {}), (b'x' * (10 * 1024 * 1024 + 1), {}), (make_wav(), {'target': 'opus'}), (make_wav(), {'sample_rate': 44100}), (make_wav(sample_rate=16000, seconds=120.1, stereo=False), {})])
def test_audio_rejects_invalid_or_unbounded_inputs(payload, kwargs):
    from backend.speech.conversion import convert_audio
    with pytest.raises(ValueError):
        convert_audio(payload, **kwargs)
