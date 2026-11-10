#include "audio_capture.h"
#include "esp_timer.h"

namespace pixelpet {
namespace { constexpr EventBits_t finished = BIT0; }

AudioCapture::~AudioCapture() {
    stop();
    if (queue_) vQueueDelete(queue_);
    if (done_) vEventGroupDelete(done_);
}

esp_err_t AudioCapture::start() {
    if (started_ || queue_ || done_) return ESP_ERR_INVALID_STATE;
    queue_ = xQueueCreate(32,sizeof(CaptureFrame));
    done_ = xEventGroupCreate();
    if (!queue_ || !done_) {
        if (microphone_begin_recording() == ESP_OK) microphone_end_recording();
        return ESP_ERR_NO_MEM;
    }
    const auto result = microphone_begin_recording();
    if (result != ESP_OK) return result;
    stop_requested_.store(false);
    stop_result_.store(ESP_OK);
    started_ = true;
    if (xTaskCreatePinnedToCore(task_entry,"pixelpet_mic",4096,this,5,nullptr,0) != pdPASS) {
        started_ = false;
        microphone_end_recording();
        return ESP_ERR_NO_MEM;
    }
    return ESP_OK;
}

bool AudioCapture::read(CaptureFrame& frame) {
    return started_ && xQueueReceive(queue_, &frame, pdMS_TO_TICKS(300)) == pdTRUE;
}

esp_err_t AudioCapture::stop() {
    if (!started_) return stop_result_.load();
    stop_requested_.store(true);
    // The producer has bounded I2S and queue waits. Join before freeing storage.
    xEventGroupWaitBits(done_,finished,pdFALSE,pdTRUE,portMAX_DELAY);
    started_ = false;
    return stop_result_.load();
}

void AudioCapture::task_entry(void* arg) {
    static_cast<AudioCapture*>(arg)->run();
    vTaskDelete(nullptr);
}

void AudioCapture::run() {
    while (!stop_requested_.load()) {
        CaptureFrame frame;
        frame.result = microphone_read(frame.samples.data(),frame.samples.size(),&frame.count);
        frame.captured_at = esp_timer_get_time()/1000;
        if (frame.result == ESP_OK && frame.count != frame.samples.size())
            frame.result = ESP_ERR_INVALID_SIZE;
        if (stop_requested_.load()) break;
        if (xQueueSend(queue_,&frame,pdMS_TO_TICKS(50)) != pdTRUE) {
            if (!stop_requested_.load()) stop_result_.store(ESP_ERR_TIMEOUT);
            break;
        }
        if (frame.result != ESP_OK) {
            stop_result_.store(frame.result);
            break;
        }
    }
    const auto result = microphone_end_recording();
    if (stop_result_.load() == ESP_OK) stop_result_.store(result);
    xEventGroupSetBits(done_,finished);
}
}
