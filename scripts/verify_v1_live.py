"""Opt-in real Whisper → DeepSeek → Edge probe with synthetic input and isolated SQLite."""
import io
import json
from pathlib import Path
import sys
from uuid import uuid4
import wave

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.main import create_app


def main():
    database = ROOT / 'tmp' / f'final-v1-live-{uuid4().hex}.sqlite3'
    output = ROOT / 'output' / 'final-v1'
    output.mkdir(parents=True, exist_ok=True)
    report = {'input': 'SAPI synthetic speech', 'physical_microphone': 'HW_PENDING',
              'physical_speaker': 'HW_PENDING', 'stages': {}}
    stage = 'startup'
    try:
        with TestClient(create_app(database_path=database)) as client:
            status = client.get('/api/status').json()
            if status['mode'] != 'deepseek':
                raise RuntimeError('DeepSeek is not configured')
            stage = 'synthetic_input'
            source = client.post('/api/audio/synthesize', json={
                'provider': 'sapi', 'voice': None, 'text': '你还记得我正在做什么吗？'})
            source.raise_for_status()
            stage = 'whisper'
            transcript = client.post('/api/audio/transcribe', files={
                'audio': ('speech.wav', source.content, 'audio/wav')})
            transcript.raise_for_status()
            recognized = transcript.json()
            report['stages'][stage] = {k: recognized[k] for k in ('text', 'provider', 'elapsed_ms')}
            stage = 'deepseek'
            fact = '主人正在开发 ESP32 AI 桌宠 PixelPet。'
            client.post('/api/memories', json={'category': 'project', 'content': fact, 'importance': .95}).raise_for_status()
            chat = client.post('/api/chat/stream', json={'message': recognized['text']})
            chat.raise_for_status()
            last = chat.text.strip().split('\n\n')[-1]
            if not last.startswith('event: done\n'):
                raise RuntimeError('DeepSeek stream did not finish')
            reply = json.loads(last.split('\ndata: ', 1)[1])
            assert reply['mode'] == 'deepseek' and ('PixelPet' in reply['reply'] or 'ESP32' in reply['reply'])
            report['stages'][stage] = {k: reply[k] for k in ('reply', 'emotion', 'timings')}
            stage = 'edge'
            payload = {'provider': 'edge', 'voice': 'zh-CN-XiaoyiNeural',
                       'text': reply['reply'], 'emotion': reply['emotion'], 'allow_fallback': False}
            audio = client.post('/api/audio/synthesize', json=payload)
            audio.raise_for_status()
            assert audio.headers['x-audio-provider'] == 'edge' and audio.headers['x-audio-cache'] == 'miss'
            with wave.open(io.BytesIO(audio.content), 'rb') as stream:
                assert (stream.getframerate(), stream.getsampwidth(), stream.getnchannels()) == (24000, 2, 1)
                assert stream.getnframes() > 0
            cached = client.post('/api/audio/synthesize', json=payload)
            assert cached.headers['x-audio-cache'] == 'hit' and cached.content == audio.content
            report['stages'][stage] = {'provider': 'edge', 'duration_s': audio.headers['x-audio-duration'],
                                        'elapsed_ms': audio.headers['x-audio-synthesis-ms'], 'cache': 'hit'}
            report['result'] = 'PASS'
    except Exception as exc:
        report.update(result='BLOCKED', stage=stage, error=type(exc).__name__)
        response = getattr(exc, 'response', None)
        if response is not None:
            report['http_status'] = response.status_code
    (output / 'live-voice.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['result'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
