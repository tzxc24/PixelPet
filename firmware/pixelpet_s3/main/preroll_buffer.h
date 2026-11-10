#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>
namespace pixelpet {
class PrerollBuffer {
    int16_t* data_;
    std::size_t capacity_;
    std::size_t size_ = 0;
    std::size_t head_ = 0;
public:
    PrerollBuffer(int16_t* data, std::size_t capacity) : data_(data),capacity_(capacity) {}
    void append(const int16_t* samples, std::size_t count) {
        if (!data_ || !capacity_) return;
        for (std::size_t i=0;i<count;++i) {
            data_[head_]=samples[i];
            head_=(head_+1)%capacity_;
            size_=std::min(size_+1,capacity_);
        }
    }
    std::size_t flatten() {
        if (size_==capacity_ && capacity_)
            std::rotate(data_,data_+head_,data_+size_);
        if (size_==capacity_) head_=0;
        return size_;
    }
};
}
