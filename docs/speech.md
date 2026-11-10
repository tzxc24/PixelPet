# PC speech service

`backend.speech.service.SpeechService(settings)` retains local CPU recognition and Windows SAPI compatibility. Its `natural` service provides replaceable Edge/SAPI/Mock adapters and reserved unconfigured Azure/Custom slots. Edge is the default. Browser `speechSynthesis` remains an explicit optional frontend capability; previews of Edge voices use actual server audio, never browser speech. DeepSeek receives recognized chat text and generates replies; it is not used for ASR or TTS. See [natural voice report](natural_tts_report.md).

## API contract

- `GET /api/audio/status`: ASR readiness, selected TTS provider/dependency readiness, separate browser capability information and limits. For Edge, `network_verified` requires an actual successful request during the current process; installed dependencies alone do not establish network availability. This endpoint never downloads or loads an ASR model.
- `GET /api/audio/voices?provider=edge`: available/disabled voice objects with labels. `provider=sapi` queries installed Windows voices; `mock` is explicitly a test tone. Xiaomeng is disabled because it was absent from the verified Edge catalogue.
- `POST /api/audio/transcribe`: multipart **audio** file plus optional `duration_ms`, `sample_rate`, `channels` client metadata. Client metadata is descriptive and never trusted to enforce duration. The server decodes samples with PyAV before ASR; actual decoded duration is limited to 60 seconds. File limit is 10 MiB. Accepted MIME types: WAV, WebM, Ogg, MP4, MPEG and FLAC audio, including codec parameters. Container contents must decode successfully regardless of extension or claimed type.
- `POST /api/audio/synthesize`: JSON `{"text":"你好，我是小星。","provider":"edge","voice":"zh-CN-XiaoyiNeural","rate_percent":0,"pitch_hz":0,"volume_percent":0,"emotion":"normal","allow_fallback":false}`. Omitted parameters use persisted voice settings; an explicitly different provider uses its own default voice. Text is 1–2000 characters. Rate is −20…20%, pitch −12…12Hz, volume −100…0%. Defaults return PCM16 mono 24kHz WAV. `output_format=device_pcm` returns raw PCM; `device_wav` returns WAV; explicit `sample_rate` can be 16000/24000. Legacy `rate`/`volume` inputs remain accepted. Response headers `X-Audio-*` declare actual provider, voice, format, parameters, timing, clipping and explicit fallback. Decode actual values; do not assume MP3 or Opus device support. Preview uses `allow_fallback=false`; optional normal-reply fallback returns provider `sapi` and fallback `sapi`.

Transcription JSON contains `text`, `language`, `duration` in seconds, `provider`, normalized `sample_rate=16000`, `channels=1`, `codec=pcm_f32le`, input MIME/byte size, `elapsed_ms`, and the untrusted `client_metadata`. ASR receives mono float samples after actual decoding/resampling, rather than mislabeled PCM bytes.

Failures use HTTP `detail: {code,message}`. Empty/bad/overlong/no-speech audio is 422, unsupported MIME 415, oversized files 413, unavailable dependencies/model/voices 503, timeout 504, and concurrent ASR 409. None return a fake transcript. The frontend should keep text chat usable and show an explicit fallback state.

## Configuration and model setup

Settings fields consumed by this service:

| Field | Default | Meaning |
|---|---|---|
| `asr_model` | `base` | `tiny`, `base`, `small`, `medium`, `large-v3` or supported English-only variants |
| `asr_model_download` | `False` | Explicit opt-in to download a missing public model on the first transcription |
| `speech_timeout` | `120` | Processing/subprocess timeout in seconds |

The app maps these fields to its single settings schema/environment template. Model files go to `D:\PixelPet\tmp\models\faster-whisper-<name>` and model download cache to `D:\PixelPet\tmp\models\hub`. ASR uses CPU/int8, at most four CPU threads and one worker, and lazily imports faster-whisper. No API key or paid service is needed. Model downloads require network access; after a complete model download recognition runs locally. For a manual download with the project Python:

```powershell
cd D:\PixelPet
.\.venv\Scripts\python.exe -c "from faster_whisper.utils import download_model; download_model('base', output_dir=r'D:\PixelPet\tmp\models\faster-whisper-base', cache_dir=r'D:\PixelPet\tmp\models\hub')"
```

The upstream implementation documents CPU int8, local model loading and lazy segment iteration: [faster-whisper](https://github.com/SYSTRAN/faster-whisper). The service consumes the segment generator inside its worker, so inference is included in the measured processing time. A timeout cannot forcibly stop a native inference thread: admission remains closed until that worker exits, preventing repeated requests from accumulating concurrent models.

## Privacy and Windows behavior

Decoded recording samples stay in memory and are not saved to SQLite or an audio cache. Multipart handling can temporarily spool large uploads; app setup must place Python's temporary directory under project `tmp/uploads`. Upload handles are always closed, deleting their spooled file. Frontend recording stops conservatively at 59 seconds, and deployment should bound total HTTP request size as well as the per-file limit.

Windows TTS invokes `scripts/sapi_synthesize.ps1` using hidden, noninteractive Windows PowerShell. The text is passed through stdin JSON, not a shell command or a disk text file. System.Speech writes a RIFF/WAVE stream in memory, returned as base64 over the private subprocess stdout and converted to real WAV bytes in Python. No generated audio file is retained by default. The result's actual sample rate/channel count are read from its WAV header. Windows voices must be installed at OS level; browser voices can differ from SAPI voices.

PC microphone permission and real speaker playback require browser/user interaction and are separate from backend WAV generation. ESP32 microphone, amplifier, speaker quality and echo behavior remain `HW_PENDING`. V1 frontend must use half duplex and must not automatically record while playback is active.

## Verification evidence

`D:\PixelPet\.venv\Scripts\python.exe -m pytest tests/test_speech.py -q` covers decoded payload validation, size/duration limits, no-speech reporting, ASR failure fallback, normalized metadata, endpoint WAV response metadata, invalid TTS fields and a Windows SAPI integration test (skipped on non-Windows/no voices).

On this Windows PC, two SAPI voices were detected. A real Chinese synthesis produced **118,182 bytes**, RIFF/WAVE, **22,050 Hz**, mono, 16-bit PCM, decoded duration **2.6788 seconds**. This is backend synthesis/decoding evidence; physical microphone capture and physical speaker audibility were not tested by this subtask. ASR model download/real transcription is recorded separately in the overall project report.
