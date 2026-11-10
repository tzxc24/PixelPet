#include "drivers.h"
#include "board_config.h"
#include "driver_interlock.h"
#include "voice_activity.h"
#include <array>
#ifndef PIXELPET_HOST_MOCK
#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "driver/i2s_std.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_ops.h"
#include "esp_lcd_panel_vendor.h"
#include "esp_timer.h"
#include "esp_attr.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include <algorithm>
#include <cstring>
static esp_lcd_panel_handle_t panel=nullptr;
static esp_lcd_panel_io_handle_t panel_io=nullptr;
static i2s_chan_handle_t microphone=nullptr,speaker=nullptr;
static bool touch_ready=false,motor_ready=false;
static bool microphone_running=false;
static DriverInterlock interlock;
static std::mutex display_lock;
static SemaphoreHandle_t lcd_done=nullptr;
constexpr int lcd_strip_rows = 20;
DMA_ATTR static uint16_t lcd_strip[PIXELPET_DISPLAY_WIDTH * lcd_strip_rows];
static bool display_faulted = false;
static bool lcd_transfer_done(esp_lcd_panel_io_handle_t,esp_lcd_panel_io_event_data_t*,void*) {
 BaseType_t wake=pdFALSE;
 xSemaphoreGiveFromISR(lcd_done,&wake);
 return wake==pdTRUE;
}
static void motor_off(){if(motor_ready)gpio_set_level((gpio_num_t)PIXELPET_PIN_MOTOR,0);}
#endif
// TODO(HW_PENDING): BL/CS-F and motor supply/threshold need electrical evidence.
static bool allowed() { return PIXELPET_HARDWARE_ENABLED && pixelpet_board_config().hardware_ready(); }

esp_err_t display_init() {
 if(!allowed()) return ESP_ERR_INVALID_STATE;
#ifndef PIXELPET_HOST_MOCK
 if(panel) return display_faulted ? ESP_ERR_INVALID_STATE : ESP_OK;
 spi_bus_config_t bus{};
 bus.sclk_io_num=PIXELPET_PIN_DISPLAY_SCK; bus.mosi_io_num=PIXELPET_PIN_DISPLAY_MOSI;
 bus.miso_io_num=-1;bus.quadwp_io_num=-1;bus.quadhd_io_num=-1;
 bus.max_transfer_sz=PIXELPET_DISPLAY_WIDTH*40*2;
 esp_err_t e=spi_bus_initialize(SPI2_HOST,&bus,SPI_DMA_CH_AUTO);if(e!=ESP_OK)return e;
 lcd_done=xSemaphoreCreateBinary();if(!lcd_done){spi_bus_free(SPI2_HOST);return ESP_ERR_NO_MEM;}
 esp_lcd_panel_io_spi_config_t io{};
 io.dc_gpio_num=(gpio_num_t)PIXELPET_PIN_DISPLAY_DC;io.cs_gpio_num=(gpio_num_t)PIXELPET_PIN_DISPLAY_CS;
 io.pclk_hz=PIXELPET_DISPLAY_SPI_HZ;io.lcd_cmd_bits=8;io.lcd_param_bits=8;io.spi_mode=0;io.trans_queue_depth=4;
 e=esp_lcd_new_panel_io_spi((esp_lcd_spi_bus_handle_t)SPI2_HOST,&io,&panel_io);
 if(e==ESP_OK){
  esp_lcd_panel_io_callbacks_t callbacks{};callbacks.on_color_trans_done=lcd_transfer_done;
  e=esp_lcd_panel_io_register_event_callbacks(panel_io,&callbacks,nullptr);
 }
 esp_lcd_panel_dev_config_t config{};
 config.reset_gpio_num=(gpio_num_t)PIXELPET_PIN_DISPLAY_RST;config.bits_per_pixel=16;
 config.data_endian=LCD_RGB_DATA_ENDIAN_LITTLE; // Matches uint16_t RGB565 and exported assets on ESP32-S3.
 config.rgb_ele_order=PIXELPET_DISPLAY_BGR?LCD_RGB_ELEMENT_ORDER_BGR:LCD_RGB_ELEMENT_ORDER_RGB;
 if(e==ESP_OK)e=esp_lcd_new_panel_st7789(panel_io,&config,&panel);
 if(e==ESP_OK)e=esp_lcd_panel_reset(panel);
 if(e==ESP_OK)e=esp_lcd_panel_init(panel);
 if(e==ESP_OK)e=esp_lcd_panel_set_gap(panel,PIXELPET_DISPLAY_OFFSET_X,PIXELPET_DISPLAY_OFFSET_Y);
 if(e==ESP_OK)e=esp_lcd_panel_disp_on_off(panel,true);
 if(e!=ESP_OK){
  if(panel)esp_lcd_panel_del(panel);
  if(panel_io)esp_lcd_panel_io_del(panel_io);
  panel=nullptr;panel_io=nullptr;
  vSemaphoreDelete(lcd_done);lcd_done=nullptr;
  spi_bus_free(SPI2_HOST);
 }
 return e;
#else
 return ESP_ERR_INVALID_STATE;
#endif
}

