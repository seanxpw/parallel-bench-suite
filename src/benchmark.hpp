
#pragma once

#include <algorithm>
#include <algorithm>
#include <cassert>
#include <chrono>
#include <iostream>
#include <random>
#include <vector>
#include <functional>
#include <optional>

#include <numa_array.hpp>
#include <tclap/CmdLine.h>
#include <tlx/math.hpp>

#include "config.hpp"
#include "datatypes.hpp"
// #include "defs.h"
#include "generator/generator.hpp"
#include "name_extractor.hpp"
#include "parallel/parallel_checker.hpp"
#include "timer.hpp"
#include "typename.hpp"
#include "vector_types.hpp"
// #include "papi_settings.hpp"
#include "perf_control.hpp" // Include the header for perf control

constexpr uint32_t ALIGNMENT = 0x100;

#ifdef DISABLE_PERF_INTERFERENCE_CHECKS
constexpr bool g_enable_benchmark_checker = false;
#else
constexpr bool g_enable_benchmark_checker = true; 
#endif


template <class T>
std::pair<size_t, size_t> logSizes(const Config& config) {
    // THe config is the amount of bytes memory useage.
    const size_t type_log_size = tlx::integer_log2_ceil(sizeof(T));
    const size_t min =
            config.begin_logn >= type_log_size ? config.begin_logn - type_log_size : 1;
    const size_t max =
            config.end_logn >= type_log_size ? config.end_logn - type_log_size : 1;
    return {min, max};
}

template <class T>
constexpr int numRuns(const Config& config, size_t size, bool parallel_algo) {
    if (config.runs > 0) return config.runs;

    if (parallel_algo && ((sizeof(T) * size) < (1ul << 33)))
        return 15;
    else if (!parallel_algo && (sizeof(T) * size) < (1ul << 30))
        return 15;
    else
        return 2;
}


namespace detail { // Encapsulate helper

    /**
     * @brief Invokes the specified sorting algorithm.
     * @tparam T The type of elements to sort.
     * @tparam Vector The type of vector container.
     * @tparam Algo The sorting algorithm provider.
     * @tparam ConfigType The type of the configuration object.
     * @param data_begin Pointer to the beginning of the data to sort.
     * @param data_end Pointer to the end of the data to sort.
     * @param config The benchmark configuration, used to get num_threads.
     * @return A pair or struct containing preprocessing time and sorting time,
     * as returned by Algo::sort.
     */
    template <class T, template <class T1> class Vector, class Algo, typename ConfigType>
    auto execute_sorting_step(
        T* data_begin,
        T* data_end,
        const ConfigType& config)
    // The return type is deduced from Algo::sort
    // For C++11/14, you might need: -> decltype(Algo::template sort<T, Vector>(data_begin, data_end, config.num_threads))
    {
        // Algo::sort modifies the data in place.
        return Algo::template sort<T, Vector>(data_begin, data_end, config.num_threads);
    }

