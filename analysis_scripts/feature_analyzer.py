# feature_analyzer.py
import pandas as pd
import numpy as np
import sys
import os # For path joining


try:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.impute import SimpleImputer # 确保 SimpleImputer 已导入
    SKLEARN_AVAILABLE = True
except ImportError:
    print("Warning: scikit-learn not found. Feature importance analysis will be skipped. "
          "Install it using: pip install scikit-learn", file=sys.stderr)
    SKLEARN_AVAILABLE = False

try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    print("Warning: matplotlib not found. Feature importance plot will be skipped. "
          "Install it using: pip install matplotlib", file=sys.stderr)
    MATPLOTLIB_AVAILABLE = False


# 定义用于模型训练的特征列名 (这些键名应该与 perf_analyzer.py 中 calculate_metrics 函数输出的字典的键一致)
FEATURE_KEYS_FOR_MODEL = [
    # 核心与指令 (来自 GROUP1, 经过基线调整)
    "Cycles",
    "Total Instructions (IC)",
    # "IPC (Instructions Per Cycle)", # 这是一个派生比率，可以考虑加入

    # 内存访问 (来自 GROUP1, 经过基线调整)
    "Memory Loads Retired",
    "Memory Stores Retired",
    # "Memory Access Instructions", # 这是 Loads + Stores 的和，可能冗余

    # L1 加载性能 (来自 GROUP2, 经过基线调整)
    "L1 Load Hits",
    "L1 Load Misses",
    # "L1 Load Hit Rate", # 派生比率
    "L1 Fill Buffer Hits (Loads)",

    # L1 存储性能 (来自 GROUP3, 经过基线调整)
    "L1D Cache Stores",
    # "L1D Cache Store Misses", # 你注释掉了，如果硬件不支持或总是0，则不加
    # "L1D Cache Store Miss Rate", # 派生比率

    # L2 加载性能 (来自 GROUP2, 经过基线调整)
    "L2 Load Hits",
    "L2 Load Misses",
    # "L2 Load Hit Rate (for loads reaching L2)", # 派生比率

    # L3 加载性能 (来自 GROUP1 和 GROUP3, 经过基线调整)
    "L3 Load Hits",                             # 来自 GROUP3 (mem_load_retired.l3_hit:u)
    "L3 Load Misses (Loads hitting DRAM)",      # 来自 GROUP1 (mem_load_retired.l3_miss:u)
    # "L3 Load Hit Rate (for loads reaching L3)", # 派生比率

    # LLC 存储性能 (来自 GROUP3, 经过基线调整)
    "LLC Stores",
    "LLC Store Misses",
    # "LLC Store Miss Rate", # 派生比率

    # 分支预测 (来自 GROUP3, 经过基线调整) - 新增
    "Branch Misses",
    # "Branch Miss Rate", # 如果收集了 branch-instructions 并计算了比率，可以加入

    # ICache & TLB (来自 GROUP4, 经过基线调整)
    "L1 ICache Load Misses",
    "dTLB Load Misses",
    "dTLB Store Misses",
    "iTLB Load Misses",

    # 系统级事件 (来自 GROUP4, 经过基线调整) - 新增
    "Context Switches",
    "Page Faults",

    # 其他重要但可能未被收集的事件 (需要确保你的 bash 脚本会收集它们，否则它们的值会是 NaN 或 0)
    # 如果这些事件没有被你的bash脚本收集，那么它们作为特征的意义不大，除非你打算总是估算它们。
    # "Offcore Reqs Demand Data Rd", # 原始事件: offcore_requests.demand_data_rd:u (目前不在任何GROUP)
    "Stalls L3 Miss (Cycles)",       # 原始事件: cycle_activity.stalls_l3_miss:u (在 GROUP1)
    # "Load Latency >128 cycles",   # 原始事件: mem_trans_retired.load_latency_gt_128:u (目前不在任何GROUP)
]

TARGET_KEY = "Average Wall Time (ms)" # 这个来自 wall_time_parser.py 的输出

