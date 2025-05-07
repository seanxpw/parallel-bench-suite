# feature_analyzer.py
import pandas as pd
import numpy as np
import sys
import os # For path joining

# 检查依赖库
try:
    from sklearn.ensemble import RandomForestRegressor
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


# 定义用于模型训练的特征列名 (来自 calculate_metrics 的输出键, 无 "Adjusted")
# 选择那些基础的计数值，避免使用比率或复合指标引入过多相关性
FEATURE_KEYS_FOR_MODEL = [
    "Cycles",
    "Total Instructions (IC)",
    "Memory Loads Retired",
    "Memory Stores Retired",
    "L1 Load Hits",             # Note: Including Hits AND Misses might be redundant
    "L1 Load Misses",
    "L1 Fill Buffer Hits (Loads)",
    "L1D Cache Stores",
    # "L1D Cache Store Misses", # Not supported/always 0
    "L2 Load Hits",
    "L2 Load Misses",
    "L3 Load Hits",
    "L3 Load Misses (Loads hitting DRAM)",
    "LLC Stores",
    "LLC Store Misses",
    "L1 ICache Load Misses",
    "dTLB Load Misses",
    "dTLB Store Misses",
    "iTLB Load Misses",
    "Offcore Reqs Demand Data Rd",
    "Stalls L3 Miss (Cycles)",
    # "Load Latency >128 cycles" # Often 0
]

TARGET_KEY = "Average Wall Time (ms)"

def perform_feature_importance(all_metrics_data, output_dir, baseline_algo_name):
    """
    使用 RandomForestRegressor 执行特征重要性分析。

    Args:
        all_metrics_data (dict): 结构为 {(gen, type): {algo: {metric: value}}} 的数据
        output_dir (str): 保存特征重要性图的目录
        baseline_algo_name (str): 基线算法名称，用于从分析中排除
    """
    if not SKLEARN_AVAILABLE:
        print("\nFeature importance analysis skipped: scikit-learn not available.")
        return

    print("\n--- Performing Feature Importance Analysis for Wall Time ---")

    data_for_df = []
    # 展平数据，排除基线和缺少目标/特征值的运行
    for config_key, algo_metrics in all_metrics_data.items():
        gen, dtype = config_key
        for algo, metrics in algo_metrics.items():
            # 排除基线算法
            if algo == baseline_algo_name:
                continue

            # 确保目标变量存在且是数字
            target_value = metrics.get(TARGET_KEY)
            if target_value is None or not isinstance(target_value, (int, float)):
                # print(f"Debug: Skipping {algo} {config_key}: Missing target value {TARGET_KEY}")
                continue

            row = {'Algorithm': algo, 'Generator': gen, 'DataType': dtype, TARGET_KEY: target_value}
            valid_features = True
            for feature in FEATURE_KEYS_FOR_MODEL:
                feature_value = metrics.get(feature)
                # 确保特征存在且是数字
                if feature_value is None or not isinstance(feature_value, (int, float)):
                     # 如果特征值是 "N/A" 或 None，则此行数据无效
                     # print(f"Debug: Skipping {algo} {config_key}: Missing/Invalid feature value {feature}: {feature_value}")
                     valid_features = False
                     break
                row[feature] = feature_value

            if valid_features:
                data_for_df.append(row)

    if len(data_for_df) < 2: # Need at least 2 samples to train a model
        print(f"  Warning: Insufficient valid data ({len(data_for_df)} samples) for feature importance analysis after filtering.", file=sys.stderr)
        return

    df = pd.DataFrame(data_for_df)

    # 分离特征 (X) 和目标 (y)
    # 确保只选择模型需要的特征列
    feature_columns = [col for col in FEATURE_KEYS_FOR_MODEL if col in df.columns]
    if not feature_columns:
         print("  Error: No valid feature columns found in the prepared data.", file=sys.stderr)
         return
         
    X = df[feature_columns]
    y = df[TARGET_KEY]

    if X.empty or y.empty or X.shape[0] != y.shape[0]:
        print("  Error: Feature matrix (X) or target vector (y) is empty or mismatched after processing.", file=sys.stderr)
        return
        
    # 处理潜在的 NaN 或 Inf 值 (虽然前面过滤了None/N/A，以防万一)
    X = X.replace([np.inf, -np.inf], np.nan)
    if X.isnull().values.any():
        print("  Warning: NaN values found in feature data. Attempting imputation with mean.", file=sys.stderr)
        # Simple imputation with mean, consider more sophisticated methods if needed
        from sklearn.impute import SimpleImputer
        imputer = SimpleImputer(missing_values=np.nan, strategy='mean')
        X = imputer.fit_transform(X)
        # Convert back to DataFrame to keep column names
        X = pd.DataFrame(X, columns=feature_columns)


    # 训练 RandomForestRegressor 模型
    try:
        # 使用更多的树并设置最小样本叶节点数来轻微正则化
        forest = RandomForestRegressor(n_estimators=200, random_state=42, n_jobs=-1, min_samples_leaf=2)
        forest.fit(X, y)
    except Exception as e:
        print(f"  Error training RandomForest model: {e}", file=sys.stderr)
        return

    # 获取特征重要性
    importances = forest.feature_importances_
    feature_labels = X.columns # Use columns from potentially imputed data
    indices = np.argsort(importances)[::-1] # 降序排序

    print("\n  Feature Importance Scores (Top 20):")
    num_features_to_display = min(20, len(feature_labels))
    # 将重要性写入文本文件
    importance_filename = os.path.join(output_dir, "feature_importance_scores.txt")
    try:
         with open(importance_filename, 'w', encoding='utf-8') as f_imp:
              f_imp.write("Feature Importance Scores for Predicting Wall Time\n")
              f_imp.write("----------------------------------------------------\n")
              for i in range(len(feature_labels)): # Write all scores
                   rank = i + 1
                   feat_index = indices[i]
                   line = f"{rank:2d}) {feature_labels[feat_index]:<45} {importances[feat_index]:.6f}\n"
                   if i < num_features_to_display:
                        print(f"    {line.strip()}") # Print top N to console
                   f_imp.write(line)
         print(f"\n  Full feature importance scores saved to: {importance_filename}")
    except IOError as e:
         print(f"  Error writing feature importance scores to file: {e}", file=sys.stderr)


    # --- 可视化 Top N 特征重要性 ---
    if not MATPLOTLIB_AVAILABLE:
         print("  Skipping feature importance plot: matplotlib not available.")
         return

    try:
        plt.figure(figsize=(12, 9)) # 调整尺寸以容纳标签
        plt.title("Top {} Feature Importances for Predicting Wall Time".format(num_features_to_display), fontsize=16)
        plt.ylabel("Importance Score (Gini Importance / Mean Decrease in Impurity)", fontsize=12) # 更准确的标签

        # 获取颜色映射
        try:
             colors = plt.get_cmap('viridis')(importances[indices[:num_features_to_display]] / (importances[indices[0]] + 1e-9)) # Normalize by max
        except:
             colors = 'skyblue' # Fallback color

        plt.bar(range(num_features_to_display),
                importances[indices[:num_features_to_display]],
                color=colors,
                align='center')

        plt.xticks(range(num_features_to_display),
                   feature_labels[indices[:num_features_to_display]],
                   rotation=70, # 调整旋转角度
                   ha='right', # 确保右对齐
                   fontsize=9)
        plt.yticks(fontsize=9)
        plt.xlim([-1, num_features_to_display])
        plt.grid(axis='y', linestyle='--', alpha=0.6)
        plt.tight_layout() # Adjust layout

        # 保存绘图
        plot_filename = os.path.join(output_dir, "feature_importance_wall_time.png")
        plt.savefig(plot_filename, dpi=150)
        print(f"  Feature importance plot saved to: {plot_filename}")
        plt.close()

    except Exception as e:
        print(f"  Error generating feature importance plot: {e}", file=sys.stderr)