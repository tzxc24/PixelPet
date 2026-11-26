#include "lamp.h"
#include "driver/ledc.h"
#include "esp_check.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include <algorithm>
#include <cmath>

namespace pixelpet {
namespace {
SemaphoreHandle_t mutex = nullptr;
struct Target { uint32_t revision=0, level=0, seconds=3; bool breath=false; } target;
constexpr auto CHANNEL = LEDC_CHANNEL_0;
constexpr auto MODE = LEDC_LOW_SPEED_MODE;
void task(void*) {
    Target current;
    float level=0, initial=0;
    uint32_t elapsed=0;
    while (true) {
        xSemaphoreTake(mutex, portMAX_DELAY);
        const auto next=target;
        xSemaphoreGive(mutex);
        if (next.revision!=current.revision) {
            current=next;
            initial=level;
            elapsed=0;
        }
        const float progress=std::min(1.0f, elapsed/(current.seconds*1000.0f));
        if (current.breath) {
            constexpr float pi=3.14159265f;
            level=current.level*(1.0f-std::cos(2*pi*elapsed/(current.seconds*1000.0f)))/2;
        } else {
            level=initial+(current.level-initial)*progress;
        }
        ledc_set_duty(MODE, CHANNEL, uint32_t(std::clamp(level,0.0f,100.0f)*8191/100));
        ledc_update_duty(MODE, CHANNEL);
        elapsed=(current.breath ? (elapsed+20)%(current.seconds*1000) : std::min(elapsed+20,current.seconds*1000));
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}
}
void lamp_init() {
    ledc_timer_config_t timer{};
    timer.speed_mode=MODE;
    timer.timer_num=LEDC_TIMER_0;
    timer.duty_resolution=LEDC_TIMER_13_BIT;
    timer.freq_hz=1000;
    timer.clk_cfg=LEDC_AUTO_CLK;
    ESP_ERROR_CHECK(ledc_timer_config(&timer));
    ledc_channel_config_t channel{};
    channel.gpio_num=3;
    channel.speed_mode=MODE;
    channel.channel=CHANNEL;
    channel.timer_sel=LEDC_TIMER_0;
    channel.duty=0;
    ESP_ERROR_CHECK(ledc_channel_config(&channel));
    mutex=xSemaphoreCreateMutex();
    configASSERT(mutex);
    configASSERT(xTaskCreate(task,"lamp",2048,nullptr,2,nullptr)==pdPASS);
}
void lamp_command(uint32_t revision,uint32_t level,uint32_t seconds,bool breath) {
    if (!mutex || !revision || level>100 || seconds>600) return;
    xSemaphoreTake(mutex,portMAX_DELAY);
    if (target.revision!=revision) target={revision,level,std::max(uint32_t(1),seconds),breath};
    xSemaphoreGive(mutex);
}
}
