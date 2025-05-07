#!/bin/bash

# ==============================================================================
# Benchmark Script with One-Time Perf Event Availability Check & Grouped Runs
#
# Checks availability of specified perf events ONCE at the start, then runs
# benchmarks with 'perf stat' using only the available events for each group.
# ==============================================================================

# --- Configuration ---
BUILD_DIR="$HOME/parallel-bench-suite/build"
BASELINE_ALGO="benchmark_donothing"
ALGOS=("benchmark_dovetailsort" "benchmark_ips4oparallel" "benchmark_plss" "benchmark_plis" "benchmark_ips2raparallel")
# DATATYPES=("pair")
# GENERATORS=("random")
DATATYPES=(uint32 uint64 pair)
GENERATORS=(random zipf exponential almostsorted)
MIN_LOG=32
MAX_LOG=32
NUM_RUNS=5
MACHINE="cheetah"


# GROUP 1: 核心性能 & 主要内存瓶颈 (保持不变，6 个事件)
GROUP1_EVENTS=(
    "cycles:u"
    "instructions:u"
    "mem_inst_retired.all_loads:u"
    "mem_inst_retired.all_stores:u"
    "mem_load_retired.l3_miss:u"
    "cycle_activity.stalls_l3_miss:u"
)

# NEW GROUP 2: L1/L2 加载缓存细节 (7 个事件)
# 目标: 精确测量 L1/L2 缓存对加载操作的影响
GROUP2_EVENTS=(
    # "cycles:u"                          # 核心周期
    # "instructions:u"                    # 指令数
    "mem_load_retired.fb_hit:u"         # L1 FB 命中
    "mem_load_retired.l1_hit:u"         # L1D 加载命中
    "mem_load_retired.l1_miss:u"        # L1D 加载未命中
    "mem_load_retired.l2_hit:u"         # L2 加载命中
    "mem_load_retired.l2_miss:u"        # L2 加载未命中
)

# NEW GROUP 3: L3 加载细节 & LLC/L1D 存储 (6 个事件)
# 目标: 测量 L3 加载命中，以及末级缓存(LLC)和L1D的存储行为
GROUP3_EVENTS=(
    # "cycles:u"                          # 核心周期
    # "instructions:u"                    # 指令数
    "mem_load_retired.l3_hit:u"         # L3 加载命中 (与 Group 1 的 L3 miss 互补)
    "LLC-stores:u"                      # LLC 存储次数
    "LLC-store-misses:u"                # LLC 存储未命中
    "L1-dcache-stores:u"                # L1D 存储次数 (若可用)
)

# NEW GROUP 4: TLB & ICache (6 个事件)
# 目标: 测量地址翻译(TLB)和指令缓存(ICache)的性能
# 注意: 如果需要计算 dTLB 命中率，可以考虑加入 dTLB-loads:u 和 dTLB-stores:u，但这会增加事件数量
GROUP4_EVENTS=(
    # "cycles:u"                          # 核心周期
    # "instructions:u"                    # 指令数
    "dTLB-load-misses:u"                # dTLB 加载未命中
    "dTLB-store-misses:u"               # dTLB 存储未命中
    "iTLB-load-misses:u"                # iTLB 加载未命中
    "L1-icache-load-misses:u"           # L1 ICache 未命中
    # 可选: "dTLB-loads:u", "dTLB-stores:u"
)


# 定义所有要运行的组名 (现在有4个组)
ALL_GROUPS=("GROUP1" "GROUP2" "GROUP3" "GROUP4")


# --- System Setup & Directory Setup ---
TOTAL_CORES=$(nproc)
if [ -z "$TOTAL_CORES" ]; then TOTAL_CORES=1; fi
# ulimit setup can be added here if needed

# --- 确定脚本文件所在的绝对目录 ---
# 使用 BASH_SOURCE[0] 获取脚本路径，然后用 dirname 获取目录，最后用 cd 和 pwd 获取绝对路径
# 这是一种比较健壮的方式，可以处理符号链接和从不同位置调用脚本的情况
SCRIPT_ABSOLUTE_DIR=$(cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd)
if [ -z "${SCRIPT_ABSOLUTE_DIR}" ]; then
    echo "Error: Could not determine script directory."
    exit 1
