#include "voice_turn_state.h"
#include "voice_activity.h"
#include "dialog_control.h"
#include "preroll_buffer.h"
#include <array>
#include <cassert>
int main() {
    using namespace pixelpet;
    assert(!voice_turn_uses_cues(VoiceTrigger::Continuous));
    assert(voice_turn_uses_cues(VoiceTrigger::Automatic));
    assert(voice_turn_uses_cues(VoiceTrigger::Touch));
    assert(voice_turn_uses_cues(VoiceTrigger::Wake));
    DialogControl dialog;
    assert(!dialog.active());
    assert(dialog.standby() && dialog.enabled());
    dialog.command('d');
    assert(dialog.active());
    dialog.command('r');
    assert(dialog.active());
    dialog.command('c');
    assert(!dialog.active());
    dialog.command('d');
    assert(dialog.apply_state("standby"));
    assert(dialog.standby() && dialog.enabled() && !dialog.active());
    assert(!dialog.apply_state("unknown"));
    assert(dialog.standby());
    assert(dialog.apply_state("active"));
    assert(dialog.active() && !dialog.standby());
    dialog.command('c');
    assert(!dialog.enabled());
    dialog.command('w');
    assert(dialog.standby() && !dialog.active() && dialog.enabled());
    dialog.command('c');
    DialogControl always_listening(false);
    assert(always_listening.active());
    assert(always_listening.apply_state("standby"));
    assert(always_listening.active());
    always_listening.command('w');
    assert(always_listening.active());
    always_listening.command('c');
    assert(!always_listening.enabled());
    always_listening.command('d');
    assert(always_listening.active());
    SpeechActivity follow_up(969.0, 450.0);
    assert(follow_up.threshold() == 450.0);
    assert(!follow_up.observe(520, 0));
    assert(!follow_up.observe(520, 60));
    assert(follow_up.observe(520, 80));
    assert(!follow_up.observe(200, 100));
    VoiceTurnState turn;
    assert(turn.start(VoiceTrigger::Continuous,0));
    assert(turn.capture(false,90000)==CaptureDecision::Continue);
    assert(turn.capture(true,91000)==CaptureDecision::Continue);
    assert(turn.capture(false,92199)==CaptureDecision::Continue);
    assert(turn.capture(false,92200)==CaptureDecision::Send);
    turn.reset();
    assert(turn.start(VoiceTrigger::Continuous,0));
    assert(turn.capture(true,200000)==CaptureDecision::Continue);
    assert(turn.capture(true,215000)==CaptureDecision::Send);
    turn.reset();
    assert(turn.start(VoiceTrigger::Continuous, 0, true));
    assert(turn.capture(true, 1000) == CaptureDecision::Continue);
    assert(turn.capture(false, 2200) == CaptureDecision::Continue);
    assert(turn.capture(false, 2800) == CaptureDecision::Send);
    std::array<int16_t,10> output{};
    PrerollBuffer pre(output.data(),6);
    int16_t a[]={1,2,3,4}, b[]={5,6,7,8};
    pre.append(a,4);pre.append(b,4);
    assert(pre.flatten()==6);
    for(int i=0;i<6;++i)assert(output[i]==i+3);
    assert(pre.flatten()==6);
    for(int i=0;i<6;++i)assert(output[i]==i+3);
}
