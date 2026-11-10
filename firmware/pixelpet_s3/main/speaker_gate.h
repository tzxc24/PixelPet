#pragma once
#include "pet_core.h"

namespace pixelpet {
inline bool speaker_test_allowed(bool speaker_mode, bool wiring_confirmed,
                                 int bclk, int ws, int data) {
    BoardConfig speaker;
    speaker.approved = wiring_confirmed;
    speaker.pins[BoardConfig::SPK_BCLK] = bclk;
    speaker.pins[BoardConfig::SPK_WS] = ws;
    speaker.pins[BoardConfig::SPK_DOUT] = data;
    return speaker_mode && wiring_confirmed &&
           bclk >= 0 && ws >= 0 && data >= 0 && speaker.validate();
}
}
