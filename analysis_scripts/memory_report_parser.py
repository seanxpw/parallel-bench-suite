# memory_report_parser.py
import re
import os
import sys
import numpy as np # 导入 numpy 以使用 np.nan 处理缺失或无效值

def parse_time_mem_report(filepath):
    """
    解析 /usr/bin/time -v 命令的输出文件，提取特定的内存和上下文切换指标，
    并计算派生指标 "kB per Total Page Fault"。
    """
    metrics = {}
    expected_metrics_patterns = {
        re.compile(r"^\s*Voluntary context switches:\s*(\d+)"): "Voluntary Context Switches",
        re.compile(r"^\s*Involuntary context switches:\s*(\d+)"): "Involuntary Context Switches",
        re.compile(r"^\s*Maximum resident set size \(kbytes\):\s*(\d+)"): "Max RSS (kB)",
        re.compile(r"^\s*Major \(requiring I/O\) page faults:\s*(\d+)"): "Major Page Faults",
        re.compile(r"^\s*Minor \(reclaiming a frame\) page faults:\s*(\d+)"): "Minor Page Faults"
    }
    
    # 初始化所有期望的指标为 np.nan，方便后续处理
    for descriptive_name in expected_metrics_patterns.values():
        metrics[descriptive_name] = np.nan

    found_any_metric = False
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                for pattern, descriptive_name in expected_metrics_patterns.items():
                    match = pattern.match(line)
                    if match:
                        try:
                            metrics[descriptive_name] = int(match.group(1))
                            found_any_metric = True
                        except ValueError:
                            print(f"Warning: Could not parse value for '{descriptive_name}' from line: '{line}' in {filepath}", file=sys.stderr)
                            #保持为 np.nan
                        break 
        
        if not found_any_metric and os.path.exists(filepath):
             print(f"Warning: No expected memory/context metrics found in {filepath}. Content might be malformed or empty.", file=sys.stderr)

    except FileNotFoundError:
        print(f"Error: Memory report file not found: {filepath}", file=sys.stderr)
        return None 
    except Exception as e:
        print(f"Error parsing memory report file {filepath}: {e}", file=sys.stderr)
        return None

    # --- 计算派生指标: kB per Total Page Fault ---
    # 确保在返回之前计算，即使某些基础指标可能是 NaN
    max_rss_kb = metrics.get("Max RSS (kB)", np.nan) # 使用 .get 以防万一键不存在
    major_faults = metrics.get("Major Page Faults", np.nan)
    minor_faults = metrics.get("Minor Page Faults", np.nan)
    
    # 确保参与计算的值是数值类型且不是 NaN
    if isinstance(major_faults, (int, float)) and not np.isnan(major_faults) and \
       isinstance(minor_faults, (int, float)) and not np.isnan(minor_faults):
        total_page_faults = major_faults + minor_faults
    else:
        total_page_faults = np.nan # 如果任一组成部分缺失，总数也缺失

    if isinstance(max_rss_kb, (int, float)) and not np.isnan(max_rss_kb) and \
       isinstance(total_page_faults, (int, float)) and not np.isnan(total_page_faults) and \
       total_page_faults > 0:
        
        kb_per_fault = max_rss_kb / total_page_faults
        metrics["kB per Total Page Fault"] = kb_per_fault
    else:
        metrics["kB per Total Page Fault"] = np.nan # 如果无法计算，则为 NaN

    return metrics

if __name__ == '__main__':
    # ... (你的测试代码可以保持不变，它现在会额外显示 "kB per Total Page Fault") ...
    if len(sys.argv) > 1:
        sample_filepath = sys.argv[1]
        print(f"Attempting to parse example file: {sample_filepath}")
        if os.path.exists(sample_filepath):
            parsed_data = parse_time_mem_report(sample_filepath)
            if parsed_data:
                print("\nParsed Memory Metrics:")
                for key, value in parsed_data.items():
                    print(f"  {key:<40}: {value}")
            else:
                print("Failed to parse the file or file was empty/malformed.")
        else:
            print(f"Error: Sample file not found: {sample_filepath}")
    else:
        print("Usage: python memory_report_parser.py <path_to_mem_report_file.txt>")
        dummy_content = """
        Command being timed: "bash -c some_command"
        User time (seconds): 1.23
        System time (seconds): 0.45
        Percent of CPU this job got: 150%
        Elapsed (wall clock) time (h:mm:ss or m:ss): 0:01.10
        Maximum resident set size (kbytes): 123456
        Major (requiring I/O) page faults: 10
        Minor (reclaiming a frame) page faults: 20000
        Voluntary context switches: 500
        Involuntary context switches: 50
        Exit status: 0
        """
        dummy_filepath = "dummy_test_mem_report.txt"
        with open(dummy_filepath, "w", encoding="utf-8") as f:
            f.write(dummy_content)
        print(f"\nParsing dummy file: {dummy_filepath}")
        parsed_data = parse_time_mem_report(dummy_filepath)
        if parsed_data:
            print("Parsed Memory Metrics from Dummy File:")
            # 预定义顺序以便测试时更容易看到新指标
            test_order = [
                "Max RSS (kB)", "Minor Page Faults", "Major Page Faults", 
                "Voluntary Context Switches", "Involuntary Context Switches", 
                "kB per Total Page Fault"
            ]
            for key in test_order:
                if key in parsed_data:
                     print(f"  {key:<40}: {parsed_data[key]}")
                else: # 确保所有预期的键都被初始化了（即使是NaN）
                     print(f"  {key:<40}: {np.nan} (Not found in dummy example, check initialization)")


        os.remove(dummy_filepath)