# analyze_memory_only.py
import os
import re
import argparse
from collections import defaultdict
import sys
import numpy as np 

# 检查 matplotlib 是否可用
try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("Warning: matplotlib not found. Plot generation will be skipped. "
          "Install it using: pip install matplotlib", file=sys.stderr)

# 从你的模块导入解析函数
from memory_report_parser import parse_time_mem_report # 确保 memory_report_parser.py 在同一目录或 PYTHONPATH 中

# 定义我们从 memory_report_parser.py 的输出中提取并用于绘图的指标及其属性
MEMORY_METRICS_TO_PLOT = {
    "Max RSS (kB)": {"lower_is_better": True, "unit": "kB"},
    "Minor Page Faults": {"lower_is_better": True, "unit": "Count"},
    "Major Page Faults": {"lower_is_better": True, "unit": "Count"},
    "Voluntary Context Switches": {"lower_is_better": True, "unit": "Count"},
    "Involuntary Context Switches": {"lower_is_better": True, "unit": "Count"},
    # --- 新增指标 ---
    "kB per Total Page Fault": {"lower_is_better": False, "unit": "kB/fault"}, # 越高越好
}

# 这些常量用于图形的标题，如果需要动态获取，则应作为参数传递
# 或者从文件名/元数据中解析。为保持与你之前脚本的风格，这里可以预设或简化。
# 在你的 bash 脚本中，这些值是动态的或有具体设置
# TOTAL_THREADS_FOR_TITLE = 48 # 示例值，从你的 perf_visualizer.py 获取
# NUM_RUNS_FOR_TITLE = 5     # 示例值
# INPUT_SIZE_LOG_FOR_TITLE = 30 # 示例值 (例如 MIN_LOG)

def find_latest_run_dir(base_run_dir="/home/xwang605/parallel-bench-suite/run/"):
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

