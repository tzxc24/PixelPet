#include "drivers.h"
#include "board_config.h"
#include <cassert>
int main(){
 assert(!pixelpet_board_config().approved);
 assert(board_init()==ESP_ERR_INVALID_STATE);
 assert(display_init()==ESP_ERR_INVALID_STATE);
 assert(microphone_init()==ESP_ERR_INVALID_STATE);
 float noise=0;assert(microphone_prepare(&noise)==ESP_ERR_INVALID_STATE);
 assert(microphone_prepare(nullptr)==ESP_ERR_INVALID_ARG);
 assert(speaker_init()==ESP_ERR_INVALID_STATE);
 assert(touch_init()==ESP_ERR_INVALID_STATE);
 assert(haptic_init()==ESP_ERR_INVALID_STATE);
 assert(haptic_pulse(50,true,false)==ESP_ERR_INVALID_STATE);
 assert(haptic_pulse(50,false,true)==ESP_ERR_INVALID_STATE);
 assert(haptic_pulse(501,false,false)==ESP_ERR_INVALID_ARG);
 uint16_t pixel=0;assert(display_region(-1,0,1,1,&pixel)==ESP_ERR_INVALID_ARG);
 bool touch=false;assert(touch_read(&touch)==ESP_ERR_INVALID_STATE);
}
