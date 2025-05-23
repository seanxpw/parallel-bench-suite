# perf_parser.py
import re
from collections import defaultdict
import sys # Import sys for stderr

# 将事件的通用名称映射到 perf stat 输出中可能出现的具体名称列表
# （处理 :u 后缀不一致的问题）
KEY_EVENT_MAPPINGS = {
    "IC": ["instructions:u", "instructions"],
    "CYCLES": ["cycles:u", "cycles"],
    "MEM_LOADS_RETIRED": ["mem_inst_retired.all_loads:u", "mem_inst_retired.all_loads"],
    "MEM_STORES_RETIRED": ["mem_inst_retired.all_stores:u", "mem_inst_retired.all_stores"],

    "MEM_LOAD_RETIRED_FB_HIT": ["mem_load_retired.fb_hit:u", "mem_load_retired.fb_hit"],
    "MEM_LOAD_RETIRED_L1_HIT": ["mem_load_retired.l1_hit:u", "mem_load_retired.l1_hit"],
    "MEM_LOAD_RETIRED_L1_MISS": ["mem_load_retired.l1_miss:u", "mem_load_retired.l1_miss"],
    "MEM_LOAD_RETIRED_L2_HIT": ["mem_load_retired.l2_hit:u", "mem_load_retired.l2_hit"],
    "MEM_LOAD_RETIRED_L2_MISS": ["mem_load_retired.l2_miss:u", "mem_load_retired.l2_miss"],
    "MEM_LOAD_RETIRED_L3_HIT": ["mem_load_retired.l3_hit:u", "mem_load_retired.l3_hit"],
    "MEM_LOAD_RETIRED_L3_MISS": ["mem_load_retired.l3_miss:u", "mem_load_retired.l3_miss"],

    "L1_ICACHE_MISSES": ["L1-icache-load-misses:u", "L1-icache-load-misses"],

    "L1_DCACHE_STORES": ["L1-dcache-stores:u", "L1-dcache-stores"],
    "L1_DCACHE_STORE_MISSES": ["L1-dcache-store-misses:u", "L1-dcache-store-misses"], # Event not supported on user's HW

    "DTLB_LOADS": ["dTLB-loads:u", "dTLB-loads"],
    "DTLB_LOAD_MISSES": ["dTLB-load-misses:u", "dTLB-load-misses"],
    "DTLB_STORES": ["dTLB-stores:u", "dTLB-stores"],
    "DTLB_STORE_MISSES": ["dTLB-store-misses:u", "dTLB-store-misses"],

    "ITLB_LOADS": ["iTLB-loads:u", "iTLB-loads"], # Might be <not supported>
    "ITLB_LOAD_MISSES": ["iTLB-load-misses:u", "iTLB-load-misses"],

    "LLC_STORES_COUNT": ["LLC-stores:u", "LLC-stores"],
    "LLC_STORE_MISSES_COUNT": ["LLC-store-misses:u", "LLC-store-misses"],

    "OFFCORE_REQS_ALL_DATA_RD": ["offcore_requests.all_data_rd:u", "offcore_requests.all_data_rd"],
    "OFFCORE_REQS_DEMAND_DATA_RD": ["offcore_requests.demand_data_rd:u", "offcore_requests.demand_data_rd"],
    "OFFCORE_REQS_OUTSTANDING_CYCLES_DATA_RD": ["offcore_requests_outstanding.cycles_with_data_rd:u", "offcore_requests_outstanding.cycles_with_data_rd"],
    "CYCLE_ACTIVITY_STALLS_L3_MISS": ["cycle_activity.stalls_l3_miss:u", "cycle_activity.stalls_l3_miss"],
    "MEM_TRANS_LATENCY_GT_32": ["mem_trans_retired.load_latency_gt_32:u", "mem_trans_retired.load_latency_gt_32"],
    "MEM_TRANS_LATENCY_GT_128": ["mem_trans_retired.load_latency_gt_128:u", "mem_trans_retired.load_latency_gt_128"],
    "MEM_TRANS_LATENCY_GT_512": ["mem_trans_retired.load_latency_gt_512:u", "mem_trans_retired.load_latency_gt_512"],

    "BRANCH_MISSES": ["branch-misses:u", "branch-misses"],

    # --- NEW MAPPINGS for context-switches and faults ---
    "CONTEXT_SWITCHES": ["context-switches:u", "context-switches", "cs"],
    "PAGE_FAULTS": ["faults:u", "faults", "page-faults:u", "page-faults"],
    "MINOR_PAGE_FAULTS": ["minor-faults:u", "minor-faults"],
}