def generate_memory_plots_for_config(config_specific_data, generator, data_type, output_dir, 
                                     title_threads="N/A", title_runs="N/A", title_log_size="N/A"): # 新增参数用于标题
    """
    为单个 (generator, data_type) 配置生成内存指标对比图。
    config_specific_data 的结构是: {algo_name: {mem_metric_name: value}}
    """
    if not MATPLOTLIB_AVAILABLE:
        print("Info: Matplotlib not available. Skipping memory plot generation.", file=sys.stderr)
        return

    plot_data = {
        algo: metrics for algo, metrics in config_specific_data.items()
        if metrics and isinstance(metrics, dict)
    }
    
    algos_to_plot = sorted(plot_data.keys())
    num_algos = len(algos_to_plot)

    if num_algos == 0:
        return

    metrics_to_plot_ordered = list(MEMORY_METRICS_TO_PLOT.keys())
    num_metrics = len(metrics_to_plot_ordered)
    if num_metrics == 0: return

    ncols = 2 if num_metrics > 2 else 1
    if num_metrics == 1: ncols = 1
    elif num_metrics > 4 : ncols = 3
    
    nrows = (num_metrics + ncols - 1) // ncols
    
    fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(ncols * 6.2, nrows * 4.2), squeeze=False) #微调figsize
    axes = axes.flatten()

    plot_idx = 0
    for metric_key in metrics_to_plot_ordered:
        if plot_idx >= len(axes): break

        ax = axes[plot_idx]
        props = MEMORY_METRICS_TO_PLOT.get(metric_key, {})

        plot_labels = []
        plot_values = []

        for algo in algos_to_plot:
            raw_algo_name = algo # benchmark_algo_name 或 benchmark_algo_name_gen
            # 清理算法名称以用于标签，尝试移除 "benchmark_" 和可能的 "_gen" 后缀（如果 generator 是 'graph'）
            # 这一清理逻辑现在更依赖于你的具体命名习惯
            # 保持与 perf_visualizer.py 中一致的简化：
            display_algo_name = raw_algo_name.replace('benchmark_', '')
            if generator == "graph" and display_algo_name.endswith("_gen"): # 与你之前的讨论一致
                 display_algo_name = display_algo_name[:-4]


            value = plot_data.get(raw_algo_name, {}).get(metric_key)
            if value is not None and isinstance(value, (int, float)) and not np.isnan(value):
                plot_labels.append(display_algo_name)
                plot_values.append(value)
        
        if not plot_labels:
            ax.set_title(f"{metric_key}\n(No Valid Data)", fontsize=9)
            ax.axis('off')
            plot_idx += 1
            continue

        try:
            if num_algos == 1:
                colors = [plt.get_cmap('Pastel1')(0.1)] 
            else:
                colors = plt.get_cmap('Pastel1')(np.linspace(0, 1, num_algos))
        except:
            colors = 'skyblue'
        
        ax.bar(plot_labels, plot_values, color=colors)

        unit = props.get("unit", "")
        title = metric_key
        ax.set_title(title, fontsize=10, wrap=True)
        ax.set_ylabel(unit, fontsize=9)
        
        # --- MODIFIED: Removed ha='right' ---
        ax.tick_params(axis='x', rotation=45, labelsize=8) 
        ax.tick_params(axis='y', labelsize=8)
        ax.grid(axis='y', linestyle='--', alpha=0.7)

        if any(abs(v) >= 1e6 for v in plot_values if isinstance(v, (int,float))):
            ax.ticklabel_format(style='sci', axis='y', scilimits=(0,0), useMathText=True)

        lower_is_better = props.get("lower_is_better", True)
        performance_arrow = "↓ Better" if lower_is_better else "↑ Better"
        ax.text(0.98, 0.98, performance_arrow, transform=ax.transAxes, fontsize=8,
                verticalalignment='top', horizontalalignment='right',
                bbox=dict(boxstyle='round,pad=0.2', fc='#E0F2F1', alpha=0.9))
        
        if plot_values:
            numeric_plot_values = [v for v in plot_values if isinstance(v, (int, float))]
            if numeric_plot_values:
                min_val = min(numeric_plot_values)
                max_val = max(numeric_plot_values)
                
                padding_factor = 0.10 # 10% padding
                range_val = max_val - min_val
                if abs(range_val) < 1e-9 : # Avoid issues if all values are the same
                    range_val = abs(max_val) if abs(max_val) > 1e-9 else 1.0 # Ensure range_val is not zero for padding

                y_bottom = min_val - padding_factor * range_val
                y_top = max_val + padding_factor * range_val

                if min_val >= 0: # If all values are non-negative, ensure y_bottom is at most 0
                    y_bottom = max(0, y_bottom) if min_val > 0 else 0
                    if abs(max_val) < 1e-9 : y_top = 0.1 # if max is 0, give a little space

                # Ensure y_top is slightly larger than y_bottom if they become equal
                if abs(y_top - y_bottom) < 1e-9:
                    y_top = y_bottom + 0.1 * abs(y_bottom) if abs(y_bottom) > 1e-9 else y_bottom + 0.1


                ax.set_ylim(bottom=y_bottom, top=y_top)
        
        plot_idx += 1

    for i in range(plot_idx, len(axes)):
        axes[i].set_visible(False)
    
    fig_title = (f'Memory & Context Switch Metrics ("No Perf Round")\n'
                 f'Generator: {generator}, DataType: {data_type} '
                 f'(Threads: {title_threads}, IntRuns: {title_runs}, SizeLog: {title_log_size})')

    fig.suptitle(fig_title, fontsize=15, y=1.0) 
    plt.tight_layout(rect=[0, 0.03, 1, 0.93]) # Adjust rect for suptitle

    plot_filename = os.path.join(output_dir, f"memory_analysis_{generator}_{data_type}.png")
    try:
        fig.savefig(plot_filename, dpi=150)
        print(f"  Memory plot saved: {plot_filename}")
    except Exception as e:
        print(f"Error saving memory plot {plot_filename}: {e}", file=sys.stderr)
    plt.close(fig)

