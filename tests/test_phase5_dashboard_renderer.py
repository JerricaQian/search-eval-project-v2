from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "phase5-report" / "dashboard_renderer.py"


def load_renderer():
    spec = importlib.util.spec_from_file_location("phase5_dashboard_renderer", RENDERER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Phase5DashboardRendererTest(unittest.TestCase):
    def test_problem_copy_uses_issue_description_directly(self) -> None:
        renderer = load_renderer()
        description = "商卡2价格信息同时使用起步价与到手价口径，命中口径一致规则，因此评级为不达标并增加横向比较成本"
        self.assertEqual(renderer.issue_description_text({"description": description}), f"{description}。")

    def test_renders_reference_layout_without_changing_issue_facts(self) -> None:
        renderer = load_renderer()
        data = {
            "generatedAt": "2026-08-26",
            "queryCount": 2,
            "batch": "验证批次",
            "businesses": [
                {
                    "businessCode": "dine_in",
                    "businessName": "到餐",
                    "issueCount": 1,
                    "tracking": {"newIssueCount": 1, "resolvedIssueCount": 0},
                }
            ],
            "groups": [
                {
                    "businessCode": "dine_in",
                    "level": "component",
                    "levelName": "组件/卡片",
                    "metricName": "信息冗余",
                    "evidence": [
                        {
                            "rating": "不达标",
                            "priority": "P1",
                            "query": "火锅",
                            "tab": "全部",
                            "elementLabel": "商家信息区",
                            "locationLabel": "商卡1",
                            "description": "商卡1：存在重复配送文案。",
                            "evidenceImage": "/tmp/firepot_evidence.png",
                            "recommendation": "调整坐标(12, 34)处的重复配送文案，并保留一次可见的履约说明。",
                        }
                    ],
                }
            ],
        }

        html = renderer.render_dashboard(data)
        self.assertIn("function activateBusiness", html)

        self.assertNotIn("class='topbar'", html)
        self.assertIn("class='summary-card summary-spaced'", html)
        self.assertNotIn("<h2>问题统计</h2>", html)
        self.assertIn("<h2>业务明细</h2>", html)
        self.assertIn("<h2>问题明细</h2>", html)
        self.assertIn("<span>解决率</span>", html)
        self.assertIn("<small>累计解决</small>", html)
        self.assertIn("<small>解决率</small>", html)
        self.assertIn("class='percent-symbol'>%</span>", html)
        self.assertIn(".percent-symbol{margin-left:1px;color:var(--muted);font-size:13px;font-weight:400}", html)
        self.assertIn("class='summary-card summary-spaced'", html)
        self.assertIn("class='summary-numbers summary-fixed-numbers'", html)
        self.assertIn(".summary-fixed-numbers{display:grid;grid-template-columns:repeat(4,112px);column-gap:24px;flex:0 0 520px;min-width:520px}", html)
        self.assertIn("class='donut-block donut-fixed'", html)
        self.assertIn(".donut-fixed{width:300px;flex:0 0 300px}", html)
        self.assertIn(".business-kpis strong{display:flex;min-width:0;flex:1;flex-direction:column;gap:2px", html)
        self.assertIn(".business-kpis .business-kpi-value{display:block;line-height:1}", html)
        self.assertIn(".business-kpis small{display:block;line-height:1}", html)
        self.assertIn(".page{max-width:1400px;margin:0 auto;padding:40px 32px 48px}", html)
        self.assertNotIn("style='max-width:1400px'", html)
        self.assertEqual(html.count("class='donut-block donut-fixed'"), 4)
        self.assertIn(".evidence-link,.evidence-link img{display:block;width:240px;height:auto;border-radius:8px}", html)
        self.assertIn(".evidence-empty{display:flex;width:240px;height:180px", html)
        self.assertIn("style='width:240px;height:auto;overflow:visible'", html)
        self.assertIn("style='width:240px;height:auto;max-height:none;object-fit:contain'", html)
        self.assertIn("商卡1：存在重复配送文案。", html)
        self.assertIn("调整该重复配送文案，并保留一次可见的履约说明。", html)
        self.assertIn("class='dimension-badge dimension-component'", html)
        self.assertIn("组件/卡片维度", html)
        self.assertNotIn("class='dimension-badge' style=", html)
        self.assertIn(".dimension-badge{margin-left:auto;padding:2px 8px;border:1px solid #d0d5dd", html)
        self.assertIn("class='dimension-badge dimension-component'", html)
        self.assertIn(".dimension-component{color:#0e9384}", html)
        self.assertIn("class='priority priority-p1'", html)
        self.assertIn(".priority{padding:2px 8px;border:1px solid var(--line);border-radius:4px;background:#f2f4f7;color:#475467", html)
        self.assertIn(".priority-p0,.priority-p1,.priority-p2{background:#f2f4f7;color:#475467}", html)
        self.assertIn("stroke-linecap='round'", html)
        donut_html = renderer.donut([("甲", 1, "#111111"), ("乙", 1, "#222222")], "连续圆环")
        self.assertIn("stroke-dasharray='125.6635 125.6635'", donut_html)
        self.assertIn("rotate(90.0 50 50)", donut_html)
        self.assertIn("#ECB5C4", html)
        self.assertEqual(renderer.TOP_COLORS, ("#ECB5C4", "#C8D8F9", "#D8BFF2"))
        self.assertEqual(renderer.OTHER_COLOR, "#D9D9D9")
        self.assertNotIn("<dt>层级</dt>", html)
        self.assertNotIn("【问题出现位置：", html)
        self.assertNotIn("【问题描述：", html)
        self.assertNotIn("对象定位", html)
        self.assertNotIn("坐标(", html)
        self.assertIn("data-detail-tab='dine_in-issue'", html)
        self.assertIn(">按问题等级</button>", html)
        self.assertIn("aria-label='问题等级筛选'", html)
        self.assertIn("data-filter-value='all'", html)
        self.assertIn("全部 <span>1</span>", html)
        self.assertIn("data-filter-value='P0'", html)
        self.assertIn("data-filter-value='P1'", html)
        self.assertIn("data-filter-value='P2'", html)
        self.assertIn("aria-label='问题指标筛选'", html)
        self.assertIn("data-filter-value='信息冗余'", html)
        self.assertIn("按 P0、P1、P2 问题等级聚合，按原始优先级排序展示。", html)
        self.assertIn("按 query 聚合，展示每个搜索词下的全部问题与对应原始截图。", html)
        self.assertIn("按体验指标聚合，选择指标后查看该指标下的问题与典型证据。", html)
        self.assertIn("querySelectorAll('.subfilter-bar')", html)
        self.assertIn("value!=='all'&&card.dataset.filterCard!==value", html)
        self.assertNotIn("class='info-tip'", html)
        self.assertNotIn("人工复核", html)

        entries = renderer.flattened_issues(data["groups"])
        query_html = renderer.render_by_query(entries)
        issue_html = renderer.render_by_issue(entries)
        metric_html = renderer.render_by_metric(entries)
        self.assertNotIn("<dt>所属搜索词</dt>", query_html)
        self.assertIn("全部 Tab <span>1</span>", query_html)
        self.assertNotIn("全部 Tab ·", query_html)
        self.assertIn("<dt>所属搜索词</dt>", issue_html)
        self.assertIn("<dt>所属搜索词</dt>", metric_html)
        self.assertIn("data-filter-value='all'", renderer.render_by_issue([]))
        self.assertEqual(renderer.render_by_issue([]).count("data-filter-value='P"), 3)

    def test_business_tabs_follow_final_nocode_stable_order(self) -> None:
        renderer = load_renderer()
        businesses = [
            {"businessCode": "maoyan", "businessName": "猫眼"},
            {"businessCode": "dine_in", "businessName": "到餐"},
            {"businessCode": "xiaoxiang", "businessName": "小象超市"},
            {"businessCode": "service_retail", "businessName": "服务零售"},
        ]
        groups = [
            {"businessCode": "dine_in", "level": "component", "metricName": "信息冗余", "evidence": [
                {"rating": "不达标", "query": "火锅", "locationLabel": "商卡1", "description": "重复信息", "recommendation": "删除重复信息。"},
            ]},
            {"businessCode": "service_retail", "level": "component", "metricName": "信息冗余", "evidence": [
                {"rating": "不达标", "query": "剧本杀", "locationLabel": "商卡1", "description": "重复信息A", "recommendation": "删除重复信息A。"},
                {"rating": "达标", "query": "美甲", "locationLabel": "商卡2", "description": "重复信息B", "recommendation": "删除重复信息B。"},
            ]},
        ]
        html = renderer.render_dashboard({"businesses": businesses, "groups": groups})
        self.assertLess(html.index("data-business='service_retail'"), html.index("data-business='dine_in'"))
        self.assertLess(html.index("data-business='dine_in'"), html.index("data-business='maoyan'"))
        self.assertLess(html.index("data-business='maoyan'"), html.index("data-business='xiaoxiang'"))
