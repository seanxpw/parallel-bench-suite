# perf_visualizer.py
import matplotlib
try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    print("Warning: matplotlib not found. Plot generation will be skipped. "
          "Install it using: pip install matplotlib", file=sys.stderr)
    MATPLOTLIB_AVAILABLE = False
import os
import sys
import numpy as np

# 定义我们想要绘制的关键指标及其属性
METRICS_TO_PLOT = {
    # --- Overall Performance ---
    "Average Wall Time (ms)": {"lower_is_better": True, "unit": "ms"},
    "IPC (Instructions Per Cycle)": {"lower_is_better": False, "unit": "IPC"},
    "Total Instructions (IC)": {"lower_is_better": True, "unit": "Count"},
    "Cycles": {"lower_is_better": True, "unit": "Count"},

    # --- Memory Bottleneck ---
    "Stalls L3 Miss (Cycles)": {"lower_is_better": True, "unit": "Count"},
    "Stalls L3 Miss / Total Cycles (%)": {"lower_is_better": True, "unit": "%", "requires": ["Stalls L3 Miss (Cycles)", "Cycles"]},

    # --- Memory Instructions (Absolute) ---
    "Memory Loads Retired": {"lower_is_better": True, "unit": "Count"},
    "Memory Stores Retired": {"lower_is_better": True, "unit": "Count"},

    # --- Cache Load Performance (Rates & Absolute Misses) ---
    "L1 Load Hit Rate": {"lower_is_better": False, "unit": "%"},
    "L1 Load Misses": {"lower_is_better": True, "unit": "Count"},
    "L2 Load Hit Rate (for loads reaching L2)": {"lower_is_better": False, "unit": "%"},
    "L2 Load Misses": {"lower_is_better": True, "unit": "Count"},
    "L3 Load Hit Rate (for loads reaching L3)": {"lower_is_better": False, "unit": "%"},
    "L3 Load Misses (Loads hitting DRAM)": {"lower_is_better": True, "unit": "Count"},

    # --- Cache Store Performance (Rates & Absolute Misses/Counts) ---
    "LLC Stores": {"lower_is_better": True, "unit": "Count"},
    "LLC Store Misses": {"lower_is_better": True, "unit": "Count"},
    # "LLC Store Miss Rate": {"lower_is_better": True, "unit": "%"}, # Optional

    # --- TLB & ICache Performance (Absolute Misses) ---
    "dTLB Load Misses": {"lower_is_better": True, "unit": "Count"},
    "dTLB Store Misses": {"lower_is_better": True, "unit": "Count"},
    "Total dTLB Misses": {"lower_is_better": True, "unit": "Count", "requires": ["dTLB Load Misses", "dTLB Store Misses"]},
    "iTLB Load Misses": {"lower_is_better": True, "unit": "Count"},
    "L1 ICache Load Misses": {"lower_is_better": True, "unit": "Count"},
}

TOTAL_THREAD_GRAPH = 64
TOTAL_RUNS_GRAPH = 5
TOTAL_MEM_GRAPH = 2**32

