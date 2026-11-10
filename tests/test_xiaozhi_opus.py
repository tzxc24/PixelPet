import numpy as np
import pytest

from backend.devices.xiaozhi import RawOpus, XiaozhiSession


def tone(rate):
    return (np.sin(np.arange(rate * 3 // 10) * (2 * np.pi * 440 / rate)) * 12000).astype('<i2').tobytes()


def hello():
    return dict(type='hello', version=1, transport='websocket',
                audio_params=dict(format='opus', sample_rate=16000, channels=1, frame_duration=60))


def start():
    session = XiaozhiSession()
    assert session.hello(hello())['audio_params']['sample_rate'] == 24000
    session.control(session.message('listen', state='start'))
    return session


def test_duplex_raw_opus_round_trip():
    session = start()
    for packet in RawOpus(16000).encode(tone(16000)):
        assert not packet.startswith(b'OggS')
        session.ingest(packet)
    recording = session.control(session.message('listen', state='stop'))
    assert len(recording) == session.packets * 960 * 2
    assert np.max(np.abs(np.frombuffer(recording, dtype='<i2'))) > 1000
    frames = list(session.reply('你好', '你好呀', 'happy', tone(24000)))
    assert [f['type'] for f in frames if isinstance(f, dict)] == ['stt', 'llm', 'tts', 'tts', 'tts']
    assert frames[-1]['state'] == 'stop'
    decoder = RawOpus(24000)
    decoded = b''.join(decoder.decode(frame) for frame in frames if isinstance(frame, bytes))
    decoded += decoder.finish_decode()
    assert len(decoded) >= len(tone(24000))
    assert np.max(np.abs(np.frombuffer(decoded, dtype='<i2'))) > 1000
    assert session.state == 'idle'


def test_abort_discards_playback_and_rejects_stale_session():
    session = start()
    for packet in RawOpus(16000).encode(tone(16000)):
        session.ingest(packet)
    session.control(session.message('listen', state='stop'))
    frames = session.reply('a', 'b', 'normal', tone(24000))
    for _ in range(5):
        next(frames)
    assert session.control(session.message('abort'))['state'] == 'stop'
    assert list(frames) == []
    with pytest.raises(ValueError, match='invalid session'):
        session.control(dict(type='listen', session_id='old', state='start'))


def test_rejects_empty_and_invalid_audio():
    session = start()
    with pytest.raises(ValueError, match='empty recording'):
        session.control(session.message('listen', state='stop'))
    session.control(session.message('listen', state='start'))
    with pytest.raises(ValueError, match='invalid Opus'):
        session.ingest(b'')
    assert session.state == 'idle'


def test_rejects_v2_framing_and_bad_parameters():
    message = hello()
    message['version'] = 2
    with pytest.raises(ValueError, match='unsupported hello'):
        XiaozhiSession().hello(message)
    message['version'] = 1
    message['audio_params']['frame_duration'] = 45
    with pytest.raises(ValueError, match='unsupported Opus parameters'):
        XiaozhiSession().hello(message)
