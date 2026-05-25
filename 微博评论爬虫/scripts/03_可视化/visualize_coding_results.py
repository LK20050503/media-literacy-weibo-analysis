#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Create an ECharts dark-theme visualization report for coded Weibo comments."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "outputs" / "01_核心数据" / "weibo_comments_analysis_coded.csv"
OUTPUT = ROOT / "outputs" / "04_历史图表版本" / "可视化报告_深色大屏.html"

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


def count_by_field(rows: list[dict[str, str]], field: str, order: list[str]) -> list[dict[str, object]]:
    counter = Counter(row[field] for row in rows)
    return [{"name": name, "value": counter.get(name, 0)} for name in order]


def percent_matrix_by_post(rows: list[dict[str, str]], field: str, categories: list[str]) -> dict[str, list[float]]:
    by_post: dict[str, Counter[str]] = defaultdict(Counter)
    totals: Counter[str] = Counter()
    for row in rows:
        post_id = row["post_id"]
        by_post[post_id][row[field]] += 1
        totals[post_id] += 1
    matrix: dict[str, list[float]] = {}
    for category in categories:
        matrix[category] = [
            round(by_post[post_id].get(category, 0) / totals[post_id] * 100, 2) if totals[post_id] else 0
            for post_id in POST_ORDER
        ]
    return matrix


