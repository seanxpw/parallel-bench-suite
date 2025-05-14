#!/bin/bash

# ==============================================================================
# Benchmark Script with FIFO-Controlled Perf Stat & a "No Perf Round" for Internal Timing
# ==============================================================================

# --- Configuration ---
BUILD_DIR="$HOME/parallel-bench-suite/build"
ALGOS=("benchmark_dovetailsort" "benchmark_ips4oparallel" "benchmark_plss" "benchmark_plis" "benchmark_ips2raparallel")
DATATYPES=(uint32 uint64 pair)
GENERATORS=(random zipf exponential almostsorted)
MIN_LOG=32
MAX_LOG=32
NUM_RUNS=5 # This NUM_RUNS is for the C++ program's internal loop
MACHINE="cheetah"

PERF_CTL_PIPE="/tmp/my_app_perf_ctl.fifo"
PERF_ACK_PIPE="/tmp/my_app_perf_ack.fifo"

# GROUP Event Definitions
GROUP1_EVENTS=( "cycles:u" "instructions:u" "mem_inst_retired.all_loads:u" "mem_inst_retired.all_stores:u" "mem_load_retired.l3_miss:u" "cycle_activity.stalls_l3_miss:u" )
GROUP2_EVENTS=( "mem_load_retired.fb_hit:u" "mem_load_retired.l1_hit:u" "mem_load_retired.l1_miss:u" "mem_load_retired.l2_hit:u" "mem_load_retired.l2_miss:u" )
GROUP3_EVENTS=( "mem_load_retired.l3_hit:u" "LLC-stores:u" "LLC-store-misses:u" "L1-dcache-stores:u" "branch-misses:u" )
GROUP4_EVENTS=( "dTLB-load-misses:u" "dTLB-store-misses:u" "iTLB-load-misses:u" "L1-icache-load-misses:u" "context-switches:u" "faults:u" )
ALL_GROUPS=("GROUP1" "GROUP2" "GROUP3" "GROUP4")

# System Setup & Directory Setup
# TOTAL_CORES=$(nproc); if [ -z "$TOTAL_CORES" ]; then TOTAL_CORES=1; fi
TOTAL_CORES=1 # Explicitly setting to 1, consistent with taskset -c 0
SCRIPT_ABSOLUTE_DIR=$(cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd); if [ -z "${SCRIPT_ABSOLUTE_DIR}" ]; then echo "Error: Could not determine script directory."; exit 1; fi
BASE_OUTPUT_DIR_REL="${SCRIPT_ABSOLUTE_DIR}/../run"; BASE_OUTPUT_DIR=$(cd "${BASE_OUTPUT_DIR_REL}" &> /dev/null && pwd); if [ $? -ne 0 ] || [ -z "${BASE_OUTPUT_DIR}" ]; then echo "Error: Could not resolve base output directory path from relative path: ${BASE_OUTPUT_DIR_REL}"; exit 1; fi
mkdir -p "${BASE_OUTPUT_DIR}"; RUN_TIMESTAMP=$(date '+%Y-%m-%d_%H_%M_%S'); PARENT_DIR="${BASE_OUTPUT_DIR}/perf_benchmark_run_${RUN_TIMESTAMP}"
LOG_DIR="${PARENT_DIR}/logs"; TXT_DIR="${PARENT_DIR}/results_stdout"; ERR_DIR="${PARENT_DIR}/results_stderr"; STAT_DIR="${PARENT_DIR}/perf_stats"
mkdir -p "${LOG_DIR}" "${TXT_DIR}" "${ERR_DIR}" "${STAT_DIR}"; if [ $? -ne 0 ]; then echo "Error: Failed to create necessary output subdirectories in ${PARENT_DIR}"; exit 1; fi
LOG_FILE="${LOG_DIR}/run_${RUN_TIMESTAMP}.log"

cleanup_fifos() { echo "Cleaning up FIFOs: ${PERF_CTL_PIPE}, ${PERF_ACK_PIPE}" | tee -a "${LOG_FILE}"; unlink "${PERF_CTL_PIPE}" 2>/dev/null || true; unlink "${PERF_ACK_PIPE}" 2>/dev/null || true; }
trap cleanup_fifos EXIT SIGINT SIGTERM

echo "Ensuring control FIFOs exist at fixed paths..." | tee -a "${LOG_FILE}"; echo "Control FIFO: ${PERF_CTL_PIPE}" | tee -a "${LOG_FILE}"; echo "Ack FIFO: ${PERF_ACK_PIPE}" | tee -a "${LOG_FILE}"
unlink "${PERF_CTL_PIPE}" 2>/dev/null || true; mkfifo "${PERF_CTL_PIPE}"; if [ $? -ne 0 ]; then echo "FATAL: Failed to create CTL FIFO: ${PERF_CTL_PIPE}." | tee -a "${LOG_FILE}"; exit 1; fi
unlink "${PERF_ACK_PIPE}" 2>/dev/null || true; mkfifo "${PERF_ACK_PIPE}"; if [ $? -ne 0 ]; then echo "FATAL: Failed to create ACK FIFO: ${PERF_ACK_PIPE}." | tee -a "${LOG_FILE}"; unlink "${PERF_CTL_PIPE}"; exit 1; fi
echo "Control FIFOs created successfully." | tee -a "${LOG_FILE}"

