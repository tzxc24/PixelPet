# SparkBot-inspired Voice Implementation Plan

> For agentic workers, execute tasks sequentially and verify each integration step.

**Goal** Improve the real-device voice interaction using the reference's VAD and queue structure.

**Architecture** Keep the existing network voice session. Add an ESP-SR adapter and a
cooperatively stopped microphone producer. Preserve GPIO and backend contracts.

**Tech Stack** ESP-IDF 6.1, ESP32-S3, FreeRTOS, official ESP-SR WebRTC VAD, Python.

1. Pin and fetch official ESP-SR, inspect standalone VAD archive dependencies,
   and add reproducible build wiring without model downloads.
2. Write failing host tests for valid VAD frame length and lifetime. Add the
   adapter, queue producer, bounded capture and cooperative stop.
3. Integrate with existing automatic endpoint/cues, build and fix integration.
4. Run C++ and Python tests. Flash only after native build passes. Verify a real
   spoken turn and collect separate software/human observations.

## Verification

All four tasks completed. Native ESP32-S3 build passed without changing the
partition table. Ten C++ host tests passed. The real device cancelled capture
and reconnected without a chat request. A real spoken turn captured 8.06 seconds,
automatically ended, reached DeepSeek and Edge TTS, and returned to IDLE.
The user confirmed hearing the reply. The pet name still has a homophone
transcription error. See output/esp32-sparkbot-upgrade-report.json.
