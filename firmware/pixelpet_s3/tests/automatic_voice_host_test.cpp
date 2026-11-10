#include "voice_turn_state.h"
#include "voice_activity.h"
#include <cassert>
#include <cstdint>
int main() {
    using namespace pixelpet;
    VoiceTurnState turn;
    assert(turn.start(VoiceTrigger::Automatic, 0));
    assert(turn.capture(false, 7999) == CaptureDecision::Continue);
    assert(turn.capture(false, 8000) == CaptureDecision::Cancel);
    turn.reset();
    assert(turn.start(VoiceTrigger::Automatic, 0));
    assert(turn.capture(true, 2000) == CaptureDecision::Continue);
    assert(turn.capture(false, 3799) == CaptureDecision::Continue);
    assert(turn.capture(false, 3800) == CaptureDecision::Send);
    turn.reset();
    assert(turn.start(VoiceTrigger::Automatic, 0));
    assert(turn.capture(true, 15000) == CaptureDecision::Send);
    SpeechActivity gate(40);
    assert(!gate.observe(100, 0));
    assert(!gate.observe(700, 100));
    assert(!gate.observe(80, 116)); // One loud frame does not count as speech.
    assert(!gate.observe(700, 200));
    assert(gate.observe(700, 280));
    assert(!gate.observe(40, 296));
    int16_t dc[] = {500, 500, 500, 500};
    assert(pcm_rms(dc, 4) == 0);
    int16_t wave[] = {-1000,1000,-1000,1000};
    assert(pcm_rms(wave,4) > 999);
}
