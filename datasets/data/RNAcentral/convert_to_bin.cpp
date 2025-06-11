#include <iostream>
#include <fstream>
#include <string>
#include <vector>
#include <cstdint>   // For uint64_t
#include <algorithm> // For std::remove_if
#include <cctype>    // For ::isspace

/**
 * @brief Reads a FASTA file, extracts all sequences, and writes them to a custom binary file.
 * The binary format is: [uint64_t num_sequences][uint64_t len1][char* data1][uint64_t len2][char* data2]...
 * @param input_filename The path to the input FASTA file.
 * @param output_filename The path to the output binary file.
 */
void processFastaToBinaryStringArray(const std::string& input_filename, const std::string& output_filename) {
    // --- Pass 1: Read all sequences from FASTA into memory ---
    std::ifstream infile(input_filename);
    if (!infile.is_open()) {
        std::cerr << "Error: Cannot open input file: " << input_filename << std::endl;
        return;
    }

    std::vector<std::string> all_sequences;
    unsigned long entries_processed_count = 0;
    std::string line, current_sequence_data, current_sequence_id;

    std::cout << "Pass 1: Reading FASTA file and collecting sequences..." << std::endl;

    auto handle_completed_sequence = [&]() {
        if (!current_sequence_data.empty()) {
            entries_processed_count++;
            all_sequences.push_back(current_sequence_data);
            if (entries_processed_count > 0 && entries_processed_count % 100000 == 0) {
                std::cout << "Sequences collected: " << entries_processed_count << "..." << std::endl;
            }
        }
    };

    while (std::getline(infile, line)) {
        if (line.empty() || line[0] == ';') continue;

        if (line[0] == '>') {
            handle_completed_sequence();
            current_sequence_id = line.substr(1);
            current_sequence_data.clear();
        } else {
            line.erase(std::remove_if(line.begin(), line.end(), [](unsigned char c){ return std::isspace(c); }), line.end());
            current_sequence_data += line;
        }
    }
    handle_completed_sequence();
    infile.close();

    std::cout << "\nPass 1 complete. Total sequences extracted: " << all_sequences.size() << std::endl;

    if (all_sequences.empty()) {
        std::cout << "No sequences were found. Output file will not be created." << std::endl;
        return;
    }

    // --- Pass 2: Write the collected sequences to a binary file ---
    std::ofstream outfile(output_filename, std::ios::binary);
    if (!outfile.is_open()) {
        std::cerr << "Error: Cannot open output file for writing: " << output_filename << std::endl;
        return;
    }

    std::cout << "\nPass 2: Writing " << all_sequences.size()
              << " sequences to binary file " << output_filename << "..." << std::endl;

    // 1. Write the header: total number of sequences
    uint64_t num_sequences = all_sequences.size();
    outfile.write(reinterpret_cast<const char*>(&num_sequences), sizeof(num_sequences));

    // 2. Write each sequence record (length followed by data)
    for (const auto& seq : all_sequences) {
        // Write the length of the string
        uint64_t len = seq.length();
        outfile.write(reinterpret_cast<const char*>(&len), sizeof(len));
        // Write the actual string data
        outfile.write(seq.c_str(), len);
    }

    outfile.close();
    std::cout << "Binary file successfully written." << std::endl;
}


/**
 * @brief (For demonstration) Reads the custom binary file back into a vector of strings.
 * @param filename The path to the binary file to read.
 * @param read_sequences The vector to store the read sequences in.
 * @return True on success, false on failure.
 */
bool readBinaryStringArray(const std::string& filename, std::vector<std::string>& read_sequences) {
    std::ifstream infile(filename, std::ios::binary);
    if (!infile.is_open()) {
        std::cerr << "Error: Cannot open binary file for reading: " << filename << std::endl;
        return false;
    }
    
    // 1. Read the header
    uint64_t num_sequences;
    infile.read(reinterpret_cast<char*>(&num_sequences), sizeof(num_sequences));
    if (!infile) {
        std::cerr << "Error: Failed to read sequence count from header." << std::endl;
        return false;
    }

    read_sequences.clear();
    read_sequences.reserve(num_sequences); // Pre-allocate memory for efficiency

    // 2. Read each sequence record
    for (uint64_t i = 0; i < num_sequences; ++i) {
        uint64_t len;
        infile.read(reinterpret_cast<char*>(&len), sizeof(len));
        if (!infile) {
            std::cerr << "Error: Failed to read length for sequence " << i << std::endl;
            return false;
        }

        std::string seq(len, '\0'); // Create a string of the correct size
        infile.read(&seq[0], len);
        if (!infile) {
            std::cerr << "Error: Failed to read data for sequence " << i << std::endl;
            return false;
        }
        read_sequences.push_back(seq);
    }
    return true;
}


// --- Main Function ---
int main(int argc, char* argv[]) {
    if (argc < 2) {
        std::cerr << "Usage: " << argv[0] << " <input_fasta_file> [output_binary_file]" << std::endl;
        std::cerr << "Example: " << argv[0] << " ena.fasta" << std::endl;
        std::cerr << "If output_binary_file is not provided, it defaults to <input_fasta_file_basename>.bin" << std::endl;
        return 1;
    }

    std::string input_filename = argv[1];
    std::string output_filename;

    if (argc >= 3) {
        output_filename = argv[2];
    } else {
        std::string base_name = input_filename;
        size_t dot_pos = base_name.rfind('.');
        if (dot_pos != std::string::npos) {
            output_filename = base_name.substr(0, dot_pos) + ".bin";
        } else {
            output_filename = base_name + ".bin";
        }
    }

    if (input_filename == output_filename) {
        std::cerr << "Error: Input and output filenames cannot be the same." << std::endl;
        return 1;
    }

    std::cout << "Input FASTA: " << input_filename << std::endl;
    std::cout << "Output Binary: " << output_filename << std::endl;

    // Call the function to perform the conversion
    processFastaToBinaryStringArray(input_filename, output_filename);

    // --- Optional verification step: Read the file back and print stats ---
    std::cout << "\n--- Verification Step ---" << std::endl;
    std::vector<std::string> verified_sequences;
    if (readBinaryStringArray(output_filename, verified_sequences)) {
        std::cout << "Successfully read back " << verified_sequences.size() << " sequences from binary file." << std::endl;
        if (!verified_sequences.empty()) {
            std::cout << "First sequence length: " << verified_sequences[0].length() << std::endl;
            std::cout << "Last sequence length: " << verified_sequences.back().length() << std::endl;
        }
    } else {
        std::cerr << "Verification failed." << std::endl;
    }

    return 0;
}