    template <class T, template <class T1> class Vector, class Algo, typename GenOperation, typename GenNameOperation>
    void run_experiment_iteration(
        Vector<T>& v_container, // Pass by reference to handle potential move in copyback
        const size_t current_data_size,
        const Config& config,
        int run_iteration_id,
        GenOperation&& generate_data_fn,     // Lambda for gen(v.get(), v.get() + size, [index])
        GenNameOperation&& get_generator_name_fn // Lambda for Generator::name([index])
    ) {
        T* current_data_ptr = v_container.get();
        T* current_data_end_ptr = v_container.get() + current_data_size;
    
        auto start_gen = std::chrono::high_resolution_clock::now();
        generate_data_fn(current_data_ptr, current_data_end_ptr);
        const auto copyback = !Algo::isParallel() || config.copyback;
    
        if (copyback) {
            // Copy data into a new array by the main thread as the
            // parallel generators may create pages at all numa nodes.
            Vector<T> v1(current_data_size, std::max<size_t>(16, ALIGNMENT));
            // Ensure the source for copy is the data just generated
            std::copy(current_data_ptr, current_data_end_ptr, v1.get());
            v_container = std::move(v1); // v_container in the caller is now the new vector
            // Update pointers to reflect the new buffer in v_container
            current_data_ptr = v_container.get();
            current_data_end_ptr = v_container.get() + current_data_size;
        }
        auto finish_gen = std::chrono::high_resolution_clock::now();
        std::chrono::duration<double, std::milli> elapsed_gen = finish_gen - start_gen;
    
        // --- Benchmark Checker Logic (Compile-time conditional) ---
        double time_checker_ms = 0.0; // Accumulates checker timing, defaults to 0 if disabled.
        std::optional<ParallelChecker<T>> checker_instance_opt; // Optional checker instance.

        if constexpr (g_enable_benchmark_checker) {
            // Only instantiate and use the checker if enabled at compile time.
            checker_instance_opt.emplace(); // Construct ParallelChecker instance.

            auto start_checker_timing = std::chrono::high_resolution_clock::now();
            checker_instance_opt->add_pre(current_data_ptr, current_data_end_ptr); // Check before sorting.
            auto finish_checker_timing = std::chrono::high_resolution_clock::now();
            time_checker_ms += std::chrono::duration<double, std::milli>(
                                   finish_checker_timing - start_checker_timing)
                                   .count();
        }
        // --- End Benchmark Checker Logic (Pre-sort) ---

        if (g_perf_ctl_fd != -1)
        { // 或者检查 perf_initialized 状态
            if (!PerfControl::start_profiling("my_target_function_call"))
            {
                std::cerr << "[PerfControl] Failed to start profiling." << std::endl;
            }
        }
        // Algo::sort modifies the data in place.
        const auto [preprocessing, sorting] = execute_sorting_step<T, Vector, Algo>(
            current_data_ptr, current_data_end_ptr, config);

        if (g_perf_ctl_fd != -1)
        {
            if (!PerfControl::stop_profiling("my_target_function_call"))
            {
                std::cerr << "[PerfControl] Failed to stop profiling." << std::endl;
            }
        }
        // --- Benchmark Checker Logic (Compile-time conditional) ---
        if constexpr (g_enable_benchmark_checker) {
            // Ensure checker_instance_opt is valid if checker is enabled.
            // This assertion is technically redundant due to if constexpr, but can be a sanity check.
            // assert(checker_instance_opt.has_value());

            auto start_checker_timing = std::chrono::high_resolution_clock::now();
            checker_instance_opt->add_post(current_data_ptr, current_data_end_ptr, Datatype<T>::getComparator()); // Check after sorting.
            auto finish_checker_timing = std::chrono::high_resolution_clock::now();
            time_checker_ms += std::chrono::duration<double, std::milli>(finish_checker_timing - start_checker_timing)
                                   .count();
        }
        // --- End Benchmark Checker Logic (Post-sort) ---
    
        std::cout << "RESULT"
                  << "\tmachine=" << config.machine
                  << "\tgen=" << get_generator_name_fn() // Use the lambda to get name
                  << "\tdatatype=" << Datatype<T>::name()
                  << "\talgo=" << Algo::name()
                  << "\tparallel=" << Algo::isParallel()
                  << "\tthreads=" << config.num_threads
                  << "\tvector=" << Vector<T>::name()
                  << "\tcopyback=" << copyback
                  << "\tsize=" << current_data_size
                  << "\trun=" << run_iteration_id
                  << "\tbenchmarkconfigerror=0";

        // Conditionally output checker-related metrics.
        if constexpr (g_enable_benchmark_checker) {
            // assert(checker_instance_opt.has_value()); // Redundant, but for clarity.
            std::cout << "\tcheckermilli=" << time_checker_ms
                      << "\tsortedsequence="
                      << checker_instance_opt->is_likely_sorted(Datatype<T>::getComparator())
                      << "\tpermutation=" << checker_instance_opt->is_likely_permutated();
        } else {
            // Output placeholders or omit if checker is disabled.
            std::cout << "\tcheckermilli=0.0" // Indicates checker was disabled or took no time.
                      << "\tsortedsequence=DISABLED"
                      << "\tpermutation=DISABLED";
        }
        
        std::cout << "\tgeneratormilli=" << elapsed_gen.count()
                  << "\tpreprocmilli=" << preprocessing
                  << "\tmilli=" << sorting
                  << config.info;
    
    #ifdef IPS4O_TIMER
        std::cout << "\tbasecase=" << g_base_case.getTime()
                  << "\tsampling=" << g_sampling.getTime()
                  << "\tclassificationphase=" << g_classification.getTime()
                  << "\tpermutationphase=" << g_permutation.getTime()
                  << "\tcleanup=" << g_cleanup.getTime()
                  << "\toverhead=" << g_overhead.getTime()
                  << "\temptyblock=" << g_empty_block.getTime()
                  << "\ttotal=" << g_total.getTime();
        g_base_case.reset();
        g_sampling.reset();
        g_classification.reset();
        g_permutation.reset();
        g_cleanup.reset();
        g_overhead.reset();
        g_empty_block.reset();
        g_total.reset();
    #endif
    
        std::cout << std::endl;
    }
    
} // namespace detail

