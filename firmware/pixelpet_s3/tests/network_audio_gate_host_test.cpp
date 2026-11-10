#include "board_config.h"
#include <cassert>
int main() {
    assert(pixelpet_network_audio_enabled());
    assert(!pixelpet_board_config().approved);
    assert(!pixelpet_speaker_test_enabled());
    assert(!pixelpet_microphone_test_enabled());
}
