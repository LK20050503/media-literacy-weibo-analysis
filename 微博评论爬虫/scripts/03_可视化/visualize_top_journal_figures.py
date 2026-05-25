#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Create clean top-journal-style 4:3 PNG figures.

Design requirements:
- no chart titles, conclusion annotations, or watermarks
- Chinese: SimSun; English/numbers: Times New Roman
- reference pastel palette
- consistent bar widths
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.font_manager import FontProperties


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "outputs" / "01_核心数据" / "weibo_comments_analysis_coded.csv"
OUT_DIR = ROOT / "outputs" / "03_最终图表PNG" / "论文单图_png_顶刊版"

POST_ORDER = ["P1", "P2", "P3", "P4"]
POST_LABELS = {
    "P1": "P1\n李首条指控",
    "P2": "P2\n单初步回应",
    "P3": "P3\n李后续证据",
    "P4": "P4\n单正式道歉",
}

STANCE_ORDER = ["支持李方", "支持单方", "中立观望", "反网暴/反平台", "双方都批评", "无关/无法判断"]
EVIDENCE_ORDER = ["无明确依据", "个人情绪或印象", "法律版权概念", "过往旧闻", "当事人原话", "授权事实"]
DISCOURSE_ORDER = ["粉圈化攻击或维护", "道德化评价", "娱乐化调侃", "法律化论证", "劝和纠偏", "关系化解读"]
LITERACY_ORDER = ["较低", "中等", "较高"]

# Colors adapted from the reference image.
CORAL = "#FE8E8D"
LAVENDER = "#A7A2F6"
BLUE = "#81B9DC"
TEAL = "#03AAA2"
MAUVE = "#B9ADD3"
PINK = "#F5C3DC"
GREEN = "#D9EAC6"
YELLOW = "#F6D36F"
GRAY = "#B8B8B8"
INK = "#202A30"
AXIS = "#58616A"
GRID = "#E7ECF1"

STANCE_COLORS = {
    "支持李方": BLUE,
    "支持单方": CORAL,
    "中立观望": GREEN,
    "反网暴/反平台": TEAL,
    "双方都批评": YELLOW,
    "无关/无法判断": MAUVE,
}

CHINESE_FP = FontProperties(family="SimSun")
EN_FP = FontProperties(family="Times New Roman")


def setup_style() -> None:
    mpl.rcParams["font.family"] = ["Times New Roman", "SimSun"]
    mpl.rcParams["axes.unicode_minus"] = False
    mpl.rcParams["figure.dpi"] = 200
    mpl.rcParams["savefig.dpi"] = 200
    mpl.rcParams["pdf.fonttype"] = 42
    mpl.rcParams["ps.fonttype"] = 42


def read_rows() -> list[dict[str, str]]:
    with open(INPUT, "r", encoding="utf-8-sig", newline="") as f:
        return [row for row in csv.DictReader(f) if row.get("content_valid_for_coding") == "1"]


def figure() -> tuple[plt.Figure, plt.Axes]:
    fig = plt.figure(figsize=(9.6, 7.2), facecolor="white")
    ax = fig.add_axes([0.14, 0.15, 0.78, 0.74])
    return fig, ax


def clean_axes(ax: plt.Axes, grid_axis: str = "x") -> None:
    ax.set_facecolor("white")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for side in ["left", "bottom"]:
        ax.spines[side].set_color("#B8C1CA")
        ax.spines[side].set_linewidth(1.0)
    ax.tick_params(axis="both", colors=AXIS, labelsize=12, length=3.5, width=0.8)
    if grid_axis:
        ax.grid(axis=grid_axis, color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)


def set_tick_fonts(ax: plt.Axes, chinese_x: bool = True, chinese_y: bool = True) -> None:
    for label in ax.get_xticklabels():
        label.set_fontproperties(CHINESE_FP if chinese_x else EN_FP)
        label.set_fontweight("bold")
    for label in ax.get_yticklabels():
        label.set_fontproperties(CHINESE_FP if chinese_y else EN_FP)
        label.set_fontweight("bold")


def save(fig: plt.Figure, filename: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_DIR / filename, facecolor="white")
    plt.close(fig)