# One-Time Perf Event Availability Check
echo "======================================================" | tee -a "${LOG_FILE}"
echo "Starting One-Time Perf Event Availability Check at $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "${LOG_FILE}"
ALL_DESIRED_EVENTS_LIST=()
TEMP_EVENTS=$(printf "%s\n" "${GROUP1_EVENTS[@]}" "${GROUP2_EVENTS[@]}" "${GROUP3_EVENTS[@]}" "${GROUP4_EVENTS[@]}"| sort -u)
readarray -t ALL_DESIRED_EVENTS_LIST <<< "$TEMP_EVENTS"
MASTER_AVAILABLE_EVENTS_LIST=()
MASTER_UNAVAILABLE_EVENTS_LIST=()
echo "--- Checking all desired unique events ---" | tee -a "${LOG_FILE}"
for event_to_check in "${ALL_DESIRED_EVENTS_LIST[@]}"; do
    clean_event_name=$(echo "${event_to_check}" | awk '{print $1}')
    if [[ -z "$clean_event_name" ]]; then continue; fi
    echo -n "              Testing event: ${clean_event_name} ... " | tee -a "${LOG_FILE}"
    if taskset -c 0 perf stat -e "${clean_event_name}" -- echo "event_check_probe" >/dev/null 2>&1; then # Added taskset here for consistency in checking
        echo "Available." | tee -a "${LOG_FILE}"
        MASTER_AVAILABLE_EVENTS_LIST+=("${clean_event_name}")
    else
        echo "UNAVAILABLE or Invalid." | tee -a "${LOG_FILE}"
        MASTER_UNAVAILABLE_EVENTS_LIST+=("${clean_event_name}")
    fi
