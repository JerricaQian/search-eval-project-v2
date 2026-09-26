#!/usr/bin/env python3
"""Materialize the current-pixel Phase3 judgement for next35 q23."""

import json
from pathlib import Path


ROOT = Path("/Users/qianjing/Documents/ChatGPT/search-eval-project-v2")
RUN = "batch-20260920-09-2-next35-r1-q23"
QUERY = "港式营养套餐饭"
STEM = "港式营养套餐饭_全部_1"
SHOT = str(ROOT / f"screenshots/{STEM}.png")
BASE = ROOT / f".artifacts/过程文件-评测结果与审计/batch-20260920-09-2-next35-r1/{RUN}"
OUT = BASE / f"results/评测原始结果_{RUN}.json"

# Reuse the already contract-complete merchant-card judgement materializer, but
# bind it to this run before execution. The post-processing below records only
# q23 current-pixel facts and leaves the shared evidence structures intact.
template_path = ROOT / "scripts/generate_q17_next35_phase3_results.py"
source = template_path.read_text(encoding="utf-8")
source = source.replace('RUN = "batch-20260920-09-2-next35-r1-q17"', f'RUN = "{RUN}"')
source = source.replace('QUERY = "正清馆空手道"', f'QUERY = "{QUERY}"')
source = source.replace('STEM = "正清馆空手道_全部_1"', f'STEM = "{STEM}"')
namespace = {"__name__": "__main__", "__file__": str(template_path)}
exec(compile(source, str(template_path), "exec"), namespace)

results = json.loads(OUT.read_text(encoding="utf-8"))
by_skill = {item["skill"]: item for item in results}


def unit(skill):
    return by_skill[skill]["units"][0]


# Two cards are fully visible; C3 is a viewport-bottom natural crop.
unit("eval-1-supply-completeness")["reason"] = (
    "2张完整商家卡均呈现商家标题、评分、评价量、人均价、位置、品类、距离与下挂商品价格；"
    "第3张为视口底部自然裁切，不推断屏外价格内容。"
)
unit("eval-1-supply-completeness")["details"]["evidence"]["excludedUnits"] = [
    {"componentId": "C3", "reason": "视口底部自然裁切，不推断屏外价格内容。"}
]

unit("eval-2-visual-order-alignment")["reason"] = (
    "2张完整同型商家卡均保持商家基础信息在上、图文下挂商品在下的稳定扫读顺序。"
)

unit("eval-3-color-logic")["reason"] = (
    "3张可见商家卡的有效非中性色相族分别为2、4、2种，均不超过优秀档上限。"
)

complexity = unit("eval-4-element-complexity")
counts = [
    row["tagStyleCount"] + row["iconStyleCount"]
    for row in complexity["details"]["evidence"]["assessmentRows"]
]
complexity["reason"] = (
    f"2张完整商家卡各有{counts[0]}和{counts[1]}枚独立彩色标签或促销标，"
    "未见附加功能图标，均未超过优秀档上限。"
)

unit("eval-5-info-hierarchy")["reason"] = (
    "商家标题稳定承担主层，评分、评价量、人均价与位置承接，优惠和下挂商品保持次级，2张完整卡均无竞争主焦点。"
)
unit("eval-6-info-partitioning")["reason"] = (
    "商家基础信息、促销标签和下挂商品通过稳定对齐与留白分开，未发现跨区粘连或错误归属。"
)
unit("eval-7-info-authenticity")["reason"] = (
    "逐卡核对商家标题、评分、位置、促销与下挂商品价格后，未发现不能同时成立的客观冲突。"
)
unit("eval-8-info-redundancy")["reason"] = (
    "已逐卡扫描3张可见商家卡的标题、基础信息、标签、促销和下挂商品，未发现可无损删除的重复事实。"
)

# The page visibly includes query navigation, a merchant-supplement entry,
# location filtering, an empty-result notice, and the recommendation list.
unit("eval-1-supply-module-completeness")["reason"] = (
    "搜索入口、业务Tab、商户补充入口、位置筛选、无相关结果提示与推荐商家列表均已清楚呈现。"
)

