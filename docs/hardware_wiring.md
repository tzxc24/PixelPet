# V1 hardware wiring — software frozen, physical unverified

Source: user's complete `E:\Downloads\PixelPet_V1_接线与GPIO定义.md`, dated 2026-11-05. This document is a reviewable proposed harness, not permission to wire unknown power pins. Every physical test remains HW_PENDING.

| Module signal | Planned GPIO | Electrical condition |
| --- | --- | --- |
| INMP441 SCK / WS / SD | 4 / 5 / 6 | 3.3V only; L/R to GND selects left; verify 24-bit alignment in 32-bit I2S slot |
| MAX98357A BCLK / LRC / DIN | 7 / 8 / 9 | Independent TX clocks; board USB5V only after rail/current confirmation; SD/MODE circuit must be checked |
| ST7789 SCL / SI | 14 / 15 | SPI SCLK/MOSI, not I2C; module VCC range unconfirmed |
| ST7789 RST / DC / CS | 16 / 17 / 18 | 240×240 RGB565; offsets/RGB-BGR/rotation pending |
| TTP223 OUT | 13 | 3V3, momentary mode and high-active candidate must be confirmed |
| MOS motor module IN | 21 | No direct motor load on GPIO; driver supply/3.3V threshold/flyback pending |
| ST7789 BL | -1 disabled, GPIO10 reserved | Do not connect BL to GPIO or supply before current limiting/control circuit review |
| ST7789 CS-F | -1 disabled | Font unused, but reliable deselection circuit must be confirmed; never assume floating safe |

SPI SO is unused. All confirmed modules share GND. Speaker connects between amplifier SPK+ and SPK-, never SPK- to ground. Motor follows supplier-rated voltage; no assumed 3V3 regulator capacity. Reserve 11/12 for future I2C,1/2 for future ADC/buttons. Keep USB19/20, strapping0/3/45/46, flash/PSRAM26..37, UART43/44, JTAG39..42 and board-dependent47/48 free.

The JSON is authoritative; the generated header is the only firmware GPIO-definition location. Firmware `board_init`, display, microphone, speaker, touch and haptic implementations are compiled behind a default-disabled activation guard. BL and CS-F have no driver output path. The motor latch is set LOW before enabling its output only after all hardware gates are explicitly approved. Current app startup cannot energize GPIO21.

Before activation: photograph board front/back and identify actual N16R8; verify flash/PSRAM boot report; confirm screen VCC/BL/CS-F; motor voltage/current/threshold/protection; amplifier SD/MODE; inspect polarities and shorts with power off. Bring up one module at a time. Follow `docs/hardware_acceptance.md`; attach dated measurement evidence before any future VERIFIED revision.