# perform_feature_importance 函数 (与你提供的版本基本一致)
# 它的输入 all_metrics_data 预期是一个列表的字典，每个字典是一行数据
# (这与 analyze_main.py 中 all_metrics_for_ml_and_plots 的扁平化处理后的结构一致)
# 修改函数参数名以更准确地反映其接收的嵌套字典结构
def perform_feature_importance(nested_metrics_data, output_dir, baseline_algo_name_to_exclude):
    """
    使用 RandomForestRegressor 执行特征重要性分析。

    Args:
        nested_metrics_data (dict): 结构为 {(gen, type): {algo: {metric_key: value}}} 的数据
        output_dir (str): 保存特征重要性图的目录
        baseline_algo_name_to_exclude (str): 要从分析中排除的算法名称
    """
    if not SKLEARN_AVAILABLE:
        print("\nFeature importance analysis skipped: scikit-learn not available.")
        return

    print("\n--- Performing Feature Importance Analysis for Wall Time ---")

    data_for_df = [] # 用于构建 DataFrame 的扁平化列表
    # 展平数据，排除基线和缺少目标/特征值的运行
    # 使用正确的参数名 nested_metrics_data
    for config_key, algo_metrics_map in nested_metrics_data.items():
        gen, dtype = config_key
        for algo, metrics_dict in algo_metrics_map.items():
            # 排除基线算法（或指定的要排除的算法）
            if algo == baseline_algo_name_to_exclude:
                continue

            target_value = metrics_dict.get(TARGET_KEY)
            # 确保目标值有效
            if target_value is None or not isinstance(target_value, (int, float)) or np.isnan(target_value):
                # print(f"Debug: Skipping {algo} ({gen}, {dtype}): Missing or invalid target value for {TARGET_KEY}: {target_value}")
                continue

            row = {'Algorithm': algo, 'Generator': gen, 'DataType': dtype, TARGET_KEY: target_value}
            # 填充特征
            for feature_key in FEATURE_KEYS_FOR_MODEL:
                feature_value = metrics_dict.get(feature_key)
                # 如果特征缺失或无效，填充为 NaN，后续由 SimpleImputer 处理
                if feature_value is None or not isinstance(feature_value, (int, float)) or np.isnan(feature_value) or str(feature_value) == "N/A":
                    row[feature_key] = np.nan
                else:
                    row[feature_key] = feature_value
            
            data_for_df.append(row)

    if len(data_for_df) < 2: # 模型训练至少需要2个样本
        print(f"  Warning: Insufficient valid data rows ({len(data_for_df)}) for feature importance analysis after initial filtering.", file=sys.stderr)
        return

    df = pd.DataFrame(data_for_df)

    # 确保 FEATURE_KEYS_FOR_MODEL 中的所有列都存在于 DataFrame 中
    # 如果列在所有数据行中都缺失，df[feature_key] 会在选择 X 时引发 KeyError
    # 所以，在创建 X 之前，最好先筛选实际存在的特征列
    
    actual_feature_columns_in_df = [col for col in FEATURE_KEYS_FOR_MODEL if col in df.columns]
    if not actual_feature_columns_in_df:
        print("  Error: No features listed in FEATURE_KEYS_FOR_MODEL were found in the processed data.", file=sys.stderr)
        return

    X = df[actual_feature_columns_in_df] # 只选择实际存在的特征列
    y = df[TARGET_KEY]

    if X.empty or y.empty or X.shape[0] != y.shape[0] or X.shape[1] == 0 :
        print("  Error: Feature matrix (X) or target vector (y) is empty, has zero features, or mismatched after processing.", file=sys.stderr)
        return
        
    # 处理 NaN 值 (使用 SimpleImputer)
    if X.isnull().values.any():
        print("  Info: NaN values found in feature data. Applying SimpleImputer with mean strategy.", file=sys.stderr)
        # SimpleImputer 只能处理数值列
        numeric_cols = X.select_dtypes(include=np.number).columns
        if not numeric_cols.empty:
            imputer = SimpleImputer(missing_values=np.nan, strategy='mean')
            X_imputed_numeric = imputer.fit_transform(X[numeric_cols])
            X_imputed_numeric_df = pd.DataFrame(X_imputed_numeric, columns=numeric_cols, index=X.index)
            
            # 如果原始X中有非数值列（理论上不应该在特征里），需要考虑如何处理
            # 为简单起见，这里假设 FEATURE_KEYS_FOR_MODEL 只包含最终应为数值的特征
            X = X_imputed_numeric_df
            # 重新确保 X 只包含我们期望的特征，并且顺序一致（如果 SimpleImputer 改变了顺序）
            # X = X[actual_feature_columns_in_df] # 确保列和顺序
        else:
            print("  Warning: No numeric columns with NaN values found to impute. If NaNs persist in non-numeric features, model training might fail.", file=sys.stderr)
            if X.isnull().values.any(): # 再次检查是否还有NaN（可能在非数值列中）
                 print("  Error: NaN values persist in X after attempting imputation, possibly in non-numeric columns. Cannot train model.", file=sys.stderr)
                 return



    # 训练 RandomForestRegressor 模型 (与你提供的代码一致)
    try:
        forest = RandomForestRegressor(n_estimators=200, random_state=42, n_jobs=-1, min_samples_leaf=2)
        forest.fit(X, y)
    except Exception as e:
        print(f"  Error training RandomForest model: {e}", file=sys.stderr)
        return

    # 获取特征重要性 (与你提供的代码一致)
    importances = forest.feature_importances_
    feature_labels_from_model = X.columns 
    indices = np.argsort(importances)[::-1]

    print("\n  Feature Importance Scores (Top 20):")
    num_features_to_display = min(20, len(feature_labels_from_model))
    importance_filename = os.path.join(output_dir, "feature_importance_scores.txt")
    try:
        with open(importance_filename, 'w', encoding='utf-8') as f_imp:
            f_imp.write("Feature Importance Scores for Predicting Wall Time\n")
            f_imp.write("----------------------------------------------------\n")
            for i in range(len(feature_labels_from_model)):
                rank = i + 1
                feat_index_in_sorted = indices[i]
                line = f"{rank:2d}) {feature_labels_from_model[feat_index_in_sorted]:<45} {importances[feat_index_in_sorted]:.6f}\n"
                if i < num_features_to_display:
                    print(f"    {line.strip()}")
                f_imp.write(line)
        print(f"\n  Full feature importance scores saved to: {importance_filename}")
    except IOError as e:
        print(f"  Error writing feature importance scores to file: {e}", file=sys.stderr)

    # 可视化 (与你提供的代码一致)
    if not MATPLOTLIB_AVAILABLE:
        print("  Skipping feature importance plot: matplotlib not available.")
        return
    try:
        plt.figure(figsize=(12, max(9, num_features_to_display * 0.4))) # 动态调整高度
        plt.title(f"Top {num_features_to_display} Feature Importances for Predicting Wall Time", fontsize=16)
        plt.ylabel("Importance Score", fontsize=12) # 简化标签

        bar_colors = 'skyblue'
        if MATPLOTLIB_AVAILABLE : # 再次检查，虽然上面有return，但更安全
            try: # 尝试使用颜色映射
                cmap = plt.get_cmap('viridis') # 或者 'plasma', 'inferno', 'magma', 'cividis'
                # 归一化重要性得分以用于颜色映射
                norm_importances = importances[indices[:num_features_to_display]]
                if len(norm_importances) > 0 and norm_importances.max() > 0 :
                     norm_importances = norm_importances / norm_importances.max()
                else: # 处理所有重要性为0或空的情况
                     norm_importances = np.zeros_like(norm_importances)

                bar_colors = cmap(norm_importances)
            except Exception as color_exc:
                print(f"Debug: Colormap failed - {color_exc}", file=sys.stderr)
                pass # fallback to skyblue

        plt.bar(range(num_features_to_display),
                importances[indices[:num_features_to_display]],
                color=bar_colors,
                align='center')
        plt.xticks(range(num_features_to_display),
                   [feature_labels_from_model[i] for i in indices[:num_features_to_display]], # 使用排序后的标签
                   rotation=70, 
                   ha='right', 
                   fontsize=9)
        plt.yticks(fontsize=9)
        plt.xlim([-1, num_features_to_display])
        plt.grid(axis='y', linestyle='--', alpha=0.6)
        plt.tight_layout() 
        plot_filename = os.path.join(output_dir, "feature_importance_wall_time.png")
        plt.savefig(plot_filename, dpi=150)
        print(f"  Feature importance plot saved to: {plot_filename}")
        plt.close()
    except Exception as e:
        print(f"  Error generating feature importance plot: {e}", file=sys.stderr)