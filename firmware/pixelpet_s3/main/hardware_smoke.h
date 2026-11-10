#pragma once
#include "esp_err.h"

namespace pixelpet {
enum class SmokeMode { Display, Animation, Microphone, Speaker, Touch, Motor };
esp_err_t run_hardware_smoke(SmokeMode mode);
}
