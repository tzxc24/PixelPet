# Hardware acceptance checklist — HW_PENDING

Record date, exact board/module IDs, firmware SHA, SDK version, pin configuration and measurement artifacts for each step. Do not mark PASS from a host mock.

1. Power off: photograph module silk labels; verify N16R8 and board revision, check continuity and shared ground. Confirm each rail from manufacturer documentation before USB power. Verify USB enumeration/flashing with a safe upstream board image only after board approval.
2. Connect ST7789 alone after BL circuit review. Test solid colors, checkerboard, all orientations, 240×240 bounds, RGB/BGR, offsets, font CS idle and frame timing. Capture photos and current readings.
3. Connect INMP441 alone at 3.3V. Capture a short local recording; inspect sample rate, L/R slot, bit alignment, noise and clipping. Keep recording data local and explicitly opt in to retaining an acceptance sample.
4. Test MAX98357A with low-amplitude known WAV/test tone. Confirm speaker differential terminals, voltage/current and clipping. Stop on heating or voltage droop.
5. Test TTP223 momentary mode, polarity, short/double/hold/release and bounce; verify one gesture causes one intended effect.
6. Verify MOS driver supply/protection and 3.3V switching threshold with the motor isolated from MCU power as required. Begin with bounded on/off pulses, then PWM only if confirmed supported. Measure noise/reset risk. Recording and quiet mode must suppress pulses.
7. Enable Wi-Fi then BLE separately; test provisioning security and reconnect. Run all modules together while measuring rail dips, task/heap usage and interference.
8. Connect to authenticated LAN gateway. Only after native protocol capture/replay passes, test touch -> recording -> ASR -> DeepSeek -> SQLite recall -> TTS -> speaker -> expression. Check half duplex and dropped connections.
9. Run soak/USB power stability tests and record reset count, memory use and thermal behavior before enclosure design.

Current evidence: portable C++ host core assertions and Python mock control tests only. Screen illumination, microphone/speaker audibility, TTP223, PWM, radio operation, native xiaozhi compatibility and full device voice loop are untested.
