#include "voice_turn_state.h"
#include <cassert>

int main() {
    using namespace pixelpet;
    VoiceTurnState turn;
    assert(turn.start(VoiceTrigger::Wake, 100));
    assert(!turn.start(VoiceTrigger::Touch, 200));
    assert(turn.capture(false, 6099) == CaptureDecision::Continue);
    assert(turn.capture(false, 6100) == CaptureDecision::Cancel);
    turn.reset();
    assert(turn.start(VoiceTrigger::Wake, 10000));
    assert(turn.capture(true, 10500) == CaptureDecision::Continue);
    assert(turn.capture(false, 11699) == CaptureDecision::Continue);
    assert(turn.capture(false, 11700) == CaptureDecision::Send);
    assert(turn.think());
    assert(turn.play());
    assert(!turn.start(VoiceTrigger::Wake, 11800));
    turn.reset(); // Socket lost during playback; a new turn can begin.
    assert(turn.start(VoiceTrigger::Touch, 12000));
    assert(turn.capture(false, 18000) == CaptureDecision::Continue);
    assert(turn.capture(false, 32000) == CaptureDecision::Send);
    turn.reset(); // Socket lost during upload.
    assert(!turn.play());
    assert(turn.start(VoiceTrigger::Wake, 33000));
    assert(turn.capture(true, 48000) == CaptureDecision::Send);
}
