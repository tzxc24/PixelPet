# PixelPet S3 guarded driver project

## V1.1 gated PCM voice path

The default firmware keeps the unapproved GPIO gate disabled and uses the original JSON control endpoint. After board and electrical approval, successful touch and I2S initialization selects `/api/devices/voice/ws`. A touch and release starts recording. The next touch and release submits it. Touch while waiting for or playing the response cancels the turn and reconnects to discard queued data. Disconnects close the active turn. The latest validated conversation ID stays in RAM across reconnects.

The client streams microphone PCM16LE mono at 16 kHz in up to 512 samples per message, capped at 20 seconds. Each frame begins with the 16 raw session ID bytes and a big-endian 32-bit frame index. I2S uses an independent RX controller with a 32-bit left slot, converted to signed 16-bit samples. The microphone channel is enabled only during capture. Playback accepts PCM16LE mono at 24 kHz, checks session, frame order and declared byte count, and streams through the TX DMA ring. Idle and underrun output is zero-filled. The negotiated format is fixed for this client, so there is no sample-rate conversion on board. Volume is applied by the server.

The network task has a 12288-byte configured stack and one reusable 16 KiB message buffer. Mic staging is 1024 bytes of stack in the I2S read helper. Octal PSRAM is configured at 40 MHz with absent-device boot fallback. Actual PSRAM, stack high-water, I2S alignment, frame timing and playback quality are HW_PENDING. Serial diagnostics show free internal and PSRAM heap and the network task high-water mark. The PCM path does not render display animations, drive RMS mouth frames or map touch feedback to motor patterns.

Status **HW_PENDING** for all physical operations. This standalone ESP-IDF project implements SPI ST7789, standard I2S RX/TX, GPIO touch and MOS control APIs, with the generated hardware gate disabled. The default boot mode implements Wi-Fi station reconnect and the PixelPet business WebSocket protocol. Native xiaozhi Opus gateway and BLE provisioning remain pending.

The single source is `hardware/pinmap.json`; generate the requested central `firmware/main/board/pixelpet_pin_config.h` with `scripts/generate_pinmap.py`. Never edit the generated header. BL is disabled (-1) with GPIO10 reserved; font CS disabled (-1), requiring verified external deselection before display activation. Motor supply and threshold must be confirmed. No hardware has been flashed or tested.

Build and host tests from repository root (Windows, ESP-IDF v6.1 and MinGW):

```powershell
.\.venv\Scripts\python.exe scripts\generate_pinmap.py --check
powershell -NoProfile -ExecutionPolicy Bypass -File firmware\build.ps1
cmake -S firmware/pixelpet_s3/tests -B tmp/firmware-host-final -G "MinGW Makefiles"
cmake --build tmp/firmware-host-final
ctest --test-dir tmp/firmware-host-final --output-on-failure
```

See `docs/firmware_build.md` for the actual ESP-IDF install/build evidence and reproducible D-drive commands. No hardware output is enabled by compilation.

## Wi-Fi and business WebSocket

Default boot mode reads a `pixelpet` NVS namespace. A missing configuration exits with an `HW_PENDING` log. The network endpoint becomes active after local provisioning and DHCP. The control client sends `hello` and heartbeats every eight seconds to `/api/devices/ws` with a MAC-derived ID. It correlates `ack`/`error` by `seq`, validates the protocol greeting, consumes `pet.state`, bounds reads to 16 KiB and four seconds, and retries with one to sixteen seconds of backoff. The separate gated PCM endpoint handles recorded and synthesized audio as described above.

Provisioning keys for a future board, using the IDF NVS partition generator and the board's verified partition table:

| Key | NVS type | Purpose |
| --- | --- | --- |
| `ssid` | string | WPA2-or-better Wi-Fi SSID, up to 32 bytes |
| `password` | string | Wi-Fi passphrase, 8–64 bytes |
| `host` | string | PC LAN IPv4 address or DNS host, no URL or port |
| `port` | u16 | PC service/proxy port, default 8765 |
| `token` | string | Local PixelPet device access bearer token, up to 192 bytes. Use a dedicated token, separate from the LLM key |
| `ca_pem` | string | Trusted CA PEM for WSS, up to 4096 bytes |
| `plain_ws` | u8 | Explicit `1` enables plain WS for isolated LAN bring-up. Default `0` requires a CA and uses WSS |

