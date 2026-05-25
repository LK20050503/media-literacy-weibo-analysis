#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Create publication-style 4:3 PNG figures with the reference pastel palette."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "outputs" / "01_核心数据" / "weibo_comments_analysis_coded.csv"
OUT_DIR = ROOT / "outputs" / "04_历史图表版本" / "论文单图_png_高级版"

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

# Palette sampled from the reference image.
CORAL = "#FE8E8D"
LAVENDER = "#A7A2F6"
BLUE = "#81B9DC"
TEAL = "#03AAA2"
MAUVE = "#B9ADD3"
PINK = "#F5C3DC"
GREEN = "#D9EAC6"
GRAY = "#B8B8B8"
INK = "#263238"
MUTED = "#6D737A"
GRID = "#E9EDF2"

STANCE_COLORS = {
    "支持李方": BLUE,
    "支持单方": CORAL,
    "中立观望": GREEN,
    "反网暴/反平台": TEAL,
    "双方都批评": "#F26D6D",
    "无关/无法判断": MAUVE,
}
BAR_COLORS = [TEAL, CORAL, LAVENDER, BLUE, MAUVE, PINK, GREEN]


def setup_style() -> None:
    mpl.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial"]
    mpl.rcParams["axes.unicode_minus"] = False
    mpl.rcParams["figure.dpi"] = 200
    mpl.rcParams["savefig.dpi"] = 200
    mpl.rcParams["axes.edgecolor"] = "#BFC7CF"
    mpl.rcParams["xtick.color"] = "#4A4F55"
    mpl.rcParams["ytick.color"] = "#4A4F55"


def read_rows() -> list[dict[str, str]]:
    with open(INPUT, "r", encoding="utf-8-sig", newline="") as f:
        return [row for row in csv.DictReader(f) if row.get("content_valid_for_coding") == "1"]


def add_header(fig: plt.Figure, title: str, subtitle: str) -> None:
    fig.text(0.055, 0.94, title, ha="left", va="center", fontsize=23, fontweight="bold", color=INK)
    fig.text(0.055, 0.905, subtitle, ha="left", va="center", fontsize=12.5, color=MUTED)
    fig.text(0.946, 0.94, "微博评论编码", ha="right", va="center", fontsize=11, color="#87929E")


def clean_axes(ax: plt.Axes, xgrid: bool = True) -> None:
    ax.set_facecolor("#FFFFFF")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#BFC7CF")
    ax.spines["bottom"].set_color("#BFC7CF")
    ax.tick_params(axis="both", labelsize=11)
    if xgrid:
        ax.grid(axis="x", color=GRID, linewidth=1.1)
        ax.set_axisbelow(True)


def rounded_barh(ax: plt.Axes, y: np.ndarray, values: list[int], colors: list[str], height: float = 0.56) -> None:
    for yi, value, color in zip(y, values, colors):
        patch = FancyBboxPatch(
            (0, yi - height / 2),
            value,
            height,
            boxstyle=f"round,pad=0,rounding_size={height / 2}",
            linewidth=0,
            facecolor=color,
        )
        ax.add_patch(patch)


def save(fig: plt.Figure, filename: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_DIR / filename, bbox_inches=None, facecolor="white")
    plt.close(fig)


def fig_stance(rows: list[dict[str, str]]) -> None:
    by_post: dict[str, Counter[str]] = defaultdict(Counter)
    totals = Counter()
    for row in rows:
        post_id = row["post_id"]
        by_post[post_id][row["stance"]] += 1
        totals[post_id] += 1

    fig = plt.figure(figsize=(9.6, 7.2), facecolor="white")
    add_header(fig, "不同微博场景下的评论立场分布", "100% 堆叠柱形图显示：道歉微博下支持单方显著上升")
    ax = fig.add_axes([0.08, 0.18, 0.86, 0.63])
    clean_axes(ax, xgrid=False)

    x = np.arange(len(POST_ORDER))
    bottom = np.zeros(len(POST_ORDER))
    for stance in STANCE_ORDER:
        vals = np.array([by_post[p][stance] / totals[p] * 100 for p in POST_ORDER])
        ax.bar(
            x,
            vals,
            bottom=bottom,
            width=0.62,
            label=stance,
            color=STANCE_COLORS[stance],
            edgecolor="white",
            linewidth=1.6,
        )
        bottom += vals

    ax.set_ylim(0, 100)
    ax.set_ylabel("评论占比（%）", fontsize=12, color=MUTED)
    ax.set_xticks(x, [POST_LABELS[p] for p in POST_ORDER], fontsize=11)
    ax.set_yticks(np.arange(0, 101, 20))
    ax.grid(axis="y", color=GRID, linewidth=1.1)
    ax.set_axisbelow(True)
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.1),
        ncol=3,
        frameon=False,
        fontsize=10.5,
        handlelength=1.4,
        columnspacing=1.6,
    )

    p4_support_single = by_post["P4"]["支持单方"] / totals["P4"] * 100
    ax.annotate(
        f"道歉后支持单方\n{p4_support_single:.1f}%",
        xy=(3, p4_support_single / 2),
        xytext=(2.26, 61),
        arrowprops=dict(arrowstyle="-|>", color=CORAL, lw=1.6, connectionstyle="arc3,rad=-0.18"),
        fontsize=12,
        color="#D45E5E",
        fontweight="bold",
        ha="center",
    )
    save(fig, "图1_评论立场分布_高级版.png")


