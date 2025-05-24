#!/bin/bash

# ==============================================================================
# Benchmark Script with FIFO-Controlled Perf Record
# for dTLB Miss Events.
# ==============================================================================

# --- Configuration ---
BUILD_DIR="$HOME/parallel-bench-suite/build" # Make sure this path is correct
ALGOS=("benchmark_dovetailsort" "benchmark_ips4oparallel" "benchmark_plss" "benchmark_plis" "benchmark_ips2raparallel" "benchmark_donothing" "benchmark_aspasparallel" "benchmark_mcstlmwm")
DATATYPES=(pair)
GENERATORS=(gen_graph)
MIN_LOG=32
MAX_LOG=32
NUM_RUNS=6
MACHINE="cheetah"

# --- FIFO Pipes for Perf Control ---
PERF_CTL_PIPE="/tmp/my_app_perf_ctl.fifo"
PERF_ACK_PIPE="/tmp/my_app_perf_ack.fifo"

# --- Events for Perf Record ---
DESIRED_RECORD_DTLB_EVENTS=(
    "dTLB-load-misses:u"
    "dTLB-store-misses:u"
)
PERF_RECORD_FREQUENCY=59 # Sampling frequency in Hz

# System Setup & Directory Setup
TOTAL_CORES=$(nproc); if [ -z "$TOTAL_CORES" ]; then TOTAL_CORES=1; fi
SCRIPT_ABSOLUTE_DIR=$(cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd); if [ -z "${SCRIPT_ABSOLUTE_DIR}" ]; then echo "Error: Could not determine script directory."; exit 1; fi
# Modified output directory name
BASE_OUTPUT_DIR_REL="${SCRIPT_ABSOLUTE_DIR}/../run_record_dtlb"; BASE_OUTPUT_DIR=$(mkdir -p "${BASE_OUTPUT_DIR_REL}" && cd "${BASE_OUTPUT_DIR_REL}" &> /dev/null && pwd); if [ $? -ne 0 ] || [ -z "${BASE_OUTPUT_DIR}" ]; then echo "Error: Could not resolve/create base output dir: ${BASE_OUTPUT_DIR_REL}"; exit 1; fi
RUN_TIMESTAMP=$(date '+%Y-%m-%d_%H_%M_%S'); PARENT_DIR="${BASE_OUTPUT_DIR}/dtlb_record_run_${RUN_TIMESTAMP}"

LOG_DIR="${PARENT_DIR}/logs";
TXT_DIR="${PARENT_DIR}/results_stdout";
ERR_DIR="${PARENT_DIR}/results_stderr";
PERF_RECORD_DATA_DIR="${PARENT_DIR}/perf_record_data"  # For perf.data files

mkdir -p "${LOG_DIR}" "${TXT_DIR}" "${ERR_DIR}" "${PERF_RECORD_DATA_DIR}"; if [ $? -ne 0 ]; then echo "Error: Failed to create output subdirs in ${PARENT_DIR}"; exit 1; fi
LOG_FILE="${LOG_DIR}/run_${RUN_TIMESTAMP}.log"

# --- Cleanup and FIFO Creation ---
cleanup_fifos() {
    echo "Cleaning up FIFOs: ${PERF_CTL_PIPE}, ${PERF_ACK_PIPE}" | tee -a "${LOG_FILE}"
    unlink "${PERF_CTL_PIPE}" 2>/dev/null || true
    unlink "${PERF_ACK_PIPE}" 2>/dev/null || true
}
trap cleanup_fifos EXIT SIGINT SIGTERM

echo "Ensuring control FIFOs exist..." | tee -a "${LOG_FILE}"
cleanup_fifos # Clean up any pre-existing FIFOs
mkfifo "${PERF_CTL_PIPE}"; if [ $? -ne 0 ]; then echo "FATAL: Failed to create CTL FIFO: ${PERF_CTL_PIPE}." | tee -a "${LOG_FILE}"; exit 1; fi
mkfifo "${PERF_ACK_PIPE}"; if [ $? -ne 0 ]; then echo "FATAL: Failed to create ACK FIFO: ${PERF_ACK_PIPE}." | tee -a "${LOG_FILE}"; unlink "${PERF_CTL_PIPE}"; exit 1; fi
echo "Control FIFOs created successfully." | tee -a "${LOG_FILE}"

