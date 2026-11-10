#include "voice_vad.h"
#include "esp_vad.h"
#include <array>
#include <cassert>
struct FakeVad {};
static FakeVad instance;
static int created=0,destroyed=0,processed=0;
static bool allocation_failed=false;
extern "C" vad_handle_t vad_create(vad_mode_t mode) {
    assert(mode==VAD_MODE_1);
    ++created;
    return allocation_failed?nullptr:&instance;
}
extern "C" vad_state_t vad_process(vad_handle_t handle,int16_t* data,int rate,int frame_ms) {
    assert(handle==&instance && rate==16000 && frame_ms==20);
    ++processed;
    return data[0]?VAD_SPEECH:VAD_SILENCE;
}
extern "C" void vad_destroy(vad_handle_t handle) {
    assert(handle==&instance);
    ++destroyed;
}
int main() {
    using namespace pixelpet;
    std::array<int16_t,VoiceVad::frame_samples> frame{};
    {
        VoiceVad vad(100);
        assert(vad.ready());
        assert(vad.process(nullptr,frame.size(),0)==VoiceDecision::Invalid);
        assert(vad.process(frame.data(),frame.size()-1,0)==VoiceDecision::Invalid);
        assert(processed==0);
        assert(vad.process(frame.data(),frame.size(),0)==VoiceDecision::Silence);
        frame[0]=1000;
        assert(vad.process(frame.data(),frame.size(),20)==VoiceDecision::Speech);
    }
    assert(created==1 && destroyed==1 && processed==2);
    allocation_failed=true;
    {
        VoiceVad vad(100);
        assert(!vad.ready());
        assert(vad.process(frame.data(),frame.size(),0)==VoiceDecision::Invalid);
    }
    assert(created==2 && destroyed==1);
}
