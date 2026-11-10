#include "voice_turn_state.h"
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
    assert(!dialog.enabled());
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
    VoiceTurnState turn;
    assert(turn.start(VoiceTrigger::Continuous,0));
    assert(turn.capture(false,90000)==CaptureDecision::Continue);
    assert(turn.capture(true,91000)==CaptureDecision::Continue);
    assert(turn.capture(false,92799)==CaptureDecision::Continue);
    assert(turn.capture(false,92800)==CaptureDecision::Send);
    turn.reset();
    assert(turn.start(VoiceTrigger::Continuous,0));
    assert(turn.capture(true,200000)==CaptureDecision::Continue);
    assert(turn.capture(true,215000)==CaptureDecision::Send);
    std::array<int16_t,10> output{};
    PrerollBuffer pre(output.data(),6);
    int16_t a[]={1,2,3,4}, b[]={5,6,7,8};
    pre.append(a,4);pre.append(b,4);
    assert(pre.flatten()==6);
    for(int i=0;i<6;++i)assert(output[i]==i+3);
    assert(pre.flatten()==6);
    for(int i=0;i<6;++i)assert(output[i]==i+3);
}
