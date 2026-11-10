"""Opt-in live PixelPet voice WebSocket verification, synthetic input and isolated data."""
import json
from contextlib import contextmanager
from pathlib import Path
import socket
import sys
from threading import Thread
from time import monotonic, sleep
from uuid import uuid4

import httpx
import uvicorn
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.main import create_app
from backend.core.config import Settings
from backend.speech.conversion import convert_audio
from scripts.virtual_esp32_voice import VirtualESP32Voice, VoiceProtocolError, pcm16_wav


@contextmanager
def loopback(app):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level='critical', access_log=False, ws_max_size=16384))
        worker = Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
        worker.start()
        try:
            deadline = monotonic() + 10
            while not server.started and worker.is_alive() and monotonic() < deadline:
                sleep(.02)
            if not server.started:
                raise RuntimeError('Local server startup failed')
            yield port
        finally:
            server.should_exit = True
            worker.join(10)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'output' / 'v1.1')
    directory = parser.parse_args().output_dir.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    database = ROOT / 'tmp' / f'v11-voice-{uuid4().hex}.sqlite3'
    report = {'source': 'Windows SAPI synthetic WAV converted to 16 kHz PCM',
              'transport': 'Uvicorn TCP WebSocket on loopback', 'physical_device': 'HW_PENDING'}
    stage = 'startup'
    try:
        settings = Settings()
        headers = {'Authorization': 'Bearer ' + settings.access_token.get_secret_value()} if settings.access_token else {}
        with loopback(create_app(database_path=database, settings=settings)) as port, httpx.Client(
                base_url=f'http://127.0.0.1:{port}', headers=headers, timeout=30) as client:
            mode = client.get('/api/status').json()['mode']
            if mode != 'deepseek':
                raise RuntimeError('DeepSeek unavailable')
            stage = 'test_audio'
            source = client.post('/api/audio/synthesize', json={
                'provider': 'sapi', 'voice': None, 'text': '你还记得我正在做什么吗？'})
            source.raise_for_status()
            pcm = convert_audio(source.content, target='device', sample_rate=16000)['data']
            client.patch('/api/pet/settings', json={'tts_provider': 'edge', 'voice': 'zh-CN-XiaoyiNeural'}).raise_for_status()
            client.post('/api/memories', json={'category': 'project', 'importance': .95,
                        'content': '主人正在开发 ESP32 AI 桌宠 PixelPet。'}).raise_for_status()
            stage = 'voice_socket'
            with connect(f'ws://127.0.0.1:{port}/api/devices/voice/ws?device_id=live-sim',
                         additional_headers=headers, max_size=16384, proxy=None) as ws:
                device = VirtualESP32Voice(ws)
                device.hello()
                start = monotonic()
                reply, output = device.turn(pcm)
                report['total_ms'] = round(1000 * (monotonic() - start))
            assert 'PixelPet' in reply['text'] or 'ESP32' in reply['text']
            report.update(result='PASS', mode=mode, tts='edge', input_bytes=len(pcm), output_bytes=len(output),
                          duration_seconds=len(output) / 48000, reply=reply)
            (directory / 'device-live-response.wav').write_bytes(pcm16_wav(output, 24000))
    except Exception as exc:
        report.update(result='BLOCKED', stage=stage, error=type(exc).__name__)
        if isinstance(exc, VoiceProtocolError):
            report['protocol_error'] = str(exc)
    (directory / 'device-live.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['result'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
