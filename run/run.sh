#!/bin/bash

# ==============================================================================
# Benchmark Script
#
# Runs specified benchmark executables with various data types and generators.
# Organizes output (.txt), error (.err), and log files into timestamped folders.
# ==============================================================================

# --- Configuration ---

# Directory where the benchmark executables are located
# Example: "/path/to/your/benchmarks"
BUILD_DIR="/home/csgrads/xwang605/parallel-bench-suite/build"

# List of algorithms (executable names) to benchmark, separated by spaces
# Ensure these executables exist in BUILD_DIR
# Example: ALGOS=("benchmark_algo1" "benchmark_algo2")
ALGOS=("benchmark_dovetailsort" "benchmark_ips4oparallel"  "benchmark_plss" "benchmark_plis" "benchmark_ips2raparallel") # Add your actual algorithm names here

# Data types to test
DATATYPES=("pair")

# Input data generators to test
GENERATORS=( "random")

# Log base 2 of the minimum number of elements (e.g., 31 for 2^31)
MIN_LOG=30
# Log base 2 of the maximum number of elements
MAX_LOG=30
# Number of runs for each configuration
NUM_RUNS=5

# Machine identifier (replace with your actual machine name/identifier)
MACHINE="test_machine"

# --- System Setup ---

# Get total number of logical cores available
TOTAL_CORES=$(nproc)
if [ -z "$TOTAL_CORES" ]; then
  echo "Warning: Could not determine core count via nproc. Defaulting to 1."
  TOTAL_CORES=1
fi

# Attempt to set maximum virtual memory limit to total physical memory.
# Note: This might not always work as intended or might require specific permissions.
# It sets the limit for this script and its child processes (like the benchmark).
TOTAL_MEMORY_KB=$(awk '/MemTotal/{print $2}' /proc/meminfo)
if [ -n "$TOTAL_MEMORY_KB" ]; then
  # ulimit -v expects KB
  echo "Attempting to set virtual memory limit (ulimit -Sv) to ${TOTAL_MEMORY_KB} KB..."
  ulimit -Sv "$TOTAL_MEMORY_KB"
  if [ $? -ne 0 ]; then
      echo "Warning: Failed to set virtual memory limit. Might require higher privileges or system configuration changes."
  fi
else
  echo "Warning: Could not determine total memory from /proc/meminfo. Skipping ulimit setting."
fi


# --- Directory and File Setup ---

# Generate a timestamp for the main run directory
RUN_TIMESTAMP=$(date '+%Y-%m-%d_%H_%M_%S')

# Define the parent directory for this run's output
PARENT_DIR="benchmark_run_${RUN_TIMESTAMP}"

# Define subdirectories for logs, results (stdout), and errors (stderr)
LOG_DIR="${PARENT_DIR}/logs"
TXT_DIR="${PARENT_DIR}/results"
ERR_DIR="${PARENT_DIR}/errors"

# Create the directories. -p ensures no error if they exist and creates parents if needed.
mkdir -p "${LOG_DIR}"
mkdir -p "${TXT_DIR}"
mkdir -p "${ERR_DIR}"

# Define the main log file path for this entire script execution
LOG_FILE="${LOG_DIR}/run_${RUN_TIMESTAMP}.log"

# --- Main Execution Logic ---

# Log the start of the entire benchmark run
echo "======================================================" | tee -a "${LOG_FILE}"
echo "Starting Benchmark Run at ${RUN_TIMESTAMP}" | tee -a "${LOG_FILE}"
echo "Output will be stored in: ${PARENT_DIR}" | tee -a "${LOG_FILE}"
echo "Using ${TOTAL_CORES} cores on machine '${MACHINE}'." | tee -a "${LOG_FILE}"
echo "Algorithms to run: ${ALGOS[*]}" | tee -a "${LOG_FILE}" # Log the list of algorithms
echo "======================================================" | tee -a "${LOG_FILE}"

# Loop through each specified algorithm
for algo in "${ALGOS[@]}"; do
    echo "------------------------------------------------------" | tee -a "${LOG_FILE}"
    echo "Processing Algorithm: ${algo}" | tee -a "${LOG_FILE}"
    echo "------------------------------------------------------" | tee -a "${LOG_FILE}"

    # Define the specific output and error file paths for this algorithm
    # Files will be named like 'benchmark_ips4oparallel_output.txt' inside the results/errors directories
    TXT_FILE="${TXT_DIR}/${algo}_output.txt"
    ERR_FILE="${ERR_DIR}/${algo}_errors.err"
    ALGO_EXECUTABLE="${BUILD_DIR}/${algo}"

    # Check if the executable exists and is executable
    if [ ! -f "${ALGO_EXECUTABLE}" ]; then
        echo "Error: Algorithm executable not found: ${ALGO_EXECUTABLE}. Skipping." | tee -a "${LOG_FILE}"
        continue # Skip to the next algorithm
    fi
    if [ ! -x "${ALGO_EXECUTABLE}" ]; then
        echo "Error: Algorithm executable is not executable: ${ALGO_EXECUTABLE}. Skipping." | tee -a "${LOG_FILE}"
        continue # Skip to the next algorithm
    fi

    # Loop through generators and data types for the current algorithm
    for gen in "${GENERATORS[@]}"; do
        for type in "${DATATYPES[@]}"; do
            echo "Running: algo=${algo}, generator=${gen}, datatype=${type}" | tee -a "${LOG_FILE}"

            # Construct the command string (primarily for logging purposes)
            COMMAND_STR="numactl -i all ${ALGO_EXECUTABLE} -b ${MIN_LOG} -e ${MAX_LOG} -r ${NUM_RUNS} -t ${TOTAL_CORES} -g ${gen} -d ${type} -v vector -m ${MACHINE}"

            # Print the full command to the main log file for debugging
            echo "Command: ${COMMAND_STR}" | tee -a "${LOG_FILE}"

            # Execute the actual benchmark command
            # Standard output (stdout) is appended to the algorithm's TXT file
            # Standard error (stderr) is appended to the algorithm's ERR file
            numactl -i all "${ALGO_EXECUTABLE}" \
                -b "${MIN_LOG}" \
                -e "${MAX_LOG}" \
                -r "${NUM_RUNS}" \
                -t "${TOTAL_CORES}" \
                -g "${gen}" \
                -d "${type}" \
                -v "vector" \
                -m "${MACHINE}" \
                >> "${TXT_FILE}" 2>> "${ERR_FILE}"

            # Check the exit status of the last command ($?)
            if [ $? -eq 0 ]; then
                echo "Finished OK: algo=${algo}, generator=${gen}, datatype=${type}" | tee -a "${LOG_FILE}"
            else
                # Log error and mention the specific error file
                echo "Error occurred: algo=${algo}, generator=${gen}, datatype=${type}. Check ${ERR_FILE}" | tee -a "${LOG_FILE}"
            fi
            # Add a small separator in the log for readability
            echo "---" | tee -a "${LOG_FILE}"
        done # End DATATYPES loop
    done # End GENERATORS loop
done # End ALGOS loop

# Log the completion of the entire benchmark run
echo "======================================================" | tee -a "${LOG_FILE}"
echo "Benchmark Run Completed at $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "${LOG_FILE}"
echo "All logs, results, and errors are stored in: ${PARENT_DIR}" | tee -a "${LOG_FILE}"
echo "Main log file: ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "======================================================" | tee -a "${LOG_FILE}"

echo "Benchmark completed. Check the directory ${PARENT_DIR} for all outputs."