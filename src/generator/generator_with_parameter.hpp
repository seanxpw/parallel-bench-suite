
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



using namespace std;

#include <vector>
#include <string>
#include <fstream>
#include <stdexcept>
#include <utility>
#include <charconv> // for std::from_chars
#include <system_error> // for std::errc
#include <cctype> // for std::isspace


static std::vector<pair_t> load_graph_data_from_chars(const std::string& file_path, size_t estimated_size = 0)
{
    std::vector<pair_t> data;
    if (estimated_size > 0) {
         printf("Reserving vector capacity: %zu\n", estimated_size);
        data.reserve(estimated_size);
    }

    std::ifstream ifs(file_path);
    if (!ifs.is_open()) {
        throw std::runtime_error("Error: Cannot open file " + file_path);
    }

    std::string line;
    uint64_t line_num = 0; // 用于错误报告
    while (std::getline(ifs, line)) {
        ++line_num;
        const char* start = line.data();
        const char* const end = start + line.size();
        const char* current_pos = start;

        uint64_t key = 0, value = 0;
        std::from_chars_result res;

        // Skip leading whitespace
        while(current_pos != end && std::isspace(*current_pos)) ++current_pos;
        if(current_pos == end) continue; // Empty or whitespace-only line

        // Parse key
        res = std::from_chars(current_pos, end, key);
        if (res.ec != std::errc() || res.ptr == current_pos) { // Check error or no chars consumed
             fprintf(stderr, "Warning: Failed to parse key on line %llu: %s\n", line_num, line.c_str());
             continue; // Skip this line
        }
        current_pos = res.ptr;

        // Skip whitespace between key and value
        while(current_pos != end && std::isspace(*current_pos)) ++current_pos;
         if(current_pos == end) { // Key found but no value following
             fprintf(stderr, "Warning: Missing value after key on line %llu: %s\n", line_num, line.c_str());
             continue; // Skip this line
         }

        // Parse value
        res = std::from_chars(current_pos, end, value);
        if (res.ec != std::errc() || res.ptr == current_pos) { // Check error or no chars consumed
             fprintf(stderr, "Warning: Failed to parse value on line %llu: %s\n", line_num, line.c_str());
             continue; // Skip this line
        }
        // current_pos = res.ptr; // Not needed unless checking for trailing chars

        // Successfully parsed pair
        data.emplace_back(key, value);
    }

     if (ifs.bad()) {
        ifs.close();
        throw std::runtime_error("Error: I/O error while reading file " + file_path);
    }
    ifs.close();
    // data.shrink_to_fit(); // Optional
    return data;
}
// 在 load_data_for_index 中调用时:
// cache[param_index] = load_graph_data_from_chars(file_path, param_list[param_index].size);


static std::vector<pair_t> load_graph_data(const std::string& file_path)
{
    // 1. 创建一个空的 vector 用于存储数据
    std::vector<pair_t> data;

    // 2. 打开文件
    std::ifstream ifs(file_path);
    if (!ifs.is_open())
    {
        // 文件打开失败，抛出异常
        throw std::runtime_error("Error: Cannot open file " + file_path);
    }

    // 3. 准备读取变量 (使用您在 read_graph_file 中使用的类型)
    uint64_t key;
    uint64_t value;

    // 4. 循环读取文件中的 key 和 value
    //    持续读取直到文件结束或遇到格式错误
    while (ifs >> key >> value)
    {
        // 将读取到的键值对添加到 vector 中
        // emplace_back 通常比 push_back 效率稍高，因为它直接在 vector 内部构造对象
        data.emplace_back(key, value);
        // 或者使用: data.push_back(pair_t(key, value));
    }

    // 5. 检查流状态 (可选但推荐)
    //    如果在读取过程中发生 I/O 错误 (不是文件结束或格式错误)
    //    ifs.bad() 会返回 true
    if (ifs.bad())
    {
        // 关闭文件（虽然 ifstream 的析构函数会自动关闭，但显式关闭无害）
        ifs.close();
        throw std::runtime_error("Error: I/O error while reading file " + file_path);
    }
    // 如果只是因为到达文件末尾或格式不匹配导致循环结束 (ifs.fail() && !ifs.eof())
    // 这里我们选择不抛出异常，认为已经读取了所有有效行

    // 6. 关闭文件 (ifstream 的析构函数会自动处理，但显式调用也可以)
    ifs.close();

    // 7. 返回包含所有数据的 vector
    return data;
}

size_t read_graph_file(const std::string &filename, pair_t *begin, pair_t *end)
{
    std::ifstream ifs(filename);
    if (!ifs.is_open())
    {
        throw std::runtime_error("Error: Cannot open file " + filename);
    }

    size_t line_count = 0;
    uint64_t key, value;

    for (auto it = begin; it != end && ifs >> key >> value; ++it)
    {
        *it = pair_t(key, value);
        ++line_count;
    }

    ifs.close();
    return line_count;
}

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
    static constexpr std::array<ParamStruct, 2> param_list = {
        ParamStruct{"/data/zmen002/kdtree/real_world/hilbert_code.in", 1000000000}, // Parameter set 0 (index 0)
        ParamStruct{"/data/zmen002/kdtree/real_world/morton_code.in", 1000000000}   // Parameter set 1 (index 1)
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