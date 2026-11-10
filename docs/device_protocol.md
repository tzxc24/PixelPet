# Device business protocol v1

This endpoint is PixelPet-specific JSON, not native xiaozhi. REST event schema is `shared/event.schema.json`. All audit history is bounded and contains only event ID, timestamp, device ID and event type. No payload, message text, raw audio, token or credentials enter this audit.

- `GET /api/devices`: current connected/disconnected mock devices and ESP32 pending status. Presence expires after 30 seconds; polling and WebSocket receive timeout enforce expiration.
- `POST /api/events`: Event -> `{event_id,effects,pet}`. Event IDs are deduplicated over the most recent 1024 inputs. Unknown event types, invalid numeric values, or payloads over 16KiB fail validation.
- `GET /api/events/status`: bounded event metadata, total count and pet state.
- `WS /api/devices/ws?device_id=mock-1`: initially returns `device.connected`. Send `{"version":1,"type":"hello","payload":{}}`; then heartbeat, event or response controls. Reply is `ack` with `payload.received`, effects and pet snapshot. Send heartbeat within 30 seconds. Maximum inbound JSON message 16KiB; close 1009 on excess. Invalid events return a sanitized error code. Disconnect resets recording/playback.

## Sequenced device sessions

After the greeting, send `{"version":1,"seq":1,"type":"hello","payload":{"client":"virtual"}}` to enable sequencing. A firmware client can use `"client":"esp32"`. Increment `seq` once per frame and reset it to 1 after reconnect. The same sequence appears in the acknowledgment or error. Replay, gaps, and missing sequence numbers in a sequenced session return `invalid_sequence` with `payload.expected_seq`; those frames do not run effects. An invalid event at the expected sequence consumes that sequence and returns `invalid_event`. The accepted range is 1–2147483647. Existing clients can omit sequence numbers.

The greeting includes the server heartbeat timeout and reconnect count. Only a valid message refreshes the timeout. Send `heartbeat` every five seconds or more frequently if the timeout is shorter. The server closes an idle session with code 1001. Oversized frames close with 1009 and binary frames close with 1003. A duplicate live device ID is rejected. Reconnect with the same ID to obtain a fresh authoritative snapshot from the new hello ACK. The client does not replay gestures or audio transitions after an uncertain ACK.

Every ACK includes `pet.state`, `pet.emotion`, `pet.recording`, `pet.speaking`, and an `effects` array. The server applies the audio interlock to the shared pet state. Recording, playback, and a pending hold are owned by the source that started them. Disconnecting another device leaves these activities intact. `GET /api/devices` includes `kind`, `connected`, and `reconnect_count` per ID. These counters are per server process.

| Device event | Existing engine event |
| --- | --- |
| TOUCH_START / TOUCH_END | touch.touch_down / touch.touch_up |
| TOUCH_SHORT / TOUCH_DOUBLE / TOUCH_LONG | touch.tap / touch.double_tap / touch.long_press |
| RECORD_START / RECORD_STOP | audio.record_start / audio.record_stop |
| AUDIO_PLAY_START / AUDIO_PLAY_END | audio.speak_start / audio.speak_end |
| HAPTIC_SHORT / HAPTIC_DOUBLE | haptic.pattern with short / double |
| DISPLAY_EMOTION | pet.emotion with `payload.emotion` |

`DISPLAY_EMOTION` accepts `normal`, `happy`, `shy`, `sad`, `angry`, `curious`, `thinking`, `sleepy`, and `surprised`. The server maps these to its supported display states and leaves active listening or speaking in control of the display. The controls carry state and motor timing. Actual PCM transfer, playback, and Xiaozhi Opus negotiation require separate adapters.

## Virtual ESP32-S3

Run the backend, then run the independent TCP WebSocket client.

```powershell
.\.venv\Scripts\python.exe scripts\virtual_esp32.py --reconnect-demo --watch 15
```

The client simulates Wi-Fi presence, touch, recording, playback, display state, and haptic pulse timing. It sends heartbeats while watching, restores state after reconnect, and prints the control trace and round-trip time. Use `--url` for a different endpoint. Access tokens travel in the Authorization header via `PIXELPET_ACCESS_TOKEN`.

Run `.\.venv\Scripts\python.exe -m pytest tests/test_virtual_esp32.py -q` to exercise a real Uvicorn loopback connection with isolated SQLite and Mock LLM. The test covers timeout and automatic reconnect with a fresh sequence, alongside in-process protocol validation. The network transport is tested on PC. GPIO, radio, I2S, and speaker output remain HW_PENDING.

WebSocket 与 HTTP 共用显式 Host/Origin/远端身份校验。启用访问令牌或使用非回环 Host/远端连接时，必须发送 Authorization: Bearer；禁止 query token，避免凭据出现在 URL 日志。LAN Host 需加入 PIXELPET_ALLOWED_HOSTS；不使用通配符。默认仍绑定127.0.0.1，未修改防火墙。

Example events: touch.touch_down, touch.touch_up, touch.tap, touch.double_tap, touch.long_press, audio.record_start/stop, audio.speak_start/end, pet.state, pet.emotion, haptic.pattern/pulse, clock.tick. Haptic patterns short/double/long produce bounded simulated effect descriptions. No GPIO, browser vibration API, recording or playback is invoked by the engine itself. UI and speech adapters consume effects.

Hold detection: touch_down records a monotonic start, clock.tick after configured threshold starts recording; touch_up stops it. Browser can also send long_press after its hold timer. Debounce and event ID deduplication apply; recording/playback are exclusive, recording suppresses all haptics. Avoid submitting both derived tap events and raw releases for a single gesture; the UI owns gesture recognition. Settings: haptic_enabled (alias haptics), haptic_strength 0..1, quiet_mode, long_press_ms 200..3000, touch_debounce_ms 10..200.

Run `.venv\Scripts\python.exe scripts\mock_device.py` for an isolated in-process real route/socket lifecycle. Optional live mode: install `websockets`, then pass `--url ws://127.0.0.1:8000/api/devices/ws?device_id=mock-client`. This tests control acknowledgements, not sound or Opus packets. `shared/ble-provisioning.json` defines only a prospective BLE GATT data contract; no BLE radio or credential persistence is implemented.
