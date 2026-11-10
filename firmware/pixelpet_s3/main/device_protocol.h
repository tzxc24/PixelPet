#pragma once
#include "pet_core.h"
#include <cstdint>
#include <string_view>

namespace pixelpet {
enum class Reply { Invalid, Connected, Ack, Error };
struct ServerFrame {
    Reply reply = Reply::Invalid;
    State state = State::IDLE;
    bool has_state = false;
};

// expected_sequence 0 is reserved for the greeting before any client message.
ServerFrame read_server_frame(std::string_view json, uint32_t expected_sequence);
struct VoiceReply {
    std::string_view type;
    std::string_view session;
    std::string_view conversation;
    uint32_t bytes = 0;
    bool pcm_output = false;
    std::string_view dialog_state;
    std::string_view error_code;
};
VoiceReply read_voice_reply(std::string_view json);
}
