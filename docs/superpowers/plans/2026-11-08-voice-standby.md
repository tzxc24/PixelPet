# Voice standby implementation plan
Goal: add voice rest and local-PC wake while preserving conversation and cloud boundary.
Architecture: strict command module, purpose-aware authenticated voice socket, firmware Off/Active/Standby state.
- [x] Write failing phrase and socket privacy/state tests plus C++ state/protocol tests.
- [x] Implement phrase matching and purpose-aware backend processing, deterministic replies, no standby persistence/cloud ASR.
- [x] Implement firmware state and protocol extensions; retain c stop and conversation ID.
- [x] Run targeted/full Python and C++ tests, compile and flash verified app only.
- [ ] Check local Whisper runtime and device standby transport; document manual wake acceptance and limitations.

User steering added full-history transmission and physical-device history/memory UI sync; both deployed and tested. Human rest passed; human wake is still BLOCKED, see output/语音待机与完整历史说明.md.
