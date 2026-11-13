#include "voice_turn_state.h"
#include "voice_vad.h"
#include "voice_activity.h"
#include "audio_capture.h"
#include "dialog_control.h"
#include "preroll_buffer.h"
#include <cmath>
#include "board_config.h"
#include <fcntl.h>
#include <unistd.h>
#include "network.h"
#include "device_protocol.h"
#include "drivers.h"
#include "esp_check.h"
#include "esp_event.h"
#include "esp_heap_caps.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "esp_transport_ssl.h"
#include "esp_transport_tcp.h"
#include "esp_transport_ws.h"
#include "esp_wifi.h"
#include "lwip/sockets.h"
#include "lwip/tcp.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"
#include "nvs_flash.h"
#include <algorithm>
#include <array>
#include <cstdio>
#include <cstring>
#include <memory>
#include <new>
#include <string>

namespace pixelpet {
namespace {
constexpr char TAG[] = "pixelpet_net";
constexpr unsigned IP_READY = BIT0;
constexpr int IO_TIMEOUT_MS = 4000;
constexpr int HEARTBEAT_MS = 8000;
constexpr int FRAME_LIMIT = 16384;
EventGroupHandle_t wifi_events = nullptr;

int64_t milliseconds() { return esp_timer_get_time() / 1000; }

struct NetworkSettings {
    std::string ssid;
    std::string password;
    std::string host;
    std::string token;
    std::string ca_pem;
    uint16_t port = 8765;
    bool plain_ws = false;
};

std::string nvs_string(nvs_handle_t handle, const char* name, std::size_t max_length) {
    std::size_t size = 0;
    if (nvs_get_str(handle, name, nullptr, &size) != ESP_OK || size < 2 || size > max_length + 1) return {};
    std::string value(size, '\0');
    if (nvs_get_str(handle, name, value.data(), &size) != ESP_OK) return {};
    value.resize(size - 1);
    return value;
}

esp_err_t load_settings(NetworkSettings& settings, bool wifi_only) {
    // Preserve existing NVS on schema or capacity errors.
    ESP_RETURN_ON_ERROR(nvs_flash_init(), TAG, "NVS init");
    nvs_handle_t handle;
    const auto result = nvs_open("pixelpet", NVS_READONLY, &handle);
    if (result != ESP_OK) return result;
    settings.ssid = nvs_string(handle, "ssid", 32);
    settings.password = nvs_string(handle, "password", 64);
    if (wifi_only) {
        nvs_close(handle);
        return !settings.ssid.empty() && settings.password.size() >= 8 ? ESP_OK : ESP_ERR_INVALID_ARG;
    }
    settings.host = nvs_string(handle, "host", 253);
    settings.token = nvs_string(handle, "token", 192);
    settings.ca_pem = nvs_string(handle, "ca_pem", 4096);
    nvs_get_u16(handle, "port", &settings.port);
    uint8_t plain = 0;
    nvs_get_u8(handle, "plain_ws", &plain);
    settings.plain_ws = plain == 1;
    nvs_close(handle);
    if (settings.ssid.empty() || settings.password.size() < 8 || settings.host.empty() ||
        settings.token.empty() || !settings.port || (!settings.plain_ws && settings.ca_pem.empty())) return ESP_ERR_INVALID_ARG;
    if (settings.host.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-") != std::string::npos ||
        settings.token.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.~+/=") != std::string::npos) return ESP_ERR_INVALID_ARG;
    return ESP_OK;
}

void on_wifi(void*, esp_event_base_t base, int32_t event, void*) {
    if (base == WIFI_EVENT && event == WIFI_EVENT_STA_DISCONNECTED) xEventGroupClearBits(wifi_events, IP_READY);
    if (base == IP_EVENT && event == IP_EVENT_STA_GOT_IP) xEventGroupSetBits(wifi_events, IP_READY);
    if (base == IP_EVENT && event == IP_EVENT_STA_LOST_IP) xEventGroupClearBits(wifi_events, IP_READY);
}

esp_err_t start_wifi(const NetworkSettings& settings) {
    wifi_events = xEventGroupCreate();
    if (!wifi_events) return ESP_ERR_NO_MEM;
    ESP_RETURN_ON_ERROR(esp_netif_init(), TAG, "network init");
    ESP_RETURN_ON_ERROR(esp_event_loop_create_default(), TAG, "event loop init");
    if (!esp_netif_create_default_wifi_sta()) return ESP_ERR_NO_MEM;
    wifi_init_config_t config = WIFI_INIT_CONFIG_DEFAULT();
    ESP_RETURN_ON_ERROR(esp_wifi_init(&config), TAG, "Wi-Fi init");
    ESP_RETURN_ON_ERROR(esp_event_handler_register(WIFI_EVENT, WIFI_EVENT_STA_DISCONNECTED, on_wifi, nullptr), TAG, "Wi-Fi callback");
    ESP_RETURN_ON_ERROR(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_wifi, nullptr), TAG, "IP callback");
    ESP_RETURN_ON_ERROR(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_LOST_IP, on_wifi, nullptr), TAG, "IP-loss callback");
    ESP_RETURN_ON_ERROR(esp_wifi_set_storage(WIFI_STORAGE_RAM), TAG, "Wi-Fi RAM storage");
    ESP_RETURN_ON_ERROR(esp_wifi_set_mode(WIFI_MODE_STA), TAG, "Wi-Fi station mode");
    wifi_config_t wifi{};
    std::memcpy(wifi.sta.ssid, settings.ssid.data(), settings.ssid.size());
    std::memcpy(wifi.sta.password, settings.password.data(), settings.password.size());
    wifi.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;
    wifi.sta.pmf_cfg.capable = true;
    ESP_RETURN_ON_ERROR(esp_wifi_set_config(WIFI_IF_STA, &wifi), TAG, "Wi-Fi configuration");
    const auto started = esp_wifi_start();
    if (started != ESP_OK) return started;
#if CONFIG_PIXELPET_NETWORK_AUDIO_CONFIRMED
    return esp_wifi_set_ps(WIFI_PS_NONE);
#else
    return ESP_OK;
#endif
}

bool wifi_ready() { return (xEventGroupGetBits(wifi_events) & IP_READY) != 0; }

bool wait_for_wifi() {
    if (wifi_ready()) return true;
    if (esp_wifi_connect() == ESP_OK &&
        (xEventGroupWaitBits(wifi_events, IP_READY, pdFALSE, pdTRUE, pdMS_TO_TICKS(12000)) & IP_READY)) return true;
    esp_wifi_disconnect();
    return false;
}

struct Socket {
    esp_transport_handle_t transport = nullptr;
    esp_transport_handle_t ws = nullptr;