def main():
    parser = argparse.ArgumentParser(description="Analyze memory report files from benchmark 'no perf' rounds and generate plots.")
    parser.add_argument("run_dir", nargs='?', default=None,
                        help="Directory of a benchmark run (e.g., perf_benchmark_run_YYYY-MM-DD_HH_MM_SS). "
                             "If not specified, attempts to find the latest run in "
                             "'/home/xwang605/parallel-bench-suite/run/'.")
    parser.add_argument("--output_dir", default=None, 
                        help="Directory to save analysis results (plots). Defaults to 'memory_analysis_plots' inside run_dir.")
    # 新增参数以获取bash脚本中的配置值
    parser.add_argument("--threads", type=int, default=64, help="Number of threads used for title (e.g., TOTAL_CORES from bash).")
    parser.add_argument("--num_runs", type=int, default=5, help="Number of internal C++ runs (e.g., NUM_RUNS from bash).")
    parser.add_argument("--min_log", type=int, default=32, help="Log of input size (e.g., MIN_LOG from bash).")


    args = parser.parse_args()

    run_dir_path = args.run_dir
    if not run_dir_path:
        print("No run directory specified, attempting to find the latest...")
        run_dir_path = find_latest_run_dir("/home/xwang605/parallel-bench-suite/run/")
        if not run_dir_path:
            print("Error: Could not find a suitable run directory. Exiting.", file=sys.stderr)
            return 1
        print(f"Automatically selected run directory: {run_dir_path}\n")
    
    if not os.path.isdir(run_dir_path):
        print(f"Error: Provided run directory does not exist: {run_dir_path}", file=sys.stderr)
        return 1

    mem_reports_sub_dir = "mem_reports"
    mem_reports_dir_abs = os.path.join(run_dir_path, mem_reports_sub_dir)
    if not os.path.isdir(mem_reports_dir_abs):
        print(f"Error: Memory reports subdirectory '{mem_reports_sub_dir}' not found in '{run_dir_path}'", file=sys.stderr)
        return 1

    analysis_plot_dir = args.output_dir
    if not analysis_plot_dir:
        analysis_plot_dir = os.path.join(run_dir_path, "memory_analysis_plots")
    
    try:
        os.makedirs(analysis_plot_dir, exist_ok=True)
        print(f"Memory analysis plots will be saved in: {analysis_plot_dir}")
    except OSError as e:
        print(f"Error creating memory analysis output directory {analysis_plot_dir}: {e}", file=sys.stderr)
        return 1

    all_extracted_memory_data = defaultdict(lambda: defaultdict(dict))
    mem_filename_pattern = re.compile(r'^(benchmark_.*?)_([^_]+)_([^_]+)_no_perf_round_mem_report\.txt$')
    
    print(f"\nScanning memory reports directory: {mem_reports_dir_abs}")
    found_files_count = 0
    parsed_successfully_count = 0

    for filename in sorted(os.listdir(mem_reports_dir_abs)):
        match = mem_filename_pattern.match(filename)
        if match:
            found_files_count +=1
            algo_name_raw = match.group(1) 
            generator = match.group(2)
            data_type = match.group(3)
            config_key_tuple = (generator, data_type)
            filepath = os.path.join(mem_reports_dir_abs, filename)
            parsed_mem_metrics = parse_time_mem_report(filepath)
            
            if parsed_mem_metrics:
                all_extracted_memory_data[config_key_tuple][algo_name_raw] = parsed_mem_metrics
                parsed_successfully_count += 1
            else:
                print(f"Warning: Could not parse or no data in memory report: {filepath}", file=sys.stderr)
    
    if found_files_count == 0: print(f"Warning: No memory report files found matching pattern in {mem_reports_dir_abs}.", file=sys.stderr)
    elif parsed_successfully_count == 0 and found_files_count > 0 : print(f"Warning: Found {found_files_count} memory report files, but none parsed successfully.", file=sys.stderr)

    if not all_extracted_memory_data:
        print("No memory data loaded. Skipping plot generation.", file=sys.stderr)
        return 1
    
    if MATPLOTLIB_AVAILABLE:
        print("\n--- Generating Memory Comparison Plots ---")
        for config_key_to_plot, data_for_this_config in sorted(all_extracted_memory_data.items()):
            gen, dtype = config_key_to_plot
            print(f"  Generating memory plot for config: Generator={gen}, DataType={dtype}")
            # 传递从命令行参数获取的配置值用于标题
            generate_memory_plots_for_config(data_for_this_config, gen, dtype, analysis_plot_dir,
                                             title_threads=args.threads, 
                                             title_runs=args.num_runs, 
                                             title_log_size=args.min_log)
    else:
        print("\nPlot generation skipped as matplotlib is not available.")

    print("\nMemory analysis (parsing and plotting) complete.")
    return 0

if __name__ == "__main__":
    sys.exit(main())