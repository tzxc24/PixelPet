#include "speaker_gate.h"
#include <cassert>
int main() {
    using pixelpet::speaker_test_allowed;
    assert(!speaker_test_allowed(false, true, 7, 8, 9));
    assert(!speaker_test_allowed(true, false, 7, 8, 9));
    assert(speaker_test_allowed(true, true, 7, 8, 9));
    assert(!speaker_test_allowed(true, true, 7, 7, 9));
    assert(!speaker_test_allowed(true, true, -1, 8, 9));
    assert(!speaker_test_allowed(true, true, 19, 8, 9));
    assert(!speaker_test_allowed(true, true, 35, 8, 9));
}
