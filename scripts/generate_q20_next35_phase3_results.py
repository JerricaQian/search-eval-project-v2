#!/usr/bin/env python3
"""Materialize the current-pixel Phase3 judgement for next35 q20."""

import json
from itertools import combinations
from pathlib import Path

ROOT = Path("/Users/qianjing/Documents/ChatGPT/search-eval-project-v2")
RUN = "batch-20260920-09-2-next35-r1-q20"
BATCH = "batch-20260920-09-2-next35-r1"
QUERY = "浐灞国家湿地公园游乐场门票"
STEM = "浐灞国家湿地公园游乐场门票_全部_1"
SHOT = str(ROOT / f"screenshots/{STEM}.png")
MANIFEST = ROOT / f"screenshots-out/elements_{STEM}_{RUN}.json"
AUDIT = ROOT / f"screenshots-out/elements_{STEM}_{RUN}.audit.json"
BASE = ROOT / f".artifacts/过程文件-评测结果与审计/{BATCH}/{RUN}"
MEASURE = BASE / f"phase3/measurements/elements_{STEM}_{RUN}.component-color-families.json"
OUT = BASE / f"results/评测原始结果_{RUN}.json"

# Generate the validated 15-skill merchant-card scaffold against this run's
# current manifest, then replace every judgement that depends on q20 content.
template = (ROOT / "scripts/generate_q17_next35_phase3_results.py").read_text(encoding="utf-8")
template = template.replace('RUN = "batch-20260920-09-2-next35-r1-q17"', f'RUN = "{RUN}"')
template = template.replace('QUERY = "正清馆空手道"', f'QUERY = "{QUERY}"')
template = template.replace('STEM = "正清馆空手道_全部_1"', f'STEM = "{STEM}"')
namespace = {"__name__": "__main__", "__file__": str(ROOT / "scripts/generate_q17_next35_phase3_results.py")}
exec(compile(template, namespace["__file__"], "exec"), namespace)

manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
audit = json.loads(AUDIT.read_text(encoding="utf-8"))
colors = json.loads(MEASURE.read_text(encoding="utf-8"))["components"]
results = json.loads(OUT.read_text(encoding="utf-8"))
all_cards = manifest["cards"]
complete_cards = [card for card in all_cards if card["structure"]["visibleStatus"] == "complete"]
by_id = {card["cardId"]: card for card in all_cards}


def unit(skill, dimension="phase3-card_or_component-eval"):
    return next(item["units"][0] for item in results if item["skill"] == skill and item["dimension"] == dimension)


def elems(card):
    return [element for region in card["regions"] for element in region["elements"]]


def region_names(card):
    return [region["name"] for region in card["regions"]]


def complete_overview(total, rating="优秀"):
    return {
        "total": total,
        "excellent": total if rating == "优秀" else 0,
        "pass": total if rating == "达标" else 0,
        "fail": total if rating == "不达标" else 0,
        "failRate": "100.0%" if rating == "不达标" else "0.0%",
    }


cropped = [{"componentId": "C4", "reason": "页面底部自然裁切，仅排除屏外不可见区域，不据此判缺失。"}]
for skill in (
    "eval-1-supply-completeness",
    "eval-2-visual-order-alignment",
    "eval-4-element-complexity",
    "eval-5-info-hierarchy",
    "eval-7-info-authenticity",
):
    unit(skill)["details"]["evidence"]["excludedUnits"] = cropped

# Card supply: complete no-downhang and text-downhang variants are assessed
# against their own card contracts rather than requiring every merchant to
# expose a purchasable rail.
u = unit("eval-1-supply-completeness")
u["rating"] = "优秀"
u["reason"] = "3张完整结果卡均按各自卡型呈现头图、主体名称、评分/评价数、位置或距离；两张文字下挂卡还完整展示两组可购买项目、价格与销量，无下挂的游乐场卡保持精简但核心信息齐全。"
u["details"]["overview"] = complete_overview(3)
u["details"]["evidence"] = {
    "sourceManifestTotal": audit["total"],
    "evaluatedUnitCount": 3,
    "evaluatedUnitIds": ["C1", "C2", "C3"],
    "assessmentRows": [],
    "excludedUnits": cropped,
}
u["details"]["issues"] = []

