# analyze_main.py
import os
import re
import argparse
from collections import defaultdict
import sys
import numpy as np # 需要导入 numpy 以便能够使用 np.nan

# 检查依赖库 (不变)
try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False 

try:
    import pandas as pd
    # import numpy as np # 已在上面导入
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.impute import SimpleImputer 
    ML_LIBS_AVAILABLE = True
except ImportError:
    print("Warning: pandas or scikit-learn not found. Feature importance analysis will be skipped. "
          "Install them using: pip install pandas scikit-learn", file=sys.stderr)
    ML_LIBS_AVAILABLE = False


# 从其他模块导入函数和数据
from perf_parser import parse_perf_file, KEY_EVENT_MAPPINGS # 导入 KEY_EVENT_MAPPINGS 以便进行映射
from perf_analyzer import calculate_metrics, METRIC_PRINT_ORDER # calculate_metrics 现在只接收一个参数
from wall_time_parser import calculate_average_wall_time

# 为了准备ML数据，我们需要 FEATURE_KEYS_FOR_MODEL 和 TARGET_KEY
# 理想情况下，这些应该从 feature_analyzer.py 导入，或者在一个共享的配置文件中定义
# 这里我们假设它们可以在 feature_analyzer 中获取，或者我们需要在这里定义一个 RAW_TO_FEATURE_NAME_MAP
# 和一个 FEATURE_KEYS_FOR_MODEL 的副本或引用，以便正确填充 all_metrics_for_ml_and_plots

# 导入绘图和特征重要性函数（如果可用）
if MATPLOTLIB_AVAILABLE:
    from perf_visualizer import generate_comparison_plots

# FEATURE_ANALYSIS_AVAILABLE 的设置逻辑保持不变
if ML_LIBS_AVAILABLE and MATPLOTLIB_AVAILABLE: 
    try:
        # 从 feature_analyzer 导入 perform_feature_importance 和它定义的 FEATURE_KEYS_FOR_MODEL, TARGET_KEY
        from feature_analyzer import perform_feature_importance, FEATURE_KEYS_FOR_MODEL, TARGET_KEY
        FEATURE_ANALYSIS_AVAILABLE = True
    except ImportError as ie:
        print(f"Warning: Could not import from feature_analyzer ({ie}). Feature importance analysis skipped.", file=sys.stderr)
        FEATURE_ANALYSIS_AVAILABLE = False
else:
    FEATURE_ANALYSIS_AVAILABLE = False
    # 如果 feature_analyzer 不能导入，我们需要为 FEATURE_KEYS_FOR_MODEL 和 TARGET_KEY 提供回退定义
    # 以免在尝试使用它们时出错，尽管特征分析会被跳过。
    # 或者，更好的做法是在使用它们的代码块之前检查 FEATURE_ANALYSIS_AVAILABLE。
    if 'FEATURE_KEYS_FOR_MODEL' not in globals(): FEATURE_KEYS_FOR_MODEL = []
    if 'TARGET_KEY' not in globals(): TARGET_KEY = "Average Wall Time (ms)"


# --- find_latest_run_dir 和 merge_group_stats 函数保持不变 ---
def find_latest_run_dir(base_run_dir="/home/xwang605/parallel-bench-suite/run/"):
    latest_run_dir = None
    try:
        if not os.path.isdir(base_run_dir): print(f"Error: Base run directory '{base_run_dir}' does not exist.", file=sys.stderr); return None
        all_runs = [d for d in os.listdir(base_run_dir) if d.startswith("perf_benchmark_run_") and os.path.isdir(os.path.join(base_run_dir, d))]
        if not all_runs: print(f"Error: No 'perf_benchmark_run_*' directories found in {base_run_dir}", file=sys.stderr); return None
        latest_run_dir_name = sorted(all_runs)[-1]
        latest_run_dir = os.path.join(base_run_dir, latest_run_dir_name)
    except Exception as e: print(f"Error during auto-detection of latest run directory: {e}", file=sys.stderr); return None
    return latest_run_dir

