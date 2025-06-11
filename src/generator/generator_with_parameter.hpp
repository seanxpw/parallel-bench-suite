
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
#include <optional> 

#include <fstream>
#include <vector>
#include <utility>
#include <string>
#include <tlx/math/integer_log2.hpp>
#include <SimdMt.hpp>

#include <mutex> // Needed for std::call_once, std::once_flag
#include <memory> // Potentially useful for managing complex static resources

#include "../datatypes.hpp"
#include "../parallel/parallel_for.hpp"
#include "../pbbs_generators/data_types.h"
#include "../pbbs_generators/utils.h"
#include "../sequence.hpp"
#include "simple_alias.hpp"
#include "zipf_distribution.hpp"
#include "utils.hpp"


using namespace std;

template <typename DerivedGenerator>
struct ParameterizedGeneratorBase
{
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
template <typename T>
inline constexpr bool is_parameterized_generator_v = is_parameterized_generator<T>::value;

class RealWorldData
{
public:
    virtual ~RealWorldData() = default;

    // data size
    virtual size_t getSize(size_t param_index) const = 0;
};

class GenZipfPara : public ParameterizedGeneratorBase<GenZipfPara>
{
public:
    // 1. Define the structure for THIS generator's parameters
    struct ParamStruct
    {
        double s;
        size_t N; // Include N as it was hardcoded before
    };

    // 2. Define the list of parameter sets for THIS generator
    static constexpr std::array<ParamStruct, 3> param_list = {
        ParamStruct{0.5, 1000000},  // Parameter set 0 (index 0)
        ParamStruct{0.75, 1500000}, // Parameter set 1 (index 1)
        ParamStruct{0.9, 2000000}   // Parameter set 2 (index 2)
    };

    // 3. Define num_params (required by Base or trait checks)
    static constexpr size_t num_params() { return param_list.size(); }

    // --- Standard methods ---
    GenZipfPara() {} // Default constructor

    static std::string name() { return "zipf_para"; } // New name
    static std::string name(int index)
    {
        if (index < 0 || static_cast<size_t>(index) >= param_list.size())
        {
            throw std::out_of_range("Index out of range for param_list in GenZipfPara::name");
        }
        return "zipf_para_s=" + std::to_string(param_list[index].s) + "_N=" + std::to_string(param_list[index].N);
    }

    template <class T>
    constexpr static bool accepts()
    { // Copied from GenZipf
        return std::is_same_v<T, pair_t> || std::is_same_v<T, uint32_t> || std::is_same_v<T, uint64_t> || std::is_same_v<T, double>;
    }

    // --- Modified operator() ---
    template <class T>
    void operator()(T *begin, T *end, size_t param_index)
    { // Added param_index
        // Check index validity
        if (param_index >= num_params())
        {
            throw std::out_of_range("Invalid parameter index (" + std::to_string(param_index) + ") for GenZipfPara");
        }

        // Get the specific parameters for this run using the index
        const ParamStruct &current_params = param_list[param_index];
        const double current_s = current_params.s;
        const size_t current_N = current_params.N;

        // Static assert for type checking (copied)
        static_assert(std::is_same_v<T, pair_t> || std::is_same_v<T, uint32_t> || std::is_same_v<T, uint64_t> || std::is_same_v<T, double>);

        // *** CRITICAL: Create distribution and alias sampler dynamically ***
        // These are NO LONGER STATIC locals. They are created based on current_N/current_s.
        auto vdistr = thrill::common::ZipfDistribution::make_vec(current_N, current_s);
        wrs::simple_alias<uint32_t> alias(vdistr.begin(), vdistr.end());
        // *******************************************************************

        // Lambda captures the dynamically created 'alias' by reference
        auto make_zipf = [&alias](double random_val_0_to_1)
        { return alias(random_val_0_to_1); };

        // Check target type T and execute parallel fill (copied)
        if constexpr (std::is_same_v<T, pair_t> || std::is_same_v<T, uint32_t> || std::is_same_v<T, uint64_t> || std::is_same_v<T, double>)
        {
            std::random_device rd;
            const uint32_t seed = rd(); // Generate seed once per call
            const size_t num_elements = std::distance(begin, end);

            std_parallel_for(num_elements,
                             [begin, seed, &make_zipf](size_t begin_idx, size_t end_idx, size_t thread_id)
                             {
                                 const auto b = begin + begin_idx;
                                 const auto e = begin + end_idx;
                                 SimdMtGenerator<double>::fill(seed + thread_id, b, e, make_zipf);
                             });
        }
    } // End operator()
}; // End class GenZipfPara

class GenGraph : public ParameterizedGeneratorBase<GenGraph>, public RealWorldData
{
public:
    // 1. Define the structure for THIS generator's parameters
    struct ParamStruct
    {
        const char *filename;
        size_t size; // Default size to 0 meaning unknown
    };

