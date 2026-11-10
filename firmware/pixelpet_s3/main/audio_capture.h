#pragma once
#include "drivers.h"
#include "voice_vad.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include <array>
#include <atomic>

namespace pixelpet {
struct CaptureFrame {
    std::array<int16_t, VoiceVad::frame_samples> samples{};
    std::size_t count = 0;
    int64_t captured_at = 0;
    esp_err_t result = ESP_OK;
};

class AudioCapture {
public:
    AudioCapture() = default;
    ~AudioCapture();
    AudioCapture(const AudioCapture&) = delete;
    AudioCapture& operator=(const AudioCapture&) = delete;
    esp_err_t start();
    bool read(CaptureFrame& frame);
    esp_err_t stop();
private:
    static void task_entry(void* arg);
    void run();
    QueueHandle_t queue_ = nullptr;
    EventGroupHandle_t done_ = nullptr;
    std::atomic<bool> stop_requested_{false};
    std::atomic<esp_err_t> stop_result_{ESP_OK};
    bool started_ = false;
};
}
