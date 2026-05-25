#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Fetch top-level hot comments from selected Weibo posts.

Cookie is read from WEIBO_COOKIE or a local cookie file. Do not hard-code it.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import random
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


DEFAULT_POSTS = [
    {
        "post_id": "P1",
        "post_type": "李首条指控微博",
        "published_at": "03月29日 14:37",
        "url": "https://weibo.com/1739046981/QyknqF30P",
    },
    {
        "post_id": "P2",
        "post_type": "单依纯初步回应微博",
        "published_at": "03月29日 16:16",
        "url": "https://weibo.com/5598574734/Qyl1MdR8l",
    },
    {
        "post_id": "P3",
        "post_type": "李后续证据帖",
        "published_at": "03月29日 16:42",
        "url": "https://weibo.com/1739046981/Qylc1AAFG?from=feed#comment",
    },
    {
        "post_id": "P4",
        "post_type": "单依纯正式道歉微博",
        "published_at": "03月30日 01:08",
        "url": "https://weibo.com/5598574734/QyovouEwc?from=feed#comment",
    },
]


RAW_FIELDS = [
    "sample_id",
    "post_id",
    "post_type",
    "post_published_at",
    "post_url",
    "status_id",
    "comment_id",
    "comment_text",
    "comment_time",
    "like_count",
    "source_order",
    "page",
    "flow",
    "crawl_time",
    "is_valid",
    "invalid_reason",
]


@dataclass(frozen=True)
class PostTarget:
    post_id: str
    post_type: str
    published_at: str
    url: str
    uid_hint: str
    mblog_id: str


class WeiboCrawlerError(RuntimeError):
    pass


