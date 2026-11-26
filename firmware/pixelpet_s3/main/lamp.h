#pragma once
#include <cstdint>
namespace pixelpet {
void lamp_init();
void lamp_command(uint32_t revision, uint32_t level, uint32_t seconds, bool breath);
}