echo "Benchmark Script (Perf Record for dTLB Misses) Started at $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "${LOG_FILE}"
echo "Output will be stored in: ${PARENT_DIR}" | tee -a "${LOG_FILE}"

# --- Perf Event Availability Check for dTLB events for Perf Record ---
echo "======================================================" | tee -a "${LOG_FILE}"
echo "Starting Perf Event Availability Check for dTLB Miss Events at $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "${LOG_FILE}"

AVAILABLE_RECORD_EVENTS_LIST=()
echo "--- Checking events for Perf Record (dTLB misses) ---" | tee -a "${LOG_FILE}"
for event_candidate in "${DESIRED_RECORD_DTLB_EVENTS[@]}"; do
    clean_event_name_for_list=$(echo "${event_candidate}" | awk -F: '{print $1}') # For perf list check
    echo -n "Testing record event candidate: ${event_candidate} ... " | tee -a "${LOG_FILE}"
    if perf list | grep -q -w "${clean_event_name_for_list}"; then
        echo -n "Listed. " | tee -a "${LOG_FILE}"
        timeout 2s bash -c "echo enable > ${PERF_CTL_PIPE} &" # Dummy enable
        # Test with a short record using control interface
        if timeout 5s perf record -e "${event_candidate}" --control fifo:${PERF_CTL_PIPE},${PERF_ACK_PIPE} -o /dev/null -- sleep 0.01 >/dev/null 2>&1; then
            echo "Successfully tested with 'perf record --control'." | tee -a "${LOG_FILE}"
            AVAILABLE_RECORD_EVENTS_LIST+=("${event_candidate}")
        else
            echo "Failed short 'perf record --control' test for ${event_candidate}." | tee -a "${LOG_FILE}"
        fi
        pkill -f "echo enable > ${PERF_CTL_PIPE}" >/dev/null 2>&1 # Clean up dummy enable
    else
        echo "UNAVAILABLE (not in perf list)." | tee -a "${LOG_FILE}"
    fi
done

