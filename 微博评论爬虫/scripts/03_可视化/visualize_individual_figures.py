#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Create individual 4:3 white-background ECharts figures for the report."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "outputs" / "01_核心数据" / "weibo_comments_analysis_coded.csv"
OUT_DIR = ROOT / "outputs" / "04_历史图表版本" / "论文单图"

POST_ORDER = ["P1", "P2", "P3", "P4"]
POST_LABELS = {
    "P1": "李首条指控",
    "P2": "单初步回应",
    "P3": "李后续证据",
    "P4": "单正式道歉",
}

STANCE_ORDER = ["支持李方", "支持单方", "中立观望", "反网暴/反平台", "双方都批评", "无关/无法判断"]
EVIDENCE_ORDER = ["无明确依据", "个人情绪或印象", "法律版权概念", "过往旧闻", "当事人原话", "授权事实"]
DISCOURSE_ORDER = ["粉圈化攻击或维护", "道德化评价", "娱乐化调侃", "法律化论证", "劝和纠偏", "关系化解读"]
LITERACY_ORDER = ["较低", "中等", "较高"]

# Reference-like ECharts palette, adapted for white report figures.
PALETTE = ["#5470C6", "#91CC75", "#FAC858", "#EE6666", "#73C0DE", "#9A60B4", "#FC8452", "#3BA272"]
STANCE_COLORS = {
    "支持李方": "#5470C6",
    "支持单方": "#FC8452",
    "中立观望": "#FAC858",
    "反网暴/反平台": "#91CC75",
    "双方都批评": "#EE6666",
    "无关/无法判断": "#9A60B4",
}


def read_rows() -> list[dict[str, str]]:
    with open(INPUT, "r", encoding="utf-8-sig", newline="") as f:
        return [row for row in csv.DictReader(f) if row.get("content_valid_for_coding") == "1"]


def js(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def count_field(rows: list[dict[str, str]], field: str, order: list[str]) -> list[dict[str, object]]:
    counter = Counter(row[field] for row in rows)
    return [{"name": name, "value": counter.get(name, 0)} for name in order]


def percent_by_post(rows: list[dict[str, str]], field: str, categories: list[str]) -> dict[str, list[float]]:
    by_post: dict[str, Counter[str]] = defaultdict(Counter)
    totals: Counter[str] = Counter()
    for row in rows:
        post_id = row["post_id"]
        by_post[post_id][row[field]] += 1
        totals[post_id] += 1
    return {
        category: [
            round(by_post[post_id].get(category, 0) / totals[post_id] * 100, 2)
            for post_id in POST_ORDER
        ]
        for category in categories
    }


def write_html(filename: str, title: str, option_js: str) -> None:
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <title>{title}</title>
  <script src="https://assets.pyecharts.org/assets/v5/echarts.min.js"></script>
  <style>
    html, body {{
      margin: 0;
      padding: 0;
      background: #ffffff;
      font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif;
    }}
    .frame {{
      width: 960px;
      height: 720px;
      background: #ffffff;
      padding: 22px 26px 18px;
      box-sizing: border-box;
    }}
    #chart {{
      width: 100%;
      height: 100%;
    }}
  </style>
</head>
<body>
  <div class="frame"><div id="chart"></div></div>
  <script>
    const chart = echarts.init(document.getElementById('chart'), null, {{ renderer: 'canvas' }});
    const palette = {js(PALETTE)};
    const option = {option_js};
    chart.setOption(option);
  </script>
