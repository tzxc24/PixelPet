#pragma once
#include "pet_core.h"
#include "../../main/board/pixelpet_pin_config.h"
// Planned mapping is available for software inspection; it never grants approval.
inline pixelpet::BoardConfig pixelpet_v1_candidate_config() {
 pixelpet::BoardConfig c;
 using B=pixelpet::BoardConfig;
 c.pins[B::MIC_BCLK]=PIXELPET_PIN_MIC_BCLK; c.pins[B::MIC_WS]=PIXELPET_PIN_MIC_WS; c.pins[B::MIC_DIN]=PIXELPET_PIN_MIC_DIN;
 c.pins[B::SPK_BCLK]=PIXELPET_PIN_SPEAKER_BCLK; c.pins[B::SPK_WS]=PIXELPET_PIN_SPEAKER_WS; c.pins[B::SPK_DOUT]=PIXELPET_PIN_SPEAKER_DOUT;
 c.pins[B::SCK]=PIXELPET_PIN_DISPLAY_SCK; c.pins[B::MOSI]=PIXELPET_PIN_DISPLAY_MOSI; c.pins[B::RST]=PIXELPET_PIN_DISPLAY_RST;
 c.pins[B::DC]=PIXELPET_PIN_DISPLAY_DC; c.pins[B::CS]=PIXELPET_PIN_DISPLAY_CS; c.pins[B::TOUCH]=PIXELPET_PIN_TOUCH; c.pins[B::MOTOR]=PIXELPET_PIN_MOTOR;
 c.pins[B::BL]=PIXELPET_PIN_DISPLAY_BL; c.pins[B::FONT_CS]=PIXELPET_PIN_DISPLAY_FONT_CS;
 c.approved=PIXELPET_HARDWARE_ENABLED;
 return c;
}
inline pixelpet::BoardConfig pixelpet_board_config() { return pixelpet_v1_candidate_config(); }

#include "speaker_gate.h"
#ifndef PIXELPET_HOST_MOCK
#include "sdkconfig.h"
#endif

inline bool pixelpet_speaker_test_enabled() {
#if defined(CONFIG_PIXELPET_BOOT_SPEAKER) && defined(CONFIG_PIXELPET_SPEAKER_WIRING_CONFIRMED)
 return pixelpet::speaker_test_allowed(true, true, PIXELPET_PIN_SPEAKER_BCLK,
                                      PIXELPET_PIN_SPEAKER_WS, PIXELPET_PIN_SPEAKER_DOUT);
#else
 return false;
#endif
}

inline bool pixelpet_microphone_test_enabled() {
#if defined(CONFIG_PIXELPET_BOOT_MICROPHONE) && defined(CONFIG_PIXELPET_MICROPHONE_WIRING_CONFIRMED)
 pixelpet::BoardConfig microphone;
 microphone.approved = true;
 microphone.pins[pixelpet::BoardConfig::MIC_BCLK] = PIXELPET_PIN_MIC_BCLK;
 microphone.pins[pixelpet::BoardConfig::MIC_WS] = PIXELPET_PIN_MIC_WS;
 microphone.pins[pixelpet::BoardConfig::MIC_DIN] = PIXELPET_PIN_MIC_DIN;
 return PIXELPET_PIN_MIC_BCLK >= 0 && PIXELPET_PIN_MIC_WS >= 0 &&
        PIXELPET_PIN_MIC_DIN >= 0 && microphone.validate();
#else
 return false;
#endif
}

inline bool pixelpet_network_audio_enabled() {
#if defined(CONFIG_PIXELPET_BOOT_NETWORK) && defined(CONFIG_PIXELPET_NETWORK_AUDIO_CONFIRMED)
 auto audio = pixelpet_v1_candidate_config();
 using B = pixelpet::BoardConfig;
 pixelpet::BoardConfig selected;
 selected.approved = true;
 for (auto signal : {B::MIC_BCLK, B::MIC_WS, B::MIC_DIN,
                     B::SPK_BCLK, B::SPK_WS, B::SPK_DOUT}) {
  if (audio.pins[signal] < 0) return false;
  selected.pins[signal] = audio.pins[signal];
 }
 return selected.validate();
#else
 return false;
#endif
}