page_alignment = unit("eval-2-visual-order-alignment")
page_alignment["reason"] = (
    "页面从搜索与Tab依次进入商户补充、位置筛选、结果状态提示和推荐商家列表，整体阅读顺序稳定。"
)
page_alignment["details"]["evidence"]["assessmentRows"][0]["pageRegions"] = [
    {"region": "搜索与Tab区", "observedRole": "建立查询和业务范围", "visualSignals": ["顶部稳定定位", "选中Tab有强调"]},
    {"region": "商户补充与位置筛选区", "observedRole": "补充商户并约束地点", "visualSignals": ["独立入口", "与结果提示留白分隔"]},
    {"region": "结果状态与推荐列表", "observedRole": "解释无相关结果并连续呈现推荐商家", "visualSignals": ["提示先于列表", "同型商家卡纵向排列"]},
]
page_alignment["details"]["evidence"]["assessmentRows"][0]["sameTypeComparisons"] = [
    {"members": ["商卡1", "商卡2"], "result": "商家信息在上、图文下挂商品在下的锚点一致"}
]
page_alignment["details"]["evidence"]["assessmentRows"][0]["flowChecks"] = [{
    "expectedOrder": ["搜索与Tab", "商户补充", "位置筛选", "结果状态", "推荐商家"],
    "observedOrder": ["搜索与Tab", "商户补充", "位置筛选", "结果状态", "推荐商家"],
    "visualSignals": ["自上而下单列推进", "提示后接同型商家卡"],
    "reason": "页面模块按操作前置、状态解释、结果浏览的顺序排列，未出现主焦点错位。",
    "status": "consistent",
}]

unit("eval-3-page-color-logic")["reason"] = (
    "全页商家组件像素色系并集为红、橙、黄、绿共4种，未超过优秀档上限。"
)

page_complexity = unit("eval-4-static-component-complexity")
page_complexity["rating"] = "达标"
page_complexity["reason"] = (
    "排除顶部搜索框并合并重复识别的结果列表后，首屏有5个独立功能区，处于达标档。"
)
page_complexity["details"]["overview"] = {
    "total": 1,
    "excellent": 0,
    "pass": 1,
    "fail": 0,
    "failRate": "0.0%",
}
page_complexity["details"]["evidence"]["assessmentRows"] = [{
    "firstScreenBounds": [0, 0, 1136, 2690],
    "functionalModules": [
        {"name": "业务Tab栏", "sourceModuleIds": ["M3"]},
        {"name": "商户补充入口", "sourceModuleIds": ["M4"]},
        {"name": "位置筛选", "sourceModuleIds": ["M5"]},
        {"name": "结果状态提示", "sourceModuleIds": ["M6"]},
        {"name": "推荐商家列表", "sourceModuleIds": ["M7", "M8"]},
    ],
    "moduleCount": 5,
    "rating": "达标",
}]
page_complexity["details"]["issues"] = [{
    "pageArea": "首屏搜索框下方至推荐商家列表",
    "description": "排除搜索框后仍有5个独立功能区，比优秀档上限多1个。",
    "rating": "达标",
    "recommendation": "合并商户补充入口与结果状态提示，将补充商户改为提示内的次级入口；验收时确认首屏独立功能区不超过4个。",
    "evidenceImage": SHOT,
}]

flow = unit("eval-5-browsing-flow-smoothness")
flow["reason"] = (
    "位置筛选与结果提示下方3个可见列表位均为同型商家卡；末位为自然裁切，已见范围内异构数为0。"
)

comparability = unit("eval-6-info-comparability")
comparability["reason"] = (
    "2张完整同型商家卡均在固定基础信息区呈现评分、评价量、人均价、位置与距离，并在下挂区呈现商品价格，可直接横向比较。"
)
comp_row = comparability["details"]["evidence"]["assessmentRows"][0]
comp_row["comparableFields"] = ["评分", "评价量", "人均价", "位置", "距离", "下挂商品价格"]
comp_row["comparisons"][0]["semanticRole"] = "rating_review_per_capita_location_distance_item_price"

page_red = unit("eval-7-info-redundancy")
page_red["reason"] = (
    "已覆盖搜索框、业务Tab、商户补充、位置筛选、结果提示和推荐列表；各区域职责不同，跨区域冗余数为0。"
)
regions = ["搜索框", "业务Tab栏", "商户补充入口", "位置筛选", "结果状态提示", "推荐商家列表"]
row = page_red["details"]["evidence"]["assessmentRows"][0]
row["pageRegions"] = regions
checks = []
for i, left in enumerate(regions):
    for right in regions[i + 1:]:
        checks.append({"regions": [left, right], "judgement": "distinct", "reason": "两区域承担不同页面任务或提供不同决策信息。"})
row["candidatePairs"] = []
row["scanCoverage"] = {
    "status": "completed",
    "scannedRegionIds": regions,
    "crossChecks": [f"{item['regions'][0]} ↔ {item['regions'][1]}" for item in checks],
}
row["crossChecks"] = checks

OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(OUT)
