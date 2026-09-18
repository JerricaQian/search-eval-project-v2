#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Canonical Phase5 business-dashboard renderer.

This module only presents the accepted governance dataset. It never reads Phase2/
Phase3 artifacts, changes ratings, or synthesizes issues/evidence.
"""
from __future__ import annotations

import html
import re
from collections import Counter, defaultdict
from typing import Any
from urllib.parse import quote

DIMENSIONS = (
    ("element", "单一元素"),
    ("component", "组件/卡片"),
    ("page", "页面框架"),
)
DIMENSION_ORDER = {"component": 0, "page": 1, "element": 2}
# The finalized NoCode template keeps business navigation in this stable sequence.
BUSINESS_DISPLAY_ORDER = (
    "service_retail", "hotel_travel", "dine_in", "flash_delivery",
    "healthcare", "food_delivery", "maoyan", "xiaoxiang",
)
LEVEL_META = {
    "element": ("单一元素", "#2563EB"),
    "component": ("组件/卡片", "#0E9384"),
    "page": ("页面框架", "#667085"),
}
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}
PRIORITY_COLORS = {"P0": "#FF3131", "P1": "#FF8282", "P2": "#FFAFAF"}
TOP_COLORS = ("#ECB5C4", "#C8D8F9", "#D8BFF2")
OTHER_COLOR = "#D9D9D9"
PROBLEM_RATINGS = {"达标", "不达标", "🟡", "🔴"}
def esc(value: Any) -> str:
    return html.escape(str(value or ""))


def sentence(value: Any) -> str:
    return str(value or "").strip().rstrip("。！？!?；;，,")


COORDINATE_PATTERNS = (
    re.compile(r"(?:横|纵)?坐标\s*[（(]\s*-?\d+(?:\.\d+)?(?:\s*[,，]\s*-?\d+(?:\.\d+)?){1,3}\s*[)）]\s*(?:处|附近|区域)?(?:的)?"),
    re.compile(r"(?:横|纵)坐标\s*-?\d+(?:\.\d+)?\s*(?:处|附近|区域)?(?:的)?"),
)


def without_coordinates(value: Any) -> str:
    """Remove implementation coordinates from reader-facing report copy only."""
    text = str(value or "")
    for pattern in COORDINATE_PATTERNS:
        text = pattern.sub("该", text)
    return re.sub(r"该{2,}", "该", text).strip()


def issue_description_text(issue: dict[str, Any]) -> str:
    description = without_coordinates(issue.get("description"))
    if not sentence(description):
        target = issue.get("elementId") or issue.get("cardId") or issue.get("query") or "未命名问题"
        raise ValueError(f"问题 {target} 缺少问题级 description")
    return f"{sentence(description)}。"


def recommendation_text(issue: dict[str, Any]) -> str:
    recommendation = without_coordinates(issue.get("recommendation"))
    if not recommendation:
        target = issue.get("elementId") or issue.get("cardId") or issue.get("query") or "未命名问题"
        raise ValueError(f"问题 {target} 缺少问题级个性化优化建议")
    return recommendation


def priority(issue: dict[str, Any], group: dict[str, Any]) -> str:
    value = str(issue.get("priority") or group.get("priority") or "P2")
    return value if value in PRIORITY_ORDER else "P2"


def issue_image(issue: dict[str, Any]) -> str:
    return str(issue.get("evidenceImage") or "")


def evidence_html(path: str, label: str) -> str:
    if not path:
        return "<div class='evidence-empty'>暂无截图证据</div>"
    safe_uri = esc(quote(path, safe="/:"))
    return (
        f"<a class='evidence-link' style='width:240px;height:auto;overflow:visible' href='file://{safe_uri}' target='_blank' rel='noopener'>"
        f"<img loading='lazy' style='width:240px;height:auto;max-height:none;object-fit:contain' src='file://{safe_uri}' alt='{esc(label)}'></a>"
    )


def flattened_issues(groups: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    return [
        (group, issue)
        for group in groups
        for issue in group.get("evidence", [])
        if isinstance(issue, dict) and str(issue.get("rating") or "") in PROBLEM_RATINGS
    ]


def make_summary(businesses: list[dict[str, Any]], groups: list[dict[str, Any]], code: str | None = None) -> dict[str, Any]:
    scoped_businesses = [item for item in businesses if code is None or item.get("businessCode") == code]
    scoped_groups = [item for item in groups if code is None or item.get("businessCode") == code]
    issues = flattened_issues(scoped_groups)
    priority_counts = Counter(priority(issue, group) for group, issue in issues)
    level_counts = Counter(str(group.get("level") or "") for group, _ in issues)
    return {
        "issues": issues,
        "priorityCounts": priority_counts,
        "levelCounts": level_counts,
        "tracking": {
            "newIssueCount": sum(int(((item.get("tracking") or {}).get("newIssueCount", item.get("issueCount", 0))) or 0) for item in scoped_businesses),
            "resolvedIssueCount": sum(int(((item.get("tracking") or {}).get("resolvedIssueCount", 0)) or 0) for item in scoped_businesses),
        },
    }


def donut(slices: list[tuple[str, int, str]], label: str) -> str:
    total = sum(value for _, value, _ in slices)
    if not total:
        paths = "<circle cx='50' cy='50' r='40' fill='none' stroke='#F2F4F7' stroke-width='14'/>"
    else:
        circumference, offset, paths = 251.327, 0.0, []
        for name, value, color in slices:
            if value <= 0:
                continue
            length = value / total * circumference
            paths.append(
                f"<circle cx='50' cy='50' r='40' fill='none' stroke='{color}' stroke-width='14' stroke-linecap='round' "
                f"stroke-dasharray='{length} {circumference - length}' "
                f"transform='rotate({offset / circumference * 360 - 90} 50 50)'><title>"
                f"{esc(name)} {value} 项（占 {value / total * 100:.1f}%）</title></circle>"
            )
            offset += length
        paths = "".join(paths)
    legend = "".join(
        f"<div class='legend'><i style='background:{color}'></i><span>{esc(name)}</span><b>{value}</b></div>"
        for name, value, color in slices
    )
    return f"<div class='donut-block donut-fixed'><svg viewBox='0 0 100 100' style='flex:0 0 120px' role='img' aria-label='{esc(label)}'>{paths}</svg><div class='legend-list'>{legend}</div></div>"


def render_summary(summary: dict[str, Any]) -> str:
    rows = summary["issues"]
    issue_count = len(rows)
    priorities = Counter(priority(issue, group) for group, issue in rows)
    metrics = Counter(str(group.get("metricName") or "体验问题") for group, _ in rows)
    top = metrics.most_common(3)
    other = issue_count - sum(value for _, value in top)
    top_slices = [
        (name, value, color)
        for (name, value), color in zip(top, TOP_COLORS)
    ]
    if other:
        top_slices.append(("其他", other, OTHER_COLOR))
    tracking = summary["tracking"]
    resolution_rate = percent_text(tracking["resolvedIssueCount"], issue_count).removesuffix("%")
    return f"""<section class='stats-section'><article class='summary-card summary-spaced'><div class='summary-numbers summary-fixed-numbers'>
