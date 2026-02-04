import subprocess
import pandas as pd
import os
import time
import csv
import json
from datetime import datetime, timedelta

# =========================== ⚙️ 用户配置区域 ===========================

THREADS = os.cpu_count() or 4
BINARY_DIR = "./build"  # 你的 build 目录

ALGORITHMS = [
    "simd",
    "ips4oparallel",
    "ips2raparallel",
    "dovetailsort",
    "mcstlbq",
    "mcstlmwm"
    # "stdsort"
]

ALGO_MAP = {
    "plss": "parlay_sample_sort",
    "plis": "parlay_integer_sort",
}

GENERATORS = [
    "random",
    "sorted",
    # "reverse",
    "zipf",
    "exponential"
]

DATATYPES = ["uint32","uint64"]

# 注意：这里的 size 是 elements（元素个数）
SIZES = [100_000_000, 1_000_000_000, 10_000_000_000]

OUTPUT_DIR = "bench_results_v5"

# ======================================================================

DTYPE_BYTES = {
    "uint32": 4,
    "uint64": 8,
}

RAW_COLUMNS = [
    "run_ts",
    "config_gen",
    "datatype",
    "elements",
    "config_algo",
    "config_algo_internal",
    "run_in_config",
    "time_ms",
    "melems_per_s",
    "bandwidth_GBps",
    "extra_json",
]

def get_binary_path(algo_name: str) -> str:
    filename = f"benchmark_{algo_name}"
    return os.path.join(BINARY_DIR, filename)

def parse_result_line(line: str) -> dict:
    data = {}
    parts = line.strip().split('\t')
    for part in parts:
        if '=' in part:
            key, value = part.split('=', 1)
            data[key.strip()] = value.strip()
    return data

def calc_metrics(elements: int, dtype: str, time_ms: float):
    """elements 个元素，dtype 决定每元素字节数，time_ms 为毫秒"""
    if time_ms <= 0:
        return 0.0, 0.0
    sec = time_ms / 1000.0

    # 吞吐：M elements/s
    melems_per_s = (elements / 1_000_000.0) / sec

    # 带宽：GB/s（按 1e9 字节）
    bpe = DTYPE_BYTES.get(dtype, 0)
    bandwidth_GBps = (elements * bpe) / sec / 1_000_000_000.0 if bpe else 0.0
    return melems_per_s, bandwidth_GBps