# Visual order: compare only the repeated complete text-downhang type.  The
# single complete no-downhang card is not forced into another layout group.
comparable = [by_id["C1"], by_id["C3"]]
signatures = []
order_checks = []
for card in comparable:
    signatures.append({
        "componentId": card["cardId"],
        "layoutMode": card["structure"]["layoutMode"],
        "layoutSignature": card["structure"]["layoutSignature"],
        "regions": [{
            "region": region["name"],
            "elementIds": [element["id"] for element in region["elements"]],
            "contentBounds": region["coord"],
        } for region in card["regions"]],
        "relations": [card["structure"]["layoutAnchorRelation"]],
    })
    order_checks.append({
        "componentId": card["cardId"],
        "expectedOrder": ["头图与商家标题", "评分/距离基础信息", "价格与文字下挂项目"],
        "observedOrder": ["头图与商家标题", "评分/距离基础信息", "价格与文字下挂项目"],
        "attentionSignals": ["标题建立主体", "评分和距离承接", "下挂项目保持次级"],
        "dominantRegion": "基础信息区",
        "reason": "主体、基础决策信息和可购买项目保持稳定的自上而下阅读顺序。",
        "auxiliaryDominance": False,
        "competingFoci": False,
        "ownershipAmbiguity": False,
        "pathInversion": False,
        "localDetour": False,
        "status": "consistent",
    })
u = unit("eval-2-visual-order-alignment")
u["rating"] = "优秀"
u["reason"] = "两张完整文字下挂商家卡均保持左侧头图、右侧主体与基础信息、下方可购买项目的稳定扫读顺序；无下挂卡为单例，不强行跨型比较。"
u["details"]["overview"] = complete_overview(1)
u["details"]["evidence"] = {
    "sourceManifestTotal": audit["total"],
    "evaluatedUnitCount": 1,
    "assessmentRows": [{
        "comparisonGroupKey": comparable[0]["structure"]["comparisonGroupKey"],
        "members": ["C1", "C3"],
        "layoutSignatures": signatures,
        "readingOrderChecks": order_checks,
        "evidenceSource": "original_screenshot_visual_review",
        "rating": "优秀",
    }],
    "excludedUnits": cropped + [{"componentId": "C2", "reason": "完整无下挂卡仅1张，不满足同型重复比较条件。"}],
}
u["details"]["issues"] = []

u = unit("eval-3-color-logic")
u["rating"] = "优秀"
u["reason"] = "4张可见结果卡的有效非中性色相族分别为2、3、2、2种，均不超过组件级优秀档上限。"
u["details"]["overview"] = complete_overview(4)
u["details"]["evidence"] = {"sourceManifestTotal": audit["total"], "evaluatedUnitCount": 4, "assessmentRows": colors}
u["details"]["issues"] = []

u = unit("eval-4-element-complexity")
u["rating"] = "优秀"
u["reason"] = "3张完整卡仅包含0至2枚独立彩色促销标签且无附加功能图标，均落入优秀档。"
u["details"]["overview"] = complete_overview(3)

u = unit("eval-5-info-hierarchy")
u["reason"] = "3张完整卡均由商家或景点标题建立主层，评分、评价数和距离承接，促销与票种下挂保持次级，未形成竞争主焦点。"

u = unit("eval-6-info-partitioning")
u["reason"] = "基础信息、优惠和文字下挂项目通过稳定对齐与留白分开；无下挂卡保持单一基础信息区，未见跨区粘连或错误归属。"

u = unit("eval-7-info-authenticity")
u["reason"] = "逐卡核对标题、头图、评分位置及下挂票种与价格归属后，未发现同一卡内不能同时成立的客观冲突。"

u = unit("eval-8-info-redundancy")
u["reason"] = "已扫描4张可见卡的标题、基础信息、标签、价格与文字下挂项目；同卡内重复出现的“门票”分别属于独立票种行，不能无损删除，语义重复数为0。"

# Page module completeness and reading order use the authoritative reviewed
# modules M4-M10; detector duplicates M1-M3 and M11 are not double-counted.
page_dim = "phase3-page_framework-eval"
u = unit("eval-1-supply-module-completeness", page_dim)
u["rating"] = "优秀"
u["reason"] = "搜索入口、心智Tab、主点景区卡、业务分类图筛、排序筛选、门票券筛选和自然结果列表均完整可见。"
u["details"]["overview"] = complete_overview(1)
u["details"]["evidence"] = {"assessmentRows": []}
u["details"]["issues"] = []