    ~Socket() {
        if (ws) {
            esp_transport_close(ws);
            esp_transport_destroy(ws);
        }
        if (transport) esp_transport_destroy(transport);
    }

    bool connect(const NetworkSettings& settings, const char* path) {
        transport = settings.plain_ws ? esp_transport_tcp_init() : esp_transport_ssl_init();
        if (!transport) return false;
        if (!settings.plain_ws) esp_transport_ssl_set_cert_data(transport, settings.ca_pem.c_str(), settings.ca_pem.size() + 1);
        ws = esp_transport_ws_init(transport);
        if (!ws) return false;
        esp_transport_ws_set_path(ws, path);
        const auto header = "Authorization: Bearer " + settings.token + "\r\n";
        if (esp_transport_ws_set_headers(ws, header.c_str()) != ESP_OK ||
            esp_transport_connect(ws, settings.host.c_str(), settings.port, IO_TIMEOUT_MS) < 0) return false;
        // The WebSocket transport sends frame headers and payloads separately.
        const int fd = esp_transport_get_socket(transport);
        const int enabled = 1;
        if (fd >= 0 && setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &enabled, sizeof(enabled)) != 0)
            ESP_LOGW(TAG, "TCP_NODELAY unavailable");
        return true;
    }
};

bool read_message(esp_transport_handle_t ws, char* buffer, std::size_t& length,
                  ws_transport_opcodes_t& first_opcode) {
    const auto deadline = milliseconds() + IO_TIMEOUT_MS;
    length = 0;
    int frame_remaining = 0;
    bool continuation = false;
    while (milliseconds() < deadline && wifi_ready()) {
        const int capacity = FRAME_LIMIT - int(length);
        if (capacity <= 0) return false;
        const int timeout = int(deadline - milliseconds());
        if (timeout <= 0) return false;
        const int received = esp_transport_read(ws, buffer + length, capacity, timeout);
        if (received < 0) return false;
        if (received == 0) {
            // IDF consumes ping/pong internally. Yield to the caller so an idle
            // control frame cannot start a four-second wait for application data.
            if (length == 0) {
                first_opcode = WS_TRANSPORT_OPCODES_PONG;
                return true;
            }
            continue;
        }
        if (frame_remaining == 0) {
            const auto opcode = esp_transport_ws_get_read_opcode(ws);
            if (continuation) {
                if (opcode != WS_TRANSPORT_OPCODES_CONT) return false;
            } else {
                if (opcode != WS_TRANSPORT_OPCODES_TEXT && opcode != WS_TRANSPORT_OPCODES_BINARY) return false;
                first_opcode = opcode;
            }
            frame_remaining = esp_transport_ws_get_read_payload_len(ws);
            if (frame_remaining > capacity) return false;
        }
        if (received > frame_remaining) return false;
        frame_remaining -= received;
        length += received;
        if (frame_remaining == 0) {
            if (esp_transport_ws_get_fin_flag(ws)) return true;
            continuation = true;
        }
    }
    return false;
}

bool read_text(esp_transport_handle_t ws, char* buffer, std::size_t& length) {
    ws_transport_opcodes_t opcode{};
    const auto deadline = milliseconds() + IO_TIMEOUT_MS;
    do {
        if (!read_message(ws, buffer, length, opcode)) return false;
        if (opcode == WS_TRANSPORT_OPCODES_TEXT) return true;
        if (opcode != WS_TRANSPORT_OPCODES_PONG || length) return false;
    } while (milliseconds() < deadline);
    return false;
}

