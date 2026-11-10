# SparkBot-inspired voice interaction design

The user approved adapting the reference voice architecture on 2026-11-08.

PixelPet keeps its current hardware mapping, FastAPI, DeepSeek, SQLite and Edge TTS.
The selected adaptation is an ESP-SR standalone WebRTC VAD and a bounded FreeRTOS
microphone capture queue. The existing start/end cues and 1.8-second endpoint
policy remain the user-facing interaction.

The input task reads 20 ms, 16 kHz, mono PCM16 blocks independently. The consumer
runs VAD and collects bounded audio in PSRAM. A queue timeout is an explicit
failure instead of silently dropping samples. Cancellation waits for capture to
stop before releasing its queue or enabling speaker playback. Network upload
begins after capture, preserving I2S timing and the server upload deadline.

ESP-SR is pinned to the reviewed official commit. Only the standalone VAD library
is linked. WakeNet, neural VAD models, AEC and custom wake-word training are
outside this change. If the official standalone library cannot link on the
installed IDF, report that failure and retain the previous working image.

Validation covers frame sizes and classification lifetime through a host adapter,
capture cancellation on the real device, ordinary speech with automatic ending,
and the existing Python and C++ suites. Human voice and audible prompts need the
user's participation. Credentials remain local in the existing ignored files.

Reference
https://gitee.com/esp-friends/esp_sparkbot/tree/d42c5b43e25168fa3592a9c3d113ab5631f47023/example/factory_demo_v1