u = unit("eval-2-visual-order-alignment", page_dim)
u["rating"] = "优秀"
u["reason"] = "页面从搜索与心智Tab进入主点景区信息，再经过业务图筛、排序及门票券筛选进入连续结果列表，阅读路径稳定。"
u["details"]["overview"] = complete_overview(1)
u["details"]["evidence"] = {"assessmentRows": [{
    "pageRegions": [
        {"region": "搜索与心智Tab", "observedRole": "建立查询与结果范围", "visualSignals": ["顶部固定顺序", "选中态清楚"]},
        {"region": "主点景区卡", "observedRole": "呈现目标景区身份与服务入口", "visualSignals": ["大块独立卡面", "位于筛选之前"]},
        {"region": "业务图筛与筛选", "observedRole": "缩小业务、排序和优惠范围", "visualSignals": ["横向分组", "与列表留白分隔"]},
        {"region": "自然结果列表", "observedRole": "连续呈现可比较供给", "visualSignals": ["商家卡纵向排列", "卡间节奏稳定"]},
    ],
    "sameTypeComparisons": [{"members": ["C1", "C3"], "result": "文字下挂卡主体与项目锚点一致"}],
    "primaryFocus": "主点景区与结果卡标题",
    "flowChecks": [{
        "expectedOrder": ["搜索与Tab", "主点景区", "图筛与筛选", "结果列表"],
        "observedOrder": ["搜索与Tab", "主点景区", "图筛与筛选", "结果列表"],
        "visualSignals": ["自上而下单列推进", "结果列表连续重复"],
        "reason": "模块先后关系清楚，未出现主焦点错位或辅助模块抢占。",
        "status": "consistent",
    }],
    "evidenceSource": "original_screenshot_visual_review",
    "rating": "优秀",
}]}
u["details"]["issues"] = []

families = sorted({family for item in colors for family in item["colorFamilies"]})
u = unit("eval-3-page-color-logic", page_dim)
u["rating"] = "优秀"
u["reason"] = f"全页结果卡的有效界面色系并集为{'、'.join(families)}共{len(families)}种，不超过5种的页面级优秀阈值。"
u["details"]["overview"] = complete_overview(1)
u["details"]["evidence"] = {"assessmentRows": [{
    "colorLogicContractVersion": "4.0",
    "componentColorArtifact": str(MEASURE),
    "componentColorSummaries": [{"componentId": item["componentId"], "colorFamilies": item["colorFamilies"], "colorFamilyCount": item["colorFamilyCount"]} for item in colors],
    "colorFamilies": families,
    "colorFamilyCount": len(families),
    "evidenceSource": "component_pixel_color_aggregation",
    "rating": "优秀",
}]}
u["details"]["issues"] = []

# Six independent functional regions remain after excluding the search box.
functional_modules = [
    {"module": "心智Tab", "sourceIds": ["M5"], "reason": "切换结果意图"},
    {"module": "主点景区卡", "sourceIds": ["M6"], "reason": "呈现目标景区身份与服务入口"},
    {"module": "业务分类图筛", "sourceIds": ["M7"], "reason": "按景点、酒店、美食等业务缩小范围"},
    {"module": "分类/距离/排序筛选", "sourceIds": ["M8"], "reason": "控制结果分类、距离与排序"},
    {"module": "门票券优惠筛选", "sourceIds": ["M9"], "reason": "按满减券权益过滤"},
    {"module": "自然结果列表", "sourceIds": ["M10", "M11"], "reason": "连续承载结果供给"},
]
u = unit("eval-4-static-component-complexity", page_dim)
u["rating"] = "不达标"
u["reason"] = "排除搜索框并合并重复识别的结果列表后，当前首屏仍有6个独立功能区，命中不达标档。"
u["details"]["overview"] = complete_overview(1, "不达标")
u["details"]["evidenceMode"] = "original-page"
u["details"]["evidence"] = {"assessmentRows": [{
    "firstScreenBounds": {"x": 0, "y": 0, "width": 1136, "height": 2690},
    "functionalModules": functional_modules,
    "moduleCount": 6,
    "excludedUnits": [{"module": "搜索框", "sourceIds": ["M4"], "reason": "按规则排除"}, {"module": "自动检测重复项", "sourceIds": ["M1", "M2", "M3"], "reason": "与人工确认的搜索、Tab或图筛区域重叠，不重复计数"}],
    "rating": "不达标",
}]}
u["details"]["issues"] = [{
    "pageArea": "首屏功能区",
    "description": "排除搜索框并去重后仍有6个独立功能区，业务图筛、常规筛选和门票券筛选形成连续三层控制，信息切换负担偏高。",
    "rating": "不达标",
    "recommendation": "合并业务分类图筛与常规分类筛选，或将门票券优惠并入同一筛选面板；验收时确认首屏独立功能区不超过5个。",
    "evidenceImage": SHOT,
}]

