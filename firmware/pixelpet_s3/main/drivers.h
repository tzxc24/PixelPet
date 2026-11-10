#pragma once
#include <cstddef>
#include <cstdint>
#ifdef PIXELPET_HOST_MOCK
using esp_err_t=int;
constexpr esp_err_t ESP_OK=0,ESP_ERR_INVALID_STATE=0x103,ESP_ERR_INVALID_ARG=0x102;
#else
#include "esp_err.h"
#endif
esp_err_t board_init();
esp_err_t display_init();
esp_err_t microphone_init();
esp_err_t microphone_prepare(float* noise_rms);
esp_err_t microphone_begin_recording();
esp_err_t microphone_end_recording();
esp_err_t speaker_init();
esp_err_t touch_init();
esp_err_t haptic_init();
esp_err_t display_region(int x,int y,int width,int height,const uint16_t* rgb565);
esp_err_t microphone_read(int16_t* pcm,std::size_t count,std::size_t* received);
esp_err_t speaker_write(const int16_t* pcm,std::size_t count);
esp_err_t touch_read(bool* pressed);
esp_err_t haptic_pulse(unsigned duration_ms,bool recording,bool quiet);
