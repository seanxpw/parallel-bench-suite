#pragma once


#include <vector>
#include <string>
#include <fstream>
#include <stdexcept>
#include <utility>
#include <charconv> // for std::from_chars
#include <system_error> // for std::errc
#include <cctype> // for std::isspace
#include <iostream>     // For std::cerr, std::cout
#include <vector>       // For std::vector
#include <string>       // For std::string
#include <fstream>      // For std::ifstream
#include <stdexcept>    // For std::runtime_error
#include <charconv>     // For std::from_chars
#include <system_error> // For std::errc
#include <thread>       // For std::thread, std::hardware_concurrency
#include <string_view>  // For std::string_view
#include <algorithm>    // For std::min, std::max, std::for_each (not strictly needed for join with range-based for)
#include <cctype>       // For std::isspace (unsigned char cast needed)
#include <cstdio>       // For snprintf (for formatted error messages)
#include <functional>   // For std::mem_fn (if using std::for_each for join), std::forward

#include "../datatypes.hpp"
#include "../parallel/parallel_for.hpp"
#include "../pbbs_generators/data_types.h"
#include "../pbbs_generators/utils.h"
#include "../sequence.hpp"

using namespace std;

// Main function to load graph data in parallel
static std::vector<pair_t> load_graph_data_from_chars_MT(const std::string& file_path, size_t estimated_num_pairs = 0)
{
    // 1. Read entire file into a string buffer
    std::ifstream ifs(file_path, std::ios::binary | std::ios::ate);
    if (!ifs.is_open()) {
        throw std::runtime_error("Error: Cannot open file " + file_path);
    }
    std::streamsize file_size_bytes = ifs.tellg();
    if (file_size_bytes <= 0) {
        ifs.close();
        return {}; // Empty file or error
    }
    ifs.seekg(0, std::ios::beg);

    std::string file_content;
    file_content.resize(static_cast<size_t>(file_size_bytes));
    if (!ifs.read(file_content.data(), file_size_bytes)) {
        ifs.close();
        throw std::runtime_error("Error: I/O error while reading file into buffer " + file_path);
    }
    ifs.close();

    // 2. Create string_views for each line
    std::vector<std::string_view> line_views;
    if (estimated_num_pairs > 0) { // User hint: e.g., 1M lines for 1M pairs
        line_views.reserve(estimated_num_pairs + estimated_num_pairs / 20 + 100); // Reserve with some buffer
    } else if (file_size_bytes > 0) {
        // Heuristic: average line length (e.g., 25-35 bytes for two uint64_t)
        line_views.reserve(static_cast<size_t>(file_size_bytes / 30 + 100));
    }

    const char* ptr = file_content.data();
    const char* const end_of_buffer = ptr + file_content.size();
    const char* line_start_ptr = ptr;
    while (ptr < end_of_buffer) {
        if (*ptr == '\n') {
            line_views.emplace_back(line_start_ptr, static_cast<size_t>(ptr - line_start_ptr));
            line_start_ptr = ptr + 1;
        }
        ptr++;
    }
    if (line_start_ptr < end_of_buffer) { // Add last line if no trailing newline
        line_views.emplace_back(line_start_ptr, static_cast<size_t>(end_of_buffer - line_start_ptr));
    }

    if (line_views.empty()) {
        return {};
    }

    // 3. Parallel processing using your std_parallel_for
    // Determine the number of threads std_parallel_for will use to correctly size thread_results.
    size_t num_hw_threads = std::thread::hardware_concurrency();
    size_t num_threads_for_results = num_hw_threads == 0 ? 1 : num_hw_threads;
    if (num_threads_for_results > line_views.size()) {
        num_threads_for_results = line_views.size();
    }
    if (line_views.size() > 0 && num_threads_for_results == 0) { // Should not happen if line_views.size() > 0
         num_threads_for_results = 1;
    }


    std::vector<std::vector<pair_t>> thread_results;
    if (num_threads_for_results > 0) { // Only resize if there will be threads/work
         thread_results.resize(num_threads_for_results);
    } else { // No lines means no threads needed by std_parallel_for's logic
        return {}; // Should be caught by line_views.empty() earlier
    }


    // Lambda function for parsing a range of lines
    auto parsing_lambda =
        [&line_views, &thread_results] // Capture necessary variables
        (size_t start_line_idx, size_t end_line_idx, size_t thread_idx) {

        // Pre-reserve for this thread's results vector for efficiency
        if (thread_idx < thread_results.size()) { // Important check
            size_t lines_for_this_thread = end_line_idx - start_line_idx;
            thread_results[thread_idx].reserve(lines_for_this_thread);
        } else {
            // This indicates a mismatch between num_threads_for_results and actual thread_idx from std_parallel_for
            fprintf(stderr, "Critical Error: Thread index %zu out of bounds for thread_results (size %zu).\n",
                    thread_idx, thread_results.size());
            return; // Avoid crashing
        }

        for (size_t i = start_line_idx; i < end_line_idx; ++i) {
            std::string_view line_sv = line_views[i];
            // The original code's line_num was for error reporting relative to file; here i+1 is the line number
            uint64_t current_line_num_in_file = i + 1; 

            if (line_sv.empty()) continue;

            const char* current_pos = line_sv.data();
            const char* const line_sv_end = line_sv.data() + line_sv.length();
            uint64_t key = 0, value = 0;
            std::from_chars_result res;

            // Skip leading whitespace
            while(current_pos != line_sv_end && std::isspace(static_cast<unsigned char>(*current_pos))) ++current_pos;
            if(current_pos == line_sv_end) continue; // Line is empty or all whitespace

            // Parse key
            res = std::from_chars(current_pos, line_sv_end, key);
            if (res.ec != std::errc() || res.ptr == current_pos) {
                char buffer[256]; // For thread-safe error message construction
                snprintf(buffer, sizeof(buffer), "Warning (Thread %zu): Failed to parse key on line %llu. Content: %.*s\n",
                         thread_idx, (unsigned long long)current_line_num_in_file, (int)std::min(line_sv.length(), (size_t)100), line_sv.data());
                std::cerr << buffer;
                continue;
            }
            current_pos = res.ptr;

            // Skip whitespace between key and value
            while(current_pos != line_sv_end && std::isspace(static_cast<unsigned char>(*current_pos))) ++current_pos;
            if(current_pos == line_sv_end) { 
                char buffer[256];
                snprintf(buffer, sizeof(buffer), "Warning (Thread %zu): Missing value after key on line %llu. Content: %.*s\n",
                         thread_idx, (unsigned long long)current_line_num_in_file, (int)std::min(line_sv.length(), (size_t)100), line_sv.data());
                std::cerr << buffer;
                continue;
            }

            // Parse value
            res = std::from_chars(current_pos, line_sv_end, value);
            if (res.ec != std::errc() || res.ptr == current_pos) {
                char buffer[256];
                snprintf(buffer, sizeof(buffer), "Warning (Thread %zu): Failed to parse value on line %llu. Content: %.*s\n",
                         thread_idx, (unsigned long long)current_line_num_in_file, (int)std::min(line_sv.length(), (size_t)100), line_sv.data());
                std::cerr << buffer;
                continue;
            }
            
            // Successfully parsed pair - ensure thread_idx is valid before pushing
            if (thread_idx < thread_results.size()) {
                 thread_results[thread_idx].emplace_back(key, value);
            }
        }
    };

    // Call your std_parallel_for function
    std_parallel_for(line_views.size(), parsing_lambda);

    // 4. Merge results from all threads
    std::vector<pair_t> final_data;
    if (estimated_num_pairs > 0) { // Use user-provided estimate for final reservation
        final_data.reserve(estimated_num_pairs);
    } else { // Fallback: estimate from parsed results
        size_t total_parsed_count = 0;
        for (const auto& vec : thread_results) {
            total_parsed_count += vec.size();
        }
        final_data.reserve(total_parsed_count);
    }

    for (const auto& local_vec : thread_results) {
        final_data.insert(final_data.end(), local_vec.begin(), local_vec.end());
    }

    return final_data;
}


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