bool read_reply(esp_transport_handle_t ws, char* buffer, uint32_t sequence, State& state) {
    std::size_t length = 0;
    if (!read_text(ws, buffer, length)) return false;
    const auto result = read_server_frame({buffer, length}, sequence);
    if (result.has_state && state != result.state) {
        state = result.state;
        ESP_LOGI(TAG, "Device state=%u", unsigned(state));
    }
    if (result.reply == Reply::Error) ESP_LOGW(TAG, "Server rejected request seq=%lu", static_cast<unsigned long>(sequence));
    return result.reply == (sequence ? Reply::Ack : Reply::Connected);
}

bool transact(esp_transport_handle_t ws, char* buffer, uint32_t& sequence, State& state, const char* kind, const char* payload = "{}") {
    if (++sequence == 0) return false;
    char message[128];
    const int length = std::snprintf(message, sizeof(message),
        "{\"version\":1,\"type\":\"%s\",\"seq\":%lu,\"payload\":%s}", kind, static_cast<unsigned long>(sequence), payload);
    if (length <= 0 || length >= int(sizeof(message))) return false;
    constexpr auto opcode = static_cast<ws_transport_opcodes_t>(WS_TRANSPORT_OPCODES_FIN | WS_TRANSPORT_OPCODES_TEXT);
    return esp_transport_ws_send_raw(ws, opcode, message, length, IO_TIMEOUT_MS) == length &&
           read_reply(ws, buffer, sequence, state);
}

char serial_voice_command() {
#if CONFIG_PIXELPET_SERIAL_VOICE_CONTROL
    char command = 0;
    return read(STDIN_FILENO, &command, 1) == 1 ? command : 0;
#else
    return 0;
#endif
}

class TouchGesture {
    bool sample_ = false;
    bool held_ = false;
    bool sent_long_ = false;
    int64_t changed_at_ = 0;
    int64_t pressed_at_ = 0;

public:
    const char* update(bool sample, int64_t now) {
        if (sample_ != sample) { sample_ = sample; changed_at_ = now; }
        if (held_ == sample_ || now - changed_at_ < 40) return nullptr;
        held_ = sample_;
        if (held_) {
            pressed_at_ = now;
            sent_long_ = false;
            return "TOUCH_START";
        }
        return "TOUCH_END";
    }

    bool long_press(int64_t now) {
        if (!held_ || !sample_ || sent_long_ || now - pressed_at_ < 650) return false;
        sent_long_ = true;
        return true;
    }

    bool short_release(int64_t now) const { return !sent_long_ && now - pressed_at_ < 650; }
};

bool send_voice(esp_transport_handle_t ws, ws_transport_opcodes_t opcode, const char* data, int bytes) {
    const auto frame = static_cast<ws_transport_opcodes_t>(WS_TRANSPORT_OPCODES_FIN | opcode);
    return esp_transport_ws_send_raw(ws, frame, data, bytes, IO_TIMEOUT_MS) == bytes;
}

bool voice_control(esp_transport_handle_t ws, const char* type, const char* session = nullptr) {
    char json[128];
    const int size = session
        ? std::snprintf(json, sizeof(json), R"({"version":1,"type":"%s","session_id":"%s"})", type, session)
        : std::snprintf(json, sizeof(json), R"({"version":1,"type":"%s","client":"esp32"})", type);
    return size > 0 && size < int(sizeof(json)) && send_voice(ws, WS_TRANSPORT_OPCODES_TEXT, json, size);
}

struct VoiceSession {
    std::array<char, 33> text{};
    std::array<uint8_t, 16> binary{};

    bool set(std::string_view value) {
        if (value.size() != 32) return false;
        for (size_t i = 0; i < value.size(); ++i) {
            const char digit = value[i];
            const int nibble = digit >= '0' && digit <= '9' ? digit - '0'
                : digit >= 'a' && digit <= 'f' ? digit - 'a' + 10 : -1;
            if (nibble < 0) return false;
            text[i] = digit;
            if (i % 2 == 0) binary[i / 2] = uint8_t(nibble << 4);
            else binary[i / 2] |= uint8_t(nibble);
        }
        return true;
    }

    void header(char* data, uint32_t sequence) const {
        std::memcpy(data, binary.data(), binary.size());
        for (size_t i = 0; i < 4; ++i) data[16 + i] = char(sequence >> (24 - 8 * i));
    }
};

enum class VoiceCue { Start = 1, End = 2, Error = 3 };