<div><b>{issue_count}</b><span>累计问题</span></div><div><b>{tracking['newIssueCount']}</b><span>本月新增</span></div><div><b>{tracking['resolvedIssueCount']}</b><span>累计解决</span></div><div><b>{resolution_rate}<span class='percent-symbol'>%</span></b><span>解决率</span></div>
</div><div class='summary-divider'></div>{donut([('P0问题', priorities['P0'], PRIORITY_COLORS['P0']), ('P1问题', priorities['P1'], PRIORITY_COLORS['P1']), ('P2问题', priorities['P2'], PRIORITY_COLORS['P2'])], 'P0/P1/P2 问题占比')}<div class='summary-divider'></div>{donut(top_slices, 'TOP 问题占比')}</article></section>"""


def percent_text(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0%"
    value = numerator / denominator * 100
    return f"{value:.1f}".rstrip("0").rstrip(".") + "%"


def render_issue(
    issue: dict[str, Any],
    group: dict[str, Any],
    number: int,
    title: str | None = None,
    *,
    show_query: bool = True,
) -> str:
    level_code = str(group.get("level") or "")
    level, _ = LEVEL_META.get(level_code, (str(group.get("levelName") or "未标注层级"), "#667085"))
    dimension_label = level if level.endswith("维度") else f"{level}维度"
    label = title or f"问题{number}：{group.get('metricName') or '体验问题'}"
    priority_label = priority(issue, group)
    query_row = f"<div><dt>所属搜索词</dt><dd>{esc(issue.get('query') or '-')}</dd></div>" if show_query else ""
    return f"""<div class='issue-copy'><div class='issue-title'><span class='priority priority-{priority_label.lower()}'>{priority_label}</span><h3>{esc(label)}</h3><span class='dimension-badge dimension-{esc(level_code)}'>{esc(dimension_label)}</span></div><dl>
{query_row}<div><dt>问题描述</dt><dd>{esc(issue_description_text(issue))}</dd></div><div><dt>优化建议</dt><dd>{esc(recommendation_text(issue))}</dd></div></dl></div>"""


def ordered(entries: list[tuple[dict[str, Any], dict[str, Any]]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    return sorted(entries, key=lambda row: (PRIORITY_ORDER.get(priority(row[1], row[0]), 3), str(row[1].get("query") or ""), str(row[0].get("metricName") or "")))


def render_subfilters(options: list[tuple[str, str, int]], active_value: str, label: str) -> str:
    buttons = []
    for value, text, count in options:
        active = value == active_value
        buttons.append(
            f"<button class='subfilter{' active' if active else ''}' type='button' "
            f"data-filter-value='{esc(value)}' aria-selected='{'true' if active else 'false'}'>"
            f"{esc(text)} <span>{count}</span></button>"
        )
    return f"<div class='subfilter-bar' role='tablist' aria-label='{esc(label)}'>{''.join(buttons)}</div>"


def render_by_issue(entries: list[tuple[dict[str, Any], dict[str, Any]]]) -> str:
    """Render the final NoCode default: all priority rows are visible first."""
    rows = ordered(entries)
    counts = Counter(priority(issue, group) for group, issue in rows)
    filters = render_subfilters(
        [("all", "全部", len(rows)), *[(item, item, counts[item]) for item in PRIORITY_ORDER]],
        "all",
        "问题等级筛选",
    )
    description = "<div class='detail-description'>按 P0、P1、P2 问题等级聚合，按原始优先级排序展示。</div>"
    if not rows:
        return filters + description + "<div class='empty'>当前等级暂无问题。</div>"
    cards = []
    for number, (group, issue) in enumerate(rows, 1):
        value = priority(issue, group)
        cards.append(
            f"<article class='issue-card filter-card' data-filter-card='{esc(value)}'>"
            f"<div class='issue-layout'><div>{evidence_html(issue_image(issue), '问题证据')}</div>"
            f"{render_issue(issue, group, number)}</div></article>"
        )
    return description + filters + "".join(cards)


def render_by_query(entries: list[tuple[dict[str, Any], dict[str, Any]]]) -> str:
    """Group final-view detail by query; tabs stay in audit data rather than repeating in cards."""
    buckets: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for group, issue in entries:
        buckets[str(issue.get("query") or "未命名搜索词")].append((group, issue))
    description = "<div class='detail-description'>按 query 聚合，展示每个搜索词下的全部问题与对应原始截图。</div>"
    if not buckets:
        return description + "<div class='empty'>该业务暂无问题。</div>"
    all_tab = f"<div class='subfilter-bar' aria-label='搜索词范围'><span class='subfilter active'>全部 Tab <span>{len(buckets)}</span></span></div>"
    blocks, number = [], 0
    for query, items in sorted(buckets.items()):
        items = ordered(items)
        image = next((issue_image(issue) for _, issue in items if issue_image(issue)), "")
        copies = []
        for group, issue in items:
            number += 1
            copies.append(render_issue(issue, group, number, show_query=False))
        blocks.append(f"<article class='issue-card'><div class='issue-layout'><div>{evidence_html(image, query + ' 证据')}</div><div><h3 class='group-title'>{esc(query)} <small>{len(items)} 条问题</small></h3>{''.join(copies)}</div></div></article>")
    return description + all_tab + "".join(blocks)


def render_by_metric(entries: list[tuple[dict[str, Any], dict[str, Any]]]) -> str:
    """Render one selected metric at a time, matching the final NoCode detail view."""
    rows = ordered(entries)
    if not rows:
        return "<div class='empty'>该业务暂无问题。</div>"
    metric_counts = Counter(str(group.get("metricName") or "体验问题") for group, _ in rows)
    metric_order = list(dict.fromkeys(str(group.get("metricName") or "体验问题") for group, _ in rows))
    active_metric = metric_order[0]
    filters = render_subfilters(
        [(metric, metric, metric_counts[metric]) for metric in metric_order], active_metric, "问题指标筛选"
    )
    description = "<div class='detail-description'>按体验指标聚合，选择指标后查看该指标下的问题与典型证据。</div>"
    cards = []
    for number, (group, issue) in enumerate(rows, 1):
        metric = str(group.get("metricName") or "体验问题")
        hidden = " filter-hidden" if metric != active_metric else ""
        cards.append(
            f"<article class='issue-card filter-card{hidden}' data-filter-card='{esc(metric)}'>"
            f"<div class='issue-layout'><div>{evidence_html(issue_image(issue), '问题证据')}</div>"
            f"{render_issue(issue, group, number, f'问题{number}：{metric}')}</div></article>"
        )
    return description + filters + "".join(cards)


def render_dashboard(data: dict[str, Any]) -> str:
    businesses = [item for item in data.get("businesses", []) if isinstance(item, dict) and item.get("businessCode")]
    groups = [item for item in data.get("groups", []) if isinstance(item, dict)]
    if not businesses:
        raise ValueError("治理数据集没有可展示的业务线")

    original_order = {str(item["businessCode"]): index for index, item in enumerate(businesses)}
    stable_order = {code: index for index, code in enumerate(BUSINESS_DISPLAY_ORDER)}
    businesses = sorted(
        businesses,
        key=lambda item: (
            stable_order.get(str(item["businessCode"]), len(stable_order)),
            original_order[str(item["businessCode"])],
        ),
    )

    overview = make_summary(businesses, groups)
    batch = str(data.get("batch") or "当前批次")
    tabs = ["<button class='business-tab active' type='button' data-business='overview' aria-selected='true'>概览</button>"]
    cards, panels = [], []
    for business in businesses:
        code, name = str(business["businessCode"]), str(business.get("businessName") or business["businessCode"])
        summary = make_summary(businesses, groups, code)
        tabs.append(f"<button class='business-tab' type='button' data-business='{esc(code)}' aria-selected='false'>{esc(name)}</button>")
        priorities = summary["priorityCounts"]
        issue_count = len(summary["issues"])
        resolved_count = summary["tracking"]["resolvedIssueCount"]
        resolution_rate = percent_text(resolved_count, issue_count).removesuffix("%")
        cards.append(f"<button class='business-card' type='button' data-target='{esc(code)}' aria-label='查看{esc(name)}问题明细'><div><h3>{esc(name)}</h3><b>新增 {summary['tracking']['newIssueCount']}</b></div><div class='business-kpis'><strong><span class='business-kpi-value'>{issue_count}</span><small>累计问题</small></strong><strong><span class='business-kpi-value'>{resolved_count}</span><small>累计解决</small></strong><strong><span class='business-kpi-value'>{resolution_rate}<span class='percent-symbol'>%</span></span><small>解决率</small></strong></div><p><span>P0 {priorities['P0']}</span><span>P1 {priorities['P1']}</span><span>P2 {priorities['P2']}</span></p></button>")
        panels.append(f"<section class='panel business-panel' data-panel='{esc(code)}'>{render_summary(summary)}<div class='detail-heading'><h2>问题明细</h2><div class='detail-tabs' role='tablist' aria-label='{esc(name)}问题分组'><div class='detail-tab-item'><button class='detail-tab active' type='button' data-detail-tab='{esc(code)}-issue' aria-selected='true'>按问题等级</button></div><div class='detail-tab-item'><button class='detail-tab' type='button' data-detail-tab='{esc(code)}-query' aria-selected='false'>按搜索词</button></div><div class='detail-tab-item'><button class='detail-tab' type='button' data-detail-tab='{esc(code)}-metric' aria-selected='false'>按指标</button></div></div></div><div class='detail-pane active' data-detail-pane='{esc(code)}-issue'>{render_by_issue(summary['issues'])}</div><div class='detail-pane' data-detail-pane='{esc(code)}-query'>{render_by_query(summary['issues'])}</div><div class='detail-pane' data-detail-pane='{esc(code)}-metric'>{render_by_metric(summary['issues'])}</div></section>")

    scope = " / ".join(sorted({LEVEL_META.get(str(group.get("level") or ""), ("其他维度", ""))[0] for group in groups}))
    evaluation_scope = data.get("evaluationScope") if isinstance(data.get("evaluationScope"), dict) else {}
    scope_label = str(evaluation_scope.get("label") or "").strip()
    selected_dimensions = {
        "phase3-single_element-eval": "单一元素维度",
        "phase3-card_or_component-eval": "组件/卡片维度",
        "phase3-page_framework-eval": "页面框架维度",
    }
    scoped_levels = " / ".join(
        selected_dimensions[dimension]
        for dimension in evaluation_scope.get("dimensions", [])
        if dimension in selected_dimensions
    )
    coverage = "、".join(part for part in (scope_label, scoped_levels or scope) if part)
    execution_notes = [str(note) for note in data.get("executionNotes", []) if str(note).strip()]
    unclassified_count = int(data.get("unclassifiedCardCount") or 0)
    coverage_notes = execution_notes + (
        [f"{unclassified_count} 张商卡业务归属证据不足，未进入业务 Tab 聚合。"] if unclassified_count else []
    )
    coverage_html = "".join(f"<span>{esc(note)}</span>" for note in coverage_notes)
    return f"""<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>大搜结果页体验评测看板</title><style>