def js(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def main() -> int:
    rows = read_rows()
    total = len(rows)

    stance_by_post = percent_matrix_by_post(rows, "stance", STANCE_ORDER)
    evidence_data = count_by_field(rows, "evidence_type", EVIDENCE_ORDER)
    discourse_data = count_by_field(rows, "discourse_strategy", DISCOURSE_ORDER)
    literacy_data = count_by_field(rows, "media_literacy", LITERACY_ORDER)
    emotion_data = count_by_field(rows, "emotion_level", ["低", "中", "高"])

    post_counts = Counter(row["post_id"] for row in rows)
    kpi_cards = [
        ("有效评论", f"{total:,}", "清洗后进入正式编码"),
        ("支持李方", f"{Counter(row['stance'] for row in rows)['支持李方'] / total * 100:.2f}%", "总体主流立场"),
        ("粉圈化话语", f"{Counter(row['discourse_strategy'] for row in rows)['粉圈化攻击或维护'] / total * 100:.2f}%", "最高频话语策略"),
        ("较低媒介素养", f"{Counter(row['media_literacy'] for row in rows)['较低'] / total * 100:.2f}%", "证据意识与表达质量"),
    ]

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>微博版权争议评论编码可视化</title>
  <script src="https://assets.pyecharts.org/assets/v5/echarts.min.js"></script>
  <script src="https://assets.pyecharts.org/assets/v5/themes/chalk.js"></script>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-width: 1180px;
      background: #202b38;
      color: #d8dee9;
      font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif;
    }}
    .page {{
      width: 1350px;
      margin: 0 auto;
      padding: 18px 18px 28px;
      background: #202b38;
    }}
    .header {{
      height: 64px;
      display: flex;
      align-items: center;
      justify-content: center;
      background: #293441;
      border: 1px solid rgba(255,255,255,0.06);
      color: #cfd8dc;
      font-size: 28px;
      font-weight: 600;
      letter-spacing: 0;
    }}
    .subtitle {{
      margin: 10px 0 16px;
      text-align: center;
      color: #9fb0c0;
      font-size: 14px;
    }}
    .kpis {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 14px;
      margin-bottom: 14px;
    }}
    .kpi {{
      height: 92px;
      padding: 14px 18px;
      background: #293441;
      border: 1px solid rgba(255,255,255,0.07);
    }}
    .kpi .label {{ color: #9fb0c0; font-size: 14px; }}
    .kpi .value {{ margin-top: 8px; color: #ffffff; font-size: 28px; font-weight: 700; }}
    .kpi .note {{ margin-top: 6px; color: #7f8d9a; font-size: 12px; }}
    .grid {{
      display: grid;
      grid-template-columns: 1.25fr 1fr;
      gap: 14px;
    }}
    .panel {{
      background: #293441;
      border: 1px solid rgba(255,255,255,0.07);
      padding: 8px 10px 6px;
    }}
    .chart {{ width: 100%; height: 390px; }}
    .wide {{ grid-column: span 2; }}
    .short {{ height: 330px; }}
  </style>
</head>
<body>
  <div class="page">
    <div class="header">李荣浩、单依纯版权争议微博评论编码可视化</div>
    <div class="subtitle">样本：四条核心微博热度排序评论，有效编码 {total} 条；图表风格参照 ECharts chalk 深色主题</div>
    <div class="kpis">
      {''.join(f'<div class="kpi"><div class="label">{label}</div><div class="value">{value}</div><div class="note">{note}</div></div>' for label, value, note in kpi_cards)}
    </div>
    <div class="grid">
      <div class="panel wide"><div id="stance" class="chart"></div></div>
      <div class="panel"><div id="evidence" class="chart"></div></div>
      <div class="panel"><div id="discourse" class="chart"></div></div>
      <div class="panel"><div id="literacy" class="chart short"></div></div>
      <div class="panel"><div id="emotion" class="chart short"></div></div>
    </div>
  </div>

  <script>
    const postLabels = {js([POST_LABELS[p] for p in POST_ORDER])};
    const stanceSeries = {js(stance_by_post)};
    const evidenceData = {js(evidence_data)};
    const discourseData = {js(discourse_data)};
    const literacyData = {js(literacy_data)};
    const emotionData = {js(emotion_data)};
    const postCounts = {js([post_counts[p] for p in POST_ORDER])};

    const textStyle = {{ color: '#d8dee9', fontFamily: 'Microsoft YaHei, PingFang SC, Arial' }};
    const axisLine = {{ lineStyle: {{ color: '#6d7d8c' }} }};
    const splitLine = {{ lineStyle: {{ color: 'rgba(255,255,255,0.08)' }} }};

    function chart(id) {{
      return echarts.init(document.getElementById(id), 'chalk');
    }}

    chart('stance').setOption({{
      title: {{ text: '四条微博评论立场分布', left: 'center', top: 8, textStyle }},
      tooltip: {{
        trigger: 'axis',
        axisPointer: {{ type: 'shadow' }},
        formatter: params => {{
          let s = params[0].axisValue + '<br/>';
          params.forEach(p => s += `${{p.marker}}${{p.seriesName}}：${{p.value}}%<br/>`);
          return s;
        }}
      }},
      legend: {{ top: 42, textStyle: {{ color: '#cfd8dc' }} }},
      grid: {{ left: 52, right: 28, bottom: 46, top: 92 }},
      xAxis: {{ type: 'category', data: postLabels, axisLabel: {{ color: '#cfd8dc' }}, axisLine }},
      yAxis: {{ type: 'value', max: 100, axisLabel: {{ color: '#cfd8dc', formatter: '{{value}}%' }}, axisLine, splitLine }},
      series: Object.keys(stanceSeries).map(name => ({{
        name,
        type: 'bar',
        stack: 'stance',
        emphasis: {{ focus: 'series' }},
        data: stanceSeries[name]
      }}))
    }});

    function horizontalBarOption(title, data) {{
      const sorted = [...data].sort((a, b) => a.value - b.value);
      return {{
        title: {{ text: title, left: 'center', top: 8, textStyle }},
        tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }} }},
        grid: {{ left: 126, right: 34, bottom: 30, top: 62 }},
        xAxis: {{ type: 'value', axisLabel: {{ color: '#cfd8dc' }}, axisLine, splitLine }},
        yAxis: {{ type: 'category', data: sorted.map(d => d.name), axisLabel: {{ color: '#cfd8dc' }}, axisLine }},
        series: [{{
          type: 'bar',
          data: sorted.map(d => d.value),
          barWidth: 18,
          label: {{ show: true, position: 'right', color: '#fff' }}
        }}]
      }};
    }}

    chart('evidence').setOption(horizontalBarOption('总体论证依据分布', evidenceData));
    chart('discourse').setOption(horizontalBarOption('总体话语策略分布', discourseData));

    chart('literacy').setOption({{
      title: {{ text: '媒介素养表现', left: 'center', top: 8, textStyle }},
      tooltip: {{ trigger: 'item', formatter: '{{b}}：{{c}}（{{d}}%）' }},
      legend: {{ bottom: 8, textStyle: {{ color: '#cfd8dc' }} }},
      series: [{{
        type: 'pie',
        radius: ['42%', '68%'],
        center: ['50%', '50%'],
        data: literacyData,
        label: {{ color: '#fff', formatter: '{{b}}\\n{{d}}%' }},
        labelLine: {{ lineStyle: {{ color: '#aab6c1' }} }}
      }}]
    }});

    chart('emotion').setOption({{
      title: {{ text: '情绪强度分布', left: 'center', top: 8, textStyle }},
      tooltip: {{ trigger: 'item', formatter: '{{b}}：{{c}}（{{d}}%）' }},
      legend: {{ bottom: 8, textStyle: {{ color: '#cfd8dc' }} }},
      series: [{{
        type: 'pie',
        radius: ['0%', '66%'],
        center: ['50%', '50%'],
        data: emotionData,
        roseType: 'radius',
        label: {{ color: '#fff', formatter: '{{b}} {{d}}%' }}
      }}]
    }});

    window.addEventListener('resize', () => {{
      ['stance', 'evidence', 'discourse', 'literacy', 'emotion'].forEach(id => echarts.getInstanceByDom(document.getElementById(id)).resize());
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
