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

    # --- Branch Prediction ---
    "Branch Misses": {"lower_is_better": True, "unit": "Count"}, # 新增

    # --- TLB & ICache Performance (Absolute Misses) ---
    "dTLB Load Misses": {"lower_is_better": True, "unit": "Count"},
    "dTLB Store Misses": {"lower_is_better": True, "unit": "Count"},
    "Total dTLB Misses": {"lower_is_better": True, "unit": "Count", "requires": ["dTLB Load Misses", "dTLB Store Misses"]},
    "iTLB Load Misses": {"lower_is_better": True, "unit": "Count"},
    "L1 ICache Load Misses": {"lower_is_better": True, "unit": "Count"},

    # --- OS Interaction / System Level --- (新增指标可以放在这里)
    "Context Switches": {"lower_is_better": True, "unit": "Count"}, # 新增
    "Page Faults": {"lower_is_better": True, "unit": "Count"},      # 新增
}

# 这些全局常量用于图形的标题，从你的脚本中保留
TOTAL_THREAD_GRAPH = 48 # 你的脚本中是 -t ${TOTAL_CORES}，这里假设一个具体值或脚本会动态传入
TOTAL_RUNS_GRAPH = 5    # 你的脚本中 NUM_RUNS=5
TOTAL_MEM_GRAPH = 2**32 # 你的脚本中 MIN_LOG=32, MAX_LOG=32, 2^32 是一个大小

