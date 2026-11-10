#include "hardware_smoke.h"
#include "board_config.h"
#include "drivers.h"
#include "esp_check.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <memory>
#include "esp_heap_caps.h"

namespace pixelpet {
namespace {
constexpr char TAG[] = "pixelpet_smoke";

esp_err_t display_test() {
    ESP_RETURN_ON_ERROR(display_init(), TAG, "display init");
    constexpr int rows = 20;
    static std::array<uint16_t, PIXELPET_DISPLAY_WIDTH * rows> strip;
    constexpr uint16_t colors[] = {0xf800, 0x07e0, 0x001f, 0xffff};
    for (int y = 0; y < PIXELPET_DISPLAY_HEIGHT; y += rows) {
        const int height = std::min(rows, PIXELPET_DISPLAY_HEIGHT - y);
        const auto color = colors[y * 4 / PIXELPET_DISPLAY_HEIGHT];
        strip.fill(color);
        ESP_RETURN_ON_ERROR(display_region(0, y, PIXELPET_DISPLAY_WIDTH, height, strip.data()), TAG, "display strip");
    }
    return ESP_OK;
}

#if CONFIG_PIXELPET_MICROPHONE_SERIAL_PCM
esp_err_t microphone_serial_capture() {
    constexpr std::size_t sample_count = 6 * PIXELPET_AUDIO_INPUT_SAMPLE_RATE;
    auto* allocated = static_cast<int16_t*>(heap_caps_malloc(
        sample_count * sizeof(int16_t), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    if (!allocated) return ESP_ERR_NO_MEM;
    std::unique_ptr<int16_t, decltype(&heap_caps_free)> pcm(allocated, heap_caps_free);
    ESP_RETURN_ON_ERROR(microphone_init(), TAG, "microphone init");
    ESP_LOGI(TAG, "MIC_PCM: recording starts in 3 seconds; speak for 6 seconds");
    vTaskDelay(pdMS_TO_TICKS(3000));
    ESP_RETURN_ON_ERROR(microphone_begin_recording(), TAG, "microphone start");
    ESP_LOGI(TAG, "MIC_PCM: RECORDING");
    std::size_t total = 0;
    esp_err_t result = ESP_OK;
    while (total < sample_count) {
        std::size_t received = 0;
        const auto wanted = std::min(std::size_t(256), sample_count - total);
        result = microphone_read(pcm.get() + total, wanted, &received);
        if (result != ESP_OK || received == 0) {
            if (result == ESP_OK) result = ESP_ERR_INVALID_SIZE;
            break;
        }
        total += received;
    }
    const auto stopped = microphone_end_recording();
    if (result != ESP_OK) return result;
    if (stopped != ESP_OK) return stopped;
    ESP_LOGI(TAG, "MIC_PCM: recording ended; transferring audio to PC");
    std::printf("MIC_PCM_BEGIN sample_rate=%d samples=%u\n",
                PIXELPET_AUDIO_INPUT_SAMPLE_RATE, unsigned(total));
    constexpr char digits[] = "0123456789abcdef";
    const auto* bytes = reinterpret_cast<const uint8_t*>(pcm.get());
    const std::size_t length = total * sizeof(int16_t);
    std::array<char, 1025> encoded{};
    for (std::size_t offset = 0; offset < length; offset += 512) {
        const auto count = std::min(std::size_t(512), length - offset);
        for (std::size_t i = 0; i < count; ++i) {
            encoded[i * 2] = digits[bytes[offset + i] >> 4];
            encoded[i * 2 + 1] = digits[bytes[offset + i] & 15];
        }
        encoded[count * 2] = 0;
        std::printf("MIC_PCM offset=%u hex=%s\n", unsigned(offset), encoded.data());
        std::fflush(stdout);
        // UART stdout can busy-wait. Let the idle task run between bounded frames.
        vTaskDelay(1);
    }
    std::printf("MIC_PCM_END bytes=%u\n", unsigned(length));
    std::fflush(stdout);
    return ESP_OK;
}
#endif

[[maybe_unused]] esp_err_t microphone_test() {
    ESP_RETURN_ON_ERROR(microphone_init(), TAG, "microphone init");
    ESP_LOGI(TAG, "MIC_TEST: capture starts in 3 seconds; quiet first, then speak");
    vTaskDelay(pdMS_TO_TICKS(3000));
    ESP_RETURN_ON_ERROR(microphone_begin_recording(), TAG, "microphone start");
    std::array<int16_t, 256> samples{};
    std::size_t total = 0;
    esp_err_t result = ESP_OK;
    for (int second = 1; second <= 20 && result == ESP_OK; ++second) {
        std::size_t window_count = 0;
        uint64_t energy = 0;
        int peak = 0;
        unsigned clipped = 0;
        while (window_count < PIXELPET_AUDIO_INPUT_SAMPLE_RATE) {
            std::size_t count = 0;
            const auto wanted = std::min(samples.size(),
                std::size_t(PIXELPET_AUDIO_INPUT_SAMPLE_RATE) - window_count);
            result = microphone_read(samples.data(), wanted, &count);
            if (result != ESP_OK || count == 0) {
                if (result == ESP_OK) result = ESP_ERR_INVALID_SIZE;
                break;
            }
            for (std::size_t i = 0; i < count; ++i) {
                const int value = samples[i];
                peak = std::max(peak, std::abs(value));
                energy += int64_t(value) * value;
                if (std::abs(value) >= 32760) ++clipped;
            }
            window_count += count;
            total += count;
        }
        if (result == ESP_OK) {
            const auto rms = std::sqrt(double(energy) / window_count);
            ESP_LOGI(TAG, "MIC_TEST: second=%d samples=%u rms=%.1f peak=%d clipped=%u",
                     second, unsigned(window_count), rms, peak, clipped);
        }
    }
    const auto stopped = microphone_end_recording();
    ESP_LOGI(TAG, "MIC_TEST: total_samples=%u result=%s stop=%s", unsigned(total),
             esp_err_to_name(result), esp_err_to_name(stopped));
    return result != ESP_OK ? result : stopped;
}

esp_err_t animation_test() {
    ESP_RETURN_ON_ERROR(display_init(), TAG, "display init");
    constexpr int side = 64;
    static std::array<uint16_t, side * side> tile;
    for (unsigned frame = 0; frame < 40; ++frame) {
        tile.fill(0x0000);
        for (int y = 8; y < 56; ++y) {
            for (int x = 8; x < 56; ++x) {
                const bool eye = (x >= 16 && x < 24) || (x >= 40 && x < 48);
                const bool blink = frame % 20 >= 18;
                const bool mouth = x >= 24 && x < 40 && y >= 38 &&
                                   y < 40 + int(frame % 4) * 2;
                tile[y * side + x] = (mouth || (eye && y >= 23 && y < (blink ? 25 : 31)))
                    ? 0x0000 : 0xffe0;
            }
        }
        ESP_RETURN_ON_ERROR(display_region((PIXELPET_DISPLAY_WIDTH-side)/2,
                                            (PIXELPET_DISPLAY_HEIGHT-side)/2,
                                            side, side, tile.data()), TAG, "animation tile");
        vTaskDelay(pdMS_TO_TICKS(100));
    }
    return ESP_OK;
}

esp_err_t speaker_test() {
    ESP_RETURN_ON_ERROR(speaker_init(), TAG, "speaker init");
    constexpr int rate = PIXELPET_AUDIO_OUTPUT_SAMPLE_RATE;
    constexpr int duration = rate / 4;
    std::array<int16_t, 120> samples{};
    for (int offset = 0; offset < duration; offset += samples.size()) {
        const int count = std::min(int(samples.size()), duration - offset);
        for (int i = 0; i < count; ++i) {
            const int position = offset + i;
            const float envelope = std::min({1.0f, position / 240.0f, (duration - position) / 240.0f});
            samples[i] = int16_t(1024 * envelope * std::sin(6.2831853f * 440 * position / rate));
        }
        ESP_RETURN_ON_ERROR(speaker_write(samples.data(), count), TAG, "speaker tone");
    }
    samples.fill(0);
    return speaker_write(samples.data(), samples.size());
}

esp_err_t touch_test() {
    ESP_RETURN_ON_ERROR(touch_init(), TAG, "touch init");
    bool prior = false;
    for (int i = 0; i < 375; ++i) {
        bool pressed = false;
        ESP_RETURN_ON_ERROR(touch_read(&pressed), TAG, "touch sample");
        if (i == 0 || pressed != prior) ESP_LOGI(TAG, "Touch: %s", pressed ? "pressed" : "released");
        prior = pressed;
        vTaskDelay(pdMS_TO_TICKS(40));
    }
    return ESP_OK;
}
}

esp_err_t run_hardware_smoke(SmokeMode mode) {
    if (!(mode == SmokeMode::Speaker && pixelpet_speaker_test_enabled()) &&
        !(mode == SmokeMode::Microphone && pixelpet_microphone_test_enabled()) &&
        (!PIXELPET_HARDWARE_ENABLED || !pixelpet_board_config().hardware_ready())) {
        ESP_LOGW(TAG, "HW_PENDING: physical test blocked by pinmap approval gate");
        return ESP_ERR_INVALID_STATE;
    }
    ESP_LOGW(TAG, "HW_PENDING: selected physical test started");
    switch (mode) {
        case SmokeMode::Display: return display_test();
        case SmokeMode::Animation: return animation_test();
        case SmokeMode::Microphone:
#if CONFIG_PIXELPET_MICROPHONE_SERIAL_PCM
            return microphone_serial_capture();
#else
            return microphone_test();
#endif
        case SmokeMode::Speaker:
            ESP_LOGI(TAG, "SPEAKER_TEST: three low-amplitude 440 Hz tones in 3 seconds");
            vTaskDelay(pdMS_TO_TICKS(3000));
            for (int tone = 0; tone < 3; ++tone) {
                ESP_LOGI(TAG, "SPEAKER_TEST: tone %d/3", tone + 1);
                ESP_RETURN_ON_ERROR(speaker_test(), TAG, "speaker tone");
                vTaskDelay(pdMS_TO_TICKS(1000));
            }
            ESP_LOGI(TAG, "SPEAKER_TEST: output completed; confirm sound by listening");
            return ESP_OK;
        case SmokeMode::Touch: return touch_test();
        case SmokeMode::Motor:
            ESP_RETURN_ON_ERROR(haptic_init(), TAG, "motor init");
            return haptic_pulse(70, false, false);
    }
    return ESP_ERR_INVALID_ARG;
}
}
