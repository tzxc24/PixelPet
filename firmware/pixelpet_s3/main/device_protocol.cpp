#include "device_protocol.h"
#define JSMN_STATIC
#define JSMN_STRICT
#include "vendor/jsmn/jsmn.h"
#include <array>
#include <charconv>
#include <utility>

namespace pixelpet {
namespace {
class FrameTokens {
    std::string_view json_;
    std::array<jsmntok_t, 192> tokens_{};
    int count_ = 0;

public:
    explicit FrameTokens(std::string_view json) : json_(json) {
        jsmn_parser parser;
        jsmn_init(&parser);
        count_ = jsmn_parse(&parser, json.data(), json.size(), tokens_.data(), tokens_.size());
    }

    bool valid() const {
        return count_ > 0 && tokens_[0].type == JSMN_OBJECT &&
               json_.find_first_not_of(" \t\r\n", tokens_[0].end) == std::string_view::npos;
    }

    int field(int object, std::string_view name) const {
        if (object < 0 || tokens_[object].type != JSMN_OBJECT) return -1;
        int match = -1;
        for (int key = object + 1; key < count_ && tokens_[key].start < tokens_[object].end;) {
            const int value = key + 1;
            if (tokens_[key].type != JSMN_STRING || value >= count_ || tokens_[value].start >= tokens_[object].end) return -1;
            if (text(key) == name) {
                if (match >= 0) return -1;
                match = value;
            }
            key = value + 1;
            while (key < count_ && tokens_[key].start < tokens_[value].end) ++key;
        }
        return match;
    }

    std::string_view string(int index) const {
        return index >= 0 && tokens_[index].type == JSMN_STRING ? text(index) : std::string_view{};
    }

    bool number(int index, uint32_t& parsed) const {
        if (index < 0 || tokens_[index].type != JSMN_PRIMITIVE) return false;
        const auto value = text(index);
        const auto end = value.data() + value.size();
        const auto result = std::from_chars(value.data(), end, parsed);
        return result.ec == std::errc{} && result.ptr == end;
    }

    bool is_number(int index, uint32_t expected) const {
        uint32_t parsed = 0;
        return number(index, parsed) && parsed == expected;
    }

private:
    std::string_view text(int index) const {
        return json_.substr(tokens_[index].start, tokens_[index].end - tokens_[index].start);
    }
};
}

ServerFrame read_server_frame(std::string_view json, uint32_t expected_sequence) {
    const FrameTokens frame(json);
    if (!frame.valid() || !frame.is_number(frame.field(0, "version"), 1)) return {};
    const auto type = frame.string(frame.field(0, "type"));
    if (expected_sequence == 0) {
        return type == "device.connected" && frame.string(frame.field(0, "protocol")) == "pixelpet-business-v1"
            ? ServerFrame{Reply::Connected} : ServerFrame{};
    }
    if (!frame.is_number(frame.field(0, "seq"), expected_sequence)) return {};
    if (type == "error") return {Reply::Error};
    if (type != "ack") return {};
    const auto state = frame.string(frame.field(frame.field(0, "pet"), "state"));
    constexpr std::pair<std::string_view, State> states[] = {
        {"IDLE", State::IDLE}, {"LISTENING", State::LISTENING}, {"THINKING", State::THINKING},
        {"SPEAKING", State::SPEAKING}, {"SLEEP", State::SLEEP}, {"HAPPY", State::HAPPY},
        {"SHY", State::SHY}, {"SURPRISED", State::SURPRISED}, {"ANNOYED", State::ANNOYED}, {"ERROR", State::ERROR},
    };
    for (const auto& [name, value] : states) {
        if (state == name) return {Reply::Ack, value, true};
    }
    return {Reply::Ack};
}

VoiceReply read_voice_reply(std::string_view json) {
    const FrameTokens frame(json);
    if (!frame.valid()) return {};
    uint32_t bytes = 0;
    frame.number(frame.field(0, "byte_count"), bytes);
    return {
        frame.string(frame.field(0, "type")),
        frame.string(frame.field(0, "session_id")),
        frame.string(frame.field(0, "conversation_id")),
        bytes,
        frame.is_number(frame.field(0, "sample_rate"), 24000) &&
        frame.is_number(frame.field(0, "channels"), 1) &&
        frame.string(frame.field(0, "format")) == "pcm_s16le",
        frame.string(frame.field(0, "dialog_state")),
        frame.string(frame.field(0, "code"))
    };
}
}