    // 2. Define the list of parameter sets for THIS generator
    static constexpr std::array<ParamStruct, 1> param_list = {
        ParamStruct{"/data/zmen002/kdtree/real_world/hilbert_code.in", 1000000000}, // Parameter set 0 (index 0)
        // ParamStruct{"/data/zmen002/kdtree/real_world/morton_code.in", 1000000000}   // Parameter set 1 (index 1)
    };

    // 3. Define num_params (required by Base or trait checks)
    static constexpr size_t num_params() { return param_list.size(); }

    // --- Standard methods ---
    GenGraph() {} // Default constructor

    static std::string name() { return "gen_graph"; }
    static std::string name(int index)
    {
        if (index < 0 || static_cast<size_t>(index) >= param_list.size())
        {
            throw std::out_of_range("Index out of range for param_list in GenGraph::name");
        }
        return "gen_graph_" + std::string(param_list[index].filename);
    }
    template <class T>
    constexpr static bool accepts() // only pairs for now
    {
        return std::is_same_v<T, pair_t>;
    }
    template <class T>
    void operator()(T *begin, T *end, size_t param_index)
    {
        if (param_index >= num_params())
        {
            throw std::out_of_range("Invalid parameter index (" + std::to_string(param_index) + ") for GenZipfPara");
        }

        // Get the specific parameters for this run using the index
        const ParamStruct &current_params = param_list[param_index];
        const string file_path = current_params.filename;
        static_assert(std::is_same_v<T, pair_t>);

        // Ensure data is loaded into the static cache (thread-safe)
        ensure_data_loaded_static(param_index);

        // Access the static cache
        const auto& source_data = get_cache()[param_index];

        size_t num_elements_to_copy = std::distance(begin, end);
        size_t available_elements = source_data.size();

        size_t copy_count = std::min(num_elements_to_copy, available_elements);
        std::copy(source_data.begin(), source_data.begin() + copy_count, begin);

        if (copy_count < num_elements_to_copy) {
            printf("Warning: Source data for index %zu has only %zu elements, requested %zu. Filling the rest with 0.\n",
                   param_index, available_elements, num_elements_to_copy);
            std::fill(begin + copy_count, end, pair_t(0, 0));
        }

    } // End operator()

    // getSize - uses static cache
    size_t getSize(size_t param_index) const override
    {
        if (param_index >= num_params()) {
            throw std::out_of_range("Invalid parameter index (" + std::to_string(param_index) + ") for GenGraph::getSize");
        }

        const ParamStruct& current_params = param_list[param_index];

        // 1. Return pre-defined size if available
        if (current_params.size != 0) {
            return current_params.size;
        }

        // 2. Ensure data is loaded into the static cache (thread-safe)
        ensure_data_loaded_static(param_index);

        // 3. Return the size from the static cache
        // Note: We access the cache via get_cache() which returns a reference
        return get_cache()[param_index].size();
    }

private:
    // --- Static Cache Implementation ---

    // Static method providing access to the singleton cache vector.
    // Initialization is thread-safe since C++11.
    static std::vector<std::vector<pair_t>> &get_cache()
    {
        // This static variable is initialized exactly once on first call.
        static std::vector<std::vector<pair_t>> cache(num_params());
        return cache;
    }

    // Static method providing access to the initialization flags for the cache.
    static std::vector<std::once_flag> &get_flags()
    {
        // Also initialized exactly once on first call.
        static std::vector<std::once_flag> flags(num_params());
        return flags;
    }

