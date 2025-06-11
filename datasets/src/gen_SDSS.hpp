#pragma once

#include <vector>
#include <iostream>
#include <fstream>   
#include <sstream>   
#include <vector>    
#include <string>    
#include <stdexcept> 

#include "../../src/generator/generator_with_parameter.hpp"
#include "../../src/generator/utils.hpp"

constexpr char SDSS_COORDINATES_FILENAME[] = "/home/csgrads/xwang605/parallel-bench-suite/datasets/data/SDSS/Star15,585,000.csv";

bool loadSdssCoordinates(const std::string& filename, 
                         std::vector<double>& ra_coords, 
                         std::vector<double>& dec_coords, 
                         bool has_header = true) {
    
    // 1. Open the file
    std::ifstream file(filename);
    if (!file.is_open()) {
        std::cerr << "Error: Could not open file '" << filename << "'" << std::endl;
        return false;
    }

    std::string line;

    // 2. If the file has a header line, read and discard the first line
    if (has_header) {
        if (!std::getline(file, line)) {
            std::cerr << "Warning: File is empty or failed to read header." << std::endl;
            return true; // Considered successful even if the file is empty
        }
    }

    long long objID;
    double ra, dec;
    char comma; // Used to consume commas during parsing

    // 3. Read and parse the file line by line
    while (std::getline(file, line)) {
        std::stringstream ss(line);

        // Expected format: objID,ra,dec
        // We read objID and two commas, but only store ra and dec
        if (ss >> objID >> comma >> ra >> comma >> dec) {
            ra_coords.push_back(ra);
            dec_coords.push_back(dec);
        } else {
            // If a line is incorrectly formatted, we can choose to skip or log a warning
            // std::cerr << "Warning: Could not parse line: " << line << std::endl;
        }
    }

    file.close();
    return true;
}

class GenSDSSCoordinates : public ParameterizedGeneratorBase<GenSDSSCoordinates>, public RealWorldData {
public:
    // Define the parameters for our generator.
    // We can generate two different "datasets" from the same file.
    struct ParamStruct {
        const char* filename;
        int target_column_idx; // 0 for RA, 1 for DEC
        const char* column_name;
    };

    static constexpr std::array<ParamStruct, 1> param_list = {{
        {SDSS_COORDINATES_FILENAME, 0, "ra"},
        // {"MySortTable.csv", 1, "dec"}
    }};

    static constexpr size_t num_params() { return param_list.size(); }
    static std::string name() { return "SDSS"; }
    static std::string name(int index) { 
        return "sdss_" + std::string(param_list.at(index).column_name);
    }

    // This generator provides `double` values
    template <class T>
    constexpr static bool accepts() { return std::is_same_v<T, double>; }

    // Main generator function, copies data to the destination buffer
    template <class T>
    void operator()(T* begin, T* end, size_t param_index) {
        static_assert(std::is_same_v<T, double>, "GenSDSSCoordinates only supports double output type.");
        
        // Ensure data is loaded from disk (will only run once)
        ensure_data_loaded();

        const auto& source_vector = get_column_data(param_index);
        size_t num_to_copy = std::distance(begin, end);

        if (num_to_copy > source_vector.size()) {
            num_to_copy = source_vector.size();
            std::cerr << "Warning: Requested " << std::distance(begin, end) 
                      << " elements, but only " << num_to_copy << " are available." << std::endl;
        }

        std::copy(source_vector.begin(), source_vector.begin() + num_to_copy, begin);
    }
    
    // Get the total number of elements for a given parameter set
    size_t getSize(size_t param_index) const {
        ensure_data_loaded();
        return get_column_data(param_index).size();
    }

private:
    // --- Static Cache for SDSS data ---
    // We use a single struct to hold all data read from the file.
    struct SDSSCache {
        std::vector<double> ra_coords;
        std::vector<double> dec_coords;
        std::once_flag flag; // A flag to ensure loading happens only once
    };

    // Meyers' Singleton pattern to get a reference to our static cache
    static SDSSCache& get_cache() {
        static SDSSCache cache;
        return cache;
    }

    // This is the function that will be called exactly once by std::call_once
    static void load_data_from_file() {
        std::cout << "--- Loading SDSS data from disk into cache (this happens only once) ---" << std::endl;
        auto& cache = get_cache();
        // The filename is the same for all parameter sets in this class
        const char* filename = param_list[0].filename; 

        if (!loadSdssCoordinates(filename, cache.ra_coords, cache.dec_coords)) {
            throw std::runtime_error("GenSDSSCoordinates: Failed to load data from " + std::string(filename));
        }
        std::cout << "--- Finished loading " << cache.ra_coords.size() << " records into cache ---" << std::endl;
    }

    // This function ensures that the data loading logic is called exactly once
    static void ensure_data_loaded() {
        auto& cache = get_cache();
        std::call_once(cache.flag, load_data_from_file);
    }
    
    // Helper function to get the correct data vector based on the parameter index
    const std::vector<double>& get_column_data(size_t param_index) const {
        const auto& params = param_list.at(param_index);
        if (params.target_column_idx == 0) {
            return get_cache().ra_coords;
        } else {
            return get_cache().dec_coords;
        }
    }
};