def merge_group_stats(group_stats_map):
    merged_stats = defaultdict(int)
    group_order = ["GROUP1", "GROUP2", "GROUP3", "GROUP4"]
    processed_events = set() # 用于确保每个事件只从其在group_order中首次出现的组获取
    for group_id in group_order:
        if group_id in group_stats_map:
            current_group_stats = group_stats_map[group_id]
            for event, count in current_group_stats.items():
                if event not in processed_events:
                    merged_stats[event] = count
                    processed_events.add(event)
    # 确保核心事件（如果GROUP1存在）的值被使用
    if "GROUP1" in group_stats_map:
        g1_stats = group_stats_map["GROUP1"]
        # 这些是 perf_parser.get_event_value 使用的通用键对应的原始事件名变体
        # merge_group_stats 返回的键应该是原始事件名
        core_event_variants_to_check = KEY_EVENT_MAPPINGS.get("CYCLES", []) + KEY_EVENT_MAPPINGS.get("IC", [])
        for core_event_variant in core_event_variants_to_check:
            if core_event_variant in g1_stats:
                merged_stats[core_event_variant] = g1_stats[core_event_variant] # 确保来自GROUP1
    return merged_stats

# --- Main Function ---
def main():
    parser = argparse.ArgumentParser(description="Analyze grouped perf stat and benchmark stdout files, generate reports and plots.")
    parser.add_argument("perf_dir", nargs='?', default=None,
                        help="Directory containing the perf_stats and results_stdout subdirectories "
                             "from a benchmark run. If not specified, attempts to find the latest run in "
                             "'/home/xwang605/parallel-bench-suite/run/'.")
    
    # --- MODIFIED help text for --baseline_algo ---
    parser.add_argument("--baseline_algo", default="benchmark_donothing",
                        help="Name of an algorithm to be treated as a reference or baseline, "
                             "often for exclusion from specific analyses (e.g., feature importance "
                             "or some plots) or for separate reporting. "
                             "Default: benchmark_donothing. Note: Numerical baseline subtraction "
                             "for all perf counters is no longer performed by default in calculate_metrics.")
    
    parser.add_argument("--no-plots", action="store_true", help="Skip plot generation.")
    parser.add_argument("--no-feature-analysis", action="store_true", help="Skip feature importance analysis.")

    args = parser.parse_args()

    run_dir_path = args.perf_dir
    print(run_dir_path)
    if not run_dir_path:
        print("No run directory specified, attempting to find the latest run...")
        run_dir_path = find_latest_run_dir()
        if not run_dir_path:
            print("Error: Could not find a suitable run directory. Exiting.", file=sys.stderr)
            return 1
        print(f"Automatically selected run directory: {run_dir_path}\n")
    
    perf_stats_dir = os.path.join(run_dir_path, "perf_stats")
    results_stdout_dir = os.path.join(run_dir_path, "results_stdout")

    if not (os.path.isdir(run_dir_path) and os.path.isdir(perf_stats_dir) and os.path.isdir(results_stdout_dir)):
        print(f"Error: Required subdirectories ('perf_stats', 'results_stdout') not found in {run_dir_path}", file=sys.stderr)
        return 1

    analysis_output_dir = os.path.join(run_dir_path, "analysis_result")
    try:
        os.makedirs(analysis_output_dir, exist_ok=True)
        print(f"Analysis results will be saved in: {analysis_output_dir}")
    except OSError as e:
        print(f"Error creating analysis output directory {analysis_output_dir}: {e}", file=sys.stderr)
        return 1
    
    # --- 1. 计算平均墙上时间 ---
    # (wall_time_parser.py 应该已经根据你的最新需求修改过了)
    average_wall_times = calculate_average_wall_time(results_stdout_dir)
    if average_wall_times is None: # calculate_average_wall_time 返回 None 表示严重错误
        print("Error: Failed to calculate average wall times. Exiting.", file=sys.stderr)
        return 1
    if not average_wall_times:
        print("Warning: No average wall times were calculated. Subsequent analyses might be affected.", file=sys.stderr)
        # 不一定退出，但后续步骤中依赖 wall time 的部分会受影响

    # --- 2. 加载并合并 Perf 数据 ---
    raw_grouped_data = defaultdict(lambda: defaultdict(dict))
    filename_pattern = re.compile(r'^(.*?)_([^_]+)_([^_]+)_(GROUP\d+)_perf_stat\.txt$')
    print(f"\nScanning perf stats directory: {perf_stats_dir}")
    file_count = 0
    for filename in sorted(os.listdir(perf_stats_dir)):
        match = filename_pattern.match(filename)
        if match:
            file_count += 1
            algo_name, generator, data_type, group_id = match.groups()
            run_key = (generator, data_type, algo_name) # (gen, type, algo)
            filepath = os.path.join(perf_stats_dir, filename)
            stats = parse_perf_file(filepath) # 从 perf_parser.py
            if stats is not None: # parse_perf_file 返回 None 表示文件读取或解析错误
                raw_grouped_data[run_key][group_id] = stats
            else:
                print(f"Warning: Could not parse {filepath}, data for this group will be missing.", file=sys.stderr)
    
    if file_count == 0:
        print(f"Error: No perf_stat files found in {perf_stats_dir}. Exiting.", file=sys.stderr)
        return 1

    all_perf_data = defaultdict(lambda: defaultdict(dict)) # {(gen, type): {algo: {merged_raw_event: count}}}
    print("Merging perf data from groups for each run...")
    for run_key, group_stats_map in raw_grouped_data.items():
        generator, data_type, algo_name = run_key
        merged_stats = merge_group_stats(group_stats_map) # merged_stats 的键是原始事件名
        if merged_stats: # 确保合并后有数据
            all_perf_data[(generator, data_type)][algo_name] = merged_stats
        else:
            print(f"Warning: No perf data merged for run {run_key}. This usually means no group files were parsed successfully.", file=sys.stderr)
    print("Merging complete.")

    # --- 3. 生成分析文件和准备绘图/特征分析数据 ---
    print("\n--- Generating Analysis Files & Preparing Plot/Feature Data ---")
    if not all_perf_data:
        print("Error: No merged perf data available to analyze. Exiting.", file=sys.stderr)
        return 1

    all_metrics_for_ml_and_plots = defaultdict(lambda: defaultdict(dict))

    # 为了将原始事件名 (如 "cycles:u") 映射到描述性特征名 (如 "Cycles")
    # 我们需要 RAW_TO_FEATURE_NAME_MAP。这个映射最好与 KEY_EVENT_MAPPINGS (在perf_parser.py中) 相关联或一致。
    # KEY_EVENT_MAPPINGS 是 {GenericKey: [raw_name1, raw_name2]}
    # 我们需要的是 {raw_name_variant: DescriptiveFeatureName}
    # 或者，让 calculate_metrics 直接返回 DescriptiveFeatureName 键的字典。
    # 当前 perf_analyzer.calculate_metrics 返回的已经是描述性键名的字典。

    for (gen, data_type), algo_perf_runs in sorted(all_perf_data.items()):
        output_filename = os.path.join(analysis_output_dir, f"analysis_{gen}_{data_type}.txt")
        print(f"  Generating Text Report: {output_filename}")
        current_config_wall_times = average_wall_times.get((gen, data_type), {})

        try:
            with open(output_filename, 'w', encoding='utf-8') as f_out:
                f_out.write(f"Configuration: Generator='{gen}', DataType='{data_type}'\n")
                f_out.write("====================================================\n")

                # baseline_stats_merged 不再用于数值减法，但 baseline_algo_name 用于排除
                # 如果要在报告中打印基线算法的原始数据，可以单独处理
                baseline_raw_metrics = algo_perf_runs.get(args.baseline_algo) # 获取基线的原始合并统计

                for algo_name, current_stats_merged in sorted(algo_perf_runs.items()):
                    avg_wall_time = current_config_wall_times.get(algo_name)
                    
                    # 调用修改后的 calculate_metrics，它只接收当前算法的合并统计数据
                    # 返回的 calculated_metrics 字典键是描述性的 (如 "Cycles", "IPC")
                    # 值是原始计数或基于原始计数的派生指标
                    calculated_metrics = calculate_metrics(current_stats_merged) 
                                        
                    # --- 存储用于ML和绘图的数据 ---
                    # metrics_to_store 将包含墙上时间和 calculate_metrics 返回的描述性指标
                    metrics_to_store = {}
                    if avg_wall_time is not None:
                        metrics_to_store[TARGET_KEY] = avg_wall_time # TARGET_KEY 来自 feature_analyzer
                    
                    # 将 calculate_metrics 的所有输出（描述性键和值）添加到 metrics_to_store
                    metrics_to_store.update(calculated_metrics) 
                    
                    if metrics_to_store.get(TARGET_KEY) is not None: # 仅当有墙上时间（目标变量）时才存储
                        all_metrics_for_ml_and_plots[(gen, data_type)][algo_name] = metrics_to_store
                    # --------------------------------

                    # --- 写入文本报告 ---
                    f_out.write(f"\n  Algorithm: {algo_name.replace('benchmark_', '')}\n")
                    f_out.write(  "  --------------------------------------\n")
                    if avg_wall_time is not None:
                        f_out.write(f"    {'Average Wall Time (ms)':<50}: {avg_wall_time:>20.3f}\n")
                    else:
                        f_out.write(f"    {'Average Wall Time (ms)':<50}: {' ':>20} (Not Found)\n")
                    
                    # 报告标题不再提及 "Baseline Adjusted"
                    f_out.write(  "    {:<50}: {:>20}\n".format("---- Perf Metrics (Raw Counts / Derived) ----", "----"))

                    # 打印 calculated_metrics 中的所有指标
                    for metric_name in METRIC_PRINT_ORDER: # METRIC_PRINT_ORDER 来自 perf_analyzer
                        if metric_name in calculated_metrics:
                            value = calculated_metrics[metric_name]
                            if value == "N/A": # 跳过明确为N/A的（例如分母为0的IPC）
                                # f_out.write(f"    {metric_name:<50}: {'N/A':>20}\n")
                                continue 
                            
                            output_line = ""
                            if "IPC" in metric_name and isinstance(value, float):
                                output_line = f"    {metric_name:<50}: {value:>20.3f}\n"
                            elif ("Rate" in metric_name or "%" in metric_name) and isinstance(value, float):
                                output_line = f"    {metric_name:<50}: {value:>20.2f} %\n"
                            elif isinstance(value, (int, np.integer)): # 处理 numpy int 类型
                                output_line = f"    {metric_name:<50}: {value:>20,}\n"
                            elif isinstance(value, (float, np.floating)): # 处理 numpy float 类型
                                # 对于非IPC、非Rate的float，可能也用.3f或科学计数法
                                if abs(value) > 1e6 or (abs(value) < 1e-2 and value != 0):
                                     output_line = f"    {metric_name:<50}: {value:>20.3e}\n"
                                else:
                                     output_line = f"    {metric_name:<50}: {value:>20.3f}\n"
                            else: # 其他如字符串 "N/A" (已被上面if跳过) 或意外类型
                                output_line = f"    {metric_name:<50}: {str(value):>20}\n"
                            f_out.write(output_line)
                f_out.write("====================================================\n")
        except Exception as e:
            print(f"Error processing/writing text report for configuration ({gen}, {data_type}): {e}", file=sys.stderr)
            # traceback.print_exc() # For more detailed error


    # --- 4. 生成绘图 ---
    if MATPLOTLIB_AVAILABLE and not args.no_plots:
        print("\n--- Generating Plots ---")
        if not all_metrics_for_ml_and_plots:
            print("  No data available for plotting.")
        else:
            for config_key, config_plot_data in sorted(all_metrics_for_ml_and_plots.items()):
                print(f"  Generating plot for config: {config_key}")
                # generate_comparison_plots 期望的数据结构是 {algo: {metric_key: value}}
                # config_plot_data 就是这个结构
                generate_comparison_plots(config_plot_data, config_key, analysis_output_dir, args.baseline_algo) # baseline_algo 用于排除
    elif args.no_plots:
        print("\nPlot generation skipped due to --no-plots flag.")
    else: # MATPLOTLIB_AVAILABLE is False
        print("\nPlot generation skipped as matplotlib is not available.")


    # --- 5. 执行特征重要性分析 ---
    if FEATURE_ANALYSIS_AVAILABLE and not args.no_feature_analysis:
        # perform_feature_importance 期望的 all_metrics_data 结构是 {(gen, type): {algo: {metric_key: value}}}
        # 这正是 all_metrics_for_ml_and_plots 的结构
        perform_feature_importance(all_metrics_for_ml_and_plots, analysis_output_dir, args.baseline_algo) # baseline_algo 用于排除
    elif args.no_feature_analysis:
        print("\nFeature importance analysis skipped due to --no-feature-analysis flag.")
    else: # FEATURE_ANALYSIS_AVAILABLE is False
        print("\nFeature importance analysis skipped as scikit-learn or matplotlib is not available.")

    print("\nAnalysis complete.")
    return 0

if __name__ == "__main__":
    exit_code = main()
    if exit_code != 0:
        sys.exit(exit_code)