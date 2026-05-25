#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Create compact ECharts figures for the analysis report."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "outputs" / "01_核心数据" / "weibo_comments_analysis_coded.csv"
OUTPUT = ROOT / "outputs" / "04_历史图表版本" / "论文插图_深色小图表.html"

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


def read_rows() -> list[dict[str, str]]:
    with open(INPUT, "r", encoding="utf-8-sig", newline="") as f:
        return [row for row in csv.DictReader(f) if row.get("content_valid_for_coding") == "1"]


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


def js(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def main() -> int:
    rows = read_rows()
    stance = percent_by_post(rows, "stance", STANCE_ORDER)
    evidence = count_field(rows, "evidence_type", EVIDENCE_ORDER)
    discourse = count_field(rows, "discourse_strategy", DISCOURSE_ORDER)
    literacy = count_field(rows, "media_literacy", LITERACY_ORDER)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <title>论文插图：微博评论编码结果</title>
  <script src="https://assets.pyecharts.org/assets/v5/echarts.min.js"></script>
  <script src="https://assets.pyecharts.org/assets/v5/themes/chalk.js"></script>
  <style>
    body {{
      margin: 0;
      padding: 24px;
      background: #1f2935;
      font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif;
      color: #d8dee9;
    }}
    .wrap {{
      width: 1060px;
      margin: 0 auto;
      display: grid;
      grid-template-columns: 1fr;
      gap: 24px;
    }}
    .figure {{
      width: 1060px;
      height: 520px;
      background: #293441;
      border: 1px solid rgba(255,255,255,0.08);
      padding: 10px 12px 6px;
    }}
    .chart {{
      width: 100%;
      height: 100%;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="figure"><div id="fig1" class="chart"></div></div>
    <div class="figure"><div id="fig2" class="chart"></div></div>
    <div class="figure"><div id="fig3" class="chart"></div></div>
    <div class="figure"><div id="fig4" class="chart"></div></div>
  </div>

  <script>
    const postLabels = {js([POST_LABELS[p] for p in POST_ORDER])};
    const stance = {js(stance)};
    const evidence = {js(evidence)};
    const discourse = {js(discourse)};
    const literacy = {js(literacy)};

    const textStyle = {{ color: '#d8dee9', fontFamily: 'Microsoft YaHei, PingFang SC, Arial', fontSize: 18 }};
    const axisLabel = {{ color: '#cfd8dc', fontSize: 13 }};
    const axisLine = {{ lineStyle: {{ color: '#6d7d8c' }} }};
    const splitLine = {{ lineStyle: {{ color: 'rgba(255,255,255,0.08)' }} }};

    function makeChart(id) {{
      return echarts.init(document.getElementById(id), 'chalk');
    }}

    makeChart('fig1').setOption({{
      title: {{ text: '图1 四条微博评论立场分布', left: 'center', top: 12, textStyle }},
      tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }} }},
      legend: {{ top: 52, textStyle: {{ color: '#cfd8dc' }} }},
      grid: {{ left: 60, right: 36, top: 105, bottom: 52 }},
      xAxis: {{ type: 'category', data: postLabels, axisLabel, axisLine }},
      yAxis: {{ type: 'value', max: 100, axisLabel: {{ ...axisLabel, formatter: '{{value}}%' }}, axisLine, splitLine }},
      series: Object.keys(stance).map(name => ({{
        name,
        type: 'bar',
        stack: 'total',
        data: stance[name],
        barWidth: 42,
        label: {{ show: false }},
        emphasis: {{ focus: 'series' }}
      }}))
    }});

    function barOption(title, data) {{
      const sorted = [...data].sort((a, b) => a.value - b.value);
      return {{
        title: {{ text: title, left: 'center', top: 12, textStyle }},
        tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }} }},
        grid: {{ left: 150, right: 64, top: 72, bottom: 46 }},
        xAxis: {{ type: 'value', axisLabel, axisLine, splitLine }},
        yAxis: {{ type: 'category', data: sorted.map(d => d.name), axisLabel, axisLine }},
        series: [{{
          type: 'bar',
          data: sorted.map(d => d.value),
          barWidth: 22,
          label: {{ show: true, position: 'right', color: '#ffffff', fontSize: 13 }}
        }}]
      }};
    }}

    makeChart('fig2').setOption(barOption('图2 评论论证依据分布', evidence));
    makeChart('fig3').setOption(barOption('图3 评论话语策略分布', discourse));

    makeChart('fig4').setOption({{
      title: {{ text: '图4 媒介素养表现分布', left: 'center', top: 12, textStyle }},
      tooltip: {{ trigger: 'item', formatter: '{{b}}：{{c}}（{{d}}%）' }},
      legend: {{ bottom: 24, textStyle: {{ color: '#cfd8dc', fontSize: 13 }} }},
      series: [{{
        type: 'pie',
        radius: ['42%', '68%'],
        center: ['50%', '50%'],
        data: literacy,
        label: {{ color: '#fff', fontSize: 14, formatter: '{{b}}\\n{{d}}%' }},
        labelLine: {{ lineStyle: {{ color: '#aab6c1' }} }}
      }}]
    }});
  </script>
</body>
</html>
"""
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"[OK] {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
