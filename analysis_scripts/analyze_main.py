# analyze_main.py
import os
import re
import argparse
from collections import defaultdict
import sys

# 检查依赖库
try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False # Will be handled in visualizer/analyzer

try:
    import pandas as pd
    import numpy as np
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.impute import SimpleImputer # Needed here or in feature_analyzer
    ML_LIBS_AVAILABLE = True
except ImportError:
     print("Warning: pandas or scikit-learn not found. Feature importance analysis will be skipped. "
           "Install them using: pip install pandas scikit-learn", file=sys.stderr)
     ML_LIBS_AVAILABLE = False


# 从其他模块导入函数和数据
from perf_parser import parse_perf_file
from perf_analyzer import calculate_metrics, METRIC_PRINT_ORDER
from wall_time_parser import calculate_average_wall_time
# 导入绘图和特征重要性函数（如果可用）
if MATPLOTLIB_AVAILABLE:
    from perf_visualizer import generate_comparison_plots
if ML_LIBS_AVAILABLE and MATPLOTLIB_AVAILABLE: # Feature analyzer needs ML libs and plotting lib
     try:
          from feature_analyzer import perform_feature_importance
          FEATURE_ANALYSIS_AVAILABLE = True
     except ImportError as ie:
          print(f"Warning: Could not import feature_analyzer ({ie}). Feature importance analysis skipped.", file=sys.stderr)
          FEATURE_ANALYSIS_AVAILABLE = False
else:
     FEATURE_ANALYSIS_AVAILABLE = False


# --- find_latest_run_dir 和 merge_group_stats 函数保持不变 ---
def find_latest_run_dir(base_run_dir="/home/xwang605/parallel-bench-suite/run/"):
    # ... (函数实现与之前相同) ...
    latest_run_dir = None
    try:
        if not os.path.isdir(base_run_dir):
            print(f"Error: Base run directory '{base_run_dir}' does not exist.", file=sys.stderr)
            return None
        all_runs = [d for d in os.listdir(base_run_dir)
                    if d.startswith("perf_benchmark_run_") and \
                       os.path.isdir(os.path.join(base_run_dir, d))]
        if not all_runs:
            print(f"Error: No 'perf_benchmark_run_*' directories found in {base_run_dir}", file=sys.stderr)
            return None
        latest_run_dir_name = sorted(all_runs)[-1]
        latest_run_dir = os.path.join(base_run_dir, latest_run_dir_name)
    except Exception as e:
        print(f"Error during auto-detection of latest run directory: {e}", file=sys.stderr)
        return None
    return latest_run_dir

def merge_group_stats(group_stats_map):
    # ... (函数实现与之前相同) ...
    merged_stats = defaultdict(int)
    group_order = ["GROUP1", "GROUP2", "GROUP3", "GROUP4"]
    processed_events = set()
    for group_id in group_order:
        if group_id in group_stats_map:
            current_group_stats = group_stats_map[group_id]
            for event, count in current_group_stats.items():
                if event not in processed_events:
                    merged_stats[event] = count
                    processed_events.add(event)
    if "GROUP1" in group_stats_map:
        g1_stats = group_stats_map["GROUP1"]
        core_events = ["cycles:u", "cycles", "instructions:u", "instructions"]
        for core_event in core_events:
            if core_event in g1_stats:
                 merged_stats[core_event] = g1_stats[core_event]
    return merged_stats