:root{{--bg:#f7f8fa;--ink:#182230;--second:#475467;--muted:#667085;--line:#eaecf0;--blue:#2563eb}}*{{box-sizing:border-box}}html{{scroll-padding-top:56px}}body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.55 -apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei','Helvetica Neue',Arial,sans-serif}}button{{font:inherit}}button:focus-visible,a:focus-visible,select:focus-visible{{outline:3px solid rgba(37,99,235,.45);outline-offset:2px}}.page{{max-width:1400px;margin:0 auto;padding:40px 32px 48px}}.head{{display:flex;justify-content:space-between;gap:24px;flex-wrap:wrap;margin-bottom:20px}}h1{{margin:0;font-size:28px;line-height:36px;font-weight:600}}.sub{{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 0;color:var(--muted);font-size:14px}}.sub i{{font-style:normal;color:#d0d5dd}}.sub a{{color:var(--blue);font-weight:500;text-decoration:none}}select{{width:280px;height:44px;border:1px solid #d0d5dd;border-radius:8px;background:#fff;padding:0 12px;color:var(--second)}}.business-tabs{{position:sticky;top:0;z-index:5;display:flex;gap:24px;margin:0 -32px 28px;padding:12px 32px;background:var(--bg);border-bottom:1px solid var(--line)}}.business-tab,.detail-tab{{position:relative;min-height:44px;padding:0 0 12px;border:0;background:none;color:var(--second);font-size:14px;cursor:pointer}}.business-tab.active,.detail-tab.active{{color:var(--blue);font-weight:600}}.business-tab.active:after,.detail-tab.active:after{{position:absolute;right:0;bottom:-1px;left:0;height:2px;background:var(--blue);content:''}}.panel{{display:none}}.panel.active{{display:block}}h2{{margin:0 0 12px;font-size:18px;line-height:28px;font-weight:600}}.summary-card,.business-card,.issue-card{{border:0;border-radius:12px;background:#fff;box-shadow:0 2px 8px rgba(16,24,40,.06)}}.summary-card{{display:flex;align-items:center;gap:32px;min-height:160px;padding:20px 24px;flex-wrap:wrap}}.summary-numbers{{display:flex;gap:24px;flex:1;min-width:240px}}.summary-numbers div{{display:flex;min-width:72px;flex:1;flex-direction:column;gap:6px}}.summary-numbers b{{font-size:36px;line-height:44px;font-weight:600;color:var(--ink)}}.summary-numbers span{{font-size:13px;line-height:18px;color:var(--muted)}}.summary-divider{{align-self:stretch;width:1px;background:var(--line)}}.donut-block{{display:flex;align-items:center;gap:16px}}.donut-block svg{{width:120px;height:120px;overflow:visible}}.legend-list{{display:flex;flex-direction:column;gap:8px}}.legend{{display:flex;align-items:center;gap:8px;color:var(--second);font-size:13px;line-height:18px}}.legend i{{width:10px;height:10px;border-radius:50%}}.legend b{{color:var(--ink)}}.stats-section{{margin-bottom:20px}}.overview-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}}.business-card{{min-height:170px;padding:16px 20px;text-align:left;cursor:pointer}}.business-card>div{{display:flex;justify-content:space-between;gap:8px}}.business-card h3{{margin:0;color:var(--ink);font-size:16px;font-weight:500}}.business-card>div b{{font-size:13px;font-weight:600}}.business-card strong{{display:block;margin-top:10px;font-size:28px;line-height:34px;font-weight:600}}.business-card strong small{{font-size:13px;font-weight:400;color:var(--muted)}}.business-card p{{display:flex;gap:8px;margin:14px 0 0}}.business-card p span{{padding:2px 10px;border:1px solid var(--line);border-radius:4px;background:#f2f4f7;color:var(--second);font-size:12px;line-height:18px}}.detail-heading{{display:flex;justify-content:space-between;align-items:center;margin:24px 0 20px;border-bottom:1px solid var(--line)}}.detail-heading h2{{margin:0;padding-bottom:12px}}.detail-tabs{{display:flex;gap:24px}}.detail-tab-item{{position:relative;display:flex;align-items:flex-start;gap:6px}}.detail-pane{{display:none}}.detail-pane.active{{display:block}}.detail-description{{margin-bottom:16px;color:var(--muted);font-size:13px;line-height:20px}}.subfilter-bar{{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 16px}}.subfilter{{min-height:34px;padding:6px 12px;border:1px solid #d0d5dd;border-radius:6px;background:#fff;color:var(--second);font-size:13px;cursor:pointer}}.subfilter span{{margin-left:4px;color:var(--muted);font-size:12px}}.subfilter.active{{border-color:var(--blue);background:#eff4ff;color:var(--blue);font-weight:600}}.subfilter.active span{{color:var(--blue)}}.filter-hidden{{display:none!important}}.issue-card{{margin-bottom:16px;padding:20px}}.issue-layout,.metric-row{{display:grid;grid-template-columns:240px minmax(0,1fr);gap:20px;align-items:start}}.metric-row+.metric-row{{margin-top:16px;padding-top:16px;border-top:1px solid var(--line)}}.evidence-link,.evidence-link img{{display:block;width:240px;height:auto;border-radius:8px}}.evidence-link{{overflow:visible;background:#f2f4f7}}.evidence-link img{{object-fit:contain}}.evidence-empty{{display:flex;width:240px;height:180px;align-items:center;justify-content:center;border-radius:8px;background:#f2f4f7;color:var(--muted);font-size:13px}}.issue-title{{display:flex;align-items:center;gap:8px;flex-wrap:wrap}}.issue-title h3,.group-title{{margin:0;color:var(--ink);font-size:16px;line-height:24px;font-weight:600}}.dimension-badge{{margin-left:auto;padding:2px 8px;border:1px solid #d0d5dd;border-radius:4px;background:#f2f4f7;color:#667085;font-size:12px;font-weight:600}}.dimension-element{{color:#2563eb}}.dimension-component{{color:#0e9384}}.dimension-page{{color:#667085}}.priority{{padding:2px 8px;border:1px solid var(--line);border-radius:4px;background:#f2f4f7;color:#475467;font-size:12px;font-weight:600}}.priority-p0,.priority-p1,.priority-p2{{background:#f2f4f7;color:#475467}}dl{{display:flex;flex-direction:column;gap:12px;margin:14px 0 0;font-size:14px;line-height:22px}}dl>div{{display:flex;flex-direction:column;align-items:flex-start;gap:3px;width:100%}}dt{{color:var(--muted);font-size:12px;line-height:18px}}dd{{width:100%;margin:0;color:var(--second);text-align:left}}.issue-copy+.issue-copy{{margin-top:12px;padding-top:12px;border-top:1px solid var(--line)}}.group-title{{margin-bottom:12px}}.group-title small{{margin-left:8px;color:var(--muted);font-size:13px;font-weight:400}}.empty{{padding:36px;border-radius:12px;background:#fff;color:var(--muted);text-align:center}}@media(max-width:900px){{.overview-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}@media(max-width:720px){{.page{{padding:24px 16px}}.business-tabs{{margin:0 -16px 28px;padding:12px 16px;overflow:auto}}.summary-divider{{display:none}}.overview-grid{{grid-template-columns:1fr}}.issue-layout,.metric-row{{grid-template-columns:1fr}}select{{width:100%}}.detail-heading{{align-items:flex-start;flex-direction:column}}.detail-tabs{{width:100%;gap:16px;overflow-x:auto}}.detail-tab-item{{flex:0 0 auto}}.subfilter-bar{{flex-wrap:nowrap;overflow-x:auto;padding-bottom:4px}}.subfilter{{flex:0 0 auto}}}}
.percent-symbol{{margin-left:1px;color:var(--muted);font-size:13px;font-weight:400}}
.summary-spaced{{justify-content:space-between}}
.summary-fixed-numbers{{display:grid;grid-template-columns:repeat(4,112px);column-gap:24px;flex:0 0 520px;min-width:520px}}.summary-fixed-numbers div{{min-width:0}}
.donut-fixed{{width:300px;flex:0 0 300px}}
.business-kpis strong{{display:flex;min-width:0;flex:1;flex-direction:column;gap:2px;margin-top:10px;line-height:1}}
.business-kpis .business-kpi-value{{display:block;line-height:1}}
.business-kpis small{{display:block;line-height:1}}
@media(max-width:900px){{.summary-fixed-numbers{{flex:1 1 100%;min-width:0}}.donut-fixed{{width:280px;flex:1 1 280px}}}}
@media(max-width:720px){{.donut-fixed{{width:100%;flex:1 1 100%}}}}
</style></head><body><main class='page'><header class='head'><div><h1>大搜结果页体验评测看板</h1><p class='sub'><span>评测日期：{esc(data.get('generatedAt') or '—')}</span><i>/</i><span>评测范围：{int(data.get('queryCount') or 0)} 个搜索词、{esc(coverage or '已执行评测')}</span>{coverage_html}<a href='https://km.sankuai.com/collabpage/2772784557' target='_blank' rel='noopener'>详情</a></p></div><select aria-label='评测批次'><option>{esc(batch)}</option></select></header><nav class='business-tabs' role='tablist'>{''.join(tabs)}</nav><section class='panel active' data-panel='overview'>{render_summary(overview)}<section><h2>业务明细</h2><div class='overview-grid'>{''.join(cards)}</div></section></section>{''.join(panels)}</main><script>
const tabs=[...document.querySelectorAll('.business-tab')],panels=[...document.querySelectorAll('.panel')];
function activateBusiness(target){{const tab=tabs.find(item=>item.dataset.business===target);if(!tab)return;tabs.forEach(item=>{{const active=item===tab;item.classList.toggle('active',active);item.setAttribute('aria-selected',String(active))}});panels.forEach(panel=>panel.classList.toggle('active',panel.dataset.panel===target))}}
tabs.forEach(tab=>tab.addEventListener('click',()=>activateBusiness(tab.dataset.business)));
document.querySelectorAll('.business-card').forEach(card=>card.addEventListener('click',()=>activateBusiness(card.dataset.target)));
document.querySelectorAll('.detail-tab').forEach(tab=>tab.addEventListener('click',()=>{{const section=tab.closest('.business-panel'),target=tab.dataset.detailTab;section.querySelectorAll('.detail-tab').forEach(item=>{{const active=item===tab;item.classList.toggle('active',active);item.setAttribute('aria-selected',String(active))}});section.querySelectorAll('.detail-pane').forEach(item=>item.classList.toggle('active',item.dataset.detailPane===target))}}));
document.querySelectorAll('.subfilter-bar').forEach(bar=>{{const pane=bar.closest('.detail-pane');bar.querySelectorAll('.subfilter').forEach(button=>button.addEventListener('click',()=>{{const value=button.dataset.filterValue;bar.querySelectorAll('.subfilter').forEach(item=>{{const active=item===button;item.classList.toggle('active',active);item.setAttribute('aria-selected',String(active))}});pane.querySelectorAll('[data-filter-card]').forEach(card=>card.classList.toggle('filter-hidden',value!=='all'&&card.dataset.filterCard!==value))}}))}});
</script></body></html>"""
