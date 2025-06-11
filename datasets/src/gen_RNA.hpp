#pragma once
#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <cstdint>   // For uint64_t
#include <stdexcept>
#include <mutex>     // For std::once_flag
#include <array>
#include <algorithm> // For std::copy

#include "../../src/generator/generator_with_parameter.hpp"
#include "../../src/generator/utils.hpp"
// Define the path to your binary data file
constexpr char RNA_SEQUENCE_FILENAME[] = "/home/csgrads/xwang605/parallel-bench-suite/datasets/data/RNAcentral/ena.bin";

/**
 * @class GenRNASequence
 * @brief A data generator that lazily loads RNA sequences from a custom binary file
 * into a static cache, providing them as std::string objects.
 * This class follows the same design pattern as GenSDSSCoordinates.
 */
class GenRNASequence : public ParameterizedGeneratorBase<GenRNASequence>, public RealWorldData {
public:
    // Define the parameters for the generator. For now, we only have one dataset.
    struct ParamStruct {
        const char* bin_filename;
        const char* dataset_name;
    };

    static constexpr std::array<ParamStruct, 1> param_list = {{
        {RNA_SEQUENCE_FILENAME, "ena_sequences"}
    }};

    static constexpr size_t num_params() { return param_list.size(); }
    static std::string name() { return "RNAcentral"; }
    static std::string name(int index) { 
        return "rna_" + std::string(param_list.at(index).dataset_name);
    }

    // This generator provides `std::string` objects
    template <class T>
    constexpr static bool accepts() { return std::is_same_v<T, std::string>; }

    // Main generator function: copies the cached strings to the destination buffer
    template <class T>
    void operator()(T* begin, T* end, size_t param_index = 0) {
        static_assert(std::is_same_v<T, std::string>, "GenRNASequence only supports std::string output type.");
        
        // This will trigger the file read on the very first call,
        // and do nothing on subsequent calls.
        ensure_data_loaded();

        const auto& source_vector = get_cache().sequences;
        size_t num_to_copy = std::distance(begin, end);

        if (num_to_copy > source_vector.size()) {
            num_to_copy = source_vector.size();
            std::cerr << "Warning: Requested " << std::distance(begin, end) 
                      << " elements, but only " << num_to_copy << " are available." << std::endl;
        }

        std::copy(source_vector.begin(), source_vector.begin() + num_to_copy, begin);
    }
    
    // Get the total number of sequences available
    size_t getSize(size_t param_index = 0) const {
        ensure_data_loaded();
        return get_cache().sequences.size();
    }

private:
    // --- Static Cache for RNA Sequence data ---
    // A single struct holds the vector of strings and the synchronization flag.
    struct RNACache {
        std::vector<std::string> sequences;
        std::once_flag flag;
    };

    // Static method to get a single, shared instance of the cache.
    static RNACache& get_cache() {
        static RNACache cache;
        return cache;
    }

    // The function that performs the actual file I/O.
    // It will be called exactly once thanks to std::call_once.
    static void load_data_from_file() {
        std::cout << "--- Loading RNA sequence data from disk into cache (this happens only once) ---" << std::endl;
        auto& cache = get_cache();
        const char* filename = param_list[0].bin_filename; 

        std::ifstream infile(filename, std::ios::binary);
        if (!infile.is_open()) {
            throw std::runtime_error("GenRNASequence: Failed to open binary file: " + std::string(filename));
        }
        
        uint64_t num_sequences;
        infile.read(reinterpret_cast<char*>(&num_sequences), sizeof(num_sequences));
        if (!infile) {
            throw std::runtime_error("GenRNASequence: Failed to read sequence count from header.");
        }

        cache.sequences.reserve(num_sequences); // Pre-allocate memory for efficiency

        for (uint64_t i = 0; i < num_sequences; ++i) {
            uint64_t len;
            infile.read(reinterpret_cast<char*>(&len), sizeof(len));
            if (!infile) throw std::runtime_error("GenRNASequence: Failed to read length for sequence " + std::to_string(i));

            std::string seq(len, '\0');
            infile.read(&seq[0], len);
            if (!infile) throw std::runtime_error("GenRNASequence: Failed to read data for sequence " + std::to_string(i));
            
            cache.sequences.push_back(std::move(seq)); // Use move for efficiency
        }
        
        std::cout << "--- Finished loading " << cache.sequences.size() << " sequences into cache ---" << std::endl;
    }

    // This function guarantees that load_data_from_file() is called exactly once.
    static void ensure_data_loaded() {
        auto& cache = get_cache();
        std::call_once(cache.flag, load_data_from_file);
    }
};