esp_err_t voice_cue(VoiceCue cue) {
    constexpr int rate = PIXELPET_AUDIO_OUTPUT_SAMPLE_RATE;
    constexpr int samples = rate * 120 / 1000;
    std::array<int16_t, 240> pcm{};
    for (int burst = 0; burst < int(cue); ++burst) {
        for (int offset = 0; offset < samples; offset += pcm.size()) {
            const int count = std::min(int(pcm.size()), samples - offset);
            for (int i = 0; i < count; ++i) {
                const int position = offset + i;
                const double envelope = std::min({1.0, position / 120.0,
                                                  (samples - position) / 120.0});
                const double frequency = cue == VoiceCue::Start ? 880.0 : cue == VoiceCue::End ? 660.0 : 440.0;
                pcm[i] = int16_t(2048 * envelope * std::sin(6.2831853 * frequency * position / rate));
            }
            const auto result = speaker_write(pcm.data(), count);
            if (result != ESP_OK) return result;
        }
        // Flush the full speaker DMA ring, then allow its silence to finish.
        std::array<int16_t, 1440> silence{};
        const auto result = speaker_write(silence.data(), silence.size());
        if (result != ESP_OK) return result;
        vTaskDelay(pdMS_TO_TICKS(70));
    }
    return ESP_OK;
}

bool play_buffered(int16_t* playback, std::size_t playback_samples, char* buffer, DialogControl& dialog) {
    ESP_LOGI(TAG, "SPEAKING bytes=%u", unsigned(playback_samples * sizeof(int16_t)));
    for (std::size_t offset = 0; offset < playback_samples; offset += 480) {
        const char control = serial_voice_command();
        dialog.command(control);
        if (control == 'c') return false;
        auto* output = playback + offset;
        const std::size_t samples = std::min(std::size_t(480), playback_samples - offset);
#if CONFIG_PIXELPET_NETWORK_AUDIO_CONFIRMED
        for (std::size_t i = 0; i < samples; ++i)
            output[i] = int16_t(int32_t(output[i]) * CONFIG_PIXELPET_NETWORK_AUDIO_GAIN_PERCENT / 100);
#endif
        const auto status = speaker_write(output, samples);
        if (status != ESP_OK) {
            ESP_LOGW(TAG, "PLAYBACK_I2S_FAILED status=%s offset=%u",
                     esp_err_to_name(status), unsigned(offset));
            return false;
        }
    }
    // Fill one DMA ring with silence and let it drain before reopening the microphone.
    std::memset(buffer, 0, 6 * 240 * sizeof(int16_t));
    if (speaker_write(reinterpret_cast<int16_t*>(buffer), 6 * 240) != ESP_OK) return false;
    vTaskDelay(pdMS_TO_TICKS(65));
    return true;
}

bool reminder_poll(esp_transport_handle_t ws, char* buffer, VoiceSession& reminder) {
    std::size_t length = 0;
    if (!voice_control(ws, "reminder.poll") || !read_text(ws, buffer, length)) return false;
    const auto reply = read_voice_reply({buffer, length});
    return reply.type == "reminder.none" ||
           (reply.type == "reminder.ready" && reminder.set(reply.session));
}

bool play_reminder(esp_transport_handle_t ws, char* buffer, const VoiceSession& reminder,
                   DialogControl& dialog) {
    if (!voice_control(ws, "reminder.play", reminder.text.data()) ||
        esp_transport_poll_read(ws, 23000) <= 0) return false;
    std::size_t length = 0;
    if (!read_text(ws, buffer, length)) return false;
    const auto start = read_voice_reply({buffer, length});
    if (start.type == "reminder.none") return true;
    if (start.type != "playback.start" || start.session != reminder.text.data() ||
        !start.pcm_output || !start.bytes || start.bytes % 2 || start.bytes > 120 * 48000) return false;
    const auto total = start.bytes;
    std::unique_ptr<int16_t, decltype(&heap_caps_free)> pcm(
        static_cast<int16_t*>(heap_caps_malloc(total, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT)), heap_caps_free);
    if (!pcm) return false;
    uint32_t seq = 0;
    std::size_t offset = 0;
    const auto deadline = milliseconds() + 10000 + total / 48;
    while (offset < total && milliseconds() < deadline) {
        ws_transport_opcodes_t opcode{};
        if (!read_message(ws, buffer, length, opcode)) return false;
        if (opcode == WS_TRANSPORT_OPCODES_PONG && !length) continue;
        char expected[20];
        reminder.header(expected, seq++);
        if (opcode != WS_TRANSPORT_OPCODES_BINARY || length <= 20 || length > 4116 ||
            length % 2 || length - 20 > total - offset || std::memcmp(buffer, expected, 20)) return false;
        std::memcpy(reinterpret_cast<char*>(pcm.get()) + offset, buffer + 20, length - 20);
        offset += length - 20;
    }
    if (offset != total || !read_text(ws, buffer, length)) return false;
    const auto end = read_voice_reply({buffer, length});
    if (end.type != "playback.end" || end.session != reminder.text.data()) return false;
    if (!play_buffered(pcm.get(), total / sizeof(int16_t), buffer, dialog)) return false;
    ESP_LOGI(TAG, "REMINDER_PLAYED");
    return voice_control(ws, "reminder.ack", reminder.text.data()) &&
           read_text(ws, buffer, length) && read_voice_reply({buffer, length}).type == "reminder.ack";
}

