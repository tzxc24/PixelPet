#pragma once
#include <cstddef>
#include <cstdint>
#ifndef PIXELPET_VAD_HOST_TEST
#include "sdkconfig.h"
#endif
#ifndef CONFIG_PIXELPET_USE_ESP_SR_VAD
#include "voice_activity.h"
#endif

namespace pixelpet {
enum class VoiceDecision { Invalid, Silence, Speech };

class VoiceVad {
public:
    static constexpr std::size_t frame_samples = 320;
    explicit VoiceVad(double background_rms);
    ~VoiceVad();
    VoiceVad(const VoiceVad&) = delete;
    VoiceVad& operator=(const VoiceVad&) = delete;
    bool ready() const;
    VoiceDecision process(int16_t* samples, std::size_t count, int64_t now);
    static const char* provider();
private:
#ifdef CONFIG_PIXELPET_USE_ESP_SR_VAD
    void* handle_ = nullptr;
#else
    SpeechActivity activity_;
#endif
};
}