fi

# --- 定义相对于脚本目录的基础输出目录 ---
# 使用 ../run 来指向 run_scripts 的父目录下的 run 目录
BASE_OUTPUT_DIR_REL="${SCRIPT_ABSOLUTE_DIR}/../run"

# --- 解析为规范的绝对路径 ---
# 使用 cd 和 pwd 来处理 ".." 并得到最终的绝对路径
BASE_OUTPUT_DIR=$(cd "${BASE_OUTPUT_DIR_REL}" &> /dev/null && pwd)
if [ $? -ne 0 ] || [ -z "${BASE_OUTPUT_DIR}" ]; then
    echo "Error: Could not resolve base output directory path from relative path: ${BASE_OUTPUT_DIR_REL}" | tee -a "${LOG_FILE:-/dev/stderr}"
    exit 1
fi
# 现在 BASE_OUTPUT_DIR 应该指向 /home/xwang605/parallel-bench-suite/run

# 确保基础输出目录存在
mkdir -p "${BASE_OUTPUT_DIR}"
if [ ! -d "${BASE_OUTPUT_DIR}" ]; then
    echo "Error: Failed to create base output directory: ${BASE_OUTPUT_DIR}" | tee -a "${LOG_FILE:-/dev/stderr}"
    exit 1
fi

# 生成时间戳和本次运行的具体目录名 (在 BASE_OUTPUT_DIR 内部)
RUN_TIMESTAMP=$(date '+%Y-%m-%d_%H_%M_%S')
PARENT_DIR="${BASE_OUTPUT_DIR}/perf_benchmark_run_${RUN_TIMESTAMP}"

# --- 子目录路径现在会自动基于新的 PARENT_DIR ---
LOG_DIR="${PARENT_DIR}/logs"
TXT_DIR="${PARENT_DIR}/results_stdout"
ERR_DIR="${PARENT_DIR}/results_stderr"
STAT_DIR="${PARENT_DIR}/perf_stats"

# --- 创建本次运行所需的所有目录 ---
mkdir -p "${LOG_DIR}" "${TXT_DIR}" "${ERR_DIR}" "${STAT_DIR}"
if [ $? -ne 0 ]; then
    echo "Error: Failed to create necessary output subdirectories in ${PARENT_DIR}" | tee -a "${LOG_FILE:-/dev/stderr}"
    exit 1
fi

# 定义主日志文件路径
LOG_FILE="${LOG_DIR}/run_${RUN_TIMESTAMP}.log"


# --- One-Time Perf Event Availability Check ---
echo "======================================================" | tee -a "${LOG_FILE}"
echo "Starting One-Time Perf Event Availability Check at $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "${LOG_FILE}"

# 1. Combine all desired events into a unique list
ALL_DESIRED_EVENTS_LIST=()
TEMP_EVENTS=$(printf "%s\n" "${GROUP1_EVENTS[@]}" "${GROUP2_EVENTS[@]}" "${GROUP3_EVENTS[@]}" "${GROUP4_EVENTS[@]}"| sort -u) # Add other groups here if defined
readarray -t ALL_DESIRED_EVENTS_LIST <<< "$TEMP_EVENTS"

# 2. Perform global availability check
MASTER_AVAILABLE_EVENTS_LIST=()
MASTER_UNAVAILABLE_EVENTS_LIST=()
echo "--- Checking all desired unique events ---" | tee -a "${LOG_FILE}"
for event_to_check in "${ALL_DESIRED_EVENTS_LIST[@]}"; do
    # Use awk to get just the event name before any potential space/comment within the string
    clean_event_name=$(echo "${event_to_check}" | awk '{print $1}')
    if [[ -z "$clean_event_name" ]]; then continue; fi # Skip empty lines

    echo -n "  Testing event: ${clean_event_name} ... " | tee -a "${LOG_FILE}"
    if perf stat -e "${clean_event_name}" -- echo "event_check_probe" >/dev/null 2>&1; then
        echo "Available." | tee -a "${LOG_FILE}"
        MASTER_AVAILABLE_EVENTS_LIST+=("${clean_event_name}")
    else
        echo "UNAVAILABLE or Invalid." | tee -a "${LOG_FILE}"
        MASTER_UNAVAILABLE_EVENTS_LIST+=("${clean_event_name}")
    fi