# --- Main Function ---
def main():
    parser = argparse.ArgumentParser(description="Analyze grouped perf stat and benchmark stdout files, generate reports and plots.")
    parser.add_argument("perf_dir", nargs='?', default=None,
                        help="Directory containing the perf_stats and results_stdout subdirectories "
                             "from a benchmark run. If not specified, attempts to find the latest run in "
                             "'/home/xwang605/parallel-bench-suite/run/'.")
    parser.add_argument("--baseline_algo", default="benchmark_donothing",
                        help="Name of the baseline algorithm (default: benchmark_donothing).")
    parser.add_argument("--no-plots", action="store_true", help="Skip plot generation.")
    parser.add_argument("--no-feature-analysis", action="store_true", help="Skip feature importance analysis.")


    args = parser.parse_args()
    run_dir_arg = args.perf_dir
    baseline_algo_name = args.baseline_algo
    perf_stats_dir = None
    results_stdout_dir = None
    run_dir_path = None

    # --- 确定路径 (与之前相同) ---
    if not run_dir_arg:
        # ... (自动查找逻辑) ...
        print("No run directory specified, attempting to find the latest run...")
        latest_run_dir_path = find_latest_run_dir()
        if latest_run_dir_path:
             run_dir_path = latest_run_dir_path
             perf_stats_dir = os.path.join(run_dir_path, "perf_stats")
             results_stdout_dir = os.path.join(run_dir_path, "results_stdout")
             print(f"Automatically selected run directory: {run_dir_path}\n")
        else: return 1
    else:
        # ... (处理用户指定路径的逻辑) ...
        if os.path.isdir(run_dir_arg):
             if os.path.basename(run_dir_arg) == "perf_stats":
                 perf_stats_dir = run_dir_arg
                 run_dir_path = os.path.dirname(run_dir_arg)
                 results_stdout_dir = os.path.join(run_dir_path, "results_stdout")
                 if not os.path.isdir(results_stdout_dir): return 1 # Error printed inside now
             elif os.path.isdir(os.path.join(run_dir_arg, "perf_stats")) and os.path.isdir(os.path.join(run_dir_arg, "results_stdout")):
                  run_dir_path = run_dir_arg
                  perf_stats_dir = os.path.join(run_dir_path, "perf_stats")
                  results_stdout_dir = os.path.join(run_dir_path, "results_stdout")
             else: return 1 # Error printed inside now
        else: return 1 # Error printed inside now


    if not all([run_dir_path, perf_stats_dir, results_stdout_dir,
                os.path.isdir(run_dir_path), os.path.isdir(perf_stats_dir), os.path.isdir(results_stdout_dir)]):
        print(f"Error: Could not determine valid run, perf_stats, or results_stdout directories.", file=sys.stderr)
        return 1

    # --- 创建分析输出目录 (与之前相同) ---
    analysis_output_dir = os.path.join(run_dir_path, "analysis_result")
    try:
        os.makedirs(analysis_output_dir, exist_ok=True)
        print(f"Analysis results will be saved in: {analysis_output_dir}")
    except OSError as e: return 1 # Error printed inside now


    # --- 1. 计算平均墙上时间 (与之前相同) ---
    average_wall_times = calculate_average_wall_time(results_stdout_dir)
    if average_wall_times is None: return 1


    # --- 2. 加载并合并 Perf 数据 (与之前相同) ---
    raw_grouped_data = defaultdict(lambda: defaultdict(dict))
    # ... (扫描和解析文件的循环) ...
    filename_pattern = re.compile(r'^(.*?)_([^_]+)_([^_]+)_(GROUP\d+)_perf_stat\.txt$')
    print(f"\nScanning perf stats directory: {perf_stats_dir}")
    file_count = 0
    for filename in sorted(os.listdir(perf_stats_dir)):
         match = filename_pattern.match(filename)
         if match:
              file_count += 1
              algo_name, generator, data_type, group_id = match.groups()
              run_key = (generator, data_type, algo_name)
              filepath = os.path.join(perf_stats_dir, filename)
              stats = parse_perf_file(filepath)
              if stats is not None:
                  raw_grouped_data[run_key][group_id] = stats
              else: print(f"Warning: Could not parse {filepath}", file=sys.stderr)
    if file_count == 0: return 1 # Error printed inside now

    all_perf_data = defaultdict(lambda: defaultdict(dict))
    print("Merging perf data from groups for each run...")
    for run_key, group_stats_map in raw_grouped_data.items():
        generator, data_type, algo_name = run_key
        merged_stats = merge_group_stats(group_stats_map)
        if merged_stats: all_perf_data[(generator, data_type)][algo_name] = merged_stats
        else: print(f"Warning: No perf data merged for run {run_key}.", file=sys.stderr)
    print("Merging complete.")


    # --- 3. 生成分析文件和准备绘图/特征分析数据 ---
    print("\n--- Generating Analysis Files & Preparing Plot/Feature Data ---")
    if not all_perf_data: return 1 # Error printed inside now

    # 存储所有配置和算法的最终指标，用于绘图和特征分析
    all_metrics_for_ml_and_plots = defaultdict(lambda: defaultdict(dict))

    for (gen, data_type), algo_perf_runs in sorted(all_perf_data.items()):
        output_filename = os.path.join(analysis_output_dir, f"analysis_{gen}_{data_type}.txt")
        print(f"  Generating Text Report: {output_filename}")
        current_config_wall_times = average_wall_times.get((gen, data_type), {})

        try:
            with open(output_filename, 'w', encoding='utf-8') as f_out:
                # ... (写入文本报告头信息) ...
                f_out.write(f"Configuration: Generator='{gen}', DataType='{data_type}'\n")
                f_out.write("====================================================\n")

                baseline_stats_merged = algo_perf_runs.get(baseline_algo_name)
                if not baseline_stats_merged:
                     f_out.write(f"  Error: Baseline algorithm '{baseline_algo_name}' perf data not found.\n")
                     f_out.write("====================================================\n")
                     continue

                for algo_name, current_stats_merged in sorted(algo_perf_runs.items()):
                    avg_wall_time = current_config_wall_times.get(algo_name)
                    calculated_metrics = {} # 校准后的指标
                    
                    # --- 存储用于ML和绘图的数据 ---
                    # 我们需要墙上时间（目标）和校准后的perf指标（特征）
                    metrics_to_store = {}
                    if avg_wall_time is not None:
                         metrics_to_store["Average Wall Time (ms)"] = avg_wall_time
                         
                    if algo_name != baseline_algo_name:
                         calculated_metrics = calculate_metrics(current_stats_merged, baseline_stats_merged)
                         metrics_to_store.update(calculated_metrics) # 添加校准后的perf指标
                    
                    # 即使是基线，也存储其墙上时间（如果有的话），但perf指标为空或不用于比较
                    if metrics_to_store: # 只存储有数据的条目
                         all_metrics_for_ml_and_plots[(gen, data_type)][algo_name] = metrics_to_store
                    # --------------------------------

                    # --- 写入文本报告 ---
                    f_out.write(f"\n  Algorithm: {algo_name.replace('benchmark_', '')}\n")
                    f_out.write(  "  --------------------------------------\n")
                    if avg_wall_time is not None:
                        f_out.write(f"    {'Average Wall Time (ms)':<50}: {avg_wall_time:>20.3f}\n")
                        f_out.write(  "    {:<50}: {:>20}\n".format("---- Perf Metrics (Baseline Adjusted) ----", "----"))
                    else:
                        f_out.write(f"    {'Average Wall Time (ms)':<50}: {' ':>20} (Not Found)\n")
                        f_out.write(  "    {:<50}: {:>20}\n".format("---- Perf Metrics (Baseline Adjusted) ----", "----"))

                    if algo_name != baseline_algo_name:
                        for metric_name in METRIC_PRINT_ORDER:
                             if metric_name in calculated_metrics:
                                value = calculated_metrics[metric_name]
                                if value == "N/A": continue
                                # ... (格式化和写入 f_out.write) ...
                                is_ipc = "IPC" in metric_name
                                output_line = ""
                                if is_ipc and isinstance(value, float):
                                    output_line = f"    {metric_name:<50}: {value:>20.3f}\n"
                                elif isinstance(value, float):
                                    output_line = f"    {metric_name:<50}: {value:>20.2f} %\n"
                                elif isinstance(value, int):
                                    output_line = f"    {metric_name:<50}: {value:>20,}\n"
                                else:
                                    output_line = f"    {metric_name:<50}: {str(value):>20}\n"
                                f_out.write(output_line)
                    else:
                         f_out.write(f"    (Baseline Algorithm - Raw Perf Data Used for Adjustment)\n")
                f_out.write("====================================================\n")
        except Exception as e:
             print(f"Error processing/writing text report for configuration ({gen}, {data_type}): {e}", file=sys.stderr)


    # --- 4. 生成绘图 ---
    if MATPLOTLIB_AVAILABLE and not args.no_plots:
        print("\n--- Generating Plots ---")
        if not all_metrics_for_ml_and_plots:
             print("  No data available for plotting.")
        else:
            for config_key, config_plot_data in all_metrics_for_ml_and_plots.items():
                 print(f"  Generating plot for config: {config_key}")
                 # 注意: generate_comparison_plots 需要的数据结构是 {algo: {metric: value}}
                 # all_metrics_for_ml_and_plots 的结构已经是这样了
                 generate_comparison_plots(config_plot_data, config_key, analysis_output_dir, baseline_algo_name)
    # ... (处理 --no-plots 和 matplotlib 不可用的情况)

    # --- 5. 执行特征重要性分析 ---
    if FEATURE_ANALYSIS_AVAILABLE and not args.no_feature_analysis:
         perform_feature_importance(all_metrics_for_ml_and_plots, analysis_output_dir, baseline_algo_name)
    elif args.no_feature_analysis:
         print("\nFeature importance analysis skipped due to --no-feature-analysis flag.")
    else:
          print("\nFeature importance analysis skipped as scikit-learn or matplotlib is not available.")


    print("\nAnalysis complete.")
    return 0

if __name__ == "__main__":
    exit_code = main()
    if exit_code != 0:
        sys.exit(exit_code)