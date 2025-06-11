# Dataset Preparation: RNAcentral Sequences

This document outlines the procedure used to download sequence data from the RNAcentral database and convert it into a custom binary format for efficient processing in performance benchmarks.

## 1. Data Source

The dataset was obtained from the official RNAcentral `https://rnacentral.org/downloads` FTP server. While the server hosts many files, the specific dataset used for this benchmark is from the European Nucleotide Archive (ENA).

- **Main FTP Site:** `https://ftp.ebi.ac.uk/pub/databases/RNAcentral/current_release/sequences/`
- **Specific File Downloaded:** `https://ftp.ebi.ac.uk/pub/databases/RNAcentral/current_release/sequences/by-database/ena.fasta.gz`

The file is a standard FASTA format, compressed with GZIP.

## 2. Preprocessing Steps

The raw `.fasta.gz` file was processed into a custom binary format (`.bin`) to allow for significantly faster data loading during benchmark execution.

### Step 2.1: Download and Decompression

The data was downloaded and decompressed on a Linux server.

```bash
# Download the compressed FASTA file
wget [https://ftp.ebi.ac.uk/pub/databases/RNAcentral/current_release/sequences/by-database/ena.fasta.gz](https://ftp.ebi.ac.uk/pub/databases/RNAcentral/current_release/sequences/by-database/ena.fasta.gz)

# Decompress the file
gunzip ena.fasta.gz
# This results in the file: ena.fasta
```

### Step 2.2: Conversion to Binary Format

A custom C++ program was used to convert the text-based `ena.fasta` file into a structured binary file.

- **Conversion Script:** `/home/csgrads/xwang605/parallel-bench-suite/datasets/data/RNAcentral/convert_to_bin.cpp`
- **Output Binary File:** `/home/csgrads/xwang605/parallel-bench-suite/datasets/data/RNAcentral/ena.bin`

**Compilation and Execution:**

```bash
# Compile the conversion script
g++ /home/csgrads/xwang605/parallel-bench-suite/datasets/data/RNAcentral/convert_to_bin.cpp -o convert_to_bin -std=c++11 -O3

# Run the conversion
./convert_to_bin ena.fasta ena.bin
```

**Processing Statistics:**

The script successfully processed the FASTA file with the following results:

```
Pass 1 complete. Total sequences extracted: 29303931
Pass 2: Writing 29303931 sequences to binary file ...
Binary file successfully written.

--- Verification Step ---
Successfully read back 29303931 sequences from binary file.
First sequence length: 200
Last sequence length: 76
```

## 3. Binary File Format (`ena.bin`)

The generated `.bin` file uses a custom, high-performance format designed for quickly reading an array of strings.

The file consists of a single header followed by a series of data records.

### 3.1. Header

The file begins with a single 8-byte header:

- **`num_sequences` (`uint64_t`):** An unsigned 64-bit integer specifying the total number of RNA sequences stored in the file.

### 3.2. Data Records

Immediately following the header, a series of records appear one after another until the end of the file. Each record represents one RNA sequence and has the following structure:

1.  **`sequence_length` (`uint64_t`):** An unsigned 64-bit integer specifying the length (number of characters) of the upcoming RNA sequence string.
2.  **`sequence_data` (`char[]`):** The raw character data of the RNA sequence. The size of this field is exactly `sequence_length` bytes. There is no null terminator.

### 3.3. Visual Layout

The structure of the binary file can be visualized as follows:

```
[ num_sequences (8 bytes) ]
------------------------------------
[ sequence_1_length (8 bytes) ]
[ sequence_1_data (N_1 bytes) ]
------------------------------------
[ sequence_2_length (8 bytes) ]
[ sequence_2_data (N_2 bytes) ]
------------------------------------
...
------------------------------------
[ sequence_k_length (8 bytes) ]
[ sequence_k_data (N_k bytes) ]
```