if [ ${#AVAILABLE_RECORD_EVENTS_LIST[@]} -eq 0 ]; then
    echo "CRITICAL ERROR: None of the desired dTLB miss events ('${DESIRED_RECORD_DTLB_EVENTS[*]}') are usable with 'perf record --control'. Exiting." | tee -a "${LOG_FILE}"
    exit 1
else
    EVENTS_TO_USE_FOR_RECORD_STRING=$(IFS=,; echo "${AVAILABLE_RECORD_EVENTS_LIST[*]}")
    echo "Using event(s) '${EVENTS_TO_USE_FOR_RECORD_STRING}' for perf record." | tee -a "${LOG_FILE}"
fi
echo "--- Perf Event Check Complete ---" | tee -a "${LOG_FILE}"


# --- Main Execution Logic ---
echo "======================================================" | tee -a "${LOG_FILE}"
echo "Starting Main Benchmark Runs (Perf Record for dTLB) at $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "${LOG_FILE}"
# ... (other echos)

for algo in "${ALGOS[@]}"; do
    echo "------------------------------------------------------" | tee -a "${LOG_FILE}"
    echo "Processing Algorithm: ${algo}" | tee -a "${LOG_FILE}"
    ALGO_EXECUTABLE="${BUILD_DIR}/${algo}"
    if [ ! -f "${ALGO_EXECUTABLE}" ] || [ ! -x "${ALGO_EXECUTABLE}" ]; then
        echo "Error: Executable not found or not executable: ${ALGO_EXECUTABLE}" | tee -a "${LOG_FILE}"
        continue
    fi

    for gen in "${GENERATORS[@]}"; do
        for type in "${DATATYPES[@]}"; do
            CONFIG_TAG="${algo}_${gen}_${type}"
            echo "--- Processing Config: ${CONFIG_TAG} (Perf Record for dTLB) ---" | tee -a "${LOG_FILE}"

            # Arguments for the C++ benchmark application
            BENCHMARK_ARGS_FOR_CPP_APP="-b ${MIN_LOG} -e ${MAX_LOG} -r ${NUM_RUNS} -t ${TOTAL_CORES} -g ${gen} -d ${type} -v vector -m ${MACHINE}"
            FULL_CPP_COMMAND_BASE="numactl -i all ${ALGO_EXECUTABLE} ${BENCHMARK_ARGS_FOR_CPP_APP}"

            # --- Perf Record Run ---
            RECORD_PHASE_STDOUT_FILE="${TXT_DIR}/${CONFIG_TAG}_record_dtlb_stdout.txt"
            RECORD_PHASE_STDERR_FILE="${ERR_DIR}/${CONFIG_TAG}_record_dtlb_stderr.err"
            PERF_RECORD_OUTPUT_FILE="${PERF_RECORD_DATA_DIR}/${CONFIG_TAG}_dtlb_misses.data"

            :> "${RECORD_PHASE_STDOUT_FILE}"
            :> "${RECORD_PHASE_STDERR_FILE}"

            export ENABLE_PERF_CONTROL="true"
            BENCHMARK_COMMAND_TO_PROFILE="${FULL_CPP_COMMAND_BASE} > '${RECORD_PHASE_STDOUT_FILE}' 2>> '${RECORD_PHASE_STDERR_FILE}'"

            # Use the comma-separated string of available dTLB events
            PERF_RECORD_COMMAND="perf record -e ${EVENTS_TO_USE_FOR_RECORD_STRING} -F ${PERF_RECORD_FREQUENCY} -g --call-graph dwarf \
                                    -o '${PERF_RECORD_OUTPUT_FILE}' \
                                    --control fifo:${PERF_CTL_PIPE},${PERF_ACK_PIPE} \
                                    -- bash -c \"${BENCHMARK_COMMAND_TO_PROFILE}\""

            echo "Executing Perf Record Command for dTLB misses:" | tee -a "${LOG_FILE}"
            echo "${PERF_RECORD_COMMAND}" | sed 's/^/    /' | tee -a "${LOG_FILE}"
            eval "${PERF_RECORD_COMMAND}"
            record_exit_status=$?

            if [ $record_exit_status -ne 0 ]; then
                echo "Error during perf record for ${CONFIG_TAG} (Exit: ${record_exit_status}). Check logs." | tee -a "${LOG_FILE}"
            else
                echo "Perf record finished for ${CONFIG_TAG}. Data: ${PERF_RECORD_OUTPUT_FILE}" | tee -a "${LOG_FILE}"
            fi
            if [ -s "${RECORD_PHASE_STDERR_FILE}" ]; then
                echo "Note: C++ stderr for record phase ('${RECORD_PHASE_STDERR_FILE}') is non-empty." | tee -a "${LOG_FILE}"
            fi
            if [ -f "${RECORD_PHASE_STDOUT_FILE}" ] && grep -q 'configwarning=1' "${RECORD_PHASE_STDOUT_FILE}"; then
                echo "CONFIG WARNING DETECTED in C++ stdout for record phase of ${CONFIG_TAG}!" | tee -a "${LOG_FILE}"
            fi
            echo "--- Finished Perf Record for ${CONFIG_TAG} ---" | tee -a "${LOG_FILE}"
            echo "---" | tee -a "${LOG_FILE}" # Separator for configs
        done # --- End datatype loop ---
    done # --- End generator loop ---
done # --- End algorithm loop ---

cleanup_fifos # Final cleanup

echo "======================================================" | tee -a "${LOG_FILE}"
echo "All Perf Record (dTLB Misses) Runs Completed at $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "${LOG_FILE}"
echo "Main log file: ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "C++ stdout logs are in: ${TXT_DIR}" | tee -a "${LOG_FILE}"
echo "C++ stderr logs are in: ${ERR_DIR}" | tee -a "${LOG_FILE}"
echo "Perf record data files (*.data) for dTLB misses are stored in: ${PERF_RECORD_DATA_DIR}" | tee -a "${LOG_FILE}"
echo "======================================================" | tee -a "${LOG_FILE}"
echo "To analyze perf data, use commands like 'perf report -i <file.data>'"
echo "Benchmark completed. Check directory ${PARENT_DIR} for outputs."

exit 0