def generate_comparison_plots(all_algo_metrics, config_key, output_dir, baseline_algo_name):
    """
    为指定配置生成包含多个子图的对比条形图。
    """
    if not MATPLOTLIB_AVAILABLE:
        return

    generator, data_type = config_key
    plot_data = {
        algo: metrics for algo, metrics in all_algo_metrics.items()
        if algo != baseline_algo_name and metrics
    }
    if not plot_data:
        print(f"Info: No non-baseline algorithms with data found for config {config_key}. Skipping plot generation.")
        return

    algos_to_plot = sorted(plot_data.keys())
    num_algos = len(algos_to_plot)
    if num_algos == 0: return

    metrics_keys_ordered = list(METRICS_TO_PLOT.keys())
    num_metrics = len(metrics_keys_ordered)
    ncols = 4
    nrows = (num_metrics + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(18, nrows * 3.5), sharex=False)
    axes = axes.flatten()

    plot_idx = 0
    for metric_key in metrics_keys_ordered:
        if plot_idx >= len(axes): break

        ax = axes[plot_idx]
        props = METRICS_TO_PLOT.get(metric_key, {})

        plot_labels = []
        plot_values = []

        for algo in algos_to_plot:
            metric_data = plot_data.get(algo, {})
            value = None
            if metric_key == "Stalls L3 Miss / Total Cycles (%)":
                stalls = metric_data.get("Stalls L3 Miss (Cycles)")
                cycles = metric_data.get("Cycles")
                if isinstance(stalls, (int, float)) and isinstance(cycles, (int, float)) and cycles > 0:
                    value = (stalls / cycles) * 100
            elif metric_key == "Total dTLB Misses":
                 load_misses = metric_data.get("dTLB Load Misses")
                 store_misses = metric_data.get("dTLB Store Misses")
                 if isinstance(load_misses, (int, float)) and isinstance(store_misses, (int, float)):
                     value = load_misses + store_misses
            else:
                value = metric_data.get(metric_key)

            if value is not None and isinstance(value, (int, float)):
                plot_labels.append(algo.replace('benchmark_', ''))
                plot_values.append(value)

        if not plot_labels:
            ax.set_title(f"{metric_key}\n(No Valid Data)", fontsize=9)
            ax.tick_params(axis='both', which='both', bottom=False, top=False, left=False, right=False, labelbottom=False, labelleft=False)
            plot_idx += 1
            continue

        try:
            colors = plt.get_cmap('viridis', num_algos)(range(num_algos))
        except ValueError:
             colors = plt.get_cmap('viridis')(0.5) if num_algos == 1 else plt.get_cmap('viridis')(np.linspace(0, 1, num_algos))
        bars = ax.bar(plot_labels, plot_values, color=colors)

        unit = props.get("unit", "")
        title = metric_key.replace(" (for loads reaching L2)", "").replace(" (for loads reaching L3)", "").replace(" (Loads hitting DRAM)", "")
        ax.set_title(title, fontsize=9, wrap=True)
        ax.set_ylabel(unit if unit != "Count" else "", fontsize=8)

        # !!!!! 修正 tick_params 调用 !!!!!
        # 移除 ha='right'
        ax.tick_params(axis='x', rotation=45, labelsize=7)
        # !!!!! --------------------- !!!!!
        ax.tick_params(axis='y', labelsize=7) # 统一Y轴标签大小
        ax.grid(axis='y', linestyle='--', alpha=0.6)

        if any(abs(v) > 1e6 for v in plot_values):
             ax.ticklabel_format(style='sci', axis='y', scilimits=(0,0), useMathText=True)

        lower_is_better = props.get("lower_is_better", False)
        performance_arrow = "↓ Better" if lower_is_better else "↑ Better"
        ax.text(0.98, 0.98, performance_arrow, transform=ax.transAxes, fontsize=8, # 减小字体
                verticalalignment='top', horizontalalignment='right',
                bbox=dict(boxstyle='round,pad=0.2', fc='#E8F5E9', alpha=0.9))

        if plot_values:
             max_val = max(plot_values) if plot_values else 0
             min_val = min(plot_values) if plot_values else 0
             current_ylim_bottom = 0 if min_val >= 0 else min_val * 1.1
             if unit == "%":
                  ymax = min(max_val * 1.15, 105)
                  ymin = max(min_val - 5, 0) if min_val > 0 else current_ylim_bottom
             else:
                  ymax = max_val * 1.20
                  ymin = current_ylim_bottom
             ax.set_ylim(bottom=ymin, top=ymax)

        plot_idx += 1

    for i in range(plot_idx, len(axes)):
        axes[i].set_visible(False)

    fig.suptitle(f'Algorithm Comparison: Generator={generator}, DataType={data_type}, Threads={TOTAL_THREAD_GRAPH}, RoundsCounted={TOTAL_RUNS_GRAPH} InputMemorySize={TOTAL_MEM_GRAPH} Bytes ', fontsize=14, y=1.0)
    plt.tight_layout(pad=1.5, rect=[0, 0.03, 1, 0.98])

    output_filename = os.path.join(output_dir, f"plot_summary_{generator}_{data_type}.png")
    try:
        fig.savefig(output_filename, dpi=150, bbox_inches='tight')
        print(f"  Plot saved: {output_filename}")
    except Exception as e:
        print(f"Error saving plot {output_filename}: {e}", file=sys.stderr)

    plt.close(fig)