#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Fetch Weibo mobile hotflow comments and merge them with existing PC hot data.

Cookie is read from M_WEIBO_COOKIE first, then WEIBO_COOKIE, or --cookie-file.
Do not hard-code cookies in this file.
"""

from __future__ import annotations

import argparse
import csv
import html
import os
import random
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from weibo_comment_crawler import (
    RAW_FIELDS,
    append_rows,
    ensure_csv,
    load_resume_state,
    make_clean_csv,
    normalize_text,
)


POSTS = [
    {
        "post_id": "P1",
        "post_type": "李首条指控微博",
        "post_published_at": "03月29日 14:37",
        "post_url": "https://weibo.com/1739046981/QyknqF30P",
        "status_id": "5281814849783031",
    },
    {
        "post_id": "P2",
        "post_type": "单依纯初步回应微博",
        "post_published_at": "03月29日 16:16",
        "post_url": "https://weibo.com/5598574734/Qyl1MdR8l",
        "status_id": "5281839863302513",
    },
    {
        "post_id": "P3",
        "post_type": "李后续证据帖",
        "post_published_at": "03月29日 16:42",
        "post_url": "https://weibo.com/1739046981/Qylc1AAFG?from=feed#comment",
        "status_id": "5281846218720776",
    },
    {
        "post_id": "P4",
        "post_type": "单依纯正式道歉微博",
        "post_published_at": "03月30日 01:08",
        "post_url": "https://weibo.com/5598574734/QyovouEwc?from=feed#comment",
        "status_id": "5281973547305596",
    },
]


def read_mobile_cookie(args: argparse.Namespace) -> str:
    if args.cookie_file:
        cookie = Path(args.cookie_file).read_text(encoding="utf-8").strip()
    else:
        cookie = os.environ.get("M_WEIBO_COOKIE") or os.environ.get("WEIBO_COOKIE") or ""
        cookie = cookie.strip()
    if not cookie:
        raise RuntimeError("Cookie missing. Set M_WEIBO_COOKIE or pass --cookie-file.")
    return cookie


def cookie_value(cookie: str, key: str) -> str | None:
    for part in cookie.split(";"):
        if "=" not in part:
            continue
        k, v = part.strip().split("=", 1)
        if k == key:
            return v
    return None


def clean_mobile_text(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return normalize_text(text)


def is_valid_text(text: str) -> bool:
    return bool(text and re.search(r"[\u4e00-\u9fffA-Za-z0-9]", text))


def copy_seed(source_csv: Path, target_csv: Path) -> None:
    if not source_csv.exists():
        return
    ensure_csv(target_csv, RAW_FIELDS)
    seen, _, _ = load_resume_state(target_csv)
    rows: list[dict[str, Any]] = []
    with open(source_csv, "r", encoding="utf-8-sig", newline="") as src:
        reader = csv.DictReader(src)
        for row in reader:
            comment_id = row.get("comment_id", "")
            if comment_id and comment_id not in seen:
                seen.add(comment_id)
                rows.append(row)
    append_rows(target_csv, RAW_FIELDS, rows)


class MobileHotflowCrawler:
    def __init__(
        self,
        cookie: str,
        sleep_min: float,
        sleep_max: float,
        timeout: float,
        max_retries: int,
    ) -> None:
        self.session = requests.Session()
        xsrf = cookie_value(cookie, "XSRF-TOKEN") or ""
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                    "Mobile/15E148 Safari/604.1"
                ),
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "MWeibo-Pwa": "1",
                "X-Requested-With": "XMLHttpRequest",
                "Cookie": cookie,
            }
        )
        if xsrf:
            self.session.headers.update({"X-XSRF-TOKEN": xsrf})
        self.sleep_min = sleep_min
        self.sleep_max = sleep_max
        self.timeout = timeout
        self.max_retries = max_retries

    def sleep(self) -> None:
        time.sleep(random.uniform(self.sleep_min, self.sleep_max))

    def fetch_page(
        self,
        status_id: str,
        max_id: str | int | None,
        max_id_type: str | int | None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "id": status_id,
            "mid": status_id,
            "max_id_type": max_id_type if max_id_type is not None else 0,
        }
        if max_id:
            params["max_id"] = max_id

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(
                    "https://m.weibo.cn/comments/hotflow",
                    params=params,
                    headers={"Referer": f"https://m.weibo.cn/detail/{status_id}"},
                    timeout=self.timeout,
                )
                response.raise_for_status()
                if "json" not in response.headers.get("Content-Type", "").lower():
                    raise RuntimeError(
                        "mobile endpoint did not return JSON; cookie may be invalid"
                    )
                payload = response.json()
                if payload.get("ok") != 1:
                    raise RuntimeError(f"mobile endpoint returned ok={payload.get('ok')}")
                return payload
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt >= self.max_retries:
                    break
                wait = min(60, 2**attempt + random.uniform(0.5, 2))
                print(
                    f"[WARN] request failed ({attempt}/{self.max_retries}): {exc}; "
                    f"sleep {wait:.1f}s",
                    file=sys.stderr,
                )
                time.sleep(wait)
        raise RuntimeError(f"Request failed after retries: {last_error}")


def item_to_row(
    item: dict[str, Any],
    post: dict[str, str],
    source_order: int,
    page: int,
) -> dict[str, Any]:
    comment_id = str(item.get("idstr") or item.get("id") or "")
    text = clean_mobile_text(item.get("text_raw") or item.get("text") or "")
    is_valid = "1" if is_valid_text(text) else "0"
    invalid_reason = "" if is_valid == "1" else "empty_or_non_textual"
    return {
        "sample_id": f"{post['post_id']}_{source_order:06d}",
        "post_id": post["post_id"],
        "post_type": post["post_type"],
        "post_published_at": post["post_published_at"],
        "post_url": post["post_url"],
        "status_id": post["status_id"],
        "comment_id": comment_id,
        "comment_text": text,
        "comment_time": str(item.get("created_at") or ""),
        "like_count": item.get("like_count", item.get("like_counts", 0)),
        "source_order": source_order,
        "page": page,
        "flow": "m_hotflow",
        "crawl_time": datetime.now().isoformat(timespec="seconds"),
        "is_valid": is_valid,
        "invalid_reason": invalid_reason,
    }


def crawl(args: argparse.Namespace) -> None:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_csv = out_dir / "weibo_comments_raw.csv"
    clean_csv = out_dir / "weibo_comments_clean.csv"
    ensure_csv(raw_csv, RAW_FIELDS)
    if args.seed_raw:
        copy_seed(Path(args.seed_raw), raw_csv)

    seen_ids, valid_counts, max_orders = load_resume_state(raw_csv)
    crawler = MobileHotflowCrawler(
        cookie=read_mobile_cookie(args),
        sleep_min=args.sleep_min,
        sleep_max=args.sleep_max,
        timeout=args.timeout,
        max_retries=args.max_retries,
    )

    for post in POSTS:
        print(f"\n[POST] {post['post_id']} {post['post_type']} {post['status_id']}")
        valid_count = valid_counts[post["post_id"]]
        source_order = max_orders[post["post_id"]]
        max_id: str | int | None = None
        max_id_type: str | int | None = 0
        seen_cursors: set[tuple[str, str]] = set()
        no_new_pages = 0

        page = 0
        while valid_count < args.limit_per_post:
            cursor_key = (str(max_id or ""), str(max_id_type or ""))
            if cursor_key in seen_cursors:
                print("[STOP] repeated cursor.")
                break
            seen_cursors.add(cursor_key)
            page += 1
            payload = crawler.fetch_page(post["status_id"], max_id, max_id_type)
            data_obj = payload.get("data") or {}
            items = data_obj.get("data") or []
            if not items:
                print("[STOP] no comment data returned.")
                break

            rows: list[dict[str, Any]] = []
            new_ids = 0
            for item in items:
                comment_id = str(item.get("idstr") or item.get("id") or "")
                if not comment_id or comment_id in seen_ids:
                    continue
                seen_ids.add(comment_id)
                source_order += 1
                row = item_to_row(item, post, source_order, page)
                rows.append(row)
                new_ids += 1
                if row["is_valid"] == "1":
                    valid_count += 1
                if valid_count >= args.limit_per_post:
                    break

            append_rows(raw_csv, RAW_FIELDS, rows)
            valid_counts[post["post_id"]] = valid_count
            max_orders[post["post_id"]] = source_order

            max_id = data_obj.get("max_id")
            max_id_type = data_obj.get("max_id_type")
            print(
                f"[PAGE {page}] got={len(items)} new={new_ids} "
                f"valid={valid_count}/{args.limit_per_post} next={max_id}"
            )

            if new_ids == 0:
                no_new_pages += 1
            else:
                no_new_pages = 0
            if no_new_pages >= args.stop_after_no_new:
                print(f"[STOP] {args.stop_after_no_new} consecutive pages had no new comments.")
                break
            if not max_id or str(max_id) == "0":
                print("[STOP] max_id is empty or 0.")
                break
            crawler.sleep()

    make_clean_csv(raw_csv, clean_csv, args.limit_per_post)
    print(f"\n[DONE] raw:   {raw_csv}")
    print(f"[DONE] clean: {clean_csv}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Crawl mobile Weibo hotflow comments.")
    parser.add_argument("--out-dir", default="data_mobile_hotflow")
    parser.add_argument("--seed-raw", help="Existing raw CSV to merge/dedupe first.")
    parser.add_argument("--limit-per-post", type=int, default=2000)
    parser.add_argument("--sleep-min", type=float, default=0.8)
    parser.add_argument("--sleep-max", type=float, default=1.8)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--max-retries", type=int, default=4)
    parser.add_argument("--cookie-file")
    parser.add_argument("--stop-after-no-new", type=int, default=20)
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

