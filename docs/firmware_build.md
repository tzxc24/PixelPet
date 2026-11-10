# ESP32-S3 firmware build evidence

Date: 2026-11-05. Target esp32s3. Hardware status remains HW_PENDING. The previous absent-SDK blocker was followed by a real installation attempt after the user's GPIO instruction; source and tools are now installed under D:\PixelPet\tmp.

Official [Windows setup](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/get-started/windows-setup.html) currently identifies v6.1 as stable and recommends EIM for new installations. This task used its legacy tool script for an isolated, unattended D-drive install; no system-wide installer or firmware flash was run. The inspected APIs are the official [I2S standard driver](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/i2s.html) and [SPI LCD driver](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/lcd/spi_lcd.html).

Source: shallow `git clone --depth 1 --branch v6.1 https://github.com/espressif/esp-idf.git tmp/esp-idf`, exact commit fff9895c82d744c7237be8847347bdd1b07c6643. Shallow recursive submodules initialized. Required esp32s3 tools installed with `tools/idf_tools.py install --targets esp32s3`, including Xtensa GCC esp-15.2.0_20251204, CMake4.0.3 and Ninja1.12.1. `install-python-env` created idf6.1_py3.10_env. Logs: output/idf-install.log, idf-submodules.log, idf-python-install.log.

Use an ESP-IDF terminal configured for this D-drive installation, or export the environment through `tools/idf_tools.py export --format key-value` with IDF_PATH=D:\PixelPet\tmp\esp-idf and IDF_TOOLS_PATH=D:\PixelPet\tmp\idf-tools. Keep TEMP/TMP/PIP_CACHE_DIR in D:\PixelPet\tmp. Then:

```powershell
.\tmp\idf-tools\python_env\idf6.1_py3.10_env\Scripts\python.exe tmp\esp-idf\tools\idf.py -C firmware\pixelpet_s3 -B D:/PixelPet/tmp/firmware-build set-target esp32s3 build
```

Actual build output: output/firmware-idf-build.log; process exit: output/firmware-idf-build.exit. Binary outputs remain in tmp/firmware-build for inspection; no flash operation is authorized or performed. Build result will be appended after completion.

The current sdkconfig declares ESP32-S3 and 16MB Flash; actual Flash/PSRAM identification and Octal PSRAM initialization remain HW_PENDING. No claim is made that the third-party board's memory configuration has been recognized. Host assertions test pure state/pin policies and disabled physical drivers. The native build type-checks and links physical API calls even though runtime activation defaults false. BL and CS-F have no enabled IO path. Motor PWM is not enabled; bounded on/off pulses require all electrical approval gates. Driver init functions do not implement full display-animation tasks, Wi-Fi/BLE provisioning or native xiaozhi protocol compatibility.

## Actual result

PASS: final native ESP32-S3 build completed with process exit 0. `output/firmware-idf-build-final.log` contains `Project build complete`; `output/firmware-idf-build-final.exit` is 0. Image: tmp/firmware-build/pixelpet_s3_scaffold.bin, 250192 bytes (0x3d150), 76% of default 1MiB app partition free. Bootloader 0x5280 bytes. No flash or hardware connection occurred. The first build exposed GPIO enum and C++ sample-rate narrowing issues, corrected in the driver; first-attempt log retained. The later completion-callback signature mismatch was corrected and its failed log retained as firmware-idf-build-sync-first-attempt.log.

The display API now fences each color transaction using the ESP-IDF completion callback, binary semaphore and display mutex. `display_region` returns only after DMA completion, so callers may release the supplied buffer after return. The wait has no timeout: failed hardware/interrupt delivery may stall the caller and needs real fault/soak validation before production use.

Recording lifecycle: call `microphone_begin_recording`, then one or more `microphone_read`, finally `microphone_end_recording`. A portable shared mutex interlock synchronously switches the motor LOW before capture begins; new haptic starts are blocked during capture and an in-flight pulse is canceled. Capture reads without an active lifecycle return invalid-state. Host concurrency tests verify this state/callback ordering; actual acoustic settling delay, GPIO timing, amplifier echo control and motor current remain HW_PENDING. The caller's quiet flag is sampled when a pulse is requested; dynamic quiet cancellation and a full firmware scheduler remain pending integration.

Portable tests: original pure state core, disabled physical driver assertions, and multithread recording/motor cancellation assertions all compile and run with g++ exit0. Python pinmap validation: 28 passed. Rebuild with `powershell -ExecutionPolicy Bypass -File firmware\build.ps1` from the project; the script resolves the D-drive project paths and exports the installed tool environment without changing system-wide settings.
