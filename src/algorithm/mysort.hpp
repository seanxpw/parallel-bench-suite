
#pragma once

#include <algorithm>
#include <string>

#include <chrono>
#include <quicksort.h>
#include "../datatypes.hpp"
#include "../sequence.hpp"

namespace mysort {

class Mysort {
 public:
 Mysort() {}

    // 只接受简单键类型
    // 只接受简单键类型，显式拒绝 pair_t 类型
    template <class T>
    static constexpr bool accepts() {
        if constexpr (std::is_same<T, pair_t>::value) {
            return false;  // 显式拒绝 pair_t 类型
        } else {
            return is_simple_key_type<T>::value;  // 对其他类型使用 is_simple_key_type 判断
        }
    }


    static bool isParallel() { return true; }

    static std::string name() { return "mysort"; }

    template <class T, template <class T1> class Vector>
    static std::pair<double, double> sort(T* begin, T* end, size_t num_threads) {
        auto start = std::chrono::high_resolution_clock::now();
        quicksort(begin, end - begin);
        auto finish = std::chrono::high_resolution_clock::now();
        std::chrono::duration<double, std::milli> elapsed = finish - start;
        return {0, elapsed.count()};
    }
};

} 
