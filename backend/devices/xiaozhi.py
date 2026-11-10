"""Independent XiaoZhi WebSocket v1 adaptation and raw Opus codec helpers."""
from dataclasses import dataclass, field
from uuid import uuid4

import av
import numpy as np

FRAME_MS = 60
MAX_RECORD_SECONDS = 20
MAX_PACKET_BYTES = 1275


class RawOpus:
    """One packet per WebSocket frame, without Ogg or v2/v3 framing."""

    def __init__(self, rate: int, frame_ms: int = FRAME_MS):
        if (type(rate) is not int or rate not in (16000, 24000) or
                type(frame_ms) is not int or frame_ms not in (20, 40, 60)):
            raise ValueError('unsupported Opus parameters')
        self.rate = rate
        self.frame_ms = frame_ms
        self.samples = rate * frame_ms // 1000
        self.decoder = av.CodecContext.create('libopus', 'r')
        self.decoder.sample_rate = rate
        self.decoder.layout = 'mono'
        self.resampler = av.AudioResampler(format='s16', layout='mono', rate=rate)

    def decode(self, packet: bytes) -> bytes:
        if not 0 < len(packet) <= MAX_PACKET_BYTES:
            raise ValueError('invalid Opus packet size')
        try:
            decoded = self.decoder.decode(av.Packet(packet))
            if sum(frame.samples * self.rate // frame.sample_rate for frame in decoded) != self.samples:
                raise ValueError('unexpected Opus frame duration')
            frames = [output for frame in decoded for output in self.resampler.resample(frame)]
        except av.FFmpegError:
            raise ValueError('invalid Opus packet') from None
        return b''.join(frame.to_ndarray().astype('<i2', copy=False).tobytes() for frame in frames)

    def finish_decode(self) -> bytes:
        return b''.join(frame.to_ndarray().astype('<i2', copy=False).tobytes()
                        for frame in self.resampler.resample(None))

    def encode(self, pcm: bytes):
        if not pcm or len(pcm) % 2:
            raise ValueError('expected PCM16LE samples')
        encoder = av.CodecContext.create('libopus', 'w')
        encoder.sample_rate = self.rate
        encoder.layout = 'mono'
        encoder.format = 's16'
        encoder.options = {'frame_duration': str(self.frame_ms)}
        width = self.samples * 2
        for offset in range(0, len(pcm), width):
            samples = np.frombuffer(pcm[offset:offset + width].ljust(width, b'\0'), dtype='<i2')
            frame = av.AudioFrame.from_ndarray(samples.reshape(1, -1), format='s16', layout='mono')
            frame.sample_rate = self.rate
            yield from (bytes(packet) for packet in encoder.encode(frame))
        yield from (bytes(packet) for packet in encoder.encode(None))


@dataclass
class XiaozhiSession:
    """Connection-scoped half-duplex protocol state; caller owns I/O and inference."""
    session_id: str = field(default_factory=lambda: uuid4().hex)
    state: str = 'connecting'
    input_codec: RawOpus | None = None
    output_codec: RawOpus | None = None
    recording: bytearray = field(default_factory=bytearray)
    packets: int = 0
    generation: int = 0

    def message(self, kind, **fields):
        return {'type': kind, 'session_id': self.session_id, **fields}

    def hello(self, message):
        audio = message.get('audio_params')
        if (self.state != 'connecting' or message.get('type') != 'hello' or
                type(message.get('version')) is not int or message['version'] != 1 or
                message.get('transport') != 'websocket' or not isinstance(audio, dict) or
                audio.get('format') != 'opus' or audio.get('channels') != 1):
            raise ValueError('unsupported hello')
        frame_ms = audio.get('frame_duration')
        self.input_codec = RawOpus(audio.get('sample_rate'), frame_ms)
        self.output_codec = RawOpus(24000, frame_ms)
        self.state = 'idle'
        return self.message('hello', version=1, transport='websocket', audio_params={
            'format': 'opus', 'sample_rate': 24000, 'channels': 1, 'frame_duration': frame_ms,
        })

    def control(self, message):
        if self.state == 'connecting' or message.get('session_id') != self.session_id:
            raise ValueError('invalid session')
        if message.get('type') == 'abort':
            return self.abort()
        if message.get('type') != 'listen':
            raise ValueError('unsupported control')
        action = message.get('state')
        if action == 'start' and self.state == 'idle':
            self.generation += 1
            self.input_codec = RawOpus(self.input_codec.rate, self.input_codec.frame_ms)
            self.recording.clear()
            self.packets = 0
            self.state = 'listening'
            return None
        if action == 'stop' and self.state == 'listening':
            if not self.recording:
                self.abort()
                raise ValueError('empty recording')
            pcm = bytes(self.recording) + self.input_codec.finish_decode()
            self.recording.clear()
            self.state = 'thinking'
            return pcm
        raise ValueError('invalid listen transition')

    def ingest(self, packet):
        if self.state != 'listening':
            raise ValueError('not listening')
        if (self.packets + 1) * self.input_codec.frame_ms > MAX_RECORD_SECONDS * 1000:
            self.abort()
            raise ValueError('recording exceeds limit')
        try:
            pcm = self.input_codec.decode(packet)
        except ValueError:
            self.abort()
            raise
        self.recording.extend(pcm)
        self.packets += 1

    def reply(self, transcript, text, emotion, pcm):
        if self.state != 'thinking':
            raise ValueError('no pending reply')
        self.state = 'speaking'
        generation = self.generation
        try:
            yield self.message('stt', text=transcript)
            yield self.message('llm', emotion=emotion, text=text)
            yield self.message('tts', state='start')
            yield self.message('tts', state='sentence_start', text=text)
            for packet in self.output_codec.encode(pcm):
                if self.state != 'speaking' or generation != self.generation:
                    return
                yield packet
            if self.state == 'speaking':
                yield self.message('tts', state='stop')
        finally:
            if self.state == 'speaking' and generation == self.generation:
                self.state = 'idle'

    def abort(self):
        playing = self.state == 'speaking'
        self.generation += 1
        self.recording.clear()
        self.packets = 0
        self.state = 'idle'
        return self.message('tts', state='stop') if playing else None