def fig_evidence(rows: list[dict[str, str]]) -> None:
    counter = Counter(row["evidence_type"] for row in rows)
    data = sorted([(name, counter[name]) for name in EVIDENCE_ORDER], key=lambda item: item[1])
    labels = [item[0] for item in data]
    values = [item[1] for item in data]
    total = sum(values)
    colors = [GRAY, MAUVE, BLUE, GREEN, LAVENDER, CORAL]

    fig = plt.figure(figsize=(9.6, 7.2), facecolor="white")
    add_header(fig, "评论论证依据分布", "无明确依据与个人情绪/印象合计超过八成，事实与法律依据相对不足")
    ax = fig.add_axes([0.2, 0.15, 0.72, 0.66])
    clean_axes(ax, xgrid=True)
    y = np.arange(len(labels))
    rounded_barh(ax, y, values, colors)
    ax.set_yticks(y, labels)
    ax.set_xlim(0, max(values) * 1.18)
    ax.set_xlabel("评论数量", fontsize=12, color=MUTED)
    for yi, value in zip(y, values):
        ax.text(value + max(values) * 0.015, yi, f"{value}  ({value / total * 100:.1f}%)", va="center", fontsize=11, color=INK)
    save(fig, "图2_论证依据分布_高级版.png")


def fig_discourse(rows: list[dict[str, str]]) -> None:
    counter = Counter(row["discourse_strategy"] for row in rows)
    data = sorted([(name, counter[name]) for name in DISCOURSE_ORDER], key=lambda item: item[1])
    labels = [item[0] for item in data]
    values = [item[1] for item in data]
    total = sum(values)
    colors = [GREEN, MAUVE, BLUE, LAVENDER, CORAL, TEAL]

    fig = plt.figure(figsize=(9.6, 7.2), facecolor="white")
    add_header(fig, "评论话语策略分布", "粉圈化攻击或维护、道德化评价占主导，版权议题被情绪化转译")
    ax = fig.add_axes([0.2, 0.15, 0.72, 0.66])
    clean_axes(ax, xgrid=True)
    y = np.arange(len(labels))
    rounded_barh(ax, y, values, colors)
    ax.set_yticks(y, labels)
    ax.set_xlim(0, max(values) * 1.18)
    ax.set_xlabel("评论数量", fontsize=12, color=MUTED)
    for yi, value in zip(y, values):
        ax.text(value + max(values) * 0.015, yi, f"{value}  ({value / total * 100:.1f}%)", va="center", fontsize=11, color=INK)
    save(fig, "图3_话语策略分布_高级版.png")


def fig_literacy(rows: list[dict[str, str]]) -> None:
    counter = Counter(row["media_literacy"] for row in rows)
    values = [counter[name] for name in LITERACY_ORDER]
    total = sum(values)
    colors = [CORAL, BLUE, TEAL]

    fig = plt.figure(figsize=(9.6, 7.2), facecolor="white")
    add_header(fig, "评论区媒介素养表现分布", "较低媒介素养评论占 69.0%，体现出证据意识与理性讨论不足")
    ax = fig.add_axes([0.16, 0.12, 0.68, 0.72])
    ax.set_aspect("equal")
    wedges, _ = ax.pie(
        values,
        startangle=96,
        counterclock=False,
        colors=colors,
        wedgeprops=dict(width=0.36, edgecolor="white", linewidth=4),
    )
    ax.text(0, 0.08, "较低", ha="center", va="center", fontsize=26, color=CORAL, fontweight="bold")
    ax.text(0, -0.1, f"{values[0] / total * 100:.1f}%", ha="center", va="center", fontsize=22, color=INK, fontweight="bold")

    label_positions = [(1.18, 0.48), (1.18, -0.02), (1.18, -0.52)]
    for (name, value, color), (lx, ly) in zip(zip(LITERACY_ORDER, values, colors), label_positions):
        ax.scatter([lx - 0.08], [ly], s=120, color=color)
        ax.text(lx, ly + 0.04, name, fontsize=14, fontweight="bold", color=INK, ha="left", va="center")
        ax.text(lx, ly - 0.12, f"{value} 条 / {value / total * 100:.1f}%", fontsize=12, color=MUTED, ha="left", va="center")
    ax.set_xlim(-1.28, 1.86)
    ax.set_ylim(-1.18, 1.18)
    ax.axis("off")
    save(fig, "图4_媒介素养表现分布_高级版.png")


def main() -> int:
    setup_style()
    rows = read_rows()
    fig_stance(rows)
    fig_evidence(rows)
    fig_discourse(rows)
    fig_literacy(rows)
    for path in sorted(OUT_DIR.glob("*.png")):
        print(f"[OK] {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
