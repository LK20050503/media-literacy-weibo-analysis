#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Merge DeepSeek coding results back into the cleaned comment table."""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path


CODING_FIELDS = [
    "stance",
    "responsibility",
    "evidence_type",
    "discourse_strategy",
    "emotion_level",
    "media_literacy",
    "coder_note",
]

CODING_META_FIELDS = ["model", "coded_at"]


def read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def pct(part: int, whole: int) -> str:
    if not whole:
        return "0.00%"
    return f"{part / whole * 100:.2f}%"


def markdown_count_table(title: str, counter: Counter[str], total: int) -> list[str]:
    lines = [f"## {title}", "", "| 类别 | 数量 | 占比 |", "| --- | ---: | ---: |"]
    for name, count in counter.most_common():
        lines.append(f"| {name} | {count} | {pct(count, total)} |")
    lines.append("")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge coding results and summarize distributions.")
    parser.add_argument("--analysis", default="outputs/01_核心数据/weibo_comments_analysis.csv")
    parser.add_argument("--coding", default="outputs/01_核心数据/weibo_comments_coded_deepseek.csv")
    parser.add_argument("--merged", default="outputs/01_核心数据/weibo_comments_analysis_coded.csv")
    parser.add_argument("--summary", default="outputs/02_摘要与交叉表/coding_summary.md")
    parser.add_argument("--crosstab", default="outputs/02_摘要与交叉表/coding_crosstabs_by_post.csv")
    args = parser.parse_args()

    analysis_path = Path(args.analysis)
    coding_path = Path(args.coding)
    merged_path = Path(args.merged)
    summary_path = Path(args.summary)
    crosstab_path = Path(args.crosstab)

    analysis_rows = read_csv(analysis_path)
    coding_rows = read_csv(coding_path)

    coding_by_id: dict[str, dict[str, str]] = {}
    duplicate_ids: list[str] = []
    for row in coding_rows:
        sample_id = row["sample_id"]
        if sample_id in coding_by_id:
            duplicate_ids.append(sample_id)
        else:
            coding_by_id[sample_id] = row

    valid_ids = {row["sample_id"] for row in analysis_rows if row.get("content_valid_for_coding") == "1"}
    coded_ids = set(coding_by_id)
    missing_ids = sorted(valid_ids - coded_ids)
    extra_ids = sorted(coded_ids - valid_ids)

    if duplicate_ids:
        raise RuntimeError(f"duplicate coded sample_id count={len(duplicate_ids)}")
    if missing_ids:
        raise RuntimeError(f"missing coded valid comments count={len(missing_ids)} first={missing_ids[:10]}")
    if extra_ids:
        raise RuntimeError(f"coding file contains sample_ids not valid for coding count={len(extra_ids)} first={extra_ids[:10]}")

    fieldnames = list(analysis_rows[0].keys())
    for field in CODING_META_FIELDS:
        if field not in fieldnames:
            fieldnames.append(field)

    for row in analysis_rows:
        coded = coding_by_id.get(row["sample_id"])
        if not coded:
            continue
        for field in CODING_FIELDS:
            row[field] = coded.get(field, "")
        row["model"] = coded.get("model", "")
        row["coded_at"] = coded.get("coded_at", "")

    write_csv(merged_path, analysis_rows, fieldnames)

    coded_analysis_rows = [row for row in analysis_rows if row["sample_id"] in coding_by_id]
    total_coded = len(coded_analysis_rows)

    lines: list[str] = [
        "# 微博评论 DeepSeek 编码结果摘要",
        "",
        "## 数据完整性",
        "",
        f"- 清洗后总评论数：{len(analysis_rows)}",
        f"- 进入正式编码评论数：{len(valid_ids)}",
        f"- 已完成编码评论数：{len(coding_by_id)}",
        f"- 未进入编码的低信息评论数：{len(analysis_rows) - len(valid_ids)}",
        f"- 重复 sample_id：{len(duplicate_ids)}",
        "",
    ]

    for field, title in [
        ("stance", "立场倾向"),
        ("responsibility", "责任归因"),
        ("evidence_type", "论证依据"),
        ("discourse_strategy", "话语策略"),
        ("emotion_level", "情绪强度"),
        ("media_literacy", "媒介素养表现"),
    ]:
        lines.extend(markdown_count_table(title, Counter(row[field] for row in coded_analysis_rows), total_coded))

    post_counts: dict[str, Counter[str]] = defaultdict(Counter)
    post_labels: dict[str, str] = {}
    for row in coded_analysis_rows:
        post_id = row["post_id"]
        post_labels[post_id] = row.get("post_type", "")
        for field in ["stance", "responsibility", "evidence_type", "discourse_strategy", "emotion_level", "media_literacy"]:
            post_counts[(post_id, field)][row[field]] += 1

    lines.extend(["## 按帖子编码数量", "", "| 帖子 | 文本类型 | 编码数 |", "| --- | --- | ---: |"])
    for post_id in sorted({row["post_id"] for row in coded_analysis_rows}):
        count = sum(1 for row in coded_analysis_rows if row["post_id"] == post_id)
        lines.append(f"| {post_id} | {post_labels.get(post_id, '')} | {count} |")
    lines.append("")

    summary_path.write_text("\n".join(lines), encoding="utf-8")

    crosstab_rows: list[dict[str, str]] = []
    for (post_id, field), counter in sorted(post_counts.items()):
        total = sum(counter.values())
        for category, count in counter.most_common():
            crosstab_rows.append(
                {
                    "post_id": post_id,
                    "post_type": post_labels.get(post_id, ""),
                    "field": field,
                    "category": category,
                    "count": str(count),
                    "percent": pct(count, total),
                }
            )
    write_csv(crosstab_path, crosstab_rows, ["post_id", "post_type", "field", "category", "count", "percent"])

    print(f"[OK] merged={merged_path}")
    print(f"[OK] summary={summary_path}")
    print(f"[OK] crosstab={crosstab_path}")
    print(f"[OK] total={len(analysis_rows)} coded={len(coding_by_id)} low_info={len(analysis_rows)-len(valid_ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
