import os
import re
import statistics # For statistics.mean
import glob
from collections import defaultdict
import sys # For sys.stderr

# 这个值应该与你的 bash 脚本中传递给 C++ 程序的 -r 参数一致
# 它代表了 C++ 程序内部会进行多少次迭代 (run=0 to NUM_CPP_INTERNAL_ITERATIONS-1)
NUM_CPP_INTERNAL_ITERATIONS = 5 # 从你的 bash 脚本中 NUM_RUNS=5

def parse_result_line_for_time(line):
    """
    专门解析 RESULT 行以提取 run ID 和 milli 时间值。
    (此函数与你提供的版本基本一致)
    """
    run_match = re.search(r'\brun=(\d+)\b', line)
    milli_match = re.search(r'\bmilli=([\d.]+(?:e-?\d+)?)', line) # 支持科学计数法

    run_id = None
    milli_value = None

    if run_match:
        try:
            run_id = int(run_match.group(1))
        except ValueError:
            pass 

    if milli_match:
        try:
            milli_value = float(milli_match.group(1))
        except ValueError:
            pass 
    return run_id, milli_value

def calculate_average_wall_time(results_stdout_dir):
    """
    分析 results_stdout 目录下的所有 benchmark_*_stdout.txt 文件。
    对于每个文件，它会读取文件开头的 NUM_CPP_INTERNAL_ITERATIONS 次 C++ 内部运行结果，
    丢弃第一次内部运行 (run=0) 的时间，然后计算剩余运行的平均 milli 时间。
    返回字典: {(gen, type): {algo_name: avg_milli_time}}
    """
    if not os.path.isdir(results_stdout_dir):
        print(f"Error: results_stdout directory not found: {results_stdout_dir}", file=sys.stderr)
        return None

    output_files = glob.glob(os.path.join(results_stdout_dir, "benchmark_*_stdout.txt"))

    if not output_files:
        print(f"Warning: No 'benchmark_*_stdout.txt' files found in {results_stdout_dir}", file=sys.stderr)
        return {} 

    # 最终结果结构: {(gen, type): {algo_name: avg_milli_time}}
    average_times_final = defaultdict(lambda: defaultdict(lambda: None))
    
    filename_pattern = re.compile(r'^(benchmark_.*?)_([^_]+)_([^_]+)_stdout\.txt$')

    print(f"\nCalculating average wall times from: {results_stdout_dir}")
    for filepath in sorted(output_files): # Sorted for consistent processing order
        filename = os.path.basename(filepath)
        match = filename_pattern.match(filename)
        
        if not match:
            print(f"Warning: Could not parse algo/gen/type from filename {filename}, skipping.")
            continue
            
        algo_name = match.group(1) 
        generator = match.group(2)
        data_type = match.group(3)
        
        run_key_for_output = (generator, data_type) # Key for the output dictionary
        
        milli_values_first_block = [] # 存储文件开头第一个C++执行块的 milli 时间
        lines_read_for_first_block = 0
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith("RESULT"):
                        if lines_read_for_first_block < NUM_CPP_INTERNAL_ITERATIONS:
                            _run_id, milli_value = parse_result_line_for_time(line) # run_id 暂时不需要，但可以解析出来验证
                            if milli_value is not None:
                                milli_values_first_block.append(milli_value)
                            lines_read_for_first_block += 1
                        else:
                            # 已经读取了第一个 C++ 执行块的所有内部迭代结果，停止读取此文件
                            break 
            
            if not milli_values_first_block:
                print(f"  Warning: No RESULT lines with milli time found in the first block of {filename}.")
                continue # 跳过这个文件

            if len(milli_values_first_block) < NUM_CPP_INTERNAL_ITERATIONS:
                 print(f"  Warning: Found only {len(milli_values_first_block)} milli values in first block of {filename}, expected {NUM_CPP_INTERNAL_ITERATIONS}. Using available data.")


            # --- 根据你的要求：去掉第一个，然后平均剩下的 ---
            times_to_average = []
            if len(milli_values_first_block) > 1: # 如果至少有两次运行的数据
                times_to_average = milli_values_first_block[1:] # 去掉第一个 (对应 C++ 内部 run=0)
            elif len(milli_values_first_block) == 1: # 如果只有一次运行的数据
                # print(f"  Note: Only one internal run found in first block for {filename}. Using its time.", file=sys.stderr)
                times_to_average = milli_values_first_block 
            
            if times_to_average: # 如果列表非空
                try:
                    mean_time = statistics.mean(times_to_average)
                    average_times_final[run_key_for_output][algo_name] = mean_time
                    # print(f"  Avg wall time for {algo_name} ({generator}, {data_type}): {mean_time:.3f} ms (from {len(times_to_average)} of {len(milli_values_first_block)} internal runs)")
                except statistics.StatisticsError:
                    print(f"  Warning: Could not calculate mean time for {algo_name} ({generator}, {data_type}) from values: {times_to_average}", file=sys.stderr)
            else:
                print(f"  Warning: No relevant times to average for {algo_name} ({generator}, {data_type}) in {filename}.", file=sys.stderr)

        except Exception as e:
            print(f"Error processing file {filepath}: {e}", file=sys.stderr)
            continue

    print("Average wall time calculation (from first C++ exec block, excluding its first internal run) complete.")
    return average_times_final