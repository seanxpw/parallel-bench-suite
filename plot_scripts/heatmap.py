#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
同时生成：
1) 总图（all elements）
2) 按 elements 拆分子图

关键点：
- 子图与总图使用完全相同的颜色范围（同一 vmin/vmax）
- 因此子图看起来就像总图裁剪出来的
"""

import os
import math
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.colors import LogNorm
from typing import Optional, Tuple, List

# =========================
# Config
# =========================
CSV_PATH = "/home/xwang605/parallel-bench-suite/bench_results_v5/summary_mean_skip2_20260205_163218.csv"
OUTPUT_ROOT = "heatmaps_all_and_split"

BASELINE_COL = "simd"
CMAP_FAST_BRIGHT = "viridis_r"
DPI = 300

# 你的最终偏好
MS_USE_LOG = False
MS_CLIP_LOW_PERCENTILE = 1
MS_CLIP_HIGH_PERCENTILE = 95
MS_VMIN_FLOOR = None

RATIO_USE_LOG = False
RATIO_CLIP_LOW_PERCENTILE = 1
RATIO_CLIP_HIGH_PERCENTILE = 80
RATIO_VMIN_FLOOR = None

# 统一算法列顺序（按你常用顺序）
PREFERRED_ALGO_ORDER = [
    "dovetailsort", "ips2raparallel", "ips4oparallel",
    "mcstlbq", "mcstlmwm", "plis", "plss", "simd"
]

# Layout
MIN_FIG_W = 9.0
MIN_FIG_H = 6.0
LABEL_TABLE_WIDTH_RATIO = 2.2
HEATMAP_WIDTH_RATIO = 6.0

# =========================
# Helpers
# =========================
def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def fmt_n_compact(n: int) -> str:
    if n == 0:
        return "0"
    exp = int(round(math.log10(n)))
    if 10 ** exp == n:
        return f"1e{exp}"
    for b in range(0, 20):
        p = 10 ** b
        if n % p == 0:
            a = n // p
            if 2 <= a <= 9 and a * p == n:
                return f"{a}e{b}"
    return f"{n:,}"

def pick_meta_columns(df: pd.DataFrame) -> Tuple[str, str, str]:
    candidates = [
        ("config_gen", "datatype", "elements"),
        ("dist", "datatype", "elements"),
        ("config_gen", "type", "n"),
        ("dist", "type", "n"),
        ("distribution", "datatype", "elements"),
        ("distribution", "type", "n"),
    ]
    for a, b, c in candidates:
        if a in df.columns and b in df.columns and c in df.columns:
            return a, b, c
    raise ValueError(
        "无法识别元数据列。需要类似 (config_gen, datatype, elements) 或 (dist, type, n)。\n"
        f"当前列: {list(df.columns)}"
    )

def infer_algo_cols(df: pd.DataFrame, meta_cols: List[str]) -> List[str]:
    algo_cols = []
    for c in df.columns:
        if c in meta_cols:
            continue
        if pd.api.types.is_numeric_dtype(df[c]):
            algo_cols.append(c)
        else:
            try:
                pd.to_numeric(df[c], errors="raise")
                algo_cols.append(c)
            except Exception:
                pass
    return algo_cols

def order_algo_cols(algo_cols: List[str]) -> List[str]:
    in_pref = [c for c in PREFERRED_ALGO_ORDER if c in algo_cols]
    rest = [c for c in algo_cols if c not in in_pref]
    return in_pref + rest

def compute_scale_from_total(
    matrix: np.ndarray,
    use_log: bool,
    clip_low_percentile: Optional[int],
    clip_high_percentile: Optional[int],
    vmin_floor: Optional[float]
) -> Tuple[float, float]:
    finite = matrix[np.isfinite(matrix)]
    if use_log:
        finite = finite[finite > 0]

    if finite.size == 0:
        raise ValueError("颜色缩放失败：没有有效数据。")

    if clip_low_percentile is None:
        low = float(np.min(finite))
    else:
        low = float(np.percentile(finite, clip_low_percentile))

    if clip_high_percentile is None:
        high = float(np.max(finite))
    else:
        high = float(np.percentile(finite, clip_high_percentile))

    if vmin_floor is not None:
        low = max(low, float(vmin_floor))

    if not (low < high):
        high = low * 1.001 if low != 0 else 1e-9

    return low, high

def build_meta_table(df_sub: pd.DataFrame, dist_col: str, type_col: str, n_col: str) -> pd.DataFrame:
    return pd.DataFrame({
        "dist": df_sub[dist_col].astype(str).to_list(),
        "type": df_sub[type_col].astype(str).to_list(),
        "n": [fmt_n_compact(int(x)) for x in df_sub[n_col].to_list()],
    })

def draw_heatmap_with_label_table(
    df_meta: pd.DataFrame,
    matrix: np.ndarray,
    col_labels: List[str],
    title: str,
    out_path: str,
    annotate_fmt,
    cbar_label: str,
    use_log: bool,
    vmin: float,
    vmax: float,
    note: Optional[str] = None,
):
    nrows, ncols = matrix.shape

    # 只影响颜色显示，不改变标注数值
    M_show = np.clip(matrix, vmin, vmax)

    fig_w = max(MIN_FIG_W, 1.0 * ncols + 4.8)
    fig_h = max(MIN_FIG_H, 0.65 * nrows + 1.8)

    fig = plt.figure(figsize=(fig_w, fig_h))
    gs = gridspec.GridSpec(1, 2, width_ratios=[LABEL_TABLE_WIDTH_RATIO, HEATMAP_WIDTH_RATIO], wspace=0.02)

    ax_lbl = fig.add_subplot(gs[0, 0])
    ax = fig.add_subplot(gs[0, 1])

    norm = LogNorm(vmin=vmin, vmax=vmax) if use_log else None
    im = ax.imshow(M_show, aspect="auto", cmap=CMAP_FAST_BRIGHT, norm=norm)

    ax.set_title(title, fontsize=14, pad=10)
    ax.set_xticks(np.arange(ncols))
    ax.set_xticklabels(col_labels, rotation=30, ha="right", fontsize=10)

    ax.set_yticks(np.arange(nrows))
    ax.set_yticklabels([""] * nrows)

    # 网格线
    ax.set_xticks(np.arange(-0.5, ncols, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, nrows, 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.2)
    ax.tick_params(which="minor", bottom=False, left=False)

    # 标注真实值
    for i in range(nrows):
        for j in range(ncols):
            v = matrix[i, j]
            txt = "NA" if (not np.isfinite(v)) else annotate_fmt(v)
            ax.text(j, i, txt, ha="center", va="center", fontsize=8.5, fontweight="bold")

    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label(cbar_label, fontsize=10)

    if note:
        ax.text(0.0, 1.01, note, transform=ax.transAxes, fontsize=9.5, va="bottom")

    # 左侧标签表
    ax_lbl.set_xlim(0, 3)
    ax_lbl.set_ylim(nrows - 0.5, -0.5)
    ax_lbl.axis("off")

    ax_lbl.text(0.05, -0.9, "dist", fontsize=11, fontweight="bold")
    ax_lbl.text(1.10, -0.9, "type", fontsize=11, fontweight="bold")
    ax_lbl.text(2.05, -0.9, "n", fontsize=11, fontweight="bold")

    for i, r in enumerate(df_meta.itertuples(index=False)):
        ax_lbl.text(0.05, i, str(r.dist), fontsize=9.5, va="center")
        ax_lbl.text(1.10, i, str(r.type), fontsize=9.5, va="center")
        ax_lbl.text(2.05, i, str(r.n), fontsize=9.5, va="center")

    for i in range(nrows + 1):
        y = i - 0.5
        ax_lbl.plot([0, 3], [y, y], linewidth=1.0, color="white")

    plt.tight_layout()
    plt.savefig(out_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)

    print(f"[OK] {out_path}")

# =========================
# Main
# =========================
def main():
    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"CSV not found: {CSV_PATH}")

    # 输出目录
    dir_total = os.path.join(OUTPUT_ROOT, "total")
    dir_ms_split = os.path.join(OUTPUT_ROOT, "by_elements", "ms")
    dir_ratio_split = os.path.join(OUTPUT_ROOT, "by_elements", "ratio_vs_simd")
    ensure_dir(dir_total)
    ensure_dir(dir_ms_split)
    ensure_dir(dir_ratio_split)

    df = pd.read_csv(CSV_PATH)

    # 元数据列
    dist_col, type_col, n_col = pick_meta_columns(df)
    df = df.copy()
    df[n_col] = pd.to_numeric(df[n_col], errors="raise").astype(np.int64)

    meta_cols = [dist_col, type_col, n_col]
    algo_cols = infer_algo_cols(df, meta_cols)
    if not algo_cols:
        raise ValueError("未检测到算法数值列。")

    algo_cols = order_algo_cols(algo_cols)

    if BASELINE_COL not in algo_cols:
        raise ValueError(f"基准列 '{BASELINE_COL}' 不在算法列中: {algo_cols}")

    # 保持全局稳定排序（总图和子图都从这套顺序切）
    df = df.sort_values([dist_col, type_col, n_col]).reset_index(drop=True)

    # -------- 总矩阵 --------
    M_ms_all = df[algo_cols].to_numpy(dtype=float)

    baseline_all = df[BASELINE_COL].to_numpy(dtype=float)
    baseline_all = np.where(baseline_all == 0, np.nan, baseline_all)
    M_ratio_all = M_ms_all / baseline_all[:, None]

    meta_all = build_meta_table(df, dist_col, type_col, n_col)

    # -------- 用“总图”计算全局色标（关键）--------
    ms_vmin, ms_vmax = compute_scale_from_total(
        M_ms_all, MS_USE_LOG, MS_CLIP_LOW_PERCENTILE, MS_CLIP_HIGH_PERCENTILE, MS_VMIN_FLOOR
    )
    ratio_vmin, ratio_vmax = compute_scale_from_total(
        M_ratio_all, RATIO_USE_LOG, RATIO_CLIP_LOW_PERCENTILE, RATIO_CLIP_HIGH_PERCENTILE, RATIO_VMIN_FLOOR
    )

    print(f"[Global MS Scale]    vmin={ms_vmin:.6g}, vmax={ms_vmax:.6g} "
          f"(p{MS_CLIP_LOW_PERCENTILE}~p{MS_CLIP_HIGH_PERCENTILE}, log={MS_USE_LOG})")
    print(f"[Global Ratio Scale] vmin={ratio_vmin:.6g}, vmax={ratio_vmax:.6g} "
          f"(p{RATIO_CLIP_LOW_PERCENTILE}~p{RATIO_CLIP_HIGH_PERCENTILE}, log={RATIO_USE_LOG})")

    # -------- 画总图 --------
    draw_heatmap_with_label_table(
        df_meta=meta_all,
        matrix=M_ms_all,
        col_labels=algo_cols,
        title="Sorting Time Heatmap (ALL elements) — brighter=faster",
        out_path=os.path.join(dir_total, "heatmap_ms_all.png"),
        annotate_fmt=lambda x: f"{x:.1f}",
        cbar_label="Time (ms)  ↓ faster",
        use_log=MS_USE_LOG,
        vmin=ms_vmin,
        vmax=ms_vmax,
        note=f"Global color scale from ALL rows: p{MS_CLIP_LOW_PERCENTILE}~p{MS_CLIP_HIGH_PERCENTILE}",
    )

    draw_heatmap_with_label_table(
        df_meta=meta_all,
        matrix=M_ratio_all,
        col_labels=algo_cols,
        title=f"Ratio Heatmap (ALL elements, time/{BASELINE_COL}) — brighter=faster",
        out_path=os.path.join(dir_total, "heatmap_ratio_all.png"),
        annotate_fmt=lambda x: f"{x:.2f}",
        cbar_label=f"Ratio (×{BASELINE_COL})  ↓ faster",
        use_log=RATIO_USE_LOG,
        vmin=ratio_vmin,
        vmax=ratio_vmax,
        note=f"Global color scale from ALL rows: p{RATIO_CLIP_LOW_PERCENTILE}~p{RATIO_CLIP_HIGH_PERCENTILE}",
    )

    # -------- 画按 elements 拆分的子图（复用总图色标）--------
    unique_elements = sorted(df[n_col].unique().tolist())

    for elem in unique_elements:
        sub = df[df[n_col] == elem].copy()
        # 保持与总图一致的行内顺序（同样按 dist/type）
        sub = sub.sort_values([dist_col, type_col]).reset_index(drop=True)

        if sub.empty:
            continue

        elem_str = str(int(elem))
        elem_show = fmt_n_compact(int(elem))

        M_ms_sub = sub[algo_cols].to_numpy(dtype=float)
        baseline_sub = sub[BASELINE_COL].to_numpy(dtype=float)
        baseline_sub = np.where(baseline_sub == 0, np.nan, baseline_sub)
        M_ratio_sub = M_ms_sub / baseline_sub[:, None]

        meta_sub = build_meta_table(sub, dist_col, type_col, n_col)

        # ms 子图（用总图 ms 的 vmin/vmax）
        draw_heatmap_with_label_table(
            df_meta=meta_sub,
            matrix=M_ms_sub,
            col_labels=algo_cols,
            title=f"Sorting Time Heatmap (n={elem_show}) — same scale as ALL",
            out_path=os.path.join(dir_ms_split, f"heatmap_ms_n{elem_str}.png"),
            annotate_fmt=lambda x: f"{x:.1f}",
            cbar_label="Time (ms)  ↓ faster",
            use_log=MS_USE_LOG,
            vmin=ms_vmin,   # 关键：固定全局
            vmax=ms_vmax,   # 关键：固定全局
            note="Using GLOBAL scale from ALL-elements heatmap",
        )

        # ratio 子图（用总图 ratio 的 vmin/vmax）
        draw_heatmap_with_label_table(
            df_meta=meta_sub,
            matrix=M_ratio_sub,
            col_labels=algo_cols,
            title=f"Ratio Heatmap (n={elem_show}, time/{BASELINE_COL}) — same scale as ALL",
            out_path=os.path.join(dir_ratio_split, f"heatmap_ratio_n{elem_str}.png"),
            annotate_fmt=lambda x: f"{x:.2f}",
            cbar_label=f"Ratio (×{BASELINE_COL})  ↓ faster",
            use_log=RATIO_USE_LOG,
            vmin=ratio_vmin,   # 关键：固定全局
            vmax=ratio_vmax,   # 关键：固定全局
            note="Using GLOBAL scale from ALL-elements heatmap",
        )

    print("\nDone.")
    print(f"Output root: {os.path.abspath(OUTPUT_ROOT)}")
    print("  total/")
    print("    - heatmap_ms_all.png")
    print("    - heatmap_ratio_all.png")
    print("  by_elements/ms/")
    print("    - heatmap_ms_n*.png")
    print("  by_elements/ratio_vs_simd/")
    print("    - heatmap_ratio_n*.png")


if __name__ == "__main__":
    main()