done

# Log unavailable events
if [ ${#MASTER_UNAVAILABLE_EVENTS_LIST[@]} -gt 0 ]; then
    echo "------------------------------------------------------" | tee -a "${LOG_FILE}"
    echo "The following desired perf events are UNAVAILABLE globally and will be skipped in all groups:" | tee -a "${LOG_FILE}"
    printf '    %s\n' "${MASTER_UNAVAILABLE_EVENTS_LIST[@]}" | tee -a "${LOG_FILE}"
fi

# Check if at least some core events are available
core_events_ok=1
if ! printf '%s\n' "${MASTER_AVAILABLE_EVENTS_LIST[@]}" | grep -q -x "cycles:u"; then core_events_ok=0; echo "Error: 'cycles:u' is not available." | tee -a "${LOG_FILE}"; fi
if ! printf '%s\n' "${MASTER_AVAILABLE_EVENTS_LIST[@]}" | grep -q -x "instructions:u"; then core_events_ok=0; echo "Error: 'instructions:u' is not available." | tee -a "${LOG_FILE}"; fi

if [ $core_events_ok -eq 0 ]; then
     echo "CRITICAL ERROR: Core perf events (cycles/instructions) not available. Exiting." | tee -a "${LOG_FILE}"
     exit 1
fi
echo "------------------------------------------------------" | tee -a "${LOG_FILE}"
echo "Master list of available events:" | tee -a "${LOG_FILE}"
printf '  %s\n' "${MASTER_AVAILABLE_EVENTS_LIST[@]}" | tee -a "${LOG_FILE}"
echo "--- Global Check Complete ---" | tee -a "${LOG_FILE}"


# 3. Filter each group's event list based on the master available list
# Using a helper function for clarity
filter_group_events() {
    local group_list_name=$1       # Name of the original group array (e.g., GROUP1_EVENTS)
    local -n original_group_ref=$1 # Nameref to the original group array
    local -n filtered_group_ref=$2 # Nameref to the array to store filtered events (e.g., FILTERED_GROUP1_EVENTS)
    
    filtered_group_ref=() # Clear the target array
    local event_seen=()   # Keep track of events added to avoid duplicates within a group if original had them
    
    for desired_event in "${original_group_ref[@]}"; do
        clean_desired_event=$(echo "${desired_event}" | awk '{print $1}')
        if [[ -z "$clean_desired_event" ]]; then continue; fi

        # Check if this desired event is in the master available list
        local found_in_master=0
        for available_event in "${MASTER_AVAILABLE_EVENTS_LIST[@]}"; do
            if [[ "${clean_desired_event}" == "${available_event}" ]]; then
                found_in_master=1
                break
            fi
        done

        # Add to filtered list only if available and not already added
        if [[ $found_in_master -eq 1 ]]; then
            local already_added=0
            for added_event in "${filtered_group_ref[@]}"; do
                if [[ "${clean_desired_event}" == "${added_event}" ]]; then
                    already_added=1
                    break
                fi
            done
            if [[ $already_added -eq 0 ]]; then
                 filtered_group_ref+=("${clean_desired_event}")
            fi
        fi
    done
}

# Create and populate filtered lists
FILTERED_GROUP1_EVENTS=()
FILTERED_GROUP2_EVENTS=()
FILTERED_GROUP3_EVENTS=()
FILTERED_GROUP4_EVENTS=()
# Add more filtered group arrays if needed (e.g., FILTERED_GROUP3_EVENTS=())

filter_group_events GROUP1_EVENTS FILTERED_GROUP1_EVENTS
filter_group_events GROUP2_EVENTS FILTERED_GROUP2_EVENTS
filter_group_events GROUP3_EVENTS FILTERED_GROUP3_EVENTS
filter_group_events GROUP4_EVENTS FILTERED_GROUP4_EVENTS
# Call filter_group_events for other groups if defined


# --- Main Execution Logic (Using Pre-Filtered Group Lists) ---
echo "======================================================" | tee -a "${LOG_FILE}"
echo "Starting Main Benchmark Runs at $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "${LOG_FILE}"
echo "Using ${TOTAL_CORES} cores on machine '${MACHINE}'." | tee -a "${LOG_FILE}"
echo "Baseline algorithm: ${BASELINE_ALGO}" | tee -a "${LOG_FILE}"
echo "Algorithms to run: ${ALGOS[*]}" | tee -a "${LOG_FILE}"
echo "======================================================" | tee -a "${LOG_FILE}"

ALL_ALGOS_TO_PROFILE=("${BASELINE_ALGO}" "${ALGOS[@]}")

# Flag to ensure benchmark output files are overwritten only on the first group run
first_group_run=1 

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

            first_stdout_write=1 # Flag for overwriting vs appending stdout

            # Define common benchmark output files for this combo
            BENCH_TXT_FILE="${TXT_DIR}/${algo}_${gen}_${type}_stdout.txt"
            BENCH_ERR_FILE="${ERR_DIR}/${algo}_${gen}_${type}_stderr.err"
            # Clear/Create stderr file at the beginning of the combo run
            :> "${BENCH_ERR_FILE}"

            # --- Loop through event groups ---
            for group_name in "${ALL_GROUPS[@]}"; do
                echo "  Running Group: ${group_name} for: algo=${algo}, gen=${gen}, type=${type}" | tee -a "${LOG_FILE}"

                # Get the pre-filtered event list
                current_filtered_list_name="FILTERED_${group_name}_EVENTS[@]"
                CURRENT_GROUP_EVENTS_TO_RUN=( "${!current_filtered_list_name}" )

                if [ ${#CURRENT_GROUP_EVENTS_TO_RUN[@]} -eq 0 ]; then
                    echo "    Warning: No available events configured for ${group_name}. Skipping group." | tee -a "${LOG_FILE}"
                    continue # Skip this group
                fi

                AVAILABLE_GROUP_EVENTS_STR=$(IFS=,; echo "${CURRENT_GROUP_EVENTS_TO_RUN[*]}")
                echo "    Using pre-filtered events for ${group_name}: ${AVAILABLE_GROUP_EVENTS_STR}" | tee -a "${LOG_FILE}"

                # Define perf stat output file for this group
                PERF_STAT_OUTPUT_FILE="${STAT_DIR}/${algo}_${gen}_${type}_${group_name}_perf_stat.txt"

                # Prepare benchmark command (handle stdout overwrite/append)
                # Use overwrite '>' for stdout only on the first group run for this combo
                # Always append '>>' for stderr
                stdout_redirect_op=">>" # Default to append
                if [ $first_stdout_write -eq 1 ]; then
                    stdout_redirect_op=">" # Overwrite on first run
                    first_stdout_write=0 # Clear flag
                fi

                BENCHMARK_COMMAND="numactl -i all ${ALGO_EXECUTABLE} \
                    -b ${MIN_LOG} -e ${MAX_LOG} -r ${NUM_RUNS} -t ${TOTAL_CORES} \
                    -g ${gen} -d ${type} -v vector -m ${MACHINE} \
                    ${stdout_redirect_op} '${BENCH_TXT_FILE}' 2>> '${BENCH_ERR_FILE}'"

                # Construct and Execute Perf Command
                PERF_COMMAND="perf stat -e ${AVAILABLE_GROUP_EVENTS_STR} -o '${PERF_STAT_OUTPUT_FILE}' -- bash -c \"${BENCHMARK_COMMAND}\""
                echo "    Executing Perf Command for ${group_name}..." | tee -a "${LOG_FILE}"

                eval "${PERF_COMMAND}"
                exit_status=$?

                if [ $exit_status -ne 0 ]; then
                    echo "    Error occurred during perf stat run for ${group_name} (Exit Status: ${exit_status}). Check '${PERF_STAT_OUTPUT_FILE}'." | tee -a "${LOG_FILE}"
                else
                    echo "    Perf stat finished for ${group_name}." | tee -a "${LOG_FILE}"
                fi

                if [ -s "${BENCH_ERR_FILE}" ]; then
                   echo "    Note: Benchmark stderr file '${BENCH_ERR_FILE}' is non-empty. Check for errors." | tee -a "${LOG_FILE}"
                fi
                echo "    --- Group ${group_name} Finished ---" | tee -a "${LOG_FILE}"

            done # --- End event group loop ---

            echo "  Finished all groups for: algo=${algo}, gen=${gen}, type=${type}" | tee -a "${LOG_FILE}"

            # --- !! NEW: Check for Benchmark Configuration Errors and Cleanup !! ---
            if [ -f "${BENCH_TXT_FILE}" ]; then # Check if stdout file exists
                if grep -q 'configwarning=1' "${BENCH_TXT_FILE}"; then
                    echo "  CONFIG WARNING DETECTED in ${BENCH_TXT_FILE}!" | tee -a "${LOG_FILE}"
                    echo "  Deleting potentially misleading perf stat files for this configuration." | tee -a "${LOG_FILE}"
                    
                    perf_file_pattern="${STAT_DIR}/${algo}_${gen}_${type}_GROUP"
                    files_to_delete=$(ls ${perf_file_pattern}*_perf_stat.txt 2>/dev/null) # Find files before deleting

                    if [ -n "$files_to_delete" ]; then
                        echo "  Deleting files:" | tee -a "${LOG_FILE}"
                        # Use loop to print deleted files for clarity
                        for file_to_del in $files_to_delete; do
                            echo "    - $file_to_del" | tee -a "${LOG_FILE}"
                            rm -f "$file_to_del"
                        done
                    else
                        echo "  No perf stat files found matching pattern to delete." | tee -a "${LOG_FILE}"
                    fi
                    
                    # Optionally delete the stdout/stderr files too
                    # echo "  Deleting stdout/stderr files for this configuration." | tee -a "${LOG_FILE}"
                    # rm -f "${BENCH_TXT_FILE}" "${BENCH_ERR_FILE}" 
                fi
            else
                 echo "  Warning: Benchmark stdout file not found: ${BENCH_TXT_FILE}. Cannot check for configwarning." | tee -a "${LOG_FILE}"
            fi
            # --- End Check and Cleanup ---

            echo "---" | tee -a "${LOG_FILE}"

        done # --- End datatype loop ---
    done # --- End generator loop ---
done # --- End algorithm loop ---

# --- Optional: Quick Analysis Section (can be removed if Python does all analysis) ---
# ... (The previous quick diff logic can remain here if desired, but it needs adaptation 
#      to handle the grouped files, which makes it significantly more complex in bash. 
#      It's likely better to rely entirely on the Python script now.) ...
echo "======================================================" | tee -a "${LOG_FILE}"
echo "Skipping bash-based quick analysis. Please use the Python script to merge and analyze grouped data." | tee -a "${LOG_FILE}"


echo "======================================================" | tee -a "${LOG_FILE}"
echo "Benchmark Run Completed at $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "${LOG_FILE}"
echo "All logs, results, and perf_stats are stored in: ${PARENT_DIR}" | tee -a "${LOG_FILE}"
echo "Main log file: ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "======================================================" | tee -a "${LOG_FILE}"

echo "Perf stat benchmark completed. Check the directory ${PARENT_DIR} for all outputs."
echo "Perf stat raw data files (grouped) for Python processing are in: ${STAT_DIR}"