#ifndef PIXELPET_HOST_MOCK
static esp_err_t audio_init(bool input) {
 i2s_chan_handle_t* handle=input?&microphone:&speaker;
 if(*handle)return ESP_OK;
 i2s_chan_config_t channel=I2S_CHANNEL_DEFAULT_CONFIG(input?I2S_NUM_0:I2S_NUM_1,I2S_ROLE_MASTER);
 if(!input)channel.auto_clear_after_cb=true; // Idle and underrun output is silence.
 esp_err_t e=i2s_new_channel(&channel,input?nullptr:handle,input?handle:nullptr);if(e!=ESP_OK)return e;
 i2s_std_config_t config{};
 config.clk_cfg=I2S_STD_CLK_DEFAULT_CONFIG((uint32_t)(input?PIXELPET_AUDIO_INPUT_SAMPLE_RATE:PIXELPET_AUDIO_OUTPUT_SAMPLE_RATE));
 config.slot_cfg=I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(input?I2S_DATA_BIT_WIDTH_32BIT:I2S_DATA_BIT_WIDTH_16BIT,I2S_SLOT_MODE_MONO);
 config.slot_cfg.slot_mask=I2S_STD_SLOT_LEFT;
 config.gpio_cfg.mclk=I2S_GPIO_UNUSED;
 config.gpio_cfg.bclk=(gpio_num_t)(input?PIXELPET_PIN_MIC_BCLK:PIXELPET_PIN_SPEAKER_BCLK);
 config.gpio_cfg.ws=(gpio_num_t)(input?PIXELPET_PIN_MIC_WS:PIXELPET_PIN_SPEAKER_WS);
 config.gpio_cfg.din=input?(gpio_num_t)PIXELPET_PIN_MIC_DIN:I2S_GPIO_UNUSED;
 config.gpio_cfg.dout=input?I2S_GPIO_UNUSED:(gpio_num_t)PIXELPET_PIN_SPEAKER_DOUT;
 e=i2s_channel_init_std_mode(*handle,&config);
 if(e==ESP_OK && !input)e=i2s_channel_enable(*handle);
 if(e!=ESP_OK){i2s_del_channel(*handle);*handle=nullptr;}
 return e;
}
#endif
esp_err_t microphone_init(){if(!allowed() && !pixelpet_microphone_test_enabled() && !pixelpet_network_audio_enabled())return ESP_ERR_INVALID_STATE;
#ifndef PIXELPET_HOST_MOCK
 return audio_init(true);
#else
 return ESP_ERR_INVALID_STATE;
#endif
}
esp_err_t speaker_init(){if(!allowed() && !pixelpet_speaker_test_enabled() && !pixelpet_network_audio_enabled())return ESP_ERR_INVALID_STATE;
#ifndef PIXELPET_HOST_MOCK
 return audio_init(false);
#else
 return ESP_ERR_INVALID_STATE;
#endif
}
esp_err_t touch_init(){if(!allowed())return ESP_ERR_INVALID_STATE;
#ifndef PIXELPET_HOST_MOCK
 gpio_config_t config{};config.pin_bit_mask=1ULL<<PIXELPET_PIN_TOUCH;config.mode=GPIO_MODE_INPUT;
 esp_err_t e=gpio_config(&config);touch_ready=e==ESP_OK;return e;
#else
 return ESP_ERR_INVALID_STATE;
#endif
}
esp_err_t haptic_init(){if(!allowed())return ESP_ERR_INVALID_STATE;
#ifndef PIXELPET_HOST_MOCK
 // Set output latch LOW before enabling the driver. Never energize motor here.
 esp_err_t e=gpio_set_level((gpio_num_t)PIXELPET_PIN_MOTOR,0);if(e!=ESP_OK)return e;
 gpio_config_t config{};config.pin_bit_mask=1ULL<<PIXELPET_PIN_MOTOR;config.mode=GPIO_MODE_OUTPUT;
 e=gpio_config(&config);motor_ready=e==ESP_OK;return e;
#else
 return ESP_ERR_INVALID_STATE;
#endif
}
esp_err_t board_init(){if(!allowed())return ESP_ERR_INVALID_STATE;
 for(auto init:{haptic_init,touch_init,display_init,microphone_init,speaker_init}){auto e=init();if(e!=ESP_OK)return e;}
 return ESP_OK;
}
esp_err_t display_region(int x,int y,int width,int height,const uint16_t* rgb565){
 if(!rgb565||x<0||y<0||width<=0||height<=0||x>PIXELPET_DISPLAY_WIDTH-width||y>PIXELPET_DISPLAY_HEIGHT-height)return ESP_ERR_INVALID_ARG;
 if(!allowed())return ESP_ERR_INVALID_STATE;
#ifndef PIXELPET_HOST_MOCK
 std::lock_guard<std::mutex> guard(display_lock);
 if(!panel||display_faulted)return ESP_ERR_INVALID_STATE;
 for(int offset=0;offset<height;offset+=lcd_strip_rows){
  const int rows=std::min(lcd_strip_rows,height-offset);
  std::memcpy(lcd_strip,rgb565+offset*width,rows*width*sizeof(uint16_t));
  xSemaphoreTake(lcd_done,0);
  const auto result=esp_lcd_panel_draw_bitmap(panel,x,y+offset,x+width,y+offset+rows,lcd_strip);
  if(result!=ESP_OK)return result;
  if(xSemaphoreTake(lcd_done,pdMS_TO_TICKS(500))!=pdTRUE){
   // Keep persistent DMA storage untouched until reboot after a lost completion.
   display_faulted=true;
   return ESP_ERR_TIMEOUT;
  }
 }
 return ESP_OK;
#else
 return ESP_ERR_INVALID_STATE;
#endif
}
esp_err_t microphone_prepare(float* noise_rms) {
 if(!noise_rms)return ESP_ERR_INVALID_ARG;
 const auto initialized=microphone_init();
 if(initialized!=ESP_OK)return initialized;
#ifndef PIXELPET_HOST_MOCK
 if(interlock.recording())return ESP_ERR_INVALID_STATE;
 motor_off();
 if(!microphone_running){
  const auto enabled=i2s_channel_enable(microphone);
  if(enabled!=ESP_OK)return enabled;
  microphone_running=true;
 }
 int32_t raw[256];
 int16_t pcm[256];
 std::array<double,16> noise{};
 std::size_t noise_windows=0;
 std::size_t remaining=2*PIXELPET_AUDIO_INPUT_SAMPLE_RATE;
 while(remaining){
  const auto count=std::min(remaining,std::size_t(256));
  std::size_t bytes=0;
  const auto result=i2s_channel_read(microphone,raw,count*sizeof(int32_t),&bytes,120);
  if(result!=ESP_OK || bytes!=count*sizeof(int32_t)){
   i2s_channel_disable(microphone);microphone_running=false;
   return result==ESP_OK?ESP_ERR_TIMEOUT:result;
  }
  if(remaining<=4096 && noise_windows<noise.size()){
   for(std::size_t i=0;i<count;++i)pcm[i]=int16_t(raw[i]>>16);
   noise[noise_windows++]=pixelpet::pcm_rms(pcm,count);
  }
  remaining-=count;
 }
 std::sort(noise.begin(),noise.begin()+noise_windows);
 *noise_rms=noise_windows?float(noise[noise_windows/2]):0;
 return ESP_OK;
#else
 return ESP_ERR_INVALID_STATE;
#endif
}

