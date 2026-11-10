#pragma once
#include "esp_err.h"

namespace pixelpet {
esp_err_t run_network(bool wifi_only = false);
}