def run_benchmark():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_file = os.path.join(OUTPUT_DIR, f"raw_{timestamp}.csv")

    total_tasks = len(GENERATORS) * len(DATATYPES) * len(ALGORITHMS) * len(SIZES)
    current_task = 0

    print(f"🚀 开始测试 (逐行落盘 + 打印 Best & Avg[Skip2])")
    print(f"📋 映射关系: {ALGO_MAP}")
    print(f"💾 Raw 输出: {raw_file}")
    print("=" * 100) # 稍微加长一点分割线

    all_rows_for_summary = []  
    
    # ⏱️ 计时开始
    start_time_global = time.time()

    with open(raw_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RAW_COLUMNS)
        writer.writeheader()
        f.flush()

        for gen in GENERATORS:
            for dtype in DATATYPES:
                for elements in SIZES:
                    for algo in ALGORITHMS:
                        current_task += 1

                        # --- [新增] ETA 计算 ---
                        elapsed_global = time.time() - start_time_global
                        if current_task > 1:
                            avg_time_per_task = elapsed_global / (current_task - 1)
                            remaining_tasks = total_tasks - (current_task - 1)
                            eta_seconds = int(avg_time_per_task * remaining_tasks)
                            eta_str = str(timedelta(seconds=eta_seconds))
                        else:
                            eta_str = "Calc..."

                        binary_path = get_binary_path(algo)
                        internal_algo_name = ALGO_MAP.get(algo, algo)

                        prefix = f"[{current_task}/{total_tasks}] [ETA: {eta_str}]"
                        size_str = f"{elements/1_000_000:.1f}M"
                        
                        # 打印当前任务信息
                        print(
                            f"{prefix} Gen={gen:<9} Type={dtype:<7} Elements={size_str:<6} "
                            f"Algo={algo}({internal_algo_name}) ... ",
                            end="",
                            flush=True
                        )

                        if not os.path.exists(binary_path):
                            print("⏭️  Skip (Binary Missing)")
                            continue

                        cmd = [
                            binary_path,
                            "-m", "py_bench_v5",
                            "-e", str(elements),
                            "-b", str(elements),
                            "-t", str(THREADS),
                            "-v", "vector",
                            "-d", dtype,
                            "-a", internal_algo_name,
                            "-r", "10",  # 每个配置跑 10 次
                            "-g", gen,
                        ]

                        try:
                            result = subprocess.run(
                                cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                text=True
                            )

                            lines = result.stdout.splitlines()
                            run_in_config = 0
                            times_ms = []

                            for line in lines:
                                line = line.strip()
                                if not line.startswith("RESULT"):
                                    continue

                                parsed = parse_result_line(line)

                                if "milli" not in parsed:
                                    continue

                                try:
                                    time_ms = float(parsed["milli"])
                                except ValueError:
                                    continue

                                run_in_config += 1
                                dtype_out = parsed.get("datatype", dtype)
                                meps, bwGBps = calc_metrics(elements, dtype_out, time_ms)
                                extra = {k: v for k, v in parsed.items() if k not in ("milli", "datatype")}

                                row = {
                                    "run_ts": datetime.now().isoformat(timespec="seconds"),
                                    "config_gen": gen,
                                    "datatype": dtype_out,
                                    "elements": elements,
                                    "config_algo": algo,
                                    "config_algo_internal": internal_algo_name,
                                    "run_in_config": run_in_config,
                                    "time_ms": time_ms,
                                    "melems_per_s": meps,
                                    "bandwidth_GBps": bwGBps,
                                    "extra_json": json.dumps(extra, ensure_ascii=False),
                                }

                                writer.writerow(row)
                                f.flush()

                                all_rows_for_summary.append(row)
                                times_ms.append(time_ms)

                            if times_ms:
                                # --- 1. Best (Min) ---
                                best_ms = min(times_ms)
                                best_meps, best_bw = calc_metrics(elements, dtype, best_ms)
                                
                                # --- 2. Avg (Skip 2) ---
                                # 如果次数够多，去掉前2次；不够则全部平均
                                if len(times_ms) > 2:
                                    valid_times = times_ms[2:]
                                    avg_tag = "avg(skip2)"
                                else:
                                    valid_times = times_ms
                                    avg_tag = "avg(all)"
                                
                                avg_ms = sum(valid_times) / len(valid_times)
                                avg_meps, avg_bw = calc_metrics(elements, dtype, avg_ms)

                                print(f"✅ best={best_ms:.1f}ms | {best_bw:.2f} GB/s || {avg_tag}={avg_ms:.1f}ms | {avg_bw:.2f} GB/s (n={len(times_ms)})")
                            else:
                                if result.returncode != 0:
                                    print(f"❌ Crash (Code {result.returncode})")
                                    # ... (Crash log logic same as before)
                                else:
                                    print("⚠️ No Data")
                                    # ... (No Data log logic same as before)

                        except Exception as e:
                            print(f"❌ Script Error: {e}")

    # ================= 结果处理 =================
    if not all_rows_for_summary:
        print("\n❌ 未收集到任何数据。")
        return

    print("=" * 100)
    df = pd.DataFrame(all_rows_for_summary)
    df["elements"] = pd.to_numeric(df["elements"])
    df["time_ms"] = pd.to_numeric(df["time_ms"])

    # 这里的 summary 依然用 min，如果需要 avg 也可以改成 mean
    pivot_min = df.pivot_table(
        index=["config_gen", "datatype", "elements"],
        columns="config_algo",
        values="time_ms",
        aggfunc="min"
    )

    summary_file = os.path.join(OUTPUT_DIR, f"summary_best_{timestamp}.csv")
    pivot_min.to_csv(summary_file)
    print(f"💾 汇总表格(最快/min): {summary_file}")
    print(pivot_min.round(1).fillna("-").head(20))

if __name__ == "__main__":
    run_benchmark()