    // The actual function that performs the loading for a given index.
    // This will be called by std::call_once. Marked static as it only uses static data.
    static void load_data_for_index(size_t param_index)
    {
        // Access the actual cache storage via the getter
        auto &cache = get_cache();
        // Check validity again just in case, although call_once should prevent redundant calls
        if (param_index >= num_params())
            return; // Or throw

        const std::string file_path = param_list[param_index].filename;
        // printf("GenGraph (Static Cache): Loading data for index %zu from %s...\n", param_index, file_path.c_str());
        try
        {
            // Load data and store it in the correct slot of the static cache
            // cache[param_index] = load_graph_data(file_path);
            cache[param_index] = load_graph_data_from_chars(file_path, param_list[param_index].size);
            // printf("GenGraph (Static Cache): Loaded %zu elements for index %zu.\n", cache[param_index].size(), param_index);

            // Optional: Verify loaded size against definition
            if (param_list[param_index].size != 0 && param_list[param_index].size != cache[param_index].size())
            {
                fprintf(stderr, "Warning: Pre-defined size %zu for %s does not match actual file size %zu\n",
                        param_list[param_index].size, file_path.c_str(), cache[param_index].size());
            }
        }
        catch (const std::exception &e)
        {
            fprintf(stderr, "Error loading graph data for index %zu into static cache from %s: %s\n", param_index, file_path.c_str(), e.what());
            // Error handling: Re-throwing allows callers to know loading failed.
            // Leaving the cache empty might lead to unexpected behavior later.
            // Consider storing an error state or empty vector if that's acceptable.
            throw;
        }
    }

    // Thread-safe static method to ensure data for a given index is loaded.
    // Uses std::call_once to guarantee loading happens exactly once across all threads/instances.
    static void ensure_data_loaded_static(size_t param_index)
    {
        if (param_index >= num_params())
        {
            // Handle invalid index before accessing flags/cache
            throw std::out_of_range("Invalid parameter index (" + std::to_string(param_index) + ") for ensure_data_loaded_static");
        }
        // Get the specific flag for this index
        auto &flags = get_flags();
        // std::call_once ensures that load_data_for_index(param_index)
        // is called exactly once for the specific flags[param_index],
        // even if multiple threads call ensure_data_loaded_static concurrently.
        std::call_once(flags[param_index], load_data_for_index, param_index);
        // After this line, load_data_for_index(param_index) has completed successfully
        // at least once across the entire program execution.
    }
}; // End class



class GenRNASequenceInt : public ParameterizedGeneratorBase<GenRNASequenceInt>, public RealWorldData {
public:
    struct ParamStruct {
        const char* bin_filename;
        size_t target_column_idx; // The column to extract (0-indexed)
        // We will read num_sequences and chunks_per_sequence from the .bin file header
    };

    static constexpr std::array<ParamStruct, 1> param_list = {
        ParamStruct{"/home/csgrads/xwang605/data/ena.bin", 0} // Extract 0th column
    };

    static constexpr size_t num_params() { return param_list.size(); }

    GenRNASequenceInt() {}

    static std::string name() { return "RNAcentral"; }
    static std::string name(int index) {
        if (index < 0 || static_cast<size_t>(index) >= param_list.size()) {
            throw std::out_of_range("Index out of range for param_list in GenRNASequence::name");
        }
        // Extract a base name from the full path for a cleaner printed name
        std::string full_path = param_list[index].bin_filename;
        size_t last_slash = full_path.rfind('/');
        std::string short_name = (last_slash == std::string::npos) ? full_path : full_path.substr(last_slash + 1);
        return "rna_" + short_name + "_col" + std::to_string(param_list[index].target_column_idx);
    }

    template <class T>
    constexpr static bool accepts() {
        // This generator provides a column of uint64_t values
        return std::is_same_v<T, uint64_t>;
    }

    size_t getSize(size_t param_index) const override {
        if (param_index >= num_params()) {
            throw std::out_of_range("Invalid parameter index (" + std::to_string(param_index) + ") for GenRNASequence::getSize");
        }
        ensure_data_loaded_static(param_index); // Ensures metadata (and data) is loaded
        return get_cache()[param_index].size(); // The size of the cached column vector is num_sequences
    }

    template <class T>
    void operator()(T* begin, T* end, size_t param_index) {
        static_assert(std::is_same_v<T, uint64_t>, "GenRNASequence only supports uint64_t output type.");

        if (param_index >= num_params()) {
            throw std::out_of_range("Invalid parameter index (" + std::to_string(param_index) + ") for GenRNASequence::operator()");
        }

        ensure_data_loaded_static(param_index);

        const auto& column_data = get_cache()[param_index]; // This is std::vector<uint64_t>

        size_t num_elements_to_generate = std::distance(begin, end);
        size_t available_elements = column_data.size();

        size_t copy_count = std::min(num_elements_to_generate, available_elements);
        std::copy(column_data.begin(), column_data.begin() + copy_count, begin);

        if (copy_count < num_elements_to_generate) {
            fprintf(stderr, "Warning: GenRNASequence (param %zu) provided %zu elements, but %zu were requested. Filling rest with 0.\n",
                    param_index, available_elements, num_elements_to_generate);
            std::fill(begin + copy_count, end, static_cast<T>(0)); // Fill remaining with 0
        }
    }

private:
    // --- Static Cache for column data ---
    // Each element of the outer vector corresponds to a param_index.
    // Each inner vector (std::vector<uint64_t>) stores the extracted column data.
    static std::vector<std::vector<uint64_t>>& get_cache() {
        static std::vector<std::vector<uint64_t>> cache(num_params());
        return cache;
    }

