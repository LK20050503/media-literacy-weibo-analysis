#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Export individual ECharts HTML figures to PNG screenshots."""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
HTML_DIR = ROOT / "outputs" / "04_历史图表版本" / "论文单图"
PNG_DIR = ROOT / "outputs" / "04_历史图表版本" / "论文单图_png"


def main() -> int:
    PNG_DIR.mkdir(parents=True, exist_ok=True)
    html_files = sorted(HTML_DIR.glob("*.html"))
    if not html_files:
        raise RuntimeError(f"No HTML figures found in {HTML_DIR}")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 980, "height": 740}, device_scale_factor=2)
        for html_path in html_files:
            page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
            page.wait_for_selector(".frame canvas", timeout=30000)
            page.wait_for_timeout(1200)
            output = PNG_DIR / f"{html_path.stem}.png"
            page.locator(".frame").screenshot(path=str(output))
            print(f"[OK] {output}")
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