def parse_post_url(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        raise ValueError(f"Cannot parse Weibo post url: {url}")
    return parts[0], parts[1]


def load_posts(path: str | None) -> list[PostTarget]:
    raw_posts = DEFAULT_POSTS
    if path:
        with open(path, "r", encoding="utf-8") as f:
            raw_posts = json.load(f)

    posts: list[PostTarget] = []
    for item in raw_posts:
        uid_hint, mblog_id = parse_post_url(item["url"])
        posts.append(
            PostTarget(
                post_id=item["post_id"],
                post_type=item["post_type"],
                published_at=item.get("published_at", ""),
                url=item["url"],
                uid_hint=uid_hint,
                mblog_id=mblog_id,
            )
        )
    return posts


def read_cookie(args: argparse.Namespace) -> str:
    if args.cookie_file:
        cookie = Path(args.cookie_file).read_text(encoding="utf-8").strip()
    else:
        cookie = os.environ.get(args.cookie_env, "").strip()

    if not cookie:
        raise WeiboCrawlerError(
            f"Cookie missing. Set {args.cookie_env} or pass --cookie-file."
        )
    return cookie


def cookie_value(cookie: str, key: str) -> str | None:
    for part in cookie.split(";"):
        if "=" not in part:
            continue
        k, v = part.strip().split("=", 1)
        if k == key:
            return v
    return None


def normalize_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    value = value.replace("\u200b", "").replace("\ufeff", "")
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def is_textual_comment(text: str) -> bool:
    if not text:
        return False
    return bool(re.search(r"[\u4e00-\u9fffA-Za-z0-9]", text))


def ensure_csv(path: Path, fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        return
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()


def append_rows(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with open(path, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writerows(rows)


def load_resume_state(raw_csv: Path) -> tuple[set[str], dict[str, int], dict[str, int]]:
    seen_ids: set[str] = set()
    valid_counts: dict[str, int] = defaultdict(int)
    max_orders: dict[str, int] = defaultdict(int)
    if not raw_csv.exists() or raw_csv.stat().st_size == 0:
        return seen_ids, valid_counts, max_orders

    with open(raw_csv, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            comment_id = row.get("comment_id", "")
            if comment_id:
                seen_ids.add(comment_id)
            post_id = row.get("post_id", "")
            if row.get("is_valid") == "1":
                valid_counts[post_id] += 1
            try:
                max_orders[post_id] = max(
                    max_orders[post_id], int(row.get("source_order") or 0)
                )
            except ValueError:
                pass
    return seen_ids, valid_counts, max_orders


class WeiboCommentCrawler:
    def __init__(
        self,
        cookie: str,
        sleep_min: float,
        sleep_max: float,
        timeout: float,
        max_retries: int,
    ) -> None:
        self.session = requests.Session()
        xsrf = cookie_value(cookie, "XSRF-TOKEN")
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Connection": "keep-alive",
                "Cookie": cookie,
                "Referer": "https://weibo.com/",
                "X-Requested-With": "XMLHttpRequest",
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

    def get_json(
        self,
        url: str,
        params: dict[str, Any],
        referer: str,
    ) -> dict[str, Any]:
        headers = {"Referer": referer}
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
                )
                text_head = response.text[:300]
                if response.status_code in {403, 418, 429}:
                    raise WeiboCrawlerError(
                        f"HTTP {response.status_code}; access may be limited."
                    )
                response.raise_for_status()

                content_type = response.headers.get("Content-Type", "")
                if "json" not in content_type.lower():
                    if "Sina Visitor System" in response.text or "login" in text_head:
                        raise WeiboCrawlerError(
                            "Weibo returned login/visitor page. Cookie may be invalid."
                        )
                return response.json()
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt >= self.max_retries:
                    break
                wait = min(60.0, (2**attempt) + random.uniform(0.5, 2.0))
                print(
                    f"[WARN] request failed ({attempt}/{self.max_retries}): {exc}; "
                    f"sleep {wait:.1f}s",
                    file=sys.stderr,
                )
                time.sleep(wait)

        raise WeiboCrawlerError(f"Request failed after retries: {last_error}")

    def resolve_status(self, post: PostTarget) -> dict[str, Any]:
        url = "https://weibo.com/ajax/statuses/show"
        payload = self.get_json(
            url,
            params={"id": post.mblog_id, "locale": "zh-CN"},
            referer=post.url,
        )
        if not isinstance(payload, dict) or not payload.get("idstr"):
            raise WeiboCrawlerError(f"Cannot resolve post status id: {post.url}")
        return payload

    def fetch_comment_page(
        self,
        post: PostTarget,
        status_id: str,
        uid: str,
        flow: int,
        count: int,
        max_id: int | str | None,
        max_id_type: int | str | None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "is_reload": 1,
            "id": status_id,
            "is_show_bulletin": 2,
            "is_mix": 0,
            "count": count,
            "uid": uid,
            "fetch_level": 0,
            "locale": "zh-CN",
            "flow": flow,
        }
        if max_id:
            params["max_id"] = max_id
        if max_id_type is not None:
            params["max_id_type"] = max_id_type

        return self.get_json(
            "https://weibo.com/ajax/statuses/buildComments",
            params=params,
            referer=post.url,
        )


def comment_to_row(
    item: dict[str, Any],
    post: PostTarget,
    status_id: str,
    source_order: int,
    page: int,
    flow: int,
) -> dict[str, Any]:
    comment_id = str(item.get("idstr") or item.get("id") or "")
    text = normalize_text(item.get("text_raw") or item.get("text") or "")
    created_at = str(item.get("created_at") or "")
    like_count = item.get("like_counts", item.get("like_count", 0))
    is_valid = "1"
    invalid_reason = ""
    if not is_textual_comment(text):
        is_valid = "0"
        invalid_reason = "empty_or_non_textual"

    return {
        "sample_id": f"{post.post_id}_{source_order:06d}",
        "post_id": post.post_id,
        "post_type": post.post_type,
        "post_published_at": post.published_at,
        "post_url": post.url,
        "status_id": status_id,
        "comment_id": comment_id,
        "comment_text": text,
        "comment_time": created_at,
        "like_count": like_count,
        "source_order": source_order,
        "page": page,
        "flow": flow,
        "crawl_time": datetime.now().isoformat(timespec="seconds"),
        "is_valid": is_valid,
        "invalid_reason": invalid_reason,
    }


def write_post_metadata(out_dir: Path, metadata: list[dict[str, Any]]) -> None:
    path = out_dir / "weibo_posts_metadata.json"
    safe_metadata = []
    for item in metadata:
        safe_metadata.append(
            {
                "post_id": item["post_id"],
                "post_type": item["post_type"],
                "post_url": item["post_url"],
                "status_id": item["status_id"],
                "uid": item["uid"],
                "created_at": item.get("created_at", ""),
                "text": normalize_text(item.get("text_raw") or item.get("text") or ""),
                "comments_count": item.get("comments_count"),
                "reposts_count": item.get("reposts_count"),
                "attitudes_count": item.get("attitudes_count"),
            }
        )
    path.write_text(
        json.dumps(safe_metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def make_clean_csv(raw_csv: Path, clean_csv: Path, limit_per_post: int) -> None:
    ensure_csv(clean_csv, RAW_FIELDS)
    counts: dict[str, int] = defaultdict(int)
    seen_ids: set[str] = set()

    with open(raw_csv, "r", encoding="utf-8-sig", newline="") as src, open(
        clean_csv, "w", encoding="utf-8-sig", newline=""
    ) as dst:
        reader = csv.DictReader(src)
        writer = csv.DictWriter(dst, fieldnames=RAW_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in reader:
            post_id = row.get("post_id", "")
            comment_id = row.get("comment_id", "")
            if row.get("is_valid") != "1":
                continue
            if comment_id in seen_ids:
                continue
            if counts[post_id] >= limit_per_post:
                continue
            seen_ids.add(comment_id)
            counts[post_id] += 1
            row["sample_id"] = f"{post_id}_{counts[post_id]:06d}"
            writer.writerow(row)


def crawl(args: argparse.Namespace) -> None:
    cookie = read_cookie(args)
    posts = load_posts(args.posts_json)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_csv = out_dir / "weibo_comments_raw.csv"
    clean_csv = out_dir / "weibo_comments_clean.csv"
    ensure_csv(raw_csv, RAW_FIELDS)

    seen_ids, valid_counts, max_orders = load_resume_state(raw_csv)
    crawler = WeiboCommentCrawler(
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

        valid_count = valid_counts[post.post_id]
        source_order = max_orders[post.post_id]
        max_id: int | str | None = None
        max_id_type: int | str | None = None
        page = 0
        stale_pages = 0

        if valid_count >= args.limit_per_post:
            print(f"[SKIP] already has {valid_count} valid comments.")
            continue

        while valid_count < args.limit_per_post:
            page += 1
            payload = crawler.fetch_comment_page(
                post=post,
                status_id=status_id,
                uid=uid,
                flow=args.flow,
                count=args.count,
                max_id=max_id,
                max_id_type=max_id_type,
            )
            items = payload.get("data") or []
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
                row = comment_to_row(
                    item=item,
                    post=post,
                    status_id=status_id,
                    source_order=source_order,
                    page=page,
                    flow=args.flow,
                )
                rows.append(row)
                new_ids += 1
                if row["is_valid"] == "1":
                    valid_count += 1
                if valid_count >= args.limit_per_post:
                    break

            append_rows(raw_csv, RAW_FIELDS, rows)
            max_orders[post.post_id] = source_order
            valid_counts[post.post_id] = valid_count

            print(
                f"[PAGE {page}] got={len(items)} new={new_ids} "
                f"valid={valid_count}/{args.limit_per_post}"
            )

            next_max_id = payload.get("max_id")
            next_max_id_type = payload.get("max_id_type")
            if not next_max_id or str(next_max_id) == "0":
                print("[STOP] max_id is empty or 0.")
                break
            if next_max_id == max_id:
                stale_pages += 1
                if stale_pages >= 3:
                    print("[STOP] max_id repeated for 3 pages.")
                    break
            else:
                stale_pages = 0
            max_id = next_max_id
            max_id_type = next_max_id_type
            crawler.sleep()

    write_post_metadata(out_dir, metadata)
    make_clean_csv(raw_csv, clean_csv, args.limit_per_post)
    print(f"\n[DONE] raw:   {raw_csv}")
    print(f"[DONE] clean: {clean_csv}")
    print(f"[DONE] meta:  {out_dir / 'weibo_posts_metadata.json'}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Crawl top-level hot comments from selected Weibo posts."
    )
    parser.add_argument("--posts-json", help="Optional custom posts JSON file.")
    parser.add_argument("--out-dir", default="data", help="Output directory.")
    parser.add_argument("--limit-per-post", type=int, default=2000)
    parser.add_argument(
        "--flow",
        type=int,
        default=0,
        help="Weibo comment flow. 0 is commonly used for hot comments.",
    )
    parser.add_argument("--count", type=int, default=20, help="Comments per request.")
    parser.add_argument("--sleep-min", type=float, default=1.8)
    parser.add_argument("--sleep-max", type=float, default=4.5)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--max-retries", type=int, default=4)
    parser.add_argument("--cookie-env", default="WEIBO_COOKIE")
    parser.add_argument("--cookie-file", help="Local file containing cookie string.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.sleep_min < 0 or args.sleep_max < args.sleep_min:
        parser.error("--sleep-max must be >= --sleep-min and both must be non-negative")
    try:
        crawl(args)
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] partial data is kept in raw CSV.", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

