
#pragma once

#include <algorithm>
#include <string>

#include <chrono>
#include <parlay/primitives.h>
#include "../datatypes.hpp"
#include "../sequence.hpp"

namespace PLIS {

class PLIS {
 public:
 PLIS() {}

    template <class T>
    static constexpr bool accepts() {
        return (Datatype<T>::hasUnsignedKey());
    }
    static bool isParallel() { return true; }

    static std::string name() { return "parlay_integer_sort"; }

    template <class T, template <class T1> class Vector>
    static std::pair<double, double> sort(T* begin, T* end, size_t num_threads) {
        parlay::slice<T*, T*> data_slice = parlay::make_slice(begin, end);
        auto start = std::chrono::high_resolution_clock::now();
        parlay::integer_sort_inplace(data_slice, Datatype<T>::getKeyExtractor());
        auto finish = std::chrono::high_resolution_clock::now();
        std::chrono::duration<double, std::milli> elapsed = finish - start;
        return {0, elapsed.count()};
    }
};

} 
