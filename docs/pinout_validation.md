# Pinout validation — 2026-11-05

Status: SOFTWARE_PINMAP_FROZEN / PHYSICAL_PINOUT_UNVERIFIED. The complete user source `E:\Downloads\PixelPet_V1_接线与GPIO定义.md` was read. The named companion original header and JSON were not present; this project's JSON/header are derived artifacts, not imported originals.

Single source: `hardware/pinmap.json`. Generate `firmware/main/board/pixelpet_pin_config.h` using `.venv\Scripts\python.exe scripts\generate_pinmap.py`; verify with `--check`. Existing ESP-IDF board code includes the generated central header. The old candidate YAML now points to the JSON rather than duplicating GPIO constants. The unassigned pins.example.yaml is an optional template, not the selected V1 profile.

The previous screenshot candidate and complete Markdown agree on all 13 active planned signals: microphone 4/5/6, speaker 7/8/9, display SCK14/MOSI15/RST16/DC17/CS18, touch13, motor21. Previous BL=-1 and CS-F=-1 remain disabled; reserve BL10 without wiring or output activation. No contradictory active mapping required migration. Original candidate literals were removed from board_config.h.

Automated guards detect duplicates; invalid GPIO; strapping 0/3/45/46; USB19/20; flash/PSRAM26..37; unavailable22..25; reserved debug39..44 and board-dependent47/48; future I2C11/12 and ADC1/2; BL10 reservation. Unverified BL and CS-F cannot be assigned in the V1 generator. Hardware activation requires explicit electrical, CS-F isolation, and motor threshold/supply reviews; defaults all false. This protects current software configuration, not arbitrary physical wiring.

Tests: `tests/test_pinmap.py` includes mutation tests for prohibited pins, duplicate assignment, disabled signals, activation guard, and byte-for-byte JSON/header consistency. Host disabled-driver tests assert every init is gated and no hardware signal is driven. They cannot validate module voltage, PSRAM, BL circuitry, color order, sampling alignment, actual GPIO breakout or motor safety.

The native ESP32-S3 build now passes using the isolated v6.1 SDK; see firmware_build.md and output/firmware-idf-build-final.log. This updates only software build status. All checks in the physical register remain pending. The driver capture/motor interlock and synchronous LCD DMA fence have portable tests and a successful native compile, not electrical measurements.
