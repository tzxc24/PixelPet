#include "pet_core.h"
#include <cassert>
int main() {
 pixelpet::BoardConfig board;
 assert(board.validate());
 assert(!board.hardware_ready());
 board.pins[0]=4;
 assert(!board.validate());
 board.approved=true;
 assert(board.validate());
 board.pins[1]=4;
 assert(!board.validate());
 board.pins[1]=26;
 assert(!board.validate());
 pixelpet::PetState pet;
 assert(pet.start_recording());
 assert(!pet.start_speaking());
 assert(!pet.haptic_allowed(true,false));
 assert(pet.stop_recording());
 assert(pet.start_speaking());
 assert(!pet.start_recording());
 pet.stop_speaking();
 assert(pet.haptic_allowed(true,false));
 assert(!pet.haptic_allowed(true,true));
}
