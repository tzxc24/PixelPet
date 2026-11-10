#pragma once
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>

namespace pixelpet {
inline double pcm_rms(const int16_t* samples, std::size_t count) {
    if (!count) return 0;
    double sum = 0, energy = 0;
    for (std::size_t i = 0; i < count; ++i) {
        sum += samples[i];
        energy += double(samples[i]) * samples[i];
    }
    const double mean = sum / count;
    return std::sqrt(std::max(0.0, energy / count - mean * mean));
}

class SpeechActivity {
    double threshold_;
    int64_t candidate_ = -1;
public:
    explicit SpeechActivity(double noise_rms)
        : threshold_(std::clamp(noise_rms * 3.0, 250.0, 3000.0)) {}

    bool observe(double rms, int64_t now) {
        if (rms < threshold_) { candidate_ = -1; return false; }
        if (candidate_ < 0) candidate_ = now;
        return now - candidate_ >= 80;
    }
    double threshold() const { return threshold_; }
};
}
