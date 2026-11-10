#include "device_protocol.h"
#include <cassert>

using pixelpet::read_server_frame;
using pixelpet::Reply;
using pixelpet::State;

int main() {
    const auto sleeping = pixelpet::read_voice_reply(R"({"type":"dialog.state","session_id":"abcd","dialog_state":"standby"})");
    assert(sleeping.dialog_state == "standby");
    assert(pixelpet::read_voice_reply(R"({"type":"error","code":"no_speech"})").error_code == "no_speech");
    assert(read_server_frame(R"({"version":1,"type":"device.connected","protocol":"pixelpet-business-v1"})", 0).reply == Reply::Connected);
    assert(read_server_frame(R"({"version":1,"type":"device.connected","protocol":"xiaozhi"})", 0).reply == Reply::Invalid);
    const auto ack = read_server_frame(R"({"version":1,"type":"ack","seq":2,"effects":[{"payload":{"state":"ERROR","seq":8}}],"pet":{"state":"LISTENING"}})", 2);
    assert(ack.reply == Reply::Ack && ack.has_state && ack.state == State::LISTENING);
    assert(read_server_frame(R"({"version":1,"type":"ack","seq":2,"pet":{"state":"INVALID"}})", 2).has_state == false);
    assert(read_server_frame(R"({"version":1,"type":"ack","seq":2})", 3).reply == Reply::Invalid);
    assert(read_server_frame(R"({"version":1,"type":"ack","seq":"2"})", 2).reply == Reply::Invalid);
    assert(read_server_frame(R"({"version":1,"type":"ack","seq":2,"seq":2})", 2).reply == Reply::Invalid);
    assert(read_server_frame(R"({"version":1,"type":"error","seq":2,"payload":{"code":"invalid_event"}})", 2).reply == Reply::Error);
    assert(read_server_frame(R"({"version":1,"type":"ack","seq":2} {})", 2).reply == Reply::Invalid);
    assert(read_server_frame(R"({"version":1,"type":"ack","seq":2)", 2).reply == Reply::Invalid);
    const auto pcm = pixelpet::read_voice_reply(R"({"type":"playback.start","session_id":"abcd","conversation_id":"9876","sample_rate":24000,"channels":1,"format":"pcm_s16le","byte_count":4096})");
    assert(pcm.type == "playback.start" && pcm.session == "abcd" && pcm.conversation == "9876");
    assert(pcm.pcm_output && pcm.bytes == 4096);
    assert(!pixelpet::read_voice_reply(R"({"type":"playback.start","sample_rate":16000,"channels":1,"format":"pcm_s16le"})").pcm_output);
    assert(!pixelpet::read_voice_reply(R"({"type":"playback.start","sample_rate":24000,"channels":2,"format":"opus"})").pcm_output);
}