u = unit("eval-5-browsing-flow-smoothness", page_dim)
u["rating"] = "优秀"
u["reason"] = "排序筛选下方4个可见列表位均为普通商家卡；无下挂卡属于标准商家卡内容变体，底部卡虽自然裁切但不构成异构插入。"
u["details"]["overview"] = complete_overview(1)
u["details"]["evidence"] = {"assessmentRows": [{
    "listPositions": [{
        "position": card["structure"]["listPosition"],
        "componentId": card["cardId"],
        "cardType": card["cardTypeName"],
        "isHeterogeneous": False,
        "visibleStatus": card["structure"]["visibleStatus"],
    } for card in all_cards],
    "visibleListPositionCount": 4,
    "coverageStatus": "partial",
    "heterogeneousCount": 0,
    "frontTenHeterogeneousCount": 0,
    "allHeterogeneousItems": [],
    "rating": "优秀",
}]}
u["details"]["issues"] = []

u = unit("eval-6-info-comparability", page_dim)
u["rating"] = "优秀"
u["reason"] = "两张完整文字下挂卡均在固定基础信息区呈现评分、评价数与距离，并在下挂区呈现两组价格和项目名；字段格式与锚点一致，可直接比较。"
u["details"]["overview"] = complete_overview(1)
u["details"]["evidence"] = {"assessmentRows": [{
    "cardGroups": [{"comparisonGroupKey": comparable[0]["structure"]["comparisonGroupKey"], "members": ["C1", "C3"]}],
    "comparableFields": ["评分", "评价数", "距离", "两组项目价格与名称"],
    "comparisons": [{
        "comparisonGroupKey": comparable[0]["structure"]["comparisonGroupKey"],
        "semanticRole": "score_review_distance_price_attachment",
        "observations": [{"componentId": card["cardId"], "present": True, "anchor": "基础信息区与文字下挂区"} for card in comparable],
        "detectedDifferences": {"missing": [], "formatMismatch": False, "anchorMismatch": False},
        "phase3Judgement": "consistent",
    }],
    "inconsistencyCount": 0,
    "excludedUnits": [{"componentId": "C2", "reason": "无下挂卡型不同，不与文字下挂卡强行比较"}, {"componentId": "C4", "reason": "页面底部自然裁切"}],
    "evidenceSource": "phase2_json_cross_card_comparison",
    "rating": "优秀",
}]}
u["details"]["issues"] = []

page_regions = ["搜索框", "心智Tab", "主点景区卡", "业务图筛与筛选", "自然结果列表"]
pairs = list(combinations(page_regions, 2))
u = unit("eval-7-info-redundancy", page_dim)
u["rating"] = "优秀"
u["reason"] = "已覆盖搜索、心智Tab、主点景区卡、筛选和结果列表并完成10组两两检查；各区域职责不同，跨区域冗余数为0。"
u["details"]["overview"] = complete_overview(1)
u["details"]["evidence"] = {"assessmentRows": [{
    "pageRegions": page_regions,
    "candidatePairs": [],
    "scanCoverage": {"status": "completed", "scannedRegionIds": page_regions, "crossChecks": [f"{left} ↔ {right}" for left, right in pairs]},
    "crossChecks": [{"regions": [left, right], "judgement": "distinct", "reason": "两区域承担不同页面任务或提供不同决策信息。"} for left, right in pairs],
    "redundancyItems": [],
    "redundancyCount": 0,
    "rating": "优秀",
}]}
u["details"]["issues"] = []

OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(OUT)
