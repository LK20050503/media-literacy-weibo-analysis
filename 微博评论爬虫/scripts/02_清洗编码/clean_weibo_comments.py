#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Create analysis-ready Weibo comments CSV without modifying source files.
"""

from __future__ import annotations

import argparse
import csv
import html
import re
from collections import Counter
from pathlib import Path
from typing import Any


URL_RE = re.compile(r"https?://\S+|http://t\.cn/\S+|t\.cn/\S+", re.I)
MENTION_RE = re.compile(r"@[\w\u4e00-\u9fff_-]+")
TOPIC_RE = re.compile(r"#([^#]{1,80})#")
EMOJI_RE = re.compile(r"\[[^\[\]]{1,12}\]")
HTML_TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"[ \t\r\f\v]+")
MULTI_NEWLINE_RE = re.compile(r"\n{2,}")


LOW_INFO_EXACT = {
    "图片评论",
    "转发微博",
}

MEANINGFUL_SHORT_PATTERNS = re.compile(
    r"支持|维权|道歉|侵权|版权|原创|尊重|抄袭|告|错|骂|牛|酷|力挺|活该|心疼|离谱|无语|加油|别骂|别吵|理性|赔偿|证据|粉丝|团队|主办方"
)


OUTPUT_FIELDS = [
    "sample_id",
    "post_id",
    "post_type",
    "post_published_at",
    "post_url",
    "status_id",
    "comment_id",
    "comment_time",
    "like_count",
    "source_order",
    "flow",
    "crawl_time",
    "comment_text",
    "text_clean",
    "text_length",
    "has_url",
    "url_count",
    "has_topic",
    "topic_tokens",
    "has_mention",
    "mention_count",
    "has_emoji",
    "emoji_tokens",
    "is_numeric_only",
    "is_exact_low_info",
    "is_single_char_low_info",
    "is_low_info",
    "low_info_reason",
    "content_valid_for_coding",
    "duplicate_text_count",
    "is_duplicate_text",
    "stance",
    "responsibility",
    "evidence_type",
    "discourse_strategy",
    "emotion_level",
    "media_literacy",
    "coder_note",
]


def normalize_basic(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = HTML_TAG_RE.sub("", text)
    text = text.replace("\u200b", "").replace("\ufeff", "")
    text = SPACE_RE.sub(" ", text)
    text = MULTI_NEWLINE_RE.sub("\n", text)
    return text.strip()


def make_clean_text(text: str) -> tuple[str, dict[str, Any]]:
    normalized = normalize_basic(text)
    urls = URL_RE.findall(normalized)
    topics = TOPIC_RE.findall(normalized)
    mentions = MENTION_RE.findall(normalized)
    emojis = EMOJI_RE.findall(normalized)

    clean = URL_RE.sub("", normalized)
    clean = MENTION_RE.sub("[用户提及]", clean)
    # Keep topic text but remove wrapping # to improve word segmentation later.
    clean = TOPIC_RE.sub(lambda m: m.group(1), clean)
    clean = SPACE_RE.sub(" ", clean)
    clean = MULTI_NEWLINE_RE.sub("\n", clean)
    clean = clean.strip()

    features = {
        "has_url": int(bool(urls)),
        "url_count": len(urls),
        "has_topic": int(bool(topics)),
        "topic_tokens": ";".join(topics),
        "has_mention": int(bool(mentions)),
        "mention_count": len(mentions),
        "has_emoji": int(bool(emojis)),
        "emoji_tokens": ";".join(emojis),
    }
    return clean, features


def is_low_info_text(text_clean: str) -> tuple[int, str, dict[str, int]]:
    compact = re.sub(r"\s+", "", text_clean)
    is_numeric_only = int(bool(compact and re.fullmatch(r"\d+", compact)))
    is_exact_low_info = int(compact in LOW_INFO_EXACT)
    is_single_char_low_info = int(
        bool(re.fullmatch(r"[A-Za-z0-9一二三四五六七八九十]+", compact))
        and not MEANINGFUL_SHORT_PATTERNS.search(compact)
        and len(compact) <= 2
    )

    reason = ""
    if not compact:
        reason = "empty_after_cleaning"
    elif is_numeric_only:
        reason = "numeric_only"
    elif is_exact_low_info:
        reason = "exact_low_info"
    elif is_single_char_low_info:
        reason = "single_char_low_info"

    return (
        int(bool(reason)),
        reason,
        {
            "is_numeric_only": is_numeric_only,
            "is_exact_low_info": is_exact_low_info,
            "is_single_char_low_info": is_single_char_low_info,
        },
    )


def load_rows(path: Path) -> list[dict[str, str]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_analysis_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    cleaned_texts: list[str] = []
    staged: list[dict[str, Any]] = []

    for row in rows:
        text_clean, features = make_clean_text(row.get("comment_text", ""))
        low_info, reason, low_info_flags = is_low_info_text(text_clean)
        staged_row: dict[str, Any] = {
            **row,
            "text_clean": text_clean,
            "text_length": len(text_clean),
            **features,
            **low_info_flags,
            "is_low_info": low_info,
            "low_info_reason": reason,
            "content_valid_for_coding": 0 if low_info else 1,
            "stance": "",
            "responsibility": "",
            "evidence_type": "",
            "discourse_strategy": "",
            "emotion_level": "",
            "media_literacy": "",
            "coder_note": "",
        }
        staged.append(staged_row)
        cleaned_texts.append(text_clean)

    duplicate_counts = Counter(cleaned_texts)
    for row in staged:
        count = duplicate_counts[row["text_clean"]]
        row["duplicate_text_count"] = count
        row["is_duplicate_text"] = int(count > 1)
    return staged


def write_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    post_counts = Counter(row["post_id"] for row in rows)
    valid_counts = Counter(
        row["post_id"] for row in rows if str(row["content_valid_for_coding"]) == "1"
    )
    low_reasons = Counter(row["low_info_reason"] for row in rows if row["low_info_reason"])
    flow_counts = Counter(row["flow"] for row in rows)

    lines = [
        "# 数据清洗结果记录",
        "",
        "## 一、总体结果",
        "",
        f"- 总评论数：{len(rows)}",
        f"- 进入正式编码的评论数：{sum(1 for row in rows if str(row['content_valid_for_coding']) == '1')}",
        f"- 标记为低信息的评论数：{sum(1 for row in rows if str(row['is_low_info']) == '1')}",
        f"- 含短链接评论数：{sum(1 for row in rows if str(row['has_url']) == '1')}",
        f"- 含话题评论数：{sum(1 for row in rows if str(row['has_topic']) == '1')}",
        f"- 含用户提及评论数：{sum(1 for row in rows if str(row['has_mention']) == '1')}",
        f"- 含微博表情评论数：{sum(1 for row in rows if str(row['has_emoji']) == '1')}",
        f"- 重复清洗文本组数：{len([1 for _, c in Counter(row['text_clean'] for row in rows).items() if c > 1])}",
        "",
        "## 二、各帖子样本量",
        "",
        "| 帖子 | 总数 | 进入编码 |",
        "| --- | ---: | ---: |",
    ]
    for post_id in sorted(post_counts):
        lines.append(f"| {post_id} | {post_counts[post_id]} | {valid_counts[post_id]} |")

    lines.extend(
        [
            "",
            "## 三、低信息原因分布",
            "",
            "| 原因 | 数量 |",
            "| --- | ---: |",
        ]
    )
    for reason, count in low_reasons.most_common():
        lines.append(f"| {reason} | {count} |")

    lines.extend(
        [
            "",
            "## 四、接口来源分布",
            "",
            "| flow | 数量 |",
            "| --- | ---: |",
        ]
    )
    for flow, count in flow_counts.most_common():
        lines.append(f"| {flow} | {count} |")

    lines.extend(
        [
            "",
            "## 五、使用说明",
            "",
            "正式人工编码建议筛选 `content_valid_for_coding = 1` 的评论；原始评论仍保留在 `comment_text`，标准化文本在 `text_clean`。",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Clean Weibo comments for coding.")
    parser.add_argument(
        "--input",
        default="data_mobile_hotflow/weibo_comments_clean.csv",
        help="Source clean CSV from crawler.",
    )
    parser.add_argument(
        "--output",
        default="outputs/01_核心数据/weibo_comments_analysis.csv",
        help="Analysis-ready CSV output.",
    )
    parser.add_argument(
        "--summary",
        default="outputs/02_摘要与交叉表/cleaning_summary.md",
        help="Cleaning summary markdown.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    source = Path(args.input)
    output = Path(args.output)
    summary = Path(args.summary)
    rows = load_rows(source)
    analysis_rows = build_analysis_rows(rows)
    write_rows(output, analysis_rows)
    write_summary(summary, analysis_rows)
    print(f"[DONE] output: {output}")
    print(f"[DONE] summary: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
