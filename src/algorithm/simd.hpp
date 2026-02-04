
#pragma once

#include <algorithm>
#include <string>

#include <chrono>
#include "../datatypes.hpp"
#include "../sequence.hpp"
#include "../../extern/sample_sort_tiled/src/two_pass/two_pass_simd.hpp"
namespace simdsort {

class Simdsort {
 public:
 Simdsort() {}

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

    static std::string name() { return "simd"; }

    template <class T, template <class T1> class Vector>
    static std::pair<double, double> sort(T* begin, T* end, size_t num_threads) {
 parlay::slice<T*, T*> data_slice = parlay::make_slice(begin, end);
        auto start = std::chrono::high_resolution_clock::now();
        parlay::internal::sample_sort_inplace(data_slice, Datatype<T>::getComparator());
        auto finish = std::chrono::high_resolution_clock::now();
        std::chrono::duration<double, std::milli> elapsed = finish - start;
        return {0, elapsed.count()};
    }
};

} 