def fig_stance(rows: list[dict[str, str]]) -> None:
    by_post: dict[str, Counter[str]] = defaultdict(Counter)
    totals = Counter()
    for row in rows:
        post = row["post_id"]
        by_post[post][row["stance"]] += 1
        totals[post] += 1

    fig = plt.figure(figsize=(9.6, 7.2), facecolor="white")
    ax = fig.add_axes([0.14, 0.24, 0.78, 0.64])
    clean_axes(ax, grid_axis="y")

    x = np.arange(len(POST_ORDER))
    bottom = np.zeros(len(POST_ORDER))
    width = 0.56
    for stance in STANCE_ORDER:
        values = np.array([by_post[p][stance] / totals[p] * 100 for p in POST_ORDER])
        ax.bar(
            x,
            values,
            bottom=bottom,
            width=width,
            color=STANCE_COLORS[stance],
            edgecolor="white",
            linewidth=1.0,
            label=stance,
        )
        bottom += values

    ax.set_ylim(0, 100)
    ax.set_xlim(-0.5, len(POST_ORDER) - 0.5)
    ax.set_xticks(x)
    ax.set_xticklabels([POST_LABELS[p] for p in POST_ORDER], fontsize=12)
    ax.set_yticks(np.arange(0, 101, 20))
    ax.set_ylabel("比例 (%)", fontproperties=CHINESE_FP, fontsize=13, fontweight="bold", color=AXIS)
    set_tick_fonts(ax, chinese_x=True, chinese_y=False)
    legend = ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.12),
        ncol=3,
        frameon=False,
        prop=CHINESE_FP,
        fontsize=10.5,
        columnspacing=1.4,
        handlelength=1.4,
    )
    for text in legend.get_texts():
        text.set_color(INK)
        text.set_fontweight("bold")
    save(fig, "a_评论立场分布.png")


def horizontal_bar(
    rows: list[dict[str, str]],
    field: str,
    order: list[str],
    filename: str,
    panel: str,
    colors: list[str],
) -> None:
    counter = Counter(row[field] for row in rows)
    data = sorted([(name, counter[name]) for name in order], key=lambda item: item[1])
    labels = [item[0] for item in data]
    values = [item[1] for item in data]
    total = sum(values)

    fig, ax = figure()
    clean_axes(ax, grid_axis="x")

    y = np.arange(len(labels))
    height = 0.48
    ax.barh(y, values, height=height, color=colors[: len(labels)], edgecolor="none")
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=13)
    ax.set_xlim(0, max(values) * 1.22)
    ax.set_xlabel("数量", fontproperties=CHINESE_FP, fontsize=13, fontweight="bold", color=AXIS)
    set_tick_fonts(ax, chinese_x=False, chinese_y=True)

    offset = max(values) * 0.018
    for yi, value in zip(y, values):
        ax.text(
            value + offset,
            yi,
            f"{value} ({value / total * 100:.1f}%)",
            va="center",
            ha="left",
            fontproperties=EN_FP,
            fontweight="bold",
            fontsize=11.5,
            color=INK,
        )
    save(fig, filename)


def fig_heatmap(rows: list[dict[str, str]]) -> None:
    matrix = np.zeros((len(LITERACY_ORDER), len(EVIDENCE_ORDER)), dtype=int)
    literacy_index = {name: i for i, name in enumerate(LITERACY_ORDER)}
    evidence_index = {name: i for i, name in enumerate(EVIDENCE_ORDER)}
    for row in rows:
        matrix[literacy_index[row["media_literacy"]], evidence_index[row["evidence_type"]]] += 1

    fig, ax = figure()
    cmap = LinearSegmentedColormap.from_list("ref_teal", ["#F7FBFB", GREEN, BLUE, TEAL])
    im = ax.imshow(matrix, cmap=cmap, aspect="auto")

    ax.set_xticks(np.arange(len(EVIDENCE_ORDER)))
    ax.set_yticks(np.arange(len(LITERACY_ORDER)))
    ax.set_xticklabels(EVIDENCE_ORDER, rotation=28, ha="right", fontsize=11.5)
    ax.set_yticklabels(LITERACY_ORDER, fontsize=13)
    set_tick_fonts(ax, chinese_x=True, chinese_y=True)
    ax.tick_params(axis="both", length=0, colors=AXIS)
    for spine in ax.spines.values():
        spine.set_visible(False)

    ax.set_xticks(np.arange(-0.5, len(EVIDENCE_ORDER), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(LITERACY_ORDER), 1), minor=True)
    ax.grid(which="minor", color="white", linestyle="-", linewidth=2.2)
    ax.tick_params(which="minor", bottom=False, left=False)

    max_value = matrix.max()
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            value = matrix[i, j]
            color = "white" if value > max_value * 0.48 else INK
            ax.text(j, i, f"{value}", ha="center", va="center", fontproperties=EN_FP, fontweight="bold", fontsize=12, color=color)

    cbar = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.025)
    cbar.outline.set_visible(False)
    cbar.ax.tick_params(labelsize=10, colors=AXIS, length=2)
    for label in cbar.ax.get_yticklabels():
        label.set_fontproperties(EN_FP)
        label.set_fontweight("bold")
    save(fig, "d_证据类型与媒介素养热力图.png")


def main() -> int:
    setup_style()
    rows = read_rows()
    fig_stance(rows)
    horizontal_bar(
        rows,
        "evidence_type",
        EVIDENCE_ORDER,
        "b_论证依据分布.png",
        "b",
        [GRAY, MAUVE, BLUE, GREEN, LAVENDER, CORAL],
    )
    horizontal_bar(
        rows,
        "discourse_strategy",
        DISCOURSE_ORDER,
        "c_话语策略分布.png",
        "c",
        [GREEN, MAUVE, BLUE, LAVENDER, CORAL, TEAL],
    )
    fig_heatmap(rows)
    for path in sorted(OUT_DIR.glob("*.png")):
        print(f"[OK] {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