esp_err_t microphone_begin_recording(){
 if(!allowed() && !pixelpet_microphone_test_enabled() && !pixelpet_network_audio_enabled())return ESP_ERR_INVALID_STATE;
#ifndef PIXELPET_HOST_MOCK
 if(!microphone||interlock.recording())return ESP_ERR_INVALID_STATE;
 interlock.begin_capture(motor_off); // Motor LOW synchronously before any PCM read.
 const auto result=microphone_running?ESP_OK:i2s_channel_enable(microphone);
 if(result!=ESP_OK)interlock.end_capture();
 else microphone_running=true;
 return result;
#else
 return ESP_ERR_INVALID_STATE;
#endif
}
esp_err_t microphone_end_recording(){
 if(!allowed() && !pixelpet_microphone_test_enabled() && !pixelpet_network_audio_enabled())return ESP_ERR_INVALID_STATE;
#ifndef PIXELPET_HOST_MOCK
 if(!microphone || !interlock.recording())return ESP_ERR_INVALID_STATE;
 const auto result=i2s_channel_disable(microphone);
 microphone_running=false;
 interlock.end_capture();return result;
#else
 return ESP_ERR_INVALID_STATE;
#endif
}
esp_err_t microphone_read(int16_t* pcm,std::size_t count,std::size_t* received){
 if(!pcm||!received||count==0||count>4096)return ESP_ERR_INVALID_ARG;
 *received=0;if(!allowed() && !pixelpet_microphone_test_enabled() && !pixelpet_network_audio_enabled())return ESP_ERR_INVALID_STATE;
#ifndef PIXELPET_HOST_MOCK
 if(!microphone||!interlock.recording())return ESP_ERR_INVALID_STATE;
 // Read a fixed DMA-sized block, even when a smoke test requests a larger buffer.
 int32_t raw[256];
 while(*received<count){
  const auto batch=std::min(count-*received,std::size_t(256));
  std::size_t bytes=0;
  const auto result=i2s_channel_read(microphone,raw,batch*sizeof(int32_t),&bytes,120);
  const auto got=bytes/sizeof(int32_t);
  for(std::size_t i=0;i<got;++i)pcm[*received+i]=(int16_t)(raw[i]>>16);
  *received+=got;
  if(result!=ESP_OK || got!=batch)return result==ESP_OK?ESP_ERR_TIMEOUT:result;
 }
 return ESP_OK;
#else
 return ESP_ERR_INVALID_STATE;
#endif
}
esp_err_t speaker_write(const int16_t* pcm,std::size_t count){
 if(!pcm||!count||count>4096)return ESP_ERR_INVALID_ARG;
 if(!allowed() && !pixelpet_speaker_test_enabled() && !pixelpet_network_audio_enabled())return ESP_ERR_INVALID_STATE;
#ifndef PIXELPET_HOST_MOCK
 if(!speaker||interlock.recording())return ESP_ERR_INVALID_STATE;
 std::size_t sent=0;
 const auto result=i2s_channel_write(speaker,pcm,count*sizeof(int16_t),&sent,1000);
 return result==ESP_OK && sent!=count*sizeof(int16_t) ? ESP_ERR_TIMEOUT : result;
#else
 return ESP_ERR_INVALID_STATE;
#endif
}
esp_err_t touch_read(bool* pressed){
 if(!pressed)return ESP_ERR_INVALID_ARG;
 if(!allowed())return ESP_ERR_INVALID_STATE;
#ifndef PIXELPET_HOST_MOCK
 if(!touch_ready)return ESP_ERR_INVALID_STATE;
 *pressed=gpio_get_level((gpio_num_t)PIXELPET_PIN_TOUCH)==PIXELPET_TOUCH_ACTIVE_HIGH;return ESP_OK;
#else
 return ESP_ERR_INVALID_STATE;
#endif
}
esp_err_t haptic_pulse(unsigned duration_ms,bool recording,bool quiet){
 if(!duration_ms||duration_ms>500)return ESP_ERR_INVALID_ARG;
 if(!allowed()||recording||quiet)return ESP_ERR_INVALID_STATE;
#ifndef PIXELPET_HOST_MOCK
 if(!motor_ready)return ESP_ERR_INVALID_STATE;
 int64_t deadline=0;
 if(!interlock.begin_pulse([&]{
  deadline=esp_timer_get_time()+int64_t(duration_ms)*1000;
  gpio_set_level((gpio_num_t)PIXELPET_PIN_MOTOR,1);
 }))return ESP_ERR_INVALID_STATE;
 // Compare elapsed wall time; a FreeRTOS tick is not necessarily 5 ms.
 while(esp_timer_get_time()<deadline&&interlock.pulse_active())vTaskDelay(1);
 interlock.end_pulse(motor_off);
 return ESP_OK;
#else
 return ESP_ERR_INVALID_STATE;
#endif
}
