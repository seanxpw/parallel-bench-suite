# perf_analyzer.py
from collections import defaultdict
# 导入来自 perf_parser 的辅助函数
from perf_parser import get_event_value # 这个函数会使用 perf_parser.py 中的 KEY_EVENT_MAPPINGS

def calculate_metrics(current_stats_merged, baseline_stats_merged):
    """
    计算性能指标 (已进行基线校准)。
    输入是已经合并了所有 Group 数据的字典 (键为原始perf事件名)。
    输出的字典键为描述性名称。
    """
    adjusted_stats = defaultdict(int)
    # 合并当前运行和基线运行中的所有事件名，以确保两者中的事件都被处理
    all_event_names_in_merged = set(current_stats_merged.keys()) | set(baseline_stats_merged.keys())

    for event_name in all_event_names_in_merged:
        adjusted_stats[event_name] = current_stats_merged.get(event_name, 0) - baseline_stats_merged.get(event_name, 0)

    metrics = {} # 用于存储最终计算出的、带有描述性键名的指标

    # --- Cycles, Instructions, IPC ---
    adj_cycles = get_event_value(adjusted_stats, "CYCLES")      # 使用通用键 "CYCLES"
    adj_ic = get_event_value(adjusted_stats, "IC")              # 使用通用键 "IC"
    metrics["Cycles"] = adj_cycles
    metrics["Total Instructions (IC)"] = adj_ic
    if adj_cycles > 0:
        metrics["IPC (Instructions Per Cycle)"] = adj_ic / adj_cycles
    else:
        metrics["IPC (Instructions Per Cycle)"] = "N/A"

    # --- Memory Access Instructions ---
    adj_mem_loads = get_event_value(adjusted_stats, "MEM_LOADS_RETIRED")
    adj_mem_stores = get_event_value(adjusted_stats, "MEM_STORES_RETIRED")
    metrics["Memory Access Instructions"] = adj_mem_loads + adj_mem_stores
    metrics["Memory Loads Retired"] = adj_mem_loads
    metrics["Memory Stores Retired"] = adj_mem_stores

    # --- L1 Load Performance ---
    adj_l1_hits_load = get_event_value(adjusted_stats, "MEM_LOAD_RETIRED_L1_HIT")
    adj_l1_misses_load = get_event_value(adjusted_stats, "MEM_LOAD_RETIRED_L1_MISS")
    adj_l1_accesses_load = adj_l1_hits_load + adj_l1_misses_load
    if adj_l1_accesses_load > 0:
        metrics["L1 Load Hit Rate"] = (adj_l1_hits_load / adj_l1_accesses_load) * 100
    else:
        metrics["L1 Load Hit Rate"] = "N/A"
    metrics["L1 Load Hits"] = adj_l1_hits_load
    metrics["L1 Load Misses"] = adj_l1_misses_load
    metrics["L1 Fill Buffer Hits (Loads)"] = get_event_value(adjusted_stats, "MEM_LOAD_RETIRED_FB_HIT")

    # --- L1 Store Performance ---
    adj_l1_dcache_stores = get_event_value(adjusted_stats, "L1_DCACHE_STORES")
    adj_l1_dcache_store_misses = get_event_value(adjusted_stats, "L1_DCACHE_STORE_MISSES") # 此事件在你的硬件上可能不支持
    metrics["L1D Cache Stores"] = adj_l1_dcache_stores
    metrics["L1D Cache Store Misses"] = adj_l1_dcache_store_misses
    if adj_l1_dcache_stores > 0 and adj_l1_dcache_store_misses != "N/A": # 确保分子也不是N/A
        if isinstance(adj_l1_dcache_store_misses, (int, float)): # 确保可以计算
             metrics["L1D Cache Store Miss Rate"] = (adj_l1_dcache_store_misses / adj_l1_dcache_stores) * 100
        else: # 如果 L1D Cache Store Misses 因为不支持而是0或者get_event_value返回了0
             metrics["L1D Cache Store Miss Rate"] = 0.0 if adj_l1_dcache_store_misses == 0 else "N/A" # 如果确实是0次miss，那miss rate是0
    else:
        metrics["L1D Cache Store Miss Rate"] = "N/A"


    # --- L2 Load Performance ---
    adj_l2_hits_load = get_event_value(adjusted_stats, "MEM_LOAD_RETIRED_L2_HIT")
    adj_l2_misses_load = get_event_value(adjusted_stats, "MEM_LOAD_RETIRED_L2_MISS")
    adj_l2_accesses_load = adj_l2_hits_load + adj_l2_misses_load
    if adj_l2_accesses_load > 0:
        metrics["L2 Load Hit Rate (for loads reaching L2)"] = (adj_l2_hits_load / adj_l2_accesses_load) * 100
    else:
        metrics["L2 Load Hit Rate (for loads reaching L2)"] = "N/A"
    metrics["L2 Load Hits"] = adj_l2_hits_load
    metrics["L2 Load Misses"] = adj_l2_misses_load

    # --- L3 Load Performance ---
    adj_l3_hits_load = get_event_value(adjusted_stats, "MEM_LOAD_RETIRED_L3_HIT")
    adj_l3_misses_load = get_event_value(adjusted_stats, "MEM_LOAD_RETIRED_L3_MISS")
    adj_l3_accesses_load = adj_l3_hits_load + adj_l3_misses_load
    if adj_l3_accesses_load > 0 :
        metrics["L3 Load Hit Rate (for loads reaching L3)"] = (adj_l3_hits_load / adj_l3_accesses_load) * 100
    else:
        metrics["L3 Load Hit Rate (for loads reaching L3)"] = "N/A"
    metrics["L3 Load Hits"] = adj_l3_hits_load
    metrics["L3 Load Misses (Loads hitting DRAM)"] = adj_l3_misses_load

    # --- LLC Store Performance ---
    adj_llc_stores = get_event_value(adjusted_stats, "LLC_STORES_COUNT")
    adj_llc_store_misses = get_event_value(adjusted_stats, "LLC_STORE_MISSES_COUNT")
    metrics["LLC Stores"] = adj_llc_stores
    metrics["LLC Store Misses"] = adj_llc_store_misses
    if adj_llc_stores > 0:
        metrics["LLC Store Miss Rate"] = (adj_llc_store_misses / adj_llc_stores) * 100
    else:
        metrics["LLC Store Miss Rate"] = "N/A"

    # --- Branch Prediction ---
    adj_branch_misses = get_event_value(adjusted_stats, "BRANCH_MISSES")
    metrics["Branch Misses"] = adj_branch_misses
    # 可选：如果你收集了 branch-instructions，可以计算 Branch Miss Rate
    # adj_branch_instructions = get_event_value(adjusted_stats, "BRANCH_INSTRUCTIONS") # 需要为 "BRANCH_INSTRUCTIONS" 添加映射
    # if adj_branch_instructions > 0:
    #     metrics["Branch Miss Rate"] = (adj_branch_misses / adj_branch_instructions) * 100
    # else:
    #     metrics["Branch Miss Rate"] = "N/A"

    # --- Other System/TLB/ICache Metrics (Including New Ones) ---
    metrics["L1 ICache Load Misses"] = get_event_value(adjusted_stats, "L1_ICACHE_MISSES")
    metrics["dTLB Load Misses"] = get_event_value(adjusted_stats, "DTLB_LOAD_MISSES")
    metrics["dTLB Store Misses"] = get_event_value(adjusted_stats, "DTLB_STORE_MISSES")
    metrics["iTLB Load Misses"] = get_event_value(adjusted_stats, "ITLB_LOAD_MISSES")
    
    # --- 新增指标 ---
    metrics["Context Switches"] = get_event_value(adjusted_stats, "CONTEXT_SWITCHES")
    metrics["Page Faults"] = get_event_value(adjusted_stats, "PAGE_FAULTS")
    
    # --- 现有其他指标 ---
    metrics["Offcore Reqs Demand Data Rd"] = get_event_value(adjusted_stats, "OFFCORE_REQS_DEMAND_DATA_RD") # 确保这个事件在某个GROUP中被收集，并且在KEY_EVENT_MAPPINGS中定义
    metrics["Stalls L3 Miss (Cycles)"] = get_event_value(adjusted_stats, "CYCLE_ACTIVITY_STALLS_L3_MISS")
    metrics["Load Latency >128 cycles"] = get_event_value(adjusted_stats, "MEM_TRANS_LATENCY_GT_128") # 确保事件被收集和映射

    return metrics

# 定义文本报告中指标的期望打印顺序
METRIC_PRINT_ORDER = [
    "Cycles",
    "Total Instructions (IC)",
    "IPC (Instructions Per Cycle)",
    
    "Memory Access Instructions",
    "Memory Loads Retired",
    "Memory Stores Retired",
    
    "L1 Load Hit Rate",
    "L1 Load Hits",
    "L1 Load Misses",
    "L1 Fill Buffer Hits (Loads)",
    
    "L1D Cache Stores",
    "L1D Cache Store Misses",       # 这个事件在你的硬件上可能不支持，所以其值可能为0或N/A
    "L1D Cache Store Miss Rate",    # 如果 L1D Cache Store Misses 为 N/A 或 0，这个也会是 N/A 或 0.0
    
    "L2 Load Hit Rate (for loads reaching L2)",
    "L2 Load Hits",
    "L2 Load Misses",
    
    "L3 Load Hit Rate (for loads reaching L3)",
    "L3 Load Hits",
    "L3 Load Misses (Loads hitting DRAM)",
    
    "LLC Stores",
    "LLC Store Misses",
    "LLC Store Miss Rate",
    
    "Branch Misses",
    # "Branch Miss Rate", # 如果计算了，可以加在这里

    "L1 ICache Load Misses",
    "dTLB Load Misses",
    "dTLB Store Misses",
    "iTLB Load Misses",
    
    "Page Faults",                  # 新增
    "Context Switches",             # 新增
    
    "Offcore Reqs Demand Data Rd",  # 确保这个事件被收集
    "Stalls L3 Miss (Cycles)",
    "Load Latency >128 cycles"      # 确保这个事件被收集
]