</body>
</html>
"""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / filename).write_text(html, encoding="utf-8")


def base_text() -> str:
    return """{
      color: '#222',
      fontFamily: 'Microsoft YaHei, PingFang SC, Arial',
      fontSize: 21,
      fontWeight: 600
    }"""


def bar_option(title: str, data: list[dict[str, object]], x_name: str) -> str:
    sorted_data = sorted(data, key=lambda item: int(item["value"]))
    categories = [item["name"] for item in sorted_data]
    values = [item["value"] for item in sorted_data]
    return f"""{{
      color: palette,
      backgroundColor: '#ffffff',
      title: {{
        text: {js(title)},
        left: 'center',
        top: 16,
        textStyle: {base_text()}
      }},
      tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }} }},
      toolbox: {{
        right: 20,
        top: 14,
        feature: {{ saveAsImage: {{ title: '保存图片', backgroundColor: '#ffffff', pixelRatio: 2 }} }}
      }},
      grid: {{ left: 154, right: 92, top: 88, bottom: 76 }},
      xAxis: {{
        type: 'value',
        name: {js(x_name)},
        nameLocation: 'middle',
        nameGap: 42,
        axisLabel: {{ color: '#555', fontSize: 14 }},
        axisLine: {{ lineStyle: {{ color: '#999' }} }},
        splitLine: {{ lineStyle: {{ color: '#e9edf3' }} }}
      }},
      yAxis: {{
        type: 'category',
        data: {js(categories)},
        axisLabel: {{ color: '#333', fontSize: 15 }},
        axisLine: {{ lineStyle: {{ color: '#999' }} }},
        axisTick: {{ show: false }}
      }},
      series: [{{
        type: 'bar',
        data: {js(values)},
        barWidth: 26,
        itemStyle: {{ borderRadius: [0, 5, 5, 0] }},
        label: {{ show: true, position: 'right', color: '#333', fontSize: 14 }}
      }}]
    }}"""


def main() -> int:
    rows = read_rows()
    stance_matrix = percent_by_post(rows, "stance", STANCE_ORDER)
    evidence = count_field(rows, "evidence_type", EVIDENCE_ORDER)
    discourse = count_field(rows, "discourse_strategy", DISCOURSE_ORDER)
    literacy = count_field(rows, "media_literacy", LITERACY_ORDER)

    stance_series = [
        {
            "name": name,
            "type": "bar",
            "stack": "total",
            "barWidth": 48,
            "data": stance_matrix[name],
            "itemStyle": {"color": STANCE_COLORS[name]},
            "emphasis": {"focus": "series"},
        }
        for name in STANCE_ORDER
    ]
    stance_option = f"""{{
      backgroundColor: '#ffffff',
      title: {{
        text: '图1 不同微博场景下的评论立场分布',
        left: 'center',
        top: 16,
        textStyle: {base_text()}
      }},
      tooltip: {{
        trigger: 'axis',
        axisPointer: {{ type: 'shadow' }},
        valueFormatter: value => value + '%'
      }},
      toolbox: {{
        right: 20,
        top: 14,
        feature: {{ saveAsImage: {{ title: '保存图片', backgroundColor: '#ffffff', pixelRatio: 2 }} }}
      }},
      legend: {{
        top: 58,
        left: 'center',
        itemWidth: 14,
        itemHeight: 10,
        textStyle: {{ color: '#333', fontSize: 13 }}
      }},
      grid: {{ left: 70, right: 42, top: 118, bottom: 78 }},
      xAxis: {{
        type: 'category',
        data: {js([POST_LABELS[p] for p in POST_ORDER])},
        axisLabel: {{ color: '#333', fontSize: 15 }},
        axisLine: {{ lineStyle: {{ color: '#999' }} }},
        axisTick: {{ show: false }}
      }},
      yAxis: {{
        type: 'value',
        max: 100,
        axisLabel: {{ color: '#555', fontSize: 14, formatter: '{{value}}%' }},
        axisLine: {{ lineStyle: {{ color: '#999' }} }},
        splitLine: {{ lineStyle: {{ color: '#e9edf3' }} }}
      }},
      series: {js(stance_series)}
    }}"""

    write_html("图1_评论立场分布_4比3.html", "图1 不同微博场景下的评论立场分布", stance_option)
    write_html("图2_论证依据分布_4比3.html", "图2 评论论证依据分布", bar_option("图2 评论论证依据分布", evidence, "评论数量"))
    write_html("图3_话语策略分布_4比3.html", "图3 评论话语策略分布", bar_option("图3 评论话语策略分布", discourse, "评论数量"))

    literacy_option = f"""{{
      color: ['#5470C6', '#91CC75', '#FAC858'],
      backgroundColor: '#ffffff',
      title: {{
        text: '图4 评论区媒介素养表现分布',
        left: 'center',
        top: 16,
        textStyle: {base_text()}
      }},
      tooltip: {{ trigger: 'item', formatter: '{{b}}：{{c}}（{{d}}%）' }},
      toolbox: {{
        right: 20,
        top: 14,
        feature: {{ saveAsImage: {{ title: '保存图片', backgroundColor: '#ffffff', pixelRatio: 2 }} }}
      }},
      legend: {{
        bottom: 42,
        left: 'center',
        textStyle: {{ color: '#333', fontSize: 15 }}
      }},
      series: [{{
        type: 'pie',
        radius: ['42%', '66%'],
        center: ['50%', '47%'],
        data: {js(literacy)},
        itemStyle: {{ borderColor: '#fff', borderWidth: 3 }},
        label: {{
          color: '#333',
          fontSize: 15,
          formatter: '{{b}}\\n{{d}}%'
        }},
        labelLine: {{ lineStyle: {{ color: '#999' }} }}
      }}]
    }}"""
    write_html("图4_媒介素养表现分布_4比3.html", "图4 评论区媒介素养表现分布", literacy_option)

    for path in sorted(OUT_DIR.glob("*.html")):
        print(f"[OK] {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