def get_event_value(stats_dict, generic_event_key):
    """
    从 stats_dict 中获取通用事件键对应的值。
    尝试 KEY_EVENT_MAPPINGS 中定义的所有可能名称。
    """
    for concrete_name in KEY_EVENT_MAPPINGS.get(generic_event_key, []):
        if concrete_name in stats_dict:
            return stats_dict[concrete_name]
    # Fallback: if the key itself is a direct name (less likely now for generic keys)
    if generic_event_key in stats_dict:
        # This might happen if a generic key accidentally matches a raw key not in mappings
        # print(f"Debug: Generic key '{generic_event_key}' found directly in stats_dict.", file=sys.stderr)
        return stats_dict[generic_event_key]
    
    # print(f"Debug: Generic key '{generic_event_key}' not found via mappings or directly.", file=sys.stderr) # Optional: for debugging missing events
    return 0 # 如果事件未找到，返回0

def parse_perf_file(filepath):
    """
    解析单个 perf stat 输出文件。
    返回一个字典 {event_name: count}。
    """
    stats = defaultdict(int)
    # Regex to capture: count (with commas), event name, optional comment/percentage
    pattern = re.compile(r'^\s*([\d,]+)\s+([\w.:-]+)(\s+.*)?$')
    not_supported_pattern = re.compile(r'^\s*<not\s+supported>\s+([\w.:-]+)(\s+.*)?$')
    # Regex for lines like 'Duration: 1.23 ms' or 'Total time: 5.41 s' which are not events
    # This helps filter out non-event lines that might otherwise be partially matched or cause warnings.
    # Example: "     5.412523614 seconds time elapsed"
    # Example: "     0.000000000 seconds user"
    # Example: "     0.000000000 seconds sys"
    non_event_value_line_pattern = re.compile(r'^\s*([\d,.]+)\s+(seconds|CPUs|GHz|cycles|instructions|CPUs utilized|stalled-cycles|insns|IPC|instructions per cycle|migrations|task-clock|context-switches|cpu-migrations|page-faults)(\s+.*)?$')


    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_number, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'): # Skip empty lines and comments
                    continue

                match = pattern.match(line)
                not_supported_match = not_supported_pattern.match(line)
                
                if match:
                    count_str = match.group(1)
                    event_name = match.group(2)
                    try:
                        stats[event_name] = int(count_str.replace(',', ''))
                    except ValueError:
                        print(f"Warning: Could not parse count '{count_str}' for event '{event_name}' in {filepath} at line {line_number}", file=sys.stderr)
                elif not_supported_match:
                    event_name = not_supported_match.group(1)
                    stats[event_name] = 0 # 将 <not supported> 的事件计为0
                else:
                    # Check if it's a known non-event line pattern to suppress warnings for those
                    if not non_event_value_line_pattern.match(line) and "Performance counter stats for" not in line and "time elapsed" not in line:
                        # print(f"Debug: Line not matched by event patterns in {filepath} at line {line_number}: '{line}'", file=sys.stderr)
                        pass
    except FileNotFoundError:
        print(f"Error: File not found {filepath}", file=sys.stderr)
        return None 
    except Exception as e:
        print(f"Error parsing file {filepath}: {e}", file=sys.stderr)
        return None 
    
    if not stats and os.path.exists(filepath):
        print(f"Warning: No parsable perf events found in {filepath}. The file might be empty or in an unexpected format.", file=sys.stderr)
        # No change needed here, returning empty defaultdict is fine.

    return stats