#pragma once
#include <mutex>
// Portable synchronization policy; actual motor switch callback must be synchronous.
class DriverInterlock {
 mutable std::mutex lock_;
 bool recording_=false,motor_=false,pulse_owned_=false;
 public:
 template<class Switch> void begin_capture(Switch turn_off) {
  std::lock_guard<std::mutex> guard(lock_);
  recording_=true;motor_=false;turn_off();
 }
 void end_capture(){std::lock_guard<std::mutex> guard(lock_);recording_=false;}
 bool recording() const {std::lock_guard<std::mutex> guard(lock_);return recording_;}
 template<class Switch> bool begin_pulse(Switch turn_on) {
  std::lock_guard<std::mutex> guard(lock_);
  if(recording_||pulse_owned_)return false;
  pulse_owned_=motor_=true;turn_on();return true;
 }
 bool pulse_active()const{std::lock_guard<std::mutex> guard(lock_);return motor_&&!recording_;}
 template<class Switch> void end_pulse(Switch turn_off){
  std::lock_guard<std::mutex> guard(lock_);
  if(!pulse_owned_)return;
  pulse_owned_=motor_=false;turn_off();
 }
};
