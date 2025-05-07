# perf_analyzer.py
from collections import defaultdict
# 导入来自 perf_parser 的辅助函数
from perf_parser import get_event_value

def calculate_metrics(current_stats_merged, baseline_stats_merged): # Renamed from calculate_adjusted_metrics
    """
    计算性能指标 (已进行基线校准)。
    输入是已经合并了所有 Group 数据的字典。
    """
    adjusted_stats = defaultdict(int)
    # Combine keys from both current and baseline merged stats
    all_event_names_in_merged = set(current_stats_merged.keys()) | set(baseline_stats_merged.keys())

    for event_name in all_event_names_in_merged:
        adjusted_stats[event_name] = current_stats_merged.get(event_name, 0) - baseline_stats_merged.get(event_name, 0)

    metrics = {} # Store results with "Adjusted" removed from keys

    # --- Cycles, Instructions, IPC ---
    adj_cycles = get_event_value(adjusted_stats, "CYCLES")
    adj_ic = get_event_value(adjusted_stats, "IC")
    metrics["Cycles"] = adj_cycles  # Key Change
    metrics["Total Instructions (IC)"] = adj_ic # Key Change
    if adj_cycles > 0:
        metrics["IPC (Instructions Per Cycle)"] = adj_ic / adj_cycles # Key Change
    else:
        metrics["IPC (Instructions Per Cycle)"] = "N/A"

    # --- Memory Access Instructions ---
    adj_mem_loads = get_event_value(adjusted_stats, "MEM_LOADS_RETIRED")
    adj_mem_stores = get_event_value(adjusted_stats, "MEM_STORES_RETIRED")
    metrics["Memory Access Instructions"] = adj_mem_loads + adj_mem_stores # Key Change
    metrics["Memory Loads Retired"] = adj_mem_loads # Key Change
    metrics["Memory Stores Retired"] = adj_mem_stores # Key Change

    # --- L1 Load Performance ---
    adj_l1_hits_load = get_event_value(adjusted_stats, "MEM_LOAD_RETIRED_L1_HIT")
    adj_l1_misses_load = get_event_value(adjusted_stats, "MEM_LOAD_RETIRED_L1_MISS")
    adj_l1_accesses_load = adj_l1_hits_load + adj_l1_misses_load
    if adj_l1_accesses_load > 0:
        metrics["L1 Load Hit Rate"] = (adj_l1_hits_load / adj_l1_accesses_load) * 100 # Key Change
    else:
        metrics["L1 Load Hit Rate"] = "N/A"
    metrics["L1 Load Hits"] = adj_l1_hits_load # Key Change
    metrics["L1 Load Misses"] = adj_l1_misses_load # Key Change
    metrics["L1 Fill Buffer Hits (Loads)"] = get_event_value(adjusted_stats, "MEM_LOAD_RETIRED_FB_HIT") # Key Change

    # --- L1 Store Performance ---
    adj_l1_dcache_stores = get_event_value(adjusted_stats, "L1_DCACHE_STORES")
    adj_l1_dcache_store_misses = get_event_value(adjusted_stats, "L1_DCACHE_STORE_MISSES")
    metrics["L1D Cache Stores"] = adj_l1_dcache_stores # Key Change
    metrics["L1D Cache Store Misses"] = adj_l1_dcache_store_misses # Key Change
    if adj_l1_dcache_stores > 0:
        metrics["L1D Cache Store Miss Rate"] = (adj_l1_dcache_store_misses / adj_l1_dcache_stores) * 100 # Key Change
    else:
        metrics["L1D Cache Store Miss Rate"] = "N/A"

    # --- L2 Load Performance ---
    adj_l2_hits_load = get_event_value(adjusted_stats, "MEM_LOAD_RETIRED_L2_HIT")
    adj_l2_misses_load = get_event_value(adjusted_stats, "MEM_LOAD_RETIRED_L2_MISS")
    adj_l2_accesses_load = adj_l2_hits_load + adj_l2_misses_load
    if adj_l2_accesses_load > 0:
        metrics["L2 Load Hit Rate (for loads reaching L2)"] = (adj_l2_hits_load / adj_l2_accesses_load) * 100 # Key Change
    else:
        metrics["L2 Load Hit Rate (for loads reaching L2)"] = "N/A"
    metrics["L2 Load Hits"] = adj_l2_hits_load # Key Change
    metrics["L2 Load Misses"] = adj_l2_misses_load # Key Change

    # --- L3 Load Performance ---
    adj_l3_hits_load = get_event_value(adjusted_stats, "MEM_LOAD_RETIRED_L3_HIT")
    adj_l3_misses_load = get_event_value(adjusted_stats, "MEM_LOAD_RETIRED_L3_MISS")
    adj_l3_accesses_load = adj_l3_hits_load + adj_l3_misses_load
    if adj_l3_accesses_load > 0 :
        metrics["L3 Load Hit Rate (for loads reaching L3)"] = (adj_l3_hits_load / adj_l3_accesses_load) * 100 # Key Change
    else:
        metrics["L3 Load Hit Rate (for loads reaching L3)"] = "N/A"
    metrics["L3 Load Hits"] = adj_l3_hits_load # Key Change
    metrics["L3 Load Misses (Loads hitting DRAM)"] = adj_l3_misses_load # Key Change

    # --- LLC Store Performance ---
    adj_llc_stores = get_event_value(adjusted_stats, "LLC_STORES_COUNT")
    adj_llc_store_misses = get_event_value(adjusted_stats, "LLC_STORE_MISSES_COUNT")
    metrics["LLC Stores"] = adj_llc_stores # Key Change
    metrics["LLC Store Misses"] = adj_llc_store_misses # Key Change
    if adj_llc_stores > 0:
        metrics["LLC Store Miss Rate"] = (adj_llc_store_misses / adj_llc_stores) * 100 # Key Change
    else:
        metrics["LLC Store Miss Rate"] = "N/A"

    # --- Other Metrics ---
    metrics["L1 ICache Load Misses"] = get_event_value(adjusted_stats, "L1_ICACHE_MISSES") # Key Change
    metrics["dTLB Load Misses"] = get_event_value(adjusted_stats, "DTLB_LOAD_MISSES") # Key Change
    metrics["dTLB Store Misses"] = get_event_value(adjusted_stats, "DTLB_STORE_MISSES") # Key Change
    metrics["iTLB Load Misses"] = get_event_value(adjusted_stats, "ITLB_LOAD_MISSES") # Key Change
    metrics["Offcore Reqs Demand Data Rd"] = get_event_value(adjusted_stats, "OFFCORE_REQS_DEMAND_DATA_RD") # Key Change
    metrics["Stalls L3 Miss (Cycles)"] = get_event_value(adjusted_stats, "CYCLE_ACTIVITY_STALLS_L3_MISS") # Key Change + Clarification
    metrics["Load Latency >128 cycles"] = get_event_value(adjusted_stats, "MEM_TRANS_LATENCY_GT_128") # Key Change

    return metrics

# Define the desired print order with "Adjusted" removed
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
    "L1D Cache Store Misses",
    "L1D Cache Store Miss Rate",
    "L2 Load Hit Rate (for loads reaching L2)",
    "L2 Load Hits",
    "L2 Load Misses",
    "L3 Load Hit Rate (for loads reaching L3)",
    "L3 Load Hits",
    "L3 Load Misses (Loads hitting DRAM)",
    "LLC Stores",
    "LLC Store Misses",
    "LLC Store Miss Rate",
    "L1 ICache Load Misses",
    "dTLB Load Misses",
    "dTLB Store Misses",
    "iTLB Load Misses",
    "Offcore Reqs Demand Data Rd",
    "Stalls L3 Miss (Cycles)",
    "Load Latency >128 cycles"
]