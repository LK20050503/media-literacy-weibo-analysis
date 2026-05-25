#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Batch-code cleaned Weibo comments with DeepSeek-compatible OpenAI SDK.

API key is read from DEEPSEEK_API_KEY. Do not hard-code it.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import random
import re
import sys
import time
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI


STANCE = {"支持李方", "支持单方", "双方都批评", "中立观望", "反网暴/反平台", "无关/无法判断"}
RESPONSIBILITY = {"单依纯本人", "单方团队或主办方", "李荣浩方", "版权机构或流程", "多方责任", "不明确"}
EVIDENCE_TYPE = {"授权事实", "法律版权概念", "当事人原话", "过往旧闻", "个人情绪或印象", "无明确依据"}
DISCOURSE_STRATEGY = {"法律化论证", "道德化评价", "关系化解读", "粉圈化攻击或维护", "娱乐化调侃", "劝和纠偏"}
EMOTION_LEVEL = {"低", "中", "高"}
MEDIA_LITERACY = {"较高", "中等", "较低"}


OUTPUT_FIELDS = [
    "sample_id",
    "stance",
    "responsibility",
    "evidence_type",
    "discourse_strategy",
    "emotion_level",
    "media_literacy",
    "coder_note",
    "model",
    "coded_at",
]


SYSTEM_PROMPT = """你是一名传播学与媒介素养研究中的内容分析编码员。你的任务是根据给定编码表，对微博评论进行一致、克制、可复核的分类编码。

你必须遵守以下原则：
1. 只根据评论文本和给定语境编码，不推断用户真实身份、粉籍、性别、年龄或动机。
2. 不判断事件法律真相，只判断评论如何表达立场、责任归因、依据、话语策略、情绪强度和媒介素养表现。
3. 必须从指定类别中选择，不能自创类别。
4. 短评如果有明确立场，如“支持维权”“支持李荣浩”，仍应编码，不得因为短而判为无效。
5. 在本事件语境下，明显表白、维护或赞许李荣浩/单依纯的一方，也应视为相应立场；只有完全看不出事件立场时才选“无关/无法判断”。
6. 输出必须是严格 JSON，不要输出解释性段落，不要输出 Markdown。"""


USER_PROMPT_PREFIX = """请根据下面的编码表，对一组微博评论逐条编码。

编码类别：

stance 只能取：支持李方 / 支持单方 / 双方都批评 / 中立观望 / 反网暴/反平台 / 无关/无法判断
responsibility 只能取：单依纯本人 / 单方团队或主办方 / 李荣浩方 / 版权机构或流程 / 多方责任 / 不明确
evidence_type 只能取：授权事实 / 法律版权概念 / 当事人原话 / 过往旧闻 / 个人情绪或印象 / 无明确依据
discourse_strategy 只能取：法律化论证 / 道德化评价 / 关系化解读 / 粉圈化攻击或维护 / 娱乐化调侃 / 劝和纠偏
emotion_level 只能取：低 / 中 / 高
media_literacy 只能取：较高 / 中等 / 较低

判断规则：
1. “支持维权”“支持原创”“尊重版权”等通常倾向于“支持李方”；如果没有明确责任主体，responsibility 选“不明确”。
2. 在争议语境下，单纯表白、维护或赞许李荣浩，通常编码为“支持李方”；单纯表白、维护或赞许单依纯，通常编码为“支持单方”；只有与事件毫无关系或无法判定具体对象时才选“无关/无法判断”。
3. 维护单依纯、强调“已道歉”“别再骂”“给她空间”等，如果核心是维护单方，stance 选“支持单方”；如果核心是反对网暴，选“反网暴/反平台”。
4. 评论提到未授权、书面授权、邮件、协会、版权公司、演唱会事实，evidence_type 优先选“授权事实”。
5. 评论提到侵权、违法、版权、赔偿、法律、授权规则，evidence_type 优先选“法律版权概念”。
6. 评论引用或转述李荣浩/单依纯原文，evidence_type 选“当事人原话”。
7. 评论使用旧作争议、抄袭、小眼睛、过往节目、导师学员关系等作为依据，evidence_type 选“过往旧闻”或 discourse_strategy 选“关系化解读”，视重点判断。
8. 评论使用粉丝群体标签、拉踩、辱骂、控评、水军等表达，discourse_strategy 选“粉圈化攻击或维护”；若攻击性强，emotion_level 选“高”，media_literacy 多数选“较低”。
9. 玩梗、吃瓜、哈哈哈、爽文式围观、单纯调侃，discourse_strategy 选“娱乐化调侃”。
10. 呼吁理性、等待证据、反对网暴、要求回到版权问题，discourse_strategy 选“劝和纠偏”，media_literacy 通常为“较高”或“中等”。
11. media_literacy 判断：
    - 较高：能引用可核查信息，区分事实与态度，理解版权合规或责任主体差异，表达克制，或反对网暴。
    - 中等：有明确观点但证据不足，或有一定情绪；没有明显造谣、攻击、煽动。
    - 较低：未经核实下结论，使用人身攻击、粉丝标签、阴谋猜测、旧闻牵连，或用嘲讽/辱骂替代论证。

请只输出严格 JSON，格式为：
{"items":[{"sample_id":"P1_000001","stance":"支持李方","responsibility":"不明确","evidence_type":"法律版权概念","discourse_strategy":"法律化论证","emotion_level":"低","media_literacy":"较高","coder_note":"强调版权与原创保护，支持维权"}]}

coder_note 用一句话说明判断依据，控制在40字以内。

待编码评论：
"""


def load_rows(path: Path, limit: int | None = None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("content_valid_for_coding") != "1":
                continue
            rows.append(row)
            if limit and len(rows) >= limit:
                break
    return rows


def load_existing(path: Path) -> set[str]:
    if not path.exists() or path.stat().st_size == 0:
        return set()
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return {row["sample_id"] for row in csv.DictReader(f) if row.get("sample_id")}


def ensure_output(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        return
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()


def append_results(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        return
    with open(path, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        writer.writerows(rows)


def chunked(rows: list[dict[str, str]], size: int) -> list[list[dict[str, str]]]:
    return [rows[i : i + size] for i in range(0, len(rows), size)]


def build_comments_payload(batch: list[dict[str, str]]) -> str:
    items = []
    for row in batch:
        items.append(
            {
                "sample_id": row["sample_id"],
                "post_id": row["post_id"],
                "post_type": row["post_type"],
                "text_clean": row["text_clean"],
                "has_emoji": row.get("has_emoji", "0"),
                "has_url": row.get("has_url", "0"),
                "duplicate_text_count": row.get("duplicate_text_count", "1"),
                "like_count": row.get("like_count", "0"),
            }
        )
    return json.dumps(items, ensure_ascii=False)


def extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def validate_item(item: dict[str, Any]) -> dict[str, str]:
    required = {
        "sample_id",
        "stance",
        "responsibility",
        "evidence_type",
        "discourse_strategy",
        "emotion_level",
        "media_literacy",
        "coder_note",
    }
    missing = required - item.keys()
    if missing:
        raise ValueError(f"missing fields: {missing}")
    checks = [
        ("stance", STANCE),
        ("responsibility", RESPONSIBILITY),
        ("evidence_type", EVIDENCE_TYPE),
        ("discourse_strategy", DISCOURSE_STRATEGY),
        ("emotion_level", EMOTION_LEVEL),
        ("media_literacy", MEDIA_LITERACY),
    ]
    for field, allowed in checks:
        if item[field] not in allowed:
            raise ValueError(f"{field}={item[field]!r} not allowed")
    note = str(item.get("coder_note") or "")[:80]
    return {
        "sample_id": str(item["sample_id"]),
        "stance": str(item["stance"]),
        "responsibility": str(item["responsibility"]),
        "evidence_type": str(item["evidence_type"]),
        "discourse_strategy": str(item["discourse_strategy"]),
        "emotion_level": str(item["emotion_level"]),
        "media_literacy": str(item["media_literacy"]),
        "coder_note": note,
    }


async def code_batch(
    client: AsyncOpenAI,
    batch: list[dict[str, str]],
    args: argparse.Namespace,
    semaphore: asyncio.Semaphore,
) -> list[dict[str, str]]:
    async with semaphore:
        prompt = USER_PROMPT_PREFIX + build_comments_payload(batch)
        last_error: Exception | None = None
        for attempt in range(1, args.max_retries + 1):
            try:
                kwargs: dict[str, Any] = {
                    "model": args.model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "temperature": args.temperature,
                    "extra_body": {"thinking": {"type": "enabled"}},
                }
                if args.reasoning_effort:
                    kwargs["reasoning_effort"] = args.reasoning_effort
                response = await client.chat.completions.create(**kwargs)
                content = response.choices[0].message.content or ""
                parsed = extract_json(content)
                items = parsed.get("items")
                if not isinstance(items, list):
                    raise ValueError("response JSON missing items list")
                validated = [validate_item(item) for item in items]
                expected_ids = {row["sample_id"] for row in batch}
                returned_ids = {row["sample_id"] for row in validated}
                if expected_ids != returned_ids:
                    raise ValueError(
                        f"sample_id mismatch missing={expected_ids-returned_ids} extra={returned_ids-expected_ids}"
                    )
                now = time.strftime("%Y-%m-%dT%H:%M:%S")
                for row in validated:
                    row["model"] = args.model
                    row["coded_at"] = now
                return validated
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                wait = min(90, 2**attempt + random.uniform(0.5, 2.5))
                print(
                    f"[WARN] batch {batch[0]['sample_id']}.. failed "
                    f"({attempt}/{args.max_retries}): {exc}; sleep {wait:.1f}s",
                    file=sys.stderr,
                )
                await asyncio.sleep(wait)
        raise RuntimeError(f"batch failed after retries: {last_error}")


async def run(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    output_path = Path(args.output)
    ensure_output(output_path)

    rows = load_rows(input_path, limit=args.limit)
    done_ids = load_existing(output_path)
    todo = [row for row in rows if row["sample_id"] not in done_ids]
    batches = chunked(todo, args.batch_size)
    print(
        f"[INFO] valid rows={len(rows)} already_done={len(done_ids)} "
        f"todo={len(todo)} batches={len(batches)}"
    )
    if args.dry_run:
        print("[DRY RUN] first prompt preview:")
        if batches:
            print(USER_PROMPT_PREFIX + build_comments_payload(batches[0]))
        return

    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not set")

    client = AsyncOpenAI(api_key=api_key, base_url=args.base_url)
    semaphore = asyncio.Semaphore(args.concurrency)
    lock = asyncio.Lock()
    completed = 0

    async def worker(batch: list[dict[str, str]]) -> None:
        nonlocal completed
        results = await code_batch(client, batch, args, semaphore)
        async with lock:
            append_results(output_path, results)
            completed += len(results)
            print(f"[PROGRESS] coded {completed}/{len(todo)}")

    await asyncio.gather(*(worker(batch) for batch in batches))
    print(f"[DONE] output: {output_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Batch code Weibo comments with DeepSeek.")
    parser.add_argument("--input", default="outputs/01_核心数据/weibo_comments_analysis.csv")
    parser.add_argument("--output", default="outputs/01_核心数据/weibo_comments_coded_deepseek.csv")
    parser.add_argument("--base-url", default="https://api.deepseek.com")
    parser.add_argument("--model", default=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro"))
    parser.add_argument("--reasoning-effort", default="high")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=50)
    parser.add_argument("--max-retries", type=int, default=4)
    parser.add_argument("--limit", type=int, help="Only load first N valid rows; useful for pilot.")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] partial output is kept.", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