template <class T, class Generator, class Algo, template <class T1> class Vector>
void exec(const Config &config)
{
    const auto [min_log_size, max_log_size] = logSizes<T>(config);

    Generator gen_instance; // Create generator instance

    for (size_t size = (1ul << min_log_size); size <= (1ul << max_log_size); size *= 2)
    {
        Vector<T> v(size, std::max<size_t>(16, ALIGNMENT));
        assert(reinterpret_cast<uintptr_t>(v.get()) % ALIGNMENT == 0);

        for (int run = 0; run != numRuns<T>(config, size, Algo::isParallel()); ++run)
        {
            // Lambda to call generator without index
            auto generate_lambda = [&](T *begin, T *end)
            {
                gen_instance(begin, end);
            };
            // Lambda to get generator name without index
            auto name_lambda = [&]()
            {
                return Generator::name();
            };

            detail::run_experiment_iteration<T, Vector, Algo>(
                v, size, config, run,
                generate_lambda, name_lambda);
        }
    }
}

//  this is an overload to receive on more parameter as index for the generator
template <class T, class Generator, class Algo, template <class T1> class Vector>
std::enable_if_t<!std::is_base_of_v<RealWorldData, Generator>, void>
exec(const Config& config, const size_t index) {
    const auto [min_log_size, max_log_size] = logSizes<T>(config);

    Generator gen_instance; // Create generator instance

    for (size_t size = (1ul << min_log_size); size <= (1ul << max_log_size); size *= 2) {
        Vector<T> v(size, std::max<size_t>(16, ALIGNMENT));
        assert(reinterpret_cast<uintptr_t>(v.get()) % ALIGNMENT == 0);

        for (int run = 0; run != numRuns<T>(config, size, Algo::isParallel()); ++run) {
            // Lambda to call generator with index
            auto generate_lambda = [&](T* begin, T* end) {
                gen_instance(begin, end, index);
            };
            // Lambda to get generator name with index
            auto name_lambda = [&]() {
                return Generator::name(index);
            };

            detail::run_experiment_iteration<T, Vector, Algo>(
                v, size, config, run,
                generate_lambda, name_lambda
            );
        }
    }
}


// real world, ignore size
template <class T, class Generator, class Algo, template <class T1> class Vector>
std::enable_if_t<std::is_base_of_v<RealWorldData, Generator>, void>
exec(const Config& config, const size_t index) {
    Generator gen_instance; // Create generator instance
    // Size is determined once using the index for RealWorldData
    size_t size = static_cast<const RealWorldData&>(gen_instance).getSize(index);
    // Original code had printf, matching that. Consider std::cout for consistency if preferred.
    // printf("size is %llu\n", static_cast<unsigned long long>(size));

    Vector<T> v(size, std::max<size_t>(16, ALIGNMENT));
    assert(reinterpret_cast<uintptr_t>(v.get()) % ALIGNMENT == 0);

    for (int run = 0; run != numRuns<T>(config, size, Algo::isParallel()); ++run) {
        // Lambda to call generator with index
        auto generate_lambda = [&](T* begin, T* end) {
            gen_instance(begin, end, index); // Regenerate data for each run
        };
        // Lambda to get generator name with index
        auto name_lambda = [&]() {
            return Generator::name(index);
        };

        detail::run_experiment_iteration<T, Vector, Algo>(
            v, size, config, run,
            generate_lambda, name_lambda
        );
    }
}


