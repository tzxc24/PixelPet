#pragma once
#include <array>
#include <cstddef>
namespace pixelpet {
// PROVISIONAL: every signal is unassigned until reviewed against the real board.
struct BoardConfig {
 enum Signal { SCK, MOSI, CS, DC, RST, BL, FONT_CS, MIC_BCLK, MIC_WS, MIC_DIN,
               SPK_BCLK, SPK_WS, SPK_DOUT, TOUCH, MOTOR, COUNT };
 std::array<int,COUNT> pins{};
 bool approved=false;
 BoardConfig() { pins.fill(-1); }
 static bool prohibited(int p) {
  return p==0 || p==3 || p==19 || p==20 || (p>=22 && p<=37) || p==45 || p==46;
 }
 bool validate() const {
  for(std::size_t i=0;i<pins.size();++i) {
   int p=pins[i]; if(p==-1) continue;
   if(!approved || p<0 || p>48 || prohibited(p)) return false;
   for(std::size_t j=0;j<i;++j) if(pins[j]==p) return false;
  }
  return true;
 }
 bool hardware_ready() const {
  if(!approved || !validate()) return false;
  for(auto signal:{SCK,MOSI,CS,DC,RST,MIC_BCLK,MIC_WS,MIC_DIN,SPK_BCLK,SPK_WS,SPK_DOUT,TOUCH,MOTOR})
   if(pins[signal]<0) return false;
  return true;
 }
};
enum class State { IDLE, LISTENING, THINKING, SPEAKING, SLEEP, HAPPY, SHY, SURPRISED, ANNOYED, ERROR };
class PetState {
 State state_=State::IDLE;
 public:
 State state() const { return state_; }
 bool start_recording() { if(state_==State::SPEAKING || state_==State::LISTENING) return false; state_=State::LISTENING; return true; }
 bool stop_recording() { if(state_!=State::LISTENING) return false; state_=State::THINKING; return true; }
 bool start_speaking() { if(state_==State::LISTENING) return false; state_=State::SPEAKING; return true; }
 void stop_speaking() { state_=State::IDLE; }
 bool haptic_allowed(bool enabled,bool quiet) const { return enabled && !quiet && state_!=State::LISTENING; }
};
// Configuration contracts, not initialized physical drivers.
struct DisplayConfig { int width=240,height=240,offset_x=0,offset_y=0; bool bgr=false; };
struct AudioInputConfig { int sample_rate=16000,slot_bits=32; };
struct AudioOutputConfig { int sample_rate=24000,slot_bits=16; };
struct TouchConfig { int debounce_ms=40,long_press_ms=650; bool active_high=true; };
struct HapticConfig { int max_pulse_ms=500; bool pwm_verified=false; };
struct NetworkConfig { const char* gateway_url=""; bool ble_provisioning_enabled=false; };
struct ClockConfig { const char* timezone="Asia/Shanghai"; };
}
