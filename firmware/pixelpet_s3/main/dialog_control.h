#pragma once
#include <string_view>
namespace pixelpet {
class DialogControl {
    enum class Mode { Off, Active, Standby };
    Mode mode_ = Mode::Off;
public:
    void command(char value) {
        if (value == 'd') mode_ = Mode::Active;
        if (value == 'w') mode_ = Mode::Standby;
        if (value == 'c') mode_ = Mode::Off;
    }
    bool apply_state(std::string_view value) {
        if (value == "standby") mode_ = Mode::Standby;
        else if (value == "active") mode_ = Mode::Active;
        else return false;
        return true;
    }
    bool active() const { return mode_ == Mode::Active; }
    bool standby() const { return mode_ == Mode::Standby; }
    bool enabled() const { return mode_ != Mode::Off; }
};
}
