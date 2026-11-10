# TTS text and audio processing

`backend.speech.text.prepare_text(text, max_chars=2000)` returns plain speech text.
It removes Markdown heading/list/quote markers, emphasis, inline backticks, image
markup, link destinations, bare web URLs, and decorative emoji. Link labels remain.
It preserves numbers, negative signs, units, Chinese punctuation, and the words of
the input; it does not add conversational filler or invent facts. Line/paragraph
breaks become sentence pauses where punctuation is absent. It does not separate
Chinese text into individual characters.

Fenced code is replaced with `代码内容请查看屏幕。` rather than reading source code.
Inline code remains readable text. This is a lightweight Markdown preparation
utility, not a complete Markdown parser. Empty or decoration-only input raises
`ValueError`. Oversized text ends at the last complete sentence within the budget,
or at a clause/word boundary with a final full stop. If no safe boundary exists,
it raises `ValueError` instead of cutting an unbroken fact or number in half.
Trailing sentences may be omitted when enforcing the speech budget; callers can
continue showing the full original answer on screen.

`emotion_parameters(emotion, rate_percent=0, pitch_hz=0, volume_percent=0)`
returns integer provider hints. Rate shifts: normal 0, happy +4, shy -3, sad -5,
curious +1, sleepy -7, surprised +5, angry 0, thinking 0. Unknown emotions use 0.
Final rate is clamped to −20…+20%, pitch to −12…+12 Hz, and volume to −100…0%.
There is no positive volume gain. These are mild prosody hints, not claims that a
provider supports SSML emotion styles. They do not alter text facts.

`backend.speech.conversion.convert_audio(data, target='pc', sample_rate=None)`
accepts in-memory MP3 (including Edge TTS output) and legacy WAV through PyAV.
Default output is PCM signed 16-bit little-endian, mono, 24 kHz. Explicit 16 kHz
is also supported. Conversion resamples normally: it does not relabel the source
sample rate, change playback speed, or apply time stretching, pitch shifting,
loudness normalization, or positive gain.

| Target | Bytes | Media type |
| --- | --- | --- |
| `pc` | WAV with valid PCM header | `audio/wav` |
| `device` | Raw PCM16 little-endian | `application/octet-stream` |
| `device_wav` | WAV with valid PCM header | `audio/wav` |

Result keys are `data`, `sample_rate`, `channels`, `duration` (seconds), `codec`
(`pcm_s16le`), `media_type`, `peak`, and `clipped_ratio`. Duration comes from actual
output sample count. Peak is absolute output amplitude divided by 32768;
clipped_ratio is the fraction of output samples at the PCM16 rails (−32768 or
+32767). This reports output saturation and cannot identify clipping already
present in a source signal below those rails. Conversion does not repair clipping.

Inputs are limited to 10 MiB and decoded duration to 120 seconds, with a running
sample bound during resampling. Source rates above 192 kHz, more than eight source
channels, multiple audio streams, empty/malformed data, and unsupported targets or
sample rates raise `ValueError`. Devices receive explicit PCM rather than an
assumption that ESP firmware can decode MP3. Opus output is not implemented.
No neural audio model, paid synthesis call, or network request is used here.

Validation: `D:\PixelPet\.venv\Scripts\python.exe -m pytest tests/test_tts_processing.py -q`.
Tests generate audio locally and check MP3 decoding, mono conversion, exact WAV
headers/sample counts, 16/24 kHz duration and 440 Hz pitch preservation, clipping
telemetry, limits, and text fact preservation.
