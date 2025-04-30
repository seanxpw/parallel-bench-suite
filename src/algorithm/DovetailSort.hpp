// DovetailSort

#pragma once

#include <string>
#include <integer_sort.h>

#include "../datatypes.hpp"
#include "../sequence.hpp"

namespace DovetailSort {

class DovetailSort {
 public:
 DovetailSort() {}

    template <class T>
    static constexpr bool accepts() {
        if constexpr (std::is_same<T, pair_t>::value) {
            return false; 
        } else {
        return Datatype<T>::hasUnsignedKey();
        }
    }

    static bool isParallel() { return true; }

    static std::string name() { return "dovetailsort"; }

    template <class T, template <class T1> class Vector>
    static std::pair<double, double> sort(T* begin, T* end, size_t num_threads) {
        static_assert(Datatype<T>::hasUnsignedKey());
        parlay::slice<T*, T*> data_slice = parlay::make_slice(begin, end);
        auto start = std::chrono::high_resolution_clock::now();
        integer_sort_inplace2(data_slice, Datatype<T>::getKeyExtractor());
        auto finish = std::chrono::high_resolution_clock::now();
        std::chrono::duration<double, std::milli> elapsed = finish - start;
        return {0, elapsed.count()};
    }
};

}  