bool voice_turn(esp_transport_handle_t ws, char* buffer, TouchGesture& touch, VoiceSession& conversation,
                VoiceTrigger trigger, DialogControl& dialog) {
    const bool checking_wake = dialog.standby();
    constexpr size_t max_samples = 20 * 16000;
    auto* allocated = static_cast<int16_t*>(heap_caps_malloc(
        max_samples * sizeof(int16_t), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    if (!allocated) return false;
    std::unique_ptr<int16_t, decltype(&heap_caps_free)> recording(allocated, heap_caps_free);
    std::size_t length = 0;
    VoiceSession session;
    float noise_rms = 0;
    ESP_LOGI(TAG, "AUDIO_WARMUP");
    if (microphone_prepare(&noise_rms) != ESP_OK) return false;
    VoiceVad activity(noise_rms);
    // Speech during microphone warmup must not set an unreachable onset threshold.
    SpeechActivity energy_activity(noise_rms, trigger == VoiceTrigger::Continuous && !checking_wake ? 450.0 : 3000.0);
    if (!activity.ready() || (voice_turn_uses_cues(trigger) && voice_cue(VoiceCue::Start) != ESP_OK)) {
        if (microphone_begin_recording() == ESP_OK) microphone_end_recording();
        return false;
    }
    AudioCapture capture_stream;
    if (capture_stream.start() != ESP_OK) return false;
    ESP_LOGI(TAG, "VAD provider=%s noise=%.1f onset=%.1f frame_ms=20; stop after %dms silence",
             checking_wake ? "energy" : "energy onset + ESP-SR continuation", double(noise_rms), energy_activity.threshold(),
             checking_wake || trigger != VoiceTrigger::Continuous ? standby_silence_ms : continuous_silence_ms);
    ESP_LOGI(TAG, "LISTENING");
    ESP_LOGI(TAG, "DIALOG_MODE=%s", checking_wake ? "STANDBY; server keyword detection" : "ACTIVE");
    ESP_LOGI(TAG, "VOICE_PROMPTS=%s", voice_turn_uses_cues(trigger) ? "on" : "off; automatic speech/silence detection");
    VoiceTurnState turn;
    turn.start(trigger, milliseconds(), checking_wake);
    auto capture = CaptureDecision::Continue;
    size_t count = 0;
    uint64_t energy = 0;
    uint32_t seq = 0;
    bool ok = true;
    bool collecting = trigger != VoiceTrigger::Continuous;
    std::size_t seen_samples = 0;
    PrerollBuffer preroll(recording.get(),3200);
    auto capture_heartbeat = milliseconds() + HEARTBEAT_MS;
    while (count < max_samples && wifi_ready()) {
        const char command = serial_voice_command();
        dialog.command(command);
        if (command == 'c') { capture = CaptureDecision::Cancel; break; }
        if (command == 's') {
            if (!count) capture = CaptureDecision::Cancel;
            break;
        }
        if (milliseconds() >= capture_heartbeat) {
            if (!voice_control(ws, "heartbeat") || !read_text(ws,buffer,length) ||
                read_voice_reply({buffer,length}).type != "heartbeat") {
                ok = false;
                break;
            }
            capture_heartbeat = milliseconds() + HEARTBEAT_MS;
            if (!collecting) {
                VoiceSession reminder;
                if (!reminder_poll(ws, buffer, reminder)) {
                    ok = false;
                    break;
                }
                if (reminder.text[0]) {
                    if (capture_stream.stop() != ESP_OK) return false;
                    recording.reset();
                    return play_reminder(ws, buffer, reminder, dialog);
                }
            }
        }
        bool pressed = false;
        if (touch_read(&pressed) == ESP_OK) {
            const auto event = touch.update(pressed, milliseconds());
            if (event && std::strcmp(event, "TOUCH_END") == 0) break;
        }
        CaptureFrame frame;
        if (!capture_stream.read(frame) || frame.result != ESP_OK ||
            frame.count != VoiceVad::frame_samples || frame.count > max_samples - count) {
            ok = false;
            break;
        }
        const auto received = frame.count;
        auto* pcm = frame.samples.data();
        uint64_t chunk_energy = 0;
        for (size_t i = 0; i < received; ++i) chunk_energy += int32_t(pcm[i]) * int32_t(pcm[i]);
        energy += chunk_energy;
        const bool energy_speech = energy_activity.observe(pcm_rms(pcm, received), frame.captured_at);
        const auto decision = checking_wake ? VoiceDecision::Silence : activity.process(pcm, received, frame.captured_at);
        if (decision == VoiceDecision::Invalid) { ok = false; break; }
        // Require sustained energy to start, then keep quieter syllables detected by ESP-SR.
        const bool speech = seen_samples >= 3200 && (energy_speech || (collecting && decision == VoiceDecision::Speech));
        seen_samples = std::min(std::size_t(3200), seen_samples + received);
        capture = turn.capture(speech, frame.captured_at);
        if (capture == CaptureDecision::Cancel) break;
        if (!collecting) {
            if (!speech) {
                preroll.append(pcm,received);
                continue;
            }
            collecting = true;
            count = preroll.flatten();
            ESP_LOGI(TAG, "SPEECH_STARTED: collecting an utterance");
        }
        std::memcpy(recording.get() + count,pcm,received * sizeof(int16_t));
        count += received;
        if (capture == CaptureDecision::Send) break;
    }
    const auto stopped = capture_stream.stop();
    ESP_LOGI(TAG, "CAPTURE_STOPPED samples=%u status=%s", unsigned(count), esp_err_to_name(stopped));
    if (stopped != ESP_OK || !ok) {
        voice_cue(VoiceCue::Error);
        return false;
    }
    if (voice_turn_uses_cues(trigger) && voice_cue(VoiceCue::End) != ESP_OK) return false;
    if (capture == CaptureDecision::Cancel) {
        ESP_LOGI(TAG, "NO_SPEECH_OR_CANCEL: no audio sent to the server");
        return false;
    }
    if (!wifi_ready() || !count || !turn.think()) return false;
    // Admit the server recording only after local capture. This keeps a full
    // 15-second utterance plus Wi-Fi upload inside the server upload deadline.
    char start[192];
    const int start_size = conversation.text[0]
        ? std::snprintf(start, sizeof(start), R"({"version":1,"type":"record.start","purpose":"%s","conversation_id":"%s"})", checking_wake ? "wake" : "conversation", conversation.text.data())
        : std::snprintf(start, sizeof(start), R"({"version":1,"type":"record.start","purpose":"%s"})", checking_wake ? "wake" : "conversation");
    if (start_size <= 0 || start_size >= int(sizeof(start)) ||
        !send_voice(ws, WS_TRANSPORT_OPCODES_TEXT, start, start_size) || !read_text(ws, buffer, length)) return false;
    const auto ready = read_voice_reply({buffer, length});
    if (ready.type != "record.ready" || !session.set(ready.session)) return false;
    ESP_LOGI(TAG, "UPLOADING samples=%u duration_ms=%u mean_square=%lu", unsigned(count), unsigned(count / 16),
             static_cast<unsigned long>(energy / count));
    // Buffer bounded audio in PSRAM first. Network writes must not stall the I2S reader.
    const auto upload_started = milliseconds();
    for (std::size_t offset = 0; offset < count; offset += 2048) {
        const auto chunk = std::min(std::size_t(2048), count - offset);
        session.header(buffer, seq++);
        std::memcpy(buffer + 20, recording.get() + offset, chunk * sizeof(int16_t));
        if (!send_voice(ws, WS_TRANSPORT_OPCODES_BINARY, buffer, int(20 + chunk * 2))) return false;
    }
    recording.reset();
    if (!voice_control(ws, "record.stop", session.text.data())) return false;
    ESP_LOGI(TAG, "UPLOAD_COMPLETE ms=%ld", static_cast<long>(milliseconds() - upload_started));
    auto deadline = milliseconds() + 100000;
    auto heartbeat_at = milliseconds() + HEARTBEAT_MS;
    bool playing = false;
    uint32_t remaining = 0;
    std::size_t playback_samples = 0;
    std::size_t buffered_samples = 0;
    std::unique_ptr<int16_t, decltype(&heap_caps_free)> playback(nullptr, heap_caps_free);
    seq = 0;
    while (wifi_ready() && milliseconds() < deadline) {
        if (!playing && milliseconds() >= heartbeat_at) {
            if (!voice_control(ws, "heartbeat")) return false;
            heartbeat_at = milliseconds() + HEARTBEAT_MS;
        }
        const char command = serial_voice_command();
        dialog.command(command);
        bool pressed = false;
        const auto touch_event = touch_read(&pressed) == ESP_OK ? touch.update(pressed, milliseconds()) : nullptr;
        if (command == 'c' || (touch_event && std::strcmp(touch_event, "TOUCH_START") == 0)) {
                voice_control(ws, "cancel", session.text.data());
                return false; // Drop queued reply frames before accepting another session.
        }
        const int readable = esp_transport_poll_read(ws, 40);
        if (readable < 0) return false;
        if (readable == 0) continue;
        ws_transport_opcodes_t opcode{};
        if (!read_message(ws, buffer, length, opcode)) {
            if (playing) ESP_LOGW(TAG, "PLAYBACK_NETWORK_INTERRUPTED bytes_remaining=%u", unsigned(remaining));
            return false;
        }
        if (opcode == WS_TRANSPORT_OPCODES_PONG && length == 0) continue;
        if (opcode == WS_TRANSPORT_OPCODES_BINARY) {
            char expected[20];
            session.header(expected, seq++);
            if (!playing || length <= 20 || length > 4116 || length % 2 || length - 20 > remaining ||
                std::memcmp(buffer, expected, 20)) {
                ESP_LOGW(TAG, "PLAYBACK_FRAME_INVALID frame=%lu bytes_remaining=%u",
                         static_cast<unsigned long>(seq), unsigned(remaining));
                return false;
            }
            const std::size_t samples = (length - 20) / sizeof(int16_t);
            std::memcpy(playback.get() + buffered_samples, buffer + 20, samples * sizeof(int16_t));
            buffered_samples += samples;
            remaining -= length - 20;
            continue;
        }
        const auto reply = read_voice_reply({buffer, length});
        if (reply.type == "heartbeat") continue;
        if (reply.type == "error") {
            if (dialog.enabled() && reply.error_code == "no_speech") {
                ESP_LOGI(TAG, "NO_SPEECH: continue listening quietly");
                return true;
            }
            ESP_LOGW(TAG, "VOICE_ERROR: %.*s", int(std::min(length, std::size_t(256))), buffer);
            voice_cue(VoiceCue::Error);
            return false;
        }
        if (reply.session != session.text.data()) return false;
        if (reply.type == "dialog.state") {
            if (!dialog.apply_state(reply.dialog_state)) return false;
            ESP_LOGI(TAG, "DIALOG_STATE=%s", dialog.standby() ? "STANDBY" : "ACTIVE");
            continue;
        }
        if (reply.type == "wake.result" && checking_wake && reply.dialog_state == "standby") {
            return dialog.apply_state("standby");
        }
        if (reply.type == "thinking") {
            ESP_LOGI(TAG, "THINKING");
        } else if (reply.type == "playback.start" && reply.pcm_output && !playing) {
            if (!reply.bytes || reply.bytes % 2 || reply.bytes > 120 * 48000 ||
                (!reply.conversation.empty() && !conversation.set(reply.conversation)) ||
                (reply.conversation.empty() && !checking_wake)) return false;
            if (!turn.play()) return false;
            remaining = reply.bytes;
            playback_samples = remaining / sizeof(int16_t);
            playback.reset(static_cast<int16_t*>(heap_caps_malloc(remaining, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT)));
            if (!playback) {
                ESP_LOGW(TAG, "PLAYBACK_BUFFER_ALLOC_FAILED bytes=%u", unsigned(remaining));
                return false;
            }
            deadline = milliseconds() + 10000 + remaining / 48;
            playing = true;
            ESP_LOGI(TAG, "PLAYBACK_BUFFERING bytes=%u", unsigned(remaining));
        } else if (reply.type == "playback.end" && playing && seq && !remaining) {
            if (buffered_samples != playback_samples) return false;
            if (!play_buffered(playback.get(), playback_samples, buffer, dialog)) return false;
            ESP_LOGI(TAG, "PLAYBACK_COMPLETE frames=%lu", static_cast<unsigned long>(seq));
            return true;
        }
    }
    return false;
}

void run_voice_session(const NetworkSettings& settings, const char* path, char* buffer, bool& connected,
                       VoiceSession& conversation, DialogControl& dialog) {
    Socket socket;
    size_t length = 0;
    char hello[] = R"({"version":1,"type":"hello","client":"esp32","reminders":true})";
    if (!socket.connect(settings, path) ||
        !send_voice(socket.ws, WS_TRANSPORT_OPCODES_TEXT, hello, sizeof(hello) - 1) ||
        !read_text(socket.ws, buffer, length) || read_voice_reply({buffer, length}).type != "hello") return;
    connected = true;
    ESP_LOGI(TAG, "PixelPet voice protocol ready; continuous listening enabled at boot; d=resume, c=stop");
    TouchGesture touch;
    auto heartbeat_at = milliseconds() + HEARTBEAT_MS;
    while (wifi_ready()) {
        const char command = serial_voice_command();
        dialog.command(command);
        bool pressed = false;
        const auto touch_event = touch_read(&pressed) == ESP_OK ? touch.update(pressed, milliseconds()) : nullptr;
        if (command == 'r' || dialog.enabled() || (touch_event && !pressed)) {
            const auto trigger = dialog.enabled() ? VoiceTrigger::Continuous : VoiceTrigger::Automatic;
            if (!voice_turn(socket.ws, buffer, touch, conversation, trigger, dialog)) return;
            if (dialog.enabled()) {
                ESP_LOGI(TAG, "NEXT_TURN: %s", dialog.standby() ? "standby local wake detection" : "continuing the same conversation");
                vTaskDelay(pdMS_TO_TICKS(100));
            }
            heartbeat_at = milliseconds() + HEARTBEAT_MS;
        } else if (milliseconds() >= heartbeat_at) {
            if (!voice_control(socket.ws, "heartbeat") || !read_text(socket.ws, buffer, length) ||
                read_voice_reply({buffer, length}).type != "heartbeat") return;
            VoiceSession reminder;
            if (!reminder_poll(socket.ws, buffer, reminder) ||
                (reminder.text[0] && !play_reminder(socket.ws, buffer, reminder, dialog))) return;
            heartbeat_at = milliseconds() + HEARTBEAT_MS;
        }
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}

void run_session(const NetworkSettings& settings, const char* path, bool touch_enabled, char* buffer, bool& connected) {
    connected = false;
    Socket socket;
    State state = State::IDLE;
    uint32_t sequence = 0;
    if (!socket.connect(settings, path) || !read_reply(socket.ws, buffer, 0, state) ||
        !transact(socket.ws, buffer, sequence, state, "hello", R"({"client":"esp32"})")) return;
    connected = true;
    ESP_LOGI(TAG, "PixelPet business protocol ready");
    auto heartbeat_at = milliseconds() + HEARTBEAT_MS;
    TouchGesture touch;
    while (wifi_ready()) {
        const auto now = milliseconds();
        if (now >= heartbeat_at) {
            if (!transact(socket.ws, buffer, sequence, state, "heartbeat")) return;
            heartbeat_at = now + HEARTBEAT_MS;
        }
        bool pressed = false;
        if (touch_enabled && touch_read(&pressed) == ESP_OK) {
            const char* type = touch.update(pressed, now);
            if (type && !transact(socket.ws, buffer, sequence, state, type)) return;
            if (touch.long_press(now) && !transact(socket.ws, buffer, sequence, state, "TOUCH_LONG")) return;
            if (type && std::strcmp(type, "TOUCH_END") == 0 && touch.short_release(now) &&
                !transact(socket.ws, buffer, sequence, state, "TOUCH_SHORT")) return;
        }
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}
}

esp_err_t run_network(bool wifi_only) {
    NetworkSettings settings;
    const auto provisioned = load_settings(settings, wifi_only);
    if (provisioned != ESP_OK) {
        ESP_LOGW(TAG, "HW_PENDING: network provisioning missing or invalid");
        return provisioned;
    }
#if !CONFIG_LOG_DYNAMIC_LEVEL_CONTROL || CONFIG_LOG_TAG_LEVEL_IMPL_NONE
    // The IDF upgrade writer can log its request on socket write errors.
    ESP_LOGE(TAG, "Network requires per-tag log suppression for credential safety");
    return ESP_ERR_NOT_SUPPORTED;
#endif
    esp_log_level_set("transport_ws", ESP_LOG_NONE);
    if (wifi_only) {
        ESP_RETURN_ON_ERROR(start_wifi(settings), TAG, "Wi-Fi start");
        while (true) {
            const bool ready = wait_for_wifi();
            ESP_LOGI(TAG, "Wi-Fi association and address: %s", ready ? "ready" : "timeout; retrying");
            do {
                vTaskDelay(pdMS_TO_TICKS(1000));
            } while (wifi_ready());
        }
    }
    const std::unique_ptr<char[]> buffer(new(std::nothrow) char[FRAME_LIMIT]);
    if (!buffer) return ESP_ERR_NO_MEM;
    uint8_t mac[6]{};
    ESP_RETURN_ON_ERROR(esp_read_mac(mac, ESP_MAC_WIFI_STA), TAG, "device identity");
    char path[80];
    std::snprintf(path, sizeof(path), "/api/devices/ws?device_id=esp32-%02x%02x%02x%02x%02x%02x",
                  unsigned(mac[0]), unsigned(mac[1]), unsigned(mac[2]), unsigned(mac[3]), unsigned(mac[4]), unsigned(mac[5]));
    ESP_RETURN_ON_ERROR(start_wifi(settings), TAG, "Wi-Fi start");
    const bool touch_enabled = touch_init() == ESP_OK; // Independently gated by the approved pinmap.
#if CONFIG_PIXELPET_SERIAL_VOICE_CONTROL
    const int input_flags = fcntl(STDIN_FILENO, F_GETFL);
    if (input_flags < 0 || fcntl(STDIN_FILENO, F_SETFL, input_flags | O_NONBLOCK) < 0)
        return ESP_FAIL;
#endif
    const bool voice_enabled = (touch_enabled || pixelpet_network_audio_enabled()) &&
                               microphone_init() == ESP_OK && speaker_init() == ESP_OK;
    char voice_path[96];
    std::snprintf(voice_path, sizeof(voice_path), "/api/devices/voice/ws%s", std::strchr(path, '?'));
    ESP_LOGI(TAG, "Booted network mode; touch enabled=%d", touch_enabled);
    ESP_LOGI(TAG, "free internal=%u PSRAM=%u bytes", unsigned(heap_caps_get_free_size(MALLOC_CAP_INTERNAL)),
             unsigned(heap_caps_get_free_size(MALLOC_CAP_SPIRAM)));
    int backoff_ms = 1000;
    unsigned reconnects = 0;
    VoiceSession conversation;
    DialogControl dialog(false);
    while (true) {
        bool connected = false;
        if (wait_for_wifi()) {
            if (voice_enabled) run_voice_session(settings, voice_path, buffer.get(), connected, conversation, dialog);
            else run_session(settings, path, touch_enabled, buffer.get(), connected);
        }
        if (connected) backoff_ms = 1000;
        ESP_LOGI(TAG, "network task minimum free stack=%u bytes", unsigned(uxTaskGetStackHighWaterMark(nullptr)));
        ESP_LOGW(TAG, "Disconnected, reconnect=%u wait=%dms", ++reconnects, backoff_ms);
        vTaskDelay(pdMS_TO_TICKS(backoff_ms));
        backoff_ms = std::min(backoff_ms * 2, 16000);
    }
}
}
