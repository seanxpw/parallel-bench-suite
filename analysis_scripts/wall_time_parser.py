# wall_time_parser.py
import os
import re
import statistics
import glob
from collections import defaultdict

def parse_result_line_for_time(line):
    """
    专门解析 RESULT 行以提取 run ID 和 milli 时间值。
    """
    run_match = re.search(r'\brun=(\d+)\b', line) # Use word boundary for run=
    # Use word boundary \b to ensure matching the whole word 'milli='
    milli_match = re.search(r'\bmilli=([\d.]+(?:e-?\d+)?)', line)

    run_id = None
    milli_value = None

    if run_match:
        try:
            run_id = int(run_match.group(1))
        except ValueError:
            pass # Ignore if run_id is not an integer

    if milli_match:
        try:
            milli_value = float(milli_match.group(1))
        except ValueError:
            pass # Ignore if milli_value is not a float

    # Return both, even if one is None initially
    return run_id, milli_value

def calculate_average_wall_time(results_stdout_dir):
    """
    分析 results_stdout 目录下的所有 benchmark_*_stdout.txt 文件。
    计算每个算法/配置的平均 milli 时间 (排除 run=0)。
    返回字典: {(gen, type): {algo_name: avg_milli_time}}
    """
    # Check if directory exists
    if not os.path.isdir(results_stdout_dir):
        print(f"Error: results_stdout directory not found: {results_stdout_dir}", file=sys.stderr)
        return None

    # Use glob to find files matching the pattern
    output_files = glob.glob(os.path.join(results_stdout_dir, "benchmark_*_stdout.txt"))

    if not output_files:
        print(f"Warning: No 'benchmark_*_stdout.txt' files found in {results_stdout_dir}", file=sys.stderr)
        return {} # Return empty dict if no files found

    # Structure: {(gen, type): {algo_name: [milli_list]}}
    raw_times_data = defaultdict(lambda: defaultdict(list))
    
    # Regex to parse algo, gen, type from filename
    # Example: benchmark_dovetailsort_random_pair_stdout.txt
    filename_pattern = re.compile(r'^(benchmark_.*?)_([^_]+)_([^_]+)_stdout\.txt$')


    print(f"\nCalculating average wall times from: {results_stdout_dir}")
    for filepath in output_files:
        filename = os.path.basename(filepath)
        match = filename_pattern.match(filename)
        
        if not match:
            print(f"Warning: Could not parse algo/gen/type from filename {filename}, skipping.")
            continue
            
        algo_name = match.group(1) # Includes "benchmark_" prefix
        generator = match.group(2)
        data_type = match.group(3)
        
        run_key = (generator, data_type)
        
        milli_values_for_algo = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith("RESULT"):
                        run_id, milli_value = parse_result_line_for_time(line)
                        # Store only if milli_value is valid, along with run_id
                        if milli_value is not None and run_id is not None:
                           milli_values_for_algo.append({'run': run_id, 'milli': milli_value})
                           
            # Store raw run times temporarily
            if milli_values_for_algo:
                 raw_times_data[run_key][algo_name] = milli_values_for_algo
            else:
                 print(f"  Warning: No valid RESULT lines with milli time found in {filename}.")

        except Exception as e:
            print(f"Error reading file {filepath}: {e}", file=sys.stderr)
            continue

    # --- Calculate Averages ---
    # Structure: {(gen, type): {algo_name: avg_milli}}
    average_times = defaultdict(lambda: defaultdict(lambda: None)) # Default to None if no valid avg

    for run_key, algo_times in raw_times_data.items():
        generator, data_type = run_key
        for algo_name, run_data_list in algo_times.items():
            # Filter out run=0 and extract milli values
            times_to_average = [item['milli'] for item in run_data_list if item.get('run') != 0]
            
            if len(times_to_average) > 0:
                try:
                    mean_time = statistics.mean(times_to_average)
                    average_times[run_key][algo_name] = mean_time
                    # print(f"  Avg time for {algo_name} ({generator}, {data_type}): {mean_time:.3f} ms (from {len(times_to_average)} runs)")
                except statistics.StatisticsError:
                     print(f"  Warning: Could not calculate mean time for {algo_name} ({generator}, {data_type})", file=sys.stderr)
            else:
                print(f"  Warning: No runs found excluding run=0 for {algo_name} ({generator}, {data_type})", file=sys.stderr)

    print("Average wall time calculation complete.")
    return average_times