Keep actual provisioning CSV and NVS images private under the project's `tmp` directory. NVS provisioning replaces that partition, so confirm the correct partition and back up its contents before writing. Plain WS carries the device access token over LAN without TLS. Firmware suppresses WebSocket transport request logging because SDK transport error logs may contain request headers. The PC service needs explicit LAN binding, host allow-list and its matching device access token. This is a text business socket; it carries no raw microphone or speaker bytes. Wi-Fi association, WSS setup and reconnection on ESP32-S3 are **HW_PENDING**. The upstream [ESP-IDF station lifecycle](https://docs.espressif.com/projects/esp-idf/en/latest/esp32s3/api-guides/wifi-driver/station-scenarios.html) describes how socket setup follows DHCP.

WSS configures certificate chain and hostname checks. The current SDK build has `CONFIG_MBEDTLS_HAVE_TIME_DATE` disabled, so it skips certificate validity dates. Clock provisioning and a date-checking WSS build are **HW_PENDING** for production deployment.

## Isolated hardware checks

After checking electrical limits and approving the centralized pinmap, select exactly one mode under **PixelPet firmware → Boot mode** in ESP-IDF `menuconfig`. A smoke mode initializes only its selected driver and exits once complete. The pinmap gate is still checked before each mode and each physical driver operation.

| Mode | Observation to verify on the board |
| --- | --- |
| ST7789 | Four horizontal red, green, blue and white bands. Verify panel orientation, color order and offsets |
| ST7789 local animation | A 64×64 face tile updates at approximately 10 FPS for four seconds. Check colors and partial redraw |
| Serial / PSRAM probe | Reports external RAM heap size and checks a 16 KiB allocation with a known pattern |
| Wi-Fi association only | Uses NVS SSID and password, reports whether DHCP completed, then stops the radio |
| INMP441 | Captures up to 4096 mono samples at 16 kHz and logs sample count and peak only. Verify left-channel data alignment and reaction to quiet speech |
| MAX98357A | One low-amplitude 440 Hz tone for 250 ms followed by silence at 24 kHz mono PCM. Verify clean output with the correct speaker wiring |
| TTP223 | Logs press/release transitions for about 15 s. Verify polarity and timing |
| MOS motor | One nominal 70 ms pulse measured against the monotonic timer, with RTOS scheduling granularity. Verify pulse length, external supply, protection and 3.3 V control before selecting this mode |

Leave the default disabled gate and current GPIO assignments in place during PC-only development. Use `docs/hardware_wiring.md` for module-by-module bring-up.

## Later upstream board extension

Reference [pinned custom-board guide](https://github.com/78/xiaozhi-esp32/blob/a73e9a7e266e3196d1368ba46c30bee0d81f0a64/docs/custom-board.md). In a separately checked-out pinned upstream, add a unique `main/boards/pixelpet-s3` directory with its own config.h, config.json, board source and README; register its unique board type through upstream CMake/Kconfig and DECLARE_BOARD. Never overwrite a vendor board. Board identity controls OTA behavior.

The inspected NoAudioCodecSimplex API supports separate mic/speaker clock/data parameters and is a future integration candidate. MAX98357A is an I2S amplifier. Upstream board registration, display state rendering and native codec/network gateway are separate integration work. The vendored lightweight JSON tokenizer is [jsmn v1.1.0](https://github.com/zserge/jsmn/tree/v1.1.0), with its MIT license in `main/vendor/jsmn/LICENSE`.

### Voice wake preparation and hardware checks

The network voice turn now shares a capture, thinking and playback state machine.
Host tests inject a wake trigger and check the 6 s no-speech cancellation, 1.2 s
silence cutoff after speech, 15 s wake capture cap, and reset after interruption.
The shipping firmware still starts turns from touch. A board-side keyword detector
and microphone threshold calibration are HW_PENDING.

From the project root in a VS Code terminal, run
`powershell -NoProfile -ExecutionPolicy Bypass -File firmware/build.ps1 -Action menuconfig`.
Under **PixelPet firmware > Boot mode**, select one check at a time. After checking
the board wiring and approving the hardware gate, build and flash to the verified
COM port, then open Monitor with the same script and `-Action monitor -Port COMn`.

- ST7789 color bars show red, green, blue and white for checking orientation and color order.
- INMP441 capture reports sample count and peak. Compare quiet and speech runs.
- MAX98357A plays a brief low-amplitude tone. Check the speaker connection first.
- TTP223 logs press and release transitions.
- The motor check remains gated and uses one short pulse. Leave the backlight and
  motor disconnected while their electrical requirements are unresolved.

Return to the WebSocket boot mode after testing. For hardware fault injection,
disconnect Wi-Fi during capture and during playback separately, then restore it.
Check the reconnect log, start a fresh touch turn and verify that the previous
audio is not replayed. Repeat with a PC service restart. These checks are HW_PENDING.