    static std::vector<std::once_flag>& get_flags() {
        static std::vector<std::once_flag> flags(num_params());
        return flags;
    }

    static void load_data_for_index(size_t param_index) {
        auto& cache_slot = get_cache()[param_index]; // Get reference to the specific vector<uint64_t>
        const ParamStruct& params = param_list[param_index];

        // printf("GenRNASequence (Static Cache): Loading column %zu for param_index %zu from %s...\n",
        //        params.target_column_idx, param_index, params.bin_filename);

        std::ifstream infile(params.bin_filename, std::ios::binary);
        if (!infile.is_open()) {
            throw std::runtime_error("GenRNASequence: Failed to open binary file: " + std::string(params.bin_filename));
        }

        uint64_t num_sequences_in_file = 0;
        uint64_t chunks_per_sequence_in_file = 0;

        infile.read(reinterpret_cast<char*>(&num_sequences_in_file), sizeof(num_sequences_in_file));
        if (!infile || infile.gcount() != sizeof(num_sequences_in_file)) {
            throw std::runtime_error("GenRNASequence: Failed to read num_sequences from " + std::string(params.bin_filename));
        }

        infile.read(reinterpret_cast<char*>(&chunks_per_sequence_in_file), sizeof(chunks_per_sequence_in_file));
        if (!infile || infile.gcount() != sizeof(chunks_per_sequence_in_file)) {
            throw std::runtime_error("GenRNASequence: Failed to read chunks_per_sequence from " + std::string(params.bin_filename));
        }

        if (params.target_column_idx >= chunks_per_sequence_in_file) {
            throw std::out_of_range("GenRNASequence: target_column_idx (" + std::to_string(params.target_column_idx) +
                                    ") is out of range for file " + std::string(params.bin_filename) +
                                    " which has " + std::to_string(chunks_per_sequence_in_file) + " chunks/columns.");
        }
        
        if (num_sequences_in_file == 0) {
            // printf("GenRNASequence (Static Cache): File %s indicates 0 sequences. Column %zu will be empty.\n",
            //        params.bin_filename, params.target_column_idx);
            cache_slot.clear(); // Ensure it's empty
            return; // Nothing to load
        }

        std::streamoff metadata_size = 2 * sizeof(uint64_t);
        std::streamoff offset_to_column = metadata_size +
                                         (static_cast<std::streamoff>(params.target_column_idx) * num_sequences_in_file * sizeof(uint64_t));

        infile.seekg(offset_to_column, std::ios::beg);
        if (!infile) {
            throw std::runtime_error("GenRNASequence: Failed to seek to column " + std::to_string(params.target_column_idx) +
                                    " in " + std::string(params.bin_filename));
        }

        cache_slot.resize(num_sequences_in_file);
        infile.read(reinterpret_cast<char*>(cache_slot.data()),
                    static_cast<std::streamsize>(num_sequences_in_file) * sizeof(uint64_t));

        if (!infile || static_cast<size_t>(infile.gcount()) != num_sequences_in_file * sizeof(uint64_t)) {
            throw std::runtime_error("GenRNASequence: Failed to read complete data for column " + std::to_string(params.target_column_idx) +
                                    " from " + std::string(params.bin_filename) + ". Read " + std::to_string(infile.gcount()) + " bytes.");
        }
        // printf("GenRNASequence (Static Cache): Loaded %zu uint64_t values for column %zu from %s.\n",
        //        cache_slot.size(), params.target_column_idx, params.bin_filename);
    }

    static void ensure_data_loaded_static(size_t param_index) {
        if (param_index >= num_params()) {
            throw std::out_of_range("Invalid parameter index (" + std::to_string(param_index) + ") for GenRNASequence::ensure_data_loaded_static");
        }
        auto& flags = get_flags();
        std::call_once(flags[param_index], load_data_for_index, param_index);
    }
};