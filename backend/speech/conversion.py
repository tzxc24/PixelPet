"""Bounded MP3/WAV decoding and PCM packaging; resampling preserves speed."""
import io
import wave

import av
import numpy as np

MAX_INPUT_BYTES = 10 * 1024 * 1024
MAX_SECONDS = 120


def convert_audio(data: bytes, target='pc', sample_rate=None) -> dict:
    """Return PCM16 mono audio and measurements; invalid inputs raise ValueError."""
    rate = 24000 if sample_rate is None else sample_rate
    if target not in {'pc', 'device', 'device_wav'} or isinstance(rate, bool) or rate not in {16000, 24000}:
        raise ValueError('Unsupported audio target or sample rate')
    if not isinstance(data, bytes) or not data or len(data) > MAX_INPUT_BYTES:
        raise ValueError('Audio must contain at most 10 MiB')
    chunks = []
    sample_count = 0
    source_seconds = 0.0
    try:
        with av.open(io.BytesIO(data)) as container:
            if not set(container.format.name.split(',')).intersection({'wav', 'mp3'}):
                raise ValueError('Only WAV and MP3 inputs are supported')
            streams = list(container.streams.audio)
            if len(streams) != 1:
                raise ValueError('Expected one audio stream')
            resampler = av.AudioResampler(format='s16', layout='mono', rate=rate)

            def collect(frames):
                nonlocal sample_count
                for frame in frames:
                    samples = frame.to_ndarray().astype('<i2', copy=False).reshape(-1)
                    sample_count += samples.size
                    if sample_count > rate * MAX_SECONDS:
                        raise ValueError('Decoded audio exceeds 120 seconds')
                    chunks.append(samples.tobytes())

            for frame in container.decode(streams[0]):
                if not frame.sample_rate or frame.sample_rate > 192000 or len(frame.layout.channels) > 8:
                    raise ValueError('Unsupported source audio layout')
                source_seconds += frame.samples / frame.sample_rate
                if source_seconds > MAX_SECONDS + 1e-8:
                    raise ValueError('Decoded audio exceeds 120 seconds')
                collect(resampler.resample(frame))
            collect(resampler.resample(None))
    except ValueError:
        raise
    except Exception:
        raise ValueError('Audio could not be decoded') from None
    if not sample_count:
        raise ValueError('Audio has no samples')
    pcm = b''.join(chunks)
    values = np.frombuffer(pcm, dtype='<i2').astype(np.int32)
    peak = float(np.abs(values).max() / 32768)
    clipped_ratio = float(np.count_nonzero((values <= -32768) | (values >= 32767)) / sample_count)
    if target != 'device':
        output = io.BytesIO()
        with wave.open(output, 'wb') as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(rate)
            writer.writeframes(pcm)
        pcm = output.getvalue()
    return {'data': pcm, 'sample_rate': rate, 'channels': 1, 'duration': sample_count / rate, 'codec': 'pcm_s16le', 'media_type': 'application/octet-stream' if target == 'device' else 'audio/wav', 'peak': peak, 'clipped_ratio': clipped_ratio}
