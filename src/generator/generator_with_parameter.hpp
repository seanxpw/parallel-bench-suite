
#pragma once

#include <algorithm>
#include <climits>
#include <random>
#include <string>
#include <type_traits> // For SFINAE or traits if needed later
#include <array>       // For std::array
#include <vector>      // For std::vector (used by dependencies)
#include <string>      // For std::string
#include <stdexcept>   // For std::out_of_range
#include <type_traits> // For std::is_same_v
#include <cstdint>     // For uint32_t, uint64_t
#include <cstddef>     // For size_t
#include <random>      // For std::random_device, std::mt19937
#include <iostream>    // For std::cout in dummy functions

#include <tlx/math/integer_log2.hpp>
#include <SimdMt.hpp>

#include "../datatypes.hpp"
#include "../parallel/parallel_for.hpp"
#include "../pbbs_generators/data_types.h"
#include "../pbbs_generators/utils.h"
#include "../sequence.hpp"
#include "simple_alias.hpp"
#include "zipf_distribution.hpp"


// template <class T>
// constexpr bool isPrimitiveDatatypeConstructable() {
//     return std::is_same_v<T, pair_t>
//             || std::is_same_v<T, double>
//             || std::is_same_v<T, uint32_t>
//             || std::is_same_v<T, uint64_t>;
// }


template<typename DerivedGenerator>
struct ParameterizedGeneratorBase {
    constexpr static bool has_compile_time_params = true;
};


// --- Type Trait to check for parameterization via inheritance ---
template <typename T>
struct is_parameterized_generator
    : std::is_base_of<
          ParameterizedGeneratorBase<T>, // Is T derived from Base<T>?
          T>
{
};

// Helper variable template (C++17 onwards)
template<typename T>
inline constexpr bool is_parameterized_generator_v = is_parameterized_generator<T>::value;


class GenZipfPara : public ParameterizedGeneratorBase<GenZipfPara> {
    public:
        // 1. Define the structure for THIS generator's parameters
        struct ParamStruct {
            double s;
            size_t N; // Include N as it was hardcoded before
        };
    
        // 2. Define the list of parameter sets for THIS generator
        static constexpr std::array<ParamStruct, 3> param_list = {
            ParamStruct{0.5, 1000000}, // Parameter set 0 (index 0)
            ParamStruct{0.75, 1500000}, // Parameter set 1 (index 1)
            ParamStruct{0.9, 2000000}  // Parameter set 2 (index 2)
        };
    
        // 3. Define num_params (required by Base or trait checks)
        static constexpr size_t num_params() { return param_list.size(); }
    
        // --- Standard methods ---
        GenZipfPara() {} // Default constructor
    
        static std::string name() { return "zipf_para"; } // New name
    
        template <class T>
        constexpr static bool accepts() { // Copied from GenZipf
            return std::is_same_v<T, pair_t>
                || std::is_same_v<T, uint32_t>
                || std::is_same_v<T, uint64_t>
                || std::is_same_v<T, double>;
        }
    
        // --- Modified operator() ---
        template <class T>
        void operator()(T* begin, T* end, size_t param_index) { // Added param_index
            // Check index validity
            if (param_index >= num_params()) {
                throw std::out_of_range("Invalid parameter index (" + std::to_string(param_index) + ") for GenZipfPara");
            }
    
            // Get the specific parameters for this run using the index
            const ParamStruct& current_params = param_list[param_index];
            const double current_s = current_params.s;
            const size_t current_N = current_params.N;
    
            // std::cout << "    GenZipfPara operating with s=" << current_s << ", N=" << current_N
            //           << " (index " << param_index << ")" << std::endl;
    
            // Static assert for type checking (copied)
            static_assert(std::is_same_v<T, pair_t>
                          || std::is_same_v<T, uint32_t>
                          || std::is_same_v<T, uint64_t>
                          || std::is_same_v<T, double>);
    
            // *** CRITICAL: Create distribution and alias sampler dynamically ***
            // These are NO LONGER STATIC locals. They are created based on current_N/current_s.
            auto vdistr = thrill::common::ZipfDistribution::make_vec(current_N, current_s);
            wrs::simple_alias<uint32_t> alias(vdistr.begin(), vdistr.end());
            // *******************************************************************
    
            // Lambda captures the dynamically created 'alias' by reference
            auto make_zipf = [&alias](double random_val_0_to_1) { return alias(random_val_0_to_1); };
    
            // Check target type T and execute parallel fill (copied)
            if constexpr (std::is_same_v<T, pair_t>
                          || std::is_same_v<T, uint32_t>
                          || std::is_same_v<T, uint64_t>
                          || std::is_same_v<T, double>) {
                std::random_device rd;
                const uint32_t seed = rd(); // Generate seed once per call
                const size_t num_elements = std::distance(begin, end);
    
                std_parallel_for(num_elements,
                    [begin, seed, &make_zipf](size_t begin_idx, size_t end_idx, size_t thread_id) {
                        const auto b = begin + begin_idx;
                        const auto e = begin + end_idx;
                        SimdMtGenerator<double>::fill(seed + thread_id, b, e, make_zipf);
                    });
            }
        } // End operator()
    }; // End class GenZipfPara