template <class T, class Generator, class Algo, typename... Args>
void selectAndExecVector(const Config& config, Args&&... args) {
    if (std::find(config.vectors.begin(), config.vectors.end(),
                  AlignedUniquePtr<T>::name()) != config.vectors.end()) {
        exec<T, Generator, Algo, AlignedUniquePtr>(config, std::forward<Args>(args)...);
    }

    if (std::find(config.vectors.begin(), config.vectors.end(),
                  Numa::AlignedArray<T>::name()) != config.vectors.end()) {
        exec<T, Generator, Algo, Numa::AlignedArray>(config, std::forward<Args>(args)...);
    }
}


template <class T, class Generator, class Algorithms, typename... Args>
void selectAndExecAlgo(const Config& config, Args&&... args) {
    using Algorithm = typename Algorithms::SequenceClass;

    for (const auto& algo : config.algos) {
        if (!Algorithm::name().compare(algo)) {
            if constexpr (Algorithm::template accepts<T>()) {
                selectAndExecVector<T, Generator, Algorithm>(config, std::forward<Args>(args)...);
            } else {
                std::cout << "RESULT"
                          << "\talgo=" << Algorithm::name() << "\tconfigwarning=1"
                          << "\tdatatype=" << Datatype<T>::name() << std::endl;
            }
        }
    }

    if constexpr (!Algorithms::isLast()) {
        selectAndExecAlgo<T, Generator, typename Algorithms::SubSequence>(
            config, std::forward<Args>(args)...);
    }
}


template <class T, class Algorithms, class Generators>
void selectAndExecGenerators(const Config &config)
{
    using Generator = typename Generators::SequenceClass;
    for (const auto generator : config.generators)
    {
        if (!Generator::name().compare(generator))
        {
            if constexpr (Generator::template accepts<T>())
            {
                // ***USE THE TYPE TRAIT HERE ***
                    // Check if Generator inherits from ParameterizedGeneratorBase<Generator>
                if constexpr (is_parameterized_generator_v<Generator>) // is_parameterized_generator_v defined in generator.hpp
                {
                    // --- Generator IS Parameterized ---
                    // Ensure it defines num_params() - Add compile-time check
                    // (This checks if Generator::num_params() exists and returns something convertible to size_t)
                    // static_assert(requires { { Generator::num_params() } -> std::convertible_to<size_t>; }, "Parameterized generator must provide static size_t num_params()");

                    // Loop through all parameter sets using the index
                    for (size_t index = 0; index < Generator::num_params(); ++index)
                    {

                        // Call the selectAndExecAlgo overload that ACCEPTS the index
                        selectAndExecAlgo<T, Generator, Algorithms>(config, index);
                    }
                }
                else // Generator is NOT Parameterized
                {
                    // --- Generator is NOT Parameterized ---
                    // Call the selectAndExecAlgo overload that does NOT take an index
                    selectAndExecAlgo<T, Generator, Algorithms>(config);
                }
            }
            else
            {
                std::cout << "RESULT"
                          << "\tgen=" << Generator::name() << "\tconfigwarning=1"
                          << "\tdatatype=" << Datatype<T>::name() << std::endl;
            }
        }
    }
    if constexpr (!Generators::isLast())
    {
        selectAndExecGenerators<T, Algorithms, typename Generators::SubSequence>(config);
    }
}

    template <class Algorithms, class Datatypes>
    void selectAndExecDatatype(const Config &config)
    {
        using TypeDescription = typename Datatypes::SequenceClass;
        using T = typename TypeDescription::value_type;

        const std::string type_name = TypeDescription::name();
        for (const auto datatype : config.datatypes)
        {
            if (!type_name.compare(datatype))
            {
                selectAndExecGenerators<T, Algorithms, Generators>(config);
            }
        }

        if constexpr (!Datatypes::isLast())
        {
            selectAndExecDatatype<Algorithms, typename Datatypes::SubSequence>(config);
        }
    }

    // entry point
    template <class Algorithms>
    void benchmark(const Config &config)
    {
#ifdef ENABLE_PAPI_PROFILING
    initialize_papi_globally_once(); // Call at the very beginning
#endif
 bool perf_initialized = PerfControl::init(); // 使用默认路径

        if (!perf_initialized) {
            std::cerr << "Failed to initialize PerfControl. Proceeding without perf signaling." << std::endl;
        }
        selectAndExecDatatype<Algorithms, Datatypes>(config);
    
         if (perf_initialized) {
        PerfControl::cleanup();
    }
    }

    inline Config readParameters(int argc, char *argv[],
                                 std::vector<std::string> algo_allowed)
    {
        Config config;

        try {
        TCLAP::CmdLine cmd("Benchmark of different Algorithms", ' ', "0.1");

        std::vector<std::string> generator_allowed = NameExtractor<Generators>();
        std::vector<std::string> datatype_allowed = NameExtractor<Datatypes>();
        std::vector<std::string> vector_allowed = get_vector_types();

        TCLAP::ValuesConstraint<std::string> generator_allowedVals(generator_allowed);

        TCLAP::ValuesConstraint<std::string> algo_allowedVals(algo_allowed);

        TCLAP::ValuesConstraint<std::string> datatype_allowedVals(datatype_allowed);

        TCLAP::ValuesConstraint<std::string> vector_allowedVals(vector_allowed);

        TCLAP::SwitchArg copyback_arg(
                "c", "copyback",
                "Copy generated values into a new array by the master thread. Inputs for "
                "sequential algorithms are always copied back.",
                false);

        TCLAP::MultiArg<std::string> generator_arg(
                "g", "generator",
                "Name of the generator. If no generator is specified, all generators are "
                "executed.",
                false, &generator_allowedVals);
        TCLAP::MultiArg<std::string> algo_arg("a", "algorithm",
                                              "Name of the algorithm. If no algorithm is "
                                              "specified, all algorithms are executed.",
                                              false, &algo_allowedVals);
        TCLAP::MultiArg<std::string> datatype_arg(
                "d", "datatype",
                "Name of the datatype. If no datatype is specified, all datatypes are "
                "executed.",
                false, &datatype_allowedVals);

        TCLAP::MultiArg<std::string> vector_arg("v", "vector",
                                                "Name of the vector. If no vector is "
                                                "specified, all vectors are executed.",
                                                false, &vector_allowedVals);

        TCLAP::ValueArg<long> runs_arg(
                "r", "runs",
                "Number of runs. If the number of runs is not set, each sequential "
                "(parallel) algorithm is executed 15 times for inputs less than 2^30 "
                "(2^33) bytes and 2 times for larger inputs.",
                false, -1, "long");

        TCLAP::ValueArg<std::string> machine_arg("m", "machine", "Name of the machine",
                                                 true, "", "string");

        TCLAP::ValueArg<std::string> info_arg(
                "i", "info",
                "Additional information provided by the user about this run. The "
                "information is appended to the result line",
                false, "", "string");

        TCLAP::ValueArg<long> threads_arg("t", "threads", "Number of threads", true, 0,
                                          "long");

        TCLAP::ValueArg<long> begin_logsize_arg(
                "b", "beginlogsize", "The logarithm of the minimum input size in bytes.",
                true, 0, "long");

        TCLAP::ValueArg<long> end_logsize_arg(
                "e", "endlogsize",
                "The logarithm of the maximum input size in bytes (incl)", true, 0,
                "long");

        cmd.add(copyback_arg);
        cmd.add(machine_arg);
        cmd.add(info_arg);
        cmd.add(algo_arg);
        cmd.add(generator_arg);
        cmd.add(datatype_arg);
        cmd.add(vector_arg);
        cmd.add(runs_arg);
        cmd.add(threads_arg);
        cmd.add(begin_logsize_arg);
        cmd.add(end_logsize_arg);

        cmd.parse(argc, argv);

        config.copyback = copyback_arg.getValue();
        config.algos = algo_arg.getValue();
        config.generators = generator_arg.getValue();
        config.datatypes = datatype_arg.getValue();
        config.vectors = vector_arg.getValue();

        if (config.algos.empty()) { config.algos = algo_allowed; }
        if (config.generators.empty()) { config.generators = generator_allowed; }
        if (config.datatypes.empty()) { config.datatypes = datatype_allowed; }
        if (config.vectors.empty()) { config.vectors = vector_allowed; }

        config.machine = machine_arg.getValue();
        config.info = info_arg.getValue();
        config.num_threads = threads_arg.getValue();
        config.runs = runs_arg.getValue();
        config.begin_logn = begin_logsize_arg.getValue();
        config.end_logn = end_logsize_arg.getValue();

    } catch (TCLAP::ArgException& e)  // catch exceptions
    {
        std::cerr << "Error: " << e.error() << " for arg " << e.argId() << std::endl;
        return Config();
    }

    return config;
}
