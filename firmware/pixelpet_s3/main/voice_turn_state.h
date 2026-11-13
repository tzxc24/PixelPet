#pragma once
#include <cstdint>

namespace pixelpet {
enum class VoiceTrigger { Touch, Wake, Automatic, Continuous };
// Continuous listening uses VAD endpoints without per-turn audible prompts.
inline bool voice_turn_uses_cues(VoiceTrigger trigger) {
    return trigger != VoiceTrigger::Continuous;
}

enum class CaptureDecision { Continue, Send, Cancel };
inline constexpr int continuous_silence_ms = 1200;
inline constexpr int standby_silence_ms = 1800;

class VoiceTurnState {
    enum class Phase { Idle, Capture, Thinking, Playback };
    Phase phase_ = Phase::Idle;
    VoiceTrigger trigger_ = VoiceTrigger::Touch;
    int64_t started_ = 0;
    int64_t last_speech_ = -1;
    int64_t first_speech_ = -1;
    bool standby_ = false;

public:
    bool start(VoiceTrigger trigger, int64_t now, bool standby = false) {
        if (phase_ != Phase::Idle) return false;
        trigger_ = trigger;
        standby_ = standby;
        started_ = now;
        last_speech_ = -1;
        first_speech_ = -1;
        phase_ = Phase::Capture;
        return true;
    }

    CaptureDecision capture(bool speech, int64_t now) {
        if (phase_ != Phase::Capture) return CaptureDecision::Cancel;
        if (trigger_ == VoiceTrigger::Touch)
            return now - started_ >= 20000 ? CaptureDecision::Send : CaptureDecision::Continue;
        if (speech) {
            last_speech_ = now;
            if (first_speech_ < 0) first_speech_ = now;
        }
        if (trigger_ == VoiceTrigger::Continuous) {
            if (first_speech_ < 0) return CaptureDecision::Continue;
            return now-first_speech_ >= 15000 || now-last_speech_ >= (standby_ ? standby_silence_ms : continuous_silence_ms)
                ? CaptureDecision::Send : CaptureDecision::Continue;
        }
        const auto no_speech_timeout = trigger_ == VoiceTrigger::Automatic ? 8000 : 6000;
        const auto silence_timeout = trigger_ == VoiceTrigger::Automatic ? 1800 : 1200;
        if (last_speech_ < 0)
            return now - started_ >= no_speech_timeout ? CaptureDecision::Cancel : CaptureDecision::Continue;
        return now - started_ >= 15000 || now - last_speech_ >= silence_timeout
            ? CaptureDecision::Send : CaptureDecision::Continue;
    }

    bool think() {
        if (phase_ != Phase::Capture) return false;
        phase_ = Phase::Thinking;
        return true;
    }

    bool play() {
        if (phase_ != Phase::Thinking) return false;
        phase_ = Phase::Playback;
        return true;
    }

    void reset() { phase_ = Phase::Idle; }
};
}
