#include "hardware_smoke.h"
#include "network.h"
#include "esp_log.h"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <cstdint>

#if CONFIG_PIXELPET_BOOT_NETWORK || CONFIG_PIXELPET_BOOT_WIFI
static void network_task(void*) {
    const auto result = pixelpet::run_network(
#if CONFIG_PIXELPET_BOOT_WIFI
        true
#else
        false
#endif
    );
    ESP_LOGI("pixelpet", "Network boot mode ended: %s", esp_err_to_name(result));
    vTaskDelete(nullptr);
}
#endif

[[maybe_unused]] static esp_err_t memory_probe() {
    constexpr size_t length = 4096;
    auto* samples = static_cast<volatile uint32_t*>(
        heap_caps_malloc(length * sizeof(uint32_t), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    ESP_LOGI("pixelpet", "PSRAM heap total=%u free=%u",
             unsigned(heap_caps_get_total_size(MALLOC_CAP_SPIRAM)),
             unsigned(heap_caps_get_free_size(MALLOC_CAP_SPIRAM)));
    if (!samples) return ESP_ERR_NO_MEM;
    for (size_t i = 0; i < length; ++i) samples[i] = uint32_t(i) ^ 0xa55a5aa5U;
    bool valid = true;
    for (size_t i = 0; i < length; ++i) {
        if (samples[i] != (uint32_t(i) ^ 0xa55a5aa5U)) { valid = false; break; }
    }
    heap_caps_free(const_cast<uint32_t*>(samples));
    return valid ? ESP_OK : ESP_FAIL;
}

extern "C" void app_main() {
#if CONFIG_PIXELPET_BOOT_NETWORK || CONFIG_PIXELPET_BOOT_WIFI
    // Leave headroom for TLS handshakes and bounded server-frame parsing.
    if (xTaskCreate(network_task, "pixelpet_net", 12288, nullptr, 4, nullptr) != pdPASS) {
        ESP_LOGE("pixelpet", "Network task allocation failed");
    }
#else
#if CONFIG_PIXELPET_BOOT_DISPLAY
    const auto result = pixelpet::run_hardware_smoke(pixelpet::SmokeMode::Display);
#elif CONFIG_PIXELPET_BOOT_ANIMATION
    const auto result = pixelpet::run_hardware_smoke(pixelpet::SmokeMode::Animation);
#elif CONFIG_PIXELPET_BOOT_MEMORY
    const auto result = memory_probe();
#elif CONFIG_PIXELPET_BOOT_MICROPHONE
    const auto result = pixelpet::run_hardware_smoke(pixelpet::SmokeMode::Microphone);
#elif CONFIG_PIXELPET_BOOT_SPEAKER
    const auto result = pixelpet::run_hardware_smoke(pixelpet::SmokeMode::Speaker);
#elif CONFIG_PIXELPET_BOOT_TOUCH
    const auto result = pixelpet::run_hardware_smoke(pixelpet::SmokeMode::Touch);
#elif CONFIG_PIXELPET_BOOT_MOTOR
    const auto result = pixelpet::run_hardware_smoke(pixelpet::SmokeMode::Motor);
#else
#error "Select one PixelPet boot mode"
#endif
    ESP_LOGI("pixelpet", "Boot mode ended: %s", esp_err_to_name(result));
#endif
}