# generate_comparison_plots 函数 (除了 METRICS_TO_PLOT 的更新外，核心逻辑保持不变)
def generate_comparison_plots(all_algo_metrics, config_key, output_dir, baseline_algo_name):
    """
    为指定配置生成包含多个子图的对比条形图。
    all_algo_metrics 的结构是: {algo_name: {metric_name: value}}
    """
    if not MATPLOTLIB_AVAILABLE:
        print("Info: Matplotlib not available. Skipping plot generation.", file=sys.stderr)
        return

    generator, data_type = config_key
    
    # 过滤掉基线算法和没有数据的算法
    plot_data = {
        algo: metrics for algo, metrics in all_algo_metrics.items()
        if algo != baseline_algo_name and metrics and isinstance(metrics, dict) # 确保 metrics 是字典且非空
    }

    if not plot_data:
        print(f"Info: No non-baseline algorithms with data found for config {config_key}. Skipping plot generation.")
        return

    algos_to_plot = sorted(plot_data.keys())
    num_algos = len(algos_to_plot)
    if num_algos == 0: return # 以防万一

    # 使用 METRICS_TO_PLOT 中的键作为顺序
    metrics_keys_ordered = [key for key in METRICS_TO_PLOT.keys() if key != "Stalls L3 Miss / Total Cycles (%)" and key != "Total dTLB Misses"]
    # 将复合指标放在最后，或者按照你期望的顺序
    if "Stalls L3 Miss / Total Cycles (%)" in METRICS_TO_PLOT:
        metrics_keys_ordered.append("Stalls L3 Miss / Total Cycles (%)")
    if "Total dTLB Misses" in METRICS_TO_PLOT:
        metrics_keys_ordered.append("Total dTLB Misses")
    
    num_metrics_to_actually_plot = 0
    # 预先检查有多少指标实际有数据，以避免创建过多空图
    temp_plotable_metrics = []
    for metric_key in metrics_keys_ordered:
        has_data_for_metric = False
        for algo in algos_to_plot:
            metric_data = plot_data.get(algo, {})
            value = None
            if METRICS_TO_PLOT.get(metric_key, {}).get("requires"): # 复合指标
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
            else: # 直接指标
                value = metric_data.get(metric_key)
            
            if value is not None and isinstance(value, (int, float)) and not np.isnan(value):
                has_data_for_metric = True
                break
        if has_data_for_metric:
            temp_plotable_metrics.append(metric_key)
    
    metrics_keys_ordered = temp_plotable_metrics # 只使用有数据的指标
    num_metrics = len(metrics_keys_ordered)
    if num_metrics == 0:
        print(f"Info: No plottable metrics with data for config {config_key}. Skipping plot generation.")
        return

    ncols = 4 # 每行4个子图
    nrows = (num_metrics + ncols - 1) // ncols # 计算需要的行数
    
    fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(18, nrows * 3.7), squeeze=False) # figsize调整, squeeze=False确保axes总是2D
    axes = axes.flatten() # 将2D数组展平为1D，方便索引

    plot_idx = 0
    for metric_key in metrics_keys_ordered: # 使用筛选和排序后的键
        if plot_idx >= len(axes): break # 不应发生，因为nrows是根据num_metrics计算的

        ax = axes[plot_idx]
        props = METRICS_TO_PLOT.get(metric_key, {}) # 获取指标属性

        plot_labels = []
        plot_values = []
        
        # 为当前指标收集所有算法的数据
        for algo in algos_to_plot: # algos_to_plot 已排序
            metric_data = plot_data.get(algo, {})
            value = None
            
            # 处理需要计算的复合指标
            if metric_key == "Stalls L3 Miss / Total Cycles (%)":
                stalls = metric_data.get("Stalls L3 Miss (Cycles)")
                cycles = metric_data.get("Cycles")
                if isinstance(stalls, (int, float)) and isinstance(cycles, (int, float)) and cycles > 0 and not (np.isnan(stalls) or np.isnan(cycles)):
                    value = (stalls / cycles) * 100
            elif metric_key == "Total dTLB Misses":
                load_misses = metric_data.get("dTLB Load Misses")
                store_misses = metric_data.get("dTLB Store Misses")
                if isinstance(load_misses, (int, float)) and isinstance(store_misses, (int, float)) and not (np.isnan(load_misses) or np.isnan(store_misses)):
                    value = load_misses + store_misses
            else: #直接获取指标值
                value = metric_data.get(metric_key)

            if value is not None and isinstance(value, (int, float)) and not np.isnan(value): # 确保值有效
                plot_labels.append(algo.replace('benchmark_', '')) # 简化算法名称
                plot_values.append(value)
            # else:
                # 如果某个算法缺少这个指标，它就不会出现在这个子图中
                # print(f"Debug: Algo {algo} missing value for {metric_key}")


        if not plot_labels: # 如果这个指标对所有算法都没有有效数据
            ax.set_title(f"{metric_key}\n(No Valid Data)", fontsize=9)
            ax.tick_params(axis='both', which='both', bottom=False, top=False, left=False, right=False, labelbottom=False, labelleft=False)
            # ax.set_visible(False) # 或者直接隐藏这个空子图
            plot_idx += 1
            continue

        # --- 核心绘图逻辑 (尽量保持与你原版本一致) ---
        try: # 尝试获取颜色，处理 num_algos=1 的情况
            if num_algos == 1:
                colors = [plt.get_cmap('viridis')(0.5)] # 单个算法给一个固定颜色
            else:
                colors = plt.get_cmap('viridis')(np.linspace(0, 1, num_algos))
        except Exception:
            colors = 'skyblue' # 最终回退

        bars = ax.bar(plot_labels, plot_values, color=colors)

        unit = props.get("unit", "")
        # 简化标题，移除括号内的额外说明，使其更简洁
        title = metric_key.split(" (")[0] 
        ax.set_title(title, fontsize=9, wrap=True)
        ax.set_ylabel(unit if unit not in ["Count", "%"] else "", fontsize=8) # 对于Count和%，Y轴标签可以省略或用特定方式处理
        if unit == "%":
             ax.set_ylabel("%", fontsize=8)


        # X轴标签旋转 (根据你的注释，移除了 ha='right')
        ax.tick_params(axis='x', rotation=45, labelsize=7) 
        ax.tick_params(axis='y', labelsize=7)
        ax.grid(axis='y', linestyle='--', alpha=0.6)

        # 科学计数法格式化Y轴
        if any(abs(v) >= 1e6 for v in plot_values if isinstance(v, (int,float))): # 仅当有大数值时
            ax.ticklabel_format(style='sci', axis='y', scilimits=(0,0), useMathText=True)
        
        # “越低越好”/“越高越好”的箭头指示
        lower_is_better = props.get("lower_is_better", False) # 默认为越高越好
        performance_arrow = "↓ Better" if lower_is_better else "↑ Better"
        ax.text(0.98, 0.98, performance_arrow, transform=ax.transAxes, fontsize=7, # 字体再小一点
                verticalalignment='top', horizontalalignment='right',
                bbox=dict(boxstyle='round,pad=0.15', fc='#E8F5E9', alpha=0.8)) # pad小一点

        # 动态调整Y轴范围
        if plot_values: #确保plot_values非空
            # 过滤掉可能的非数值类型，以防万一
            numeric_plot_values = [v for v in plot_values if isinstance(v, (int, float))]
            if numeric_plot_values:
                max_val = max(numeric_plot_values)
                min_val = min(numeric_plot_values)
                
                # 设置Y轴下限
                current_ylim_bottom = 0
                if min_val < 0: # 如果有负值
                    current_ylim_bottom = min_val * 1.15
                elif min_val > 0 : # 如果所有值都大于0，可以稍微留点空隙或从0开始
                    current_ylim_bottom = 0 # min(0, min_val * 0.85) 
                
                # 设置Y轴上限
                current_ylim_top = max_val
                if max_val > 0:
                    current_ylim_top = max_val * 1.15
                elif max_val < 0: # 如果所有值都是负数
                     current_ylim_top = max_val * 0.85
                else: # max_val is 0
                     current_ylim_top = 0.1 # 避免0上限

                if unit == "%": # 百分比特殊处理
                    current_ylim_top = min(current_ylim_top, 105) # 上限不超过105%
                    current_ylim_bottom = max(current_ylim_bottom, -5 if min_val < 0 else 0) # 下限不低于-5%或0

                # 避免上限和下限相同导致绘图问题
                if abs(current_ylim_top - current_ylim_bottom) < 1e-9: # 如果非常接近
                    current_ylim_top += 0.1 # 稍微增加一点范围

                ax.set_ylim(bottom=current_ylim_bottom, top=current_ylim_top)

        plot_idx += 1

    # 隐藏任何未使用的子图轴
    for i in range(plot_idx, len(axes)):
        axes[i].set_visible(False)

    # 设置整个图的标题
    # 从你的脚本中获取这些常量，如果它们是动态的，则需要传递给此函数
    # 为简单起见，这里使用你在脚本中定义的全局常量（如果适用）
    # 或者你可以将这些值作为参数传递给 generate_comparison_plots
    fig_title = (f'Algorithm Comparison: Generator={generator}, DataType={data_type}\n'
                 f'(Threads={TOTAL_THREAD_GRAPH}, Internal Runs={TOTAL_RUNS_GRAPH}, Input Size=2^{MIN_LOG})') # MIN_LOG 假设与MAX_LOG相同

    fig.suptitle(fig_title, fontsize=14, y=0.99) # y值调整以避免与子图标题重叠
    
    # 调整布局以防止标签重叠
    plt.tight_layout(pad=2.0, h_pad=2.5, w_pad=1.5, rect=[0, 0.03, 1, 0.95]) # 调整rect和pad

    # 保存图像
    output_filename = os.path.join(output_dir, f"plot_summary_{generator}_{data_type}.png")
    try:
        fig.savefig(output_filename, dpi=150) # bbox_inches='tight' 移到 plt.tight_layout 中通过 rect 控制
        print(f"  Plot saved: {output_filename}")
    except Exception as e:
        print(f"Error saving plot {output_filename}: {e}", file=sys.stderr)

    plt.close(fig) # 关闭图像以释放内存