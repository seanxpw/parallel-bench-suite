# perf_analyzer.py (修改后的版本)
from collections import defaultdict
from perf_parser import get_event_value # 确保 get_event_value 和 KEY_EVENT_MAPPINGS 在 perf_parser.py 中

# calculate_metrics 函数现在只接收 current_stats_merged
def calculate_metrics(current_stats_merged): #移除了 baseline_stats_merged 参数
    """
    计算性能指标 (基于原始合并值和派生指标)。
    输入是已经合并了所有 Group 数据的字典 (键为原始perf事件名)。
    """
    # 不再需要 adjusted_stats，直接从 current_stats_merged 中获取值
    metrics = {} 

    # --- Cycles, Instructions, IPC ---
    # 这些现在是原始的合并计数值 (通过 get_event_value 查找)
    raw_cycles = get_event_value(current_stats_merged, "CYCLES")
    raw_ic = get_event_value(current_stats_merged, "IC")
    metrics["Cycles"] = raw_cycles
    metrics["Total Instructions (IC)"] = raw_ic
    if raw_cycles > 0:
        metrics["IPC (Instructions Per Cycle)"] = raw_ic / raw_cycles
    else:
        metrics["IPC (Instructions Per Cycle)"] = "N/A"

    # --- Memory Access Instructions ---
    raw_mem_loads = get_event_value(current_stats_merged, "MEM_LOADS_RETIRED")
    raw_mem_stores = get_event_value(current_stats_merged, "MEM_STORES_RETIRED")
    metrics["Memory Access Instructions"] = raw_mem_loads + raw_mem_stores
    metrics["Memory Loads Retired"] = raw_mem_loads
    metrics["Memory Stores Retired"] = raw_mem_stores

    # --- L1 Load Performance ---
    raw_l1_hits_load = get_event_value(current_stats_merged, "MEM_LOAD_RETIRED_L1_HIT")
    raw_l1_misses_load = get_event_value(current_stats_merged, "MEM_LOAD_RETIRED_L1_MISS")
    raw_l1_accesses_load = raw_l1_hits_load + raw_l1_misses_load # 这是原始访问次数
    if raw_l1_accesses_load > 0:
        metrics["L1 Load Hit Rate"] = (raw_l1_hits_load / raw_l1_accesses_load) * 100
    else:
        metrics["L1 Load Hit Rate"] = "N/A"
    metrics["L1 Load Hits"] = raw_l1_hits_load
    metrics["L1 Load Misses"] = raw_l1_misses_load
    metrics["L1 Fill Buffer Hits (Loads)"] = get_event_value(current_stats_merged, "MEM_LOAD_RETIRED_FB_HIT")

    # --- L1 Store Performance ---
    raw_l1_dcache_stores = get_event_value(current_stats_merged, "L1_DCACHE_STORES")
    raw_l1_dcache_store_misses = get_event_value(current_stats_merged, "L1_DCACHE_STORE_MISSES")
    metrics["L1D Cache Stores"] = raw_l1_dcache_stores
    metrics["L1D Cache Store Misses"] = raw_l1_dcache_store_misses
    if raw_l1_dcache_stores > 0:
        if isinstance(raw_l1_dcache_store_misses, (int, float)): # 确保可以计算
            metrics["L1D Cache Store Miss Rate"] = (raw_l1_dcache_store_misses / raw_l1_dcache_stores) * 100
        else: # 如果事件不支持等返回的是0
            metrics["L1D Cache Store Miss Rate"] = 0.0 if raw_l1_dcache_store_misses == 0 else "N/A"
    else:
        metrics["L1D Cache Store Miss Rate"] = "N/A"

    # --- L2 Load Performance ---
    raw_l2_hits_load = get_event_value(current_stats_merged, "MEM_LOAD_RETIRED_L2_HIT")
    raw_l2_misses_load = get_event_value(current_stats_merged, "MEM_LOAD_RETIRED_L2_MISS")
    raw_l2_accesses_load = raw_l2_hits_load + raw_l2_misses_load
    if raw_l2_accesses_load > 0:
        metrics["L2 Load Hit Rate (for loads reaching L2)"] = (raw_l2_hits_load / raw_l2_accesses_load) * 100
    else:
        metrics["L2 Load Hit Rate (for loads reaching L2)"] = "N/A"
    metrics["L2 Load Hits"] = raw_l2_hits_load
    metrics["L2 Load Misses"] = raw_l2_misses_load

    # --- L3 Load Performance ---
    raw_l3_hits_load = get_event_value(current_stats_merged, "MEM_LOAD_RETIRED_L3_HIT")
    raw_l3_misses_load = get_event_value(current_stats_merged, "MEM_LOAD_RETIRED_L3_MISS")
    raw_l3_accesses_load = raw_l3_hits_load + raw_l3_misses_load
    if raw_l3_accesses_load > 0 :
        metrics["L3 Load Hit Rate (for loads reaching L3)"] = (raw_l3_hits_load / raw_l3_accesses_load) * 100
    else:
        metrics["L3 Load Hit Rate (for loads reaching L3)"] = "N/A"
    metrics["L3 Load Hits"] = raw_l3_hits_load
    metrics["L3 Load Misses (Loads hitting DRAM)"] = raw_l3_misses_load

    # --- LLC Store Performance ---
    raw_llc_stores = get_event_value(current_stats_merged, "LLC_STORES_COUNT")
    raw_llc_store_misses = get_event_value(current_stats_merged, "LLC_STORE_MISSES_COUNT")
    metrics["LLC Stores"] = raw_llc_stores
    metrics["LLC Store Misses"] = raw_llc_store_misses
    if raw_llc_stores > 0:
        metrics["LLC Store Miss Rate"] = (raw_llc_store_misses / raw_llc_stores) * 100
    else:
        metrics["LLC Store Miss Rate"] = "N/A"

    # --- Branch Prediction ---
    raw_branch_misses = get_event_value(current_stats_merged, "BRANCH_MISSES")
    metrics["Branch Misses"] = raw_branch_misses
    # ... (可以添加 Branch Miss Rate 如果收集了 branch-instructions)

    # --- Other System/TLB/ICache Metrics (Including New Ones) ---
    metrics["L1 ICache Load Misses"] = get_event_value(current_stats_merged, "L1_ICACHE_MISSES")
    metrics["dTLB Load Misses"] = get_event_value(current_stats_merged, "DTLB_LOAD_MISSES")
    metrics["dTLB Store Misses"] = get_event_value(current_stats_merged, "DTLB_STORE_MISSES")
    metrics["iTLB Load Misses"] = get_event_value(current_stats_merged, "ITLB_LOAD_MISSES")
    
    metrics["Context Switches"] = get_event_value(current_stats_merged, "CONTEXT_SWITCHES")
    metrics["Page Faults"] = get_event_value(current_stats_merged, "PAGE_FAULTS")
    
    metrics["Offcore Reqs Demand Data Rd"] = get_event_value(current_stats_merged, "OFFCORE_REQS_DEMAND_DATA_RD") 
    metrics["Stalls L3 Miss (Cycles)"] = get_event_value(current_stats_merged, "CYCLE_ACTIVITY_STALLS_L3_MISS")
    metrics["Load Latency >128 cycles"] = get_event_value(current_stats_merged, "MEM_TRANS_LATENCY_GT_128") 

    metrics["Minor Page Faults"] = get_event_value(current_stats_merged, "MINOR_PAGE_FAULTS")

    
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
    "Minor Page Faults",    # 新增：次要缺页
    "Context Switches",             # 新增
    
    "Offcore Reqs Demand Data Rd",  # 确保这个事件被收集
    "Stalls L3 Miss (Cycles)",
    "Load Latency >128 cycles"      # 确保这个事件被收集
]