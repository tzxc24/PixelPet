#include "driver_interlock.h"
#include <atomic>
#include <cassert>
#include <thread>
int main(){
 DriverInterlock gate;
 std::atomic<bool> motor{false},capture_ready{false};
 assert(gate.begin_pulse([&]{motor=true;}));
 assert(!gate.begin_pulse([&]{assert(false && "active pulse must reject another owner");}));
 std::thread recording([&]{gate.begin_capture([&]{motor=false;});capture_ready=true;});
 recording.join();
 assert(capture_ready&&!motor&&!gate.pulse_active());
 assert(!gate.begin_pulse([&]{motor=true;}));
 gate.end_capture();
 assert(!gate.begin_pulse([&]{assert(false && "cancelled pulse must finish its cleanup");}));
 gate.end_pulse([&]{motor=false;});
 assert(gate.begin_pulse([&]{motor=true;}));
 gate.end_pulse([&]{motor=false;});
 assert(!motor);
}
