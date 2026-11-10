#include "voice_vad.h"
#ifdef CONFIG_PIXELPET_USE_ESP_SR_VAD
#include "esp_vad.h"
#endif

namespace pixelpet {
VoiceVad::VoiceVad(double background_rms)
#ifndef CONFIG_PIXELPET_USE_ESP_SR_VAD
    : activity_(background_rms)
#endif
{
#ifdef CONFIG_PIXELPET_USE_ESP_SR_VAD
    (void)background_rms;
    handle_ = vad_create(VAD_MODE_1);
#endif
}

VoiceVad::~VoiceVad() {
#ifdef CONFIG_PIXELPET_USE_ESP_SR_VAD
    if (handle_) vad_destroy(static_cast<vad_handle_t>(handle_));
#endif
}

bool VoiceVad::ready() const {
#ifdef CONFIG_PIXELPET_USE_ESP_SR_VAD
    return handle_ != nullptr;
#else
    return true;
#endif
}

VoiceDecision VoiceVad::process(int16_t* samples, std::size_t count, int64_t now) {
    if (!ready() || !samples || count != frame_samples) return VoiceDecision::Invalid;
#ifdef CONFIG_PIXELPET_USE_ESP_SR_VAD
    (void)now;
    const auto result = vad_process(static_cast<vad_handle_t>(handle_), samples, 16000, 20);
    if (result == VAD_SPEECH) return VoiceDecision::Speech;
    if (result == VAD_SILENCE) return VoiceDecision::Silence;
    return VoiceDecision::Invalid;
#else
    return activity_.observe(pcm_rms(samples,count),now) ? VoiceDecision::Speech : VoiceDecision::Silence;
#endif
}

const char* VoiceVad::provider() {
#ifdef CONFIG_PIXELPET_USE_ESP_SR_VAD
    return "esp-sr-webrtc-vad";
#else
    return "energy";
#endif
}
}