done
if [ ${#MASTER_UNAVAILABLE_EVENTS_LIST[@]} -gt 0 ]; then
    echo "------------------------------------------------------" | tee -a "${LOG_FILE}"
    echo "The following desired perf events are UNAVAILABLE globally and will be skipped in all groups:" | tee -a "${LOG_FILE}"
    printf '              %s\n' "${MASTER_UNAVAILABLE_EVENTS_LIST[@]}" | tee -a "${LOG_FILE}"
fi
core_events_ok=1
if ! printf '%s\n' "${MASTER_AVAILABLE_EVENTS_LIST[@]}" | grep -q -x "cycles:u"; then core_events_ok=0; echo "Error: 'cycles:u' is not available." | tee -a "${LOG_FILE}"; fi
if ! printf '%s\n' "${MASTER_AVAILABLE_EVENTS_LIST[@]}" | grep -q -x "instructions:u"; then core_events_ok=0; echo "Error: 'instructions:u' is not available." | tee -a "${LOG_FILE}"; fi
if [ $core_events_ok -eq 0 ]; then
      echo "CRITICAL ERROR: Core perf events (cycles/instructions) not available. Exiting." | tee -a "${LOG_FILE}"
      exit 1
fi
echo "------------------------------------------------------" | tee -a "${LOG_FILE}"
echo "Master list of available events:" | tee -a "${LOG_FILE}"
printf '   %s\n' "${MASTER_AVAILABLE_EVENTS_LIST[@]}" | tee -a "${LOG_FILE}"
echo "--- Global Check Complete ---" | tee -a "${LOG_FILE}"

filter_group_events() {
    local group_list_name=$1; local -n original_group_ref=$1; local -n filtered_group_ref=$2
    filtered_group_ref=();
    for desired_event in "${original_group_ref[@]}"; do
        clean_desired_event=$(echo "${desired_event}" | awk '{print $1}'); if [[ -z "$clean_desired_event" ]]; then continue; fi
        local found_in_master=0; for available_event in "${MASTER_AVAILABLE_EVENTS_LIST[@]}"; do if [[ "${clean_desired_event}" == "${available_event}" ]]; then found_in_master=1; break; fi; done
        if [[ $found_in_master -eq 1 ]]; then
            local already_added_to_filtered_group=0; for added_event_in_filtered in "${filtered_group_ref[@]}"; do if [[ "${clean_desired_event}" == "${added_event_in_filtered}" ]]; then already_added_to_filtered_group=1; break; fi; done
            if [[ $already_added_to_filtered_group -eq 0 ]]; then filtered_group_ref+=("${clean_desired_event}"); fi
        fi
    done
}
FILTERED_GROUP1_EVENTS=(); filter_group_events GROUP1_EVENTS FILTERED_GROUP1_EVENTS
FILTERED_GROUP2_EVENTS=(); filter_group_events GROUP2_EVENTS FILTERED_GROUP2_EVENTS
FILTERED_GROUP3_EVENTS=(); filter_group_events GROUP3_EVENTS FILTERED_GROUP3_EVENTS
FILTERED_GROUP4_EVENTS=(); filter_group_events GROUP4_EVENTS FILTERED_GROUP4_EVENTS

# --- Main Execution Logic ---
echo "======================================================" | tee -a "${LOG_FILE}"
echo "Starting Main Benchmark Runs at $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "${LOG_FILE}"
echo "Using CPU 0 (via taskset -c 0) on machine '${MACHINE}'. Benchmark configured for ${TOTAL_CORES} core(s)." | tee -a "${LOG_FILE}"
echo "Algorithms to run: ${ALGOS[*]}" | tee -a "${LOG_FILE}"
echo "======================================================" | tee -a "${LOG_FILE}"

ALL_ALGOS_TO_PROFILE=("${ALGOS[@]}")

for algo in "${ALL_ALGOS_TO_PROFILE[@]}"; do
    echo "------------------------------------------------------" | tee -a "${LOG_FILE}"
    echo "Processing Algorithm: ${algo}" | tee -a "${LOG_FILE}"
    echo "------------------------------------------------------" | tee -a "${LOG_FILE}"
    ALGO_EXECUTABLE="${BUILD_DIR}/${algo}"
    if [ ! -f "${ALGO_EXECUTABLE}" ] || [ ! -x "${ALGO_EXECUTABLE}" ]; then
        echo "Error: Executable not found or not executable: ${ALGO_EXECUTABLE}" | tee -a "${LOG_FILE}"
        continue
    fi

    for gen in "${GENERATORS[@]}"; do
        for type in "${DATATYPES[@]}"; do
            BENCH_TXT_FILE="${TXT_DIR}/${algo}_${gen}_${type}_stdout.txt"
            BENCH_ERR_FILE="${ERR_DIR}/${algo}_${gen}_${type}_stderr.err"
            :> "${BENCH_ERR_FILE}" # Clear/Create stderr file for the whole (algo,gen,type) combo initially

            # MODIFIED: Added taskset -c 0
            BENCHMARK_ARGS_BASE="taskset -c 0 numactl -i all ${ALGO_EXECUTABLE} \
                                  -b ${MIN_LOG} -e ${MAX_LOG} -r ${NUM_RUNS} -t ${TOTAL_CORES} \
                                  -g ${gen} -d ${type} -v vector -m ${MACHINE}"

            # --- 1. NO PERF ROUND (for internal C++ timing) ---
            echo "              Performing NO PERF ROUND for: algo=${algo}, gen=${gen}, type=${type} (for internal timing)" | tee -a "${LOG_FILE}"
            export ENABLE_PERF_CONTROL="false" # Signal C++ to NOT use PerfControl FIFOs

            # This run overwrites main stdout file and appends to (initially empty) stderr file
            NO_PERF_EXEC_COMMAND="${BENCHMARK_ARGS_BASE} > '${BENCH_TXT_FILE}' 2>> '${BENCH_ERR_FILE}'"

            echo "                     Executing No Perf Round Command (on CPU 0)..." | tee -a "${LOG_FILE}"
            eval "${NO_PERF_EXEC_COMMAND}"
            no_perf_exit_status=$?

            if [ $no_perf_exit_status -ne 0 ]; then
                echo "                     Error during NO PERF ROUND for ${algo}_${gen}_${type} (Exit: ${no_perf_exit_status}). Stderr in '${BENCH_ERR_FILE}'." | tee -a "${LOG_FILE}"
            else
                echo "                     No Perf Round finished for ${algo}_${gen}_${type}." | tee -a "${LOG_FILE}"
            fi
            if [ -s "${BENCH_ERR_FILE}" ]; then
                echo "                     Note: No Perf Round stderr file '${BENCH_ERR_FILE}' is non-empty." | tee -a "${LOG_FILE}"
            fi

            # --- 2. PERF STAT RUNS FOR EACH GROUP ---
            export ENABLE_PERF_CONTROL="true" # Signal C++ to USE PerfControl FIFOs

            BENCHMARK_COMMAND_FOR_PERF_SHELL="${BENCHMARK_ARGS_BASE} >> '${BENCH_TXT_FILE}' 2>> '${BENCH_ERR_FILE}'"

            for group_name in "${ALL_GROUPS[@]}"; do
                echo "              Running Group: ${group_name} for: algo=${algo}, gen=${gen}, type=${type}" | tee -a "${LOG_FILE}"
                current_filtered_list_name="FILTERED_${group_name}_EVENTS[@]"
                CURRENT_GROUP_EVENTS_TO_RUN=( "${!current_filtered_list_name}" )

                if [ ${#CURRENT_GROUP_EVENTS_TO_RUN[@]} -eq 0 ]; then
                    echo "                     Warning: No available events configured for ${group_name}. Skipping group." | tee -a "${LOG_FILE}"
                    continue
                fi

                AVAILABLE_GROUP_EVENTS_STR=$(IFS=,; echo "${CURRENT_GROUP_EVENTS_TO_RUN[*]}")
                echo "                     Using pre-filtered events for ${group_name}: ${AVAILABLE_GROUP_EVENTS_STR}" | tee -a "${LOG_FILE}"
                PERF_STAT_OUTPUT_FILE="${STAT_DIR}/${algo}_${gen}_${type}_${group_name}_perf_stat.txt"

                # MODIFIED: Added taskset -c 0 before perf stat
                PERF_COMMAND="taskset -c 0 perf stat -e ${AVAILABLE_GROUP_EVENTS_STR} \
                                  -o '${PERF_STAT_OUTPUT_FILE}' \
                                  --control fifo:${PERF_CTL_PIPE},${PERF_ACK_PIPE} \
                                  -- bash -c \"${BENCHMARK_COMMAND_FOR_PERF_SHELL}\""

                echo "                     Executing Perf Command for ${group_name} (perf and app on CPU 0)..." | tee -a "${LOG_FILE}"
                eval "${PERF_COMMAND}"
                exit_status=$?

                if [ $exit_status -ne 0 ]; then
                    echo "                     Error occurred during perf stat run for ${group_name} (Exit Status: ${exit_status}). Check '${PERF_STAT_OUTPUT_FILE}' and '${BENCH_ERR_FILE}'." | tee -a "${LOG_FILE}"
                else
                    echo "                     Perf stat finished for ${group_name}." | tee -a "${LOG_FILE}"
                fi

                if [ -s "${BENCH_ERR_FILE}" ]; then
                    echo "                     Note: Benchmark stderr file '${BENCH_ERR_FILE}' may contain new messages from this group's run." | tee -a "${LOG_FILE}"
                fi
                echo "                     --- Group ${group_name} Finished ---" | tee -a "${LOG_FILE}"
            done # --- End event group loop ---

            echo "              Finished all groups for: algo=${algo}, gen=${gen}, type=${type}" | tee -a "${LOG_FILE}"

            if [ -f "${BENCH_TXT_FILE}" ]; then
                if grep -q 'configwarning=1' "${BENCH_TXT_FILE}"; then
                    echo "              CONFIG WARNING DETECTED in ${BENCH_TXT_FILE}!" | tee -a "${LOG_FILE}"
                    echo "              Deleting potentially misleading perf stat files for this configuration." | tee -a "${LOG_FILE}"
                    perf_file_pattern="${STAT_DIR}/${algo}_${gen}_${type}_GROUP"
                    files_to_delete=$(ls ${perf_file_pattern}*_perf_stat.txt 2>/dev/null)
                    if [ -n "$files_to_delete" ]; then
                        echo "              Deleting files:" | tee -a "${LOG_FILE}"
                        for file_to_del in $files_to_delete; do
                            echo "                     - $file_to_del" | tee -a "${LOG_FILE}"; rm -f "$file_to_del"; done
                    else echo "              No perf stat files found matching pattern to delete." | tee -a "${LOG_FILE}"; fi
                fi
            else echo "              Warning: Benchmark stdout file not found: ${BENCH_TXT_FILE}. Cannot check for configwarning." | tee -a "${LOG_FILE}"; fi
            echo "---" | tee -a "${LOG_FILE}"
        done # --- End datatype loop ---
    done # --- End generator loop ---
done # --- End algorithm loop ---

echo "======================================================" | tee -a "${LOG_FILE}"
echo "Skipping bash-based quick analysis. Please use the Python script to merge and analyze grouped data." | tee -a "${LOG_FILE}"
echo "======================================================" | tee -a "${LOG_FILE}"
echo "Benchmark Run Completed at $(date '+%Y-%m-%d_%H_%M_%S')" | tee -a "${LOG_FILE}"
echo "All logs, results, and perf_stats are stored in: ${PARENT_DIR}" | tee -a "${LOG_FILE}"
echo "Main log file: ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "======================================================" | tee -a "${LOG_FILE}"
echo "Perf stat benchmark completed. Check the directory ${PARENT_DIR} for all outputs."
echo "Perf stat raw data files (grouped) for Python processing are in: ${STAT_DIR}"

# Trap will call cleanup_fifos on exit