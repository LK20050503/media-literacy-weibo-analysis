#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Explore multiple Weibo hot-comment cursor branches for selected posts.

This script is a companion to weibo_comment_crawler.py. The standard crawler
follows one hot-comment cursor chain. Weibo sometimes returns different hot
cursor branches for different parameter combinations, so this script traverses
those branches and merges unique top-level comments.
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import sys
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from weibo_comment_crawler import (
    RAW_FIELDS,
    WeiboCommentCrawler,
    WeiboCrawlerError,
    append_rows,
    comment_to_row,
    ensure_csv,
    load_posts,
    load_resume_state,
    make_clean_csv,
    read_cookie,
    write_post_metadata,
)


HOT_COMBOS = [
    {"flow": 0, "is_mix": 0, "fetch_level": 0},
    {"flow": 0, "is_mix": 1, "fetch_level": 0},
    {"flow": 0, "is_mix": 0, "fetch_level": 2},
    {"flow": 0, "is_mix": 1, "fetch_level": 2},
    {"flow": 2, "is_mix": 0, "fetch_level": 0},
    {"flow": 2, "is_mix": 1, "fetch_level": 0},
    {"flow": 2, "is_mix": 0, "fetch_level": 2},
    {"flow": 2, "is_mix": 1, "fetch_level": 2},
    {"flow": 3, "is_mix": 0, "fetch_level": 0},
    {"flow": 3, "is_mix": 1, "fetch_level": 0},
    {"flow": 3, "is_mix": 0, "fetch_level": 2},
    {"flow": 3, "is_mix": 1, "fetch_level": 2},
]


class BranchCrawler(WeiboCommentCrawler):
    def fetch_branch_page(
        self,
        post_url: str,
        status_id: str,
        uid: str,
        combo: dict[str, int],
        count: int,
        max_id: int | str | None,
        max_id_type: int | str | None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "is_reload": 1,
            "id": status_id,
            "is_show_bulletin": 2,
            "is_mix": combo["is_mix"],
            "count": count,
            "uid": uid,
            "fetch_level": combo["fetch_level"],
            "locale": "zh-CN",
            "flow": combo["flow"],
        }
        if max_id:
            params["max_id"] = max_id
        if max_id_type is not None:
            params["max_id_type"] = max_id_type
        return self.get_json(
            "https://weibo.com/ajax/statuses/buildComments",
            params=params,
            referer=post_url,
        )


def copy_existing_rows(source_csv: Path, target_csv: Path) -> None:
    if not source_csv.exists():
        return
    ensure_csv(target_csv, RAW_FIELDS)
    existing_ids, _, _ = load_resume_state(target_csv)
    rows: list[dict[str, Any]] = []
    with open(source_csv, "r", encoding="utf-8-sig", newline="") as src:
        reader = csv.DictReader(src)
        for row in reader:
            comment_id = row.get("comment_id", "")
            if comment_id and comment_id not in existing_ids:
                existing_ids.add(comment_id)
                rows.append(row)
    append_rows(target_csv, RAW_FIELDS, rows)


def crawl(args: argparse.Namespace) -> None:
    cookie = read_cookie(args)
    posts = load_posts(args.posts_json)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_csv = out_dir / "weibo_comments_raw.csv"
    clean_csv = out_dir / "weibo_comments_clean.csv"
    ensure_csv(raw_csv, RAW_FIELDS)

    if args.seed_raw:
        copy_existing_rows(Path(args.seed_raw), raw_csv)

    seen_ids, valid_counts, max_orders = load_resume_state(raw_csv)
    crawler = BranchCrawler(
        cookie=cookie,
        sleep_min=args.sleep_min,
        sleep_max=args.sleep_max,
        timeout=args.timeout,
        max_retries=args.max_retries,
    )

    metadata: list[dict[str, Any]] = []
    for post in posts:
        print(f"\n[POST] {post.post_id} {post.post_type} {post.url}")
        status = crawler.resolve_status(post)
        status_id = str(status["idstr"])
        user = status.get("user") or {}
        uid = str(user.get("idstr") or user.get("id") or post.uid_hint)
        metadata.append(
            {
                **status,
                "post_id": post.post_id,
                "post_type": post.post_type,
                "post_url": post.url,
                "status_id": status_id,
                "uid": uid,
            }
        )

        queue: deque[tuple[int, str | int | None, str | int | None, dict[str, int]]] = deque()
        visited: set[tuple[int, str, str, int, int]] = set()
        for combo in HOT_COMBOS:
            queue.append((1, None, None, combo))

        valid_count = valid_counts[post.post_id]
        source_order = max_orders[post.post_id]
        no_new_branches = 0

        while queue and valid_count < args.limit_per_post:
            page, max_id, max_id_type, combo = queue.popleft()
            key = (
                combo["flow"],
                str(max_id or ""),
                str(max_id_type or ""),
                combo["is_mix"],
                combo["fetch_level"],
            )
            if key in visited:
                continue
            visited.add(key)
            if len(visited) > args.max_branch_requests:
                print(f"[STOP] reached branch request cap {args.max_branch_requests}.")
                break

            try:
                payload = crawler.fetch_branch_page(
                    post_url=post.url,
                    status_id=status_id,
                    uid=uid,
                    combo=combo,
                    count=args.count,
                    max_id=max_id,
                    max_id_type=max_id_type,
                )
            except WeiboCrawlerError as exc:
                print(f"[WARN] branch failed {key}: {exc}", file=sys.stderr)
                continue

            items = payload.get("data") or []
            rows: list[dict[str, Any]] = []
            new_ids = 0
            for item in items:
                comment_id = str(item.get("idstr") or item.get("id") or "")
                if not comment_id or comment_id in seen_ids:
                    continue
                seen_ids.add(comment_id)
                source_order += 1
                row = comment_to_row(
                    item=item,
                    post=post,
                    status_id=status_id,
                    source_order=source_order,
                    page=page,
                    flow=combo["flow"],
                )
                rows.append(row)
                new_ids += 1
                if row["is_valid"] == "1":
                    valid_count += 1
                if valid_count >= args.limit_per_post:
                    break

            append_rows(raw_csv, RAW_FIELDS, rows)
            valid_counts[post.post_id] = valid_count
            max_orders[post.post_id] = source_order

            print(
                "[BRANCH] flow={flow} mix={mix} level={level} page={page} "
                "got={got} new={new} valid={valid}/{limit} next={next_id}".format(
                    flow=combo["flow"],
                    mix=combo["is_mix"],
                    level=combo["fetch_level"],
                    page=page,
                    got=len(items),
                    new=new_ids,
                    valid=valid_count,
                    limit=args.limit_per_post,
                    next_id=payload.get("max_id"),
                )
            )

            next_max_id = payload.get("max_id")
            next_max_id_type = payload.get("max_id_type")
            if next_max_id and str(next_max_id) != "0":
                queue.append((page + 1, next_max_id, next_max_id_type, combo))

            if new_ids == 0:
                no_new_branches += 1
            else:
                no_new_branches = 0
            if no_new_branches >= args.stop_after_no_new:
                print(f"[STOP] {args.stop_after_no_new} consecutive branches had no new comments.")
                break

            time.sleep(random.uniform(args.sleep_min, args.sleep_max))

    write_post_metadata(out_dir, metadata)
    make_clean_csv(raw_csv, clean_csv, args.limit_per_post)
    print(f"\n[DONE] raw:   {raw_csv}")
    print(f"[DONE] clean: {clean_csv}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Explore multiple hot-comment cursor branches."
    )
    parser.add_argument("--posts-json")
    parser.add_argument("--out-dir", default="data_hot_expand")
    parser.add_argument("--seed-raw", help="Existing raw CSV to seed dedupe.")
    parser.add_argument("--limit-per-post", type=int, default=2000)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--sleep-min", type=float, default=0.8)
    parser.add_argument("--sleep-max", type=float, default=1.8)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--max-retries", type=int, default=4)
    parser.add_argument("--cookie-env", default="WEIBO_COOKIE")
    parser.add_argument("--cookie-file")
    parser.add_argument("--max-branch-requests", type=int, default=600)
    parser.add_argument("--stop-after-no-new", type=int, default=80)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        crawl(args)
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] partial data is kept.", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

