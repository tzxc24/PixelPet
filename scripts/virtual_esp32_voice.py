"""Run an audio turn through the separate PixelPet device voice socket."""
import argparse
import io
import json
from pathlib import Path
import struct
import sys
from uuid import UUID
import wave

from websockets.sync.client import connect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.mock_device import connection_options

HEADER = struct.Struct('!16sI')
UPLOAD_LIMIT = 16000 * 2 * 20
OUTPUT_LIMIT = 24000 * 2 * 120


def pcm16_wav(pcm, rate):
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav:
        wav.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        wav.writeframes(pcm)
    return buffer.getvalue()


class VoiceProtocolError(RuntimeError):
    pass


class VirtualESP32Voice:
    def __init__(self, socket, timeout=90):
        self.socket = socket
        self.timeout = timeout

    def send(self, kind, **fields):
        self.socket.send(json.dumps({'version': 1, 'type': kind, **fields}))

    def control(self, expected):
        packet = self.socket.recv(timeout=self.timeout)
        if not isinstance(packet, str):
            raise VoiceProtocolError('Expected a JSON control frame')
        value = json.loads(packet)
        if value.get('type') == 'error':
            raise VoiceProtocolError(value.get('code', 'device_error'))
        if value.get('type') != expected:
            raise VoiceProtocolError(f'Expected {expected}, got {value.get("type")}')
        return value

    def hello(self):
        self.send('hello', client='virtual', firmware='virtual-v1.1')
        greeting = self.control('hello')
        if (greeting.get('version'), greeting.get('protocol'), greeting.get('sample_rate'),
                greeting.get('channels'), greeting.get('format')) != (1, 'pixelpet-pcm-v1', 16000, 1, 'pcm_s16le'):
            raise VoiceProtocolError('Unsupported voice greeting')
        return greeting

    def turn(self, pcm, conversation_id=None):
        if not pcm or len(pcm) % 2 or len(pcm) > UPLOAD_LIMIT:
            raise ValueError('Input must be nonempty PCM16, at most 20 seconds')
        self.send('record.start', **({'conversation_id': conversation_id} if conversation_id else {}))
        session = self.control('record.ready')['session_id']
        session_bytes = UUID(hex=session).bytes
        for sequence, offset in enumerate(range(0, len(pcm), 4096)):
            self.socket.send(HEADER.pack(session_bytes, sequence) + pcm[offset:offset + 4096])
        self.send('record.stop', session_id=session)
        if self.control('thinking').get('session_id') != session:
            raise VoiceProtocolError('Unexpected thinking session')
        playback = self.control('playback.start')
        if (playback.get('session_id'), playback.get('sample_rate'), playback.get('channels'), playback.get('format')) != (session, 24000, 1, 'pcm_s16le'):
            raise VoiceProtocolError('Unexpected playback format or session')
        declared = playback.get('byte_count')
        if type(declared) is not int or not 0 < declared <= OUTPUT_LIMIT or declared % 2:
            raise VoiceProtocolError('Invalid playback length')
        output = bytearray()
        sequence = 0
        while True:
            packet = self.socket.recv(timeout=self.timeout)
            if isinstance(packet, str):
                message = json.loads(packet)
                if message.get('type') == 'error':
                    raise VoiceProtocolError(message.get('code', 'device_error'))
                if message.get('type') != 'playback.end' or message.get('session_id') != session or len(output) != declared:
                    raise VoiceProtocolError('Invalid playback termination')
                break
            if not HEADER.size < len(packet) <= HEADER.size + 4096 or len(packet) % 2 or HEADER.unpack_from(packet) != (session_bytes, sequence):
                raise VoiceProtocolError('Invalid audio frame, sequence, or session')
            output.extend(packet[HEADER.size:])
            if len(output) > declared:
                raise VoiceProtocolError('Playback exceeded local buffer limit')
            sequence += 1
        return playback, bytes(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--url', default='ws://127.0.0.1:8765/api/devices/voice/ws?device_id=virtual-voice')
    args = parser.parse_args()
    with wave.open(str(args.input), 'rb') as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (16000, 1, 2):
            parser.error('Expected 16 kHz mono PCM16 WAV')
        pcm = wav.readframes(UPLOAD_LIMIT // 2 + 1)
    with connect(args.url, max_size=16384, proxy=None, **connection_options(args.url)) as socket:
        client = VirtualESP32Voice(socket)
        client.hello()
        metadata, output = client.turn(pcm)
    args.output.write_bytes(pcm16_wav(output, 24000))
    print(json.dumps({'bytes': len(output), 'sample_rate': 24000, 'emotion': metadata.get('emotion')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
