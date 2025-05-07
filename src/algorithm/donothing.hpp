
#pragma once

#include <algorithm>
#include <string>

#include <chrono>
#include "../datatypes.hpp"
#include "../sequence.hpp"

namespace NOTHING
{

    class NOTHING
    {
    public:
        NOTHING() {}

        template <class T>
        static constexpr bool accepts()
        {
            return true;
        }
        static bool isParallel() { return true; }

        static std::string name() { return "do_nothing"; }

        template <class T, template <class T1> class Vector>
        static std::pair<double, double> sort(T *begin, T *end, size_t num_threads)
        {
            auto start = std::chrono::high_resolution_clock::now();
            T tmp1 = *begin;
            T tmp2 = *(end - 1);
            T tmp3 = tmp1;
            begin[(end - begin) / 2] = tmp3;
            asm volatile("" : : "g"(tmp1), "g"(tmp2), "g"(tmp3) : "memory"); // prevent optimization
            auto finish = std::chrono::high_resolution_clock::now();
            std::chrono::duration<double, std::milli> elapsed = finish - start;
            return {0, elapsed.count()};
        }
    };

}
