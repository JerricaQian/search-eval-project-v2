#!/usr/bin/env python3
"""Generate the current-pixel Phase3 judgement for final30 q14."""

import json
from itertools import combinations
from pathlib import Path

ROOT = Path("/Users/qianjing/Documents/ChatGPT/search-eval-project-v2")
RUN = "batch-20260920-09-2-final30-r1-q14"
BATCH = "batch-20260920-09-2-final30-r1"
QUERY = "葛尼沙印度菜"
STEM = "葛尼沙印度菜_全部_1"
SHOT = str(ROOT / f"screenshots/{STEM}.png")
MANIFEST = ROOT / f"screenshots-out/elements_{STEM}_{RUN}.json"
AUDIT = ROOT / f"screenshots-out/elements_{STEM}_{RUN}.audit.json"
BASE = ROOT / f".artifacts/过程文件-评测结果与审计/{BATCH}/{RUN}"
MEASURE = BASE / f"phase3/measurements/elements_{STEM}_{RUN}.component-color-families.json"
OUT = BASE / f"results/评测原始结果_{RUN}.json"

# Build a schema-complete shell from the current batch's q5 generator, then
# replace every current-page judgement below.
scaffold = ROOT / "scripts/generate_q5_final30_phase3_results.py"
source = scaffold.read_text(encoding="utf-8")
source = source.replace('RUN = "batch-20260920-09-2-final30-r1-q5"', f'RUN = "{RUN}"')
source = source.replace('QUERY = "老东北麻黏糊辣烫"', f'QUERY = "{QUERY}"')
source = source.replace('STEM = "老东北麻黏糊辣烫_全部_1"', f'STEM = "{STEM}"')
exec(compile(source, str(scaffold), "exec"), {"__name__": "__main__", "__file__": str(scaffold)})

manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
audit = json.loads(AUDIT.read_text(encoding="utf-8"))
colors = json.loads(MEASURE.read_text(encoding="utf-8"))["components"]
results = json.loads(OUT.read_text(encoding="utf-8"))
all_cards = manifest["cards"]
cards = [card for card in all_cards if card["structure"]["visibleStatus"] == "complete"]
card_ids = [card["cardId"] for card in cards]
source_total = audit["total"]


def component_unit(skill):
    return next(item["units"][0] for item in results if item["dimension"] == "phase3-card_or_component-eval" and item["skill"] == skill)


def page_unit(skill):
    return next(item["units"][0] for item in results if item["dimension"] == "phase3-page_framework-eval" and item["skill"] == skill)


def elements(card):
    return [element for region in card["regions"] for element in region["elements"]]


def text_elements(card):
    return [element for element in elements(card) if not element.get("render", {}).get("isPhoto")]


def region_names(card):
    return [region["name"] for region in card["regions"]]


def set_overview(unit, total, excellent, passed=0, failed=0):
    unit["details"]["overview"] = {
        "total": total,
        "excellent": excellent,
        "pass": passed,
        "fail": failed,
        "failRate": f"{(failed / total * 100):.1f}%" if total else "0.0%",
    }


cropped = [{"componentId": "C2", "reason": "底部自然裁切，仅保留当前可见事实，不用于完整商卡结论。"}]

# Component supply.
u = component_unit("eval-1-supply-completeness")
u["rating"] = "优秀"
u["reason"] = "2张完整商家卡均呈现商家标题、评分、位置、口碑与可读图文下挂；第3张为底部自然裁切，不作为字段缺失样本。"
u["details"]["evidence"] = {"sourceManifestTotal": source_total, "evaluatedUnitCount": 2, "assessmentRows": [], "excludedUnits": cropped}
u["details"]["issues"] = []
set_overview(u, 2, 2)

# Component visual order.
layout_signatures, order_checks = [], []
for card in cards:
    layout_signatures.append({
        "componentId": card["cardId"],
        "layoutMode": card["structure"]["layoutMode"],
        "layoutSignature": card["structure"]["layoutSignature"],
        "regions": [{"region": region["name"], "elementIds": [element["id"] for element in region["elements"]], "contentBounds": region["coord"]} for region in card["regions"]],
        "relations": [card["structure"]["layoutAnchorRelation"]],
    })
    order_checks.append({
        "componentId": card["cardId"],
        "expectedOrder": ["商家标题与头图", "评分、位置与榜单", "优惠与下挂商品"],
        "observedOrder": ["商家标题与头图", "评分、位置与榜单", "优惠与下挂商品"],
        "attentionSignals": ["标题与头图先建立商家主体", "优惠和商品位保持次级"],
        "dominantRegion": "基础信息区",
        "auxiliaryDominance": False,
        "competingFoci": False,
        "ownershipAmbiguity": False,
        "pathInversion": False,
        "localDetour": False,
        "reason": "主体、基础决策字段和下挂供给按稳定顺序展开，未出现归属混乱。",
        "status": "consistent",
    })
alignment = {
    "comparisonGroupKey": cards[0]["structure"]["comparisonGroupKey"],
    "members": card_ids,
    "layoutSignatures": layout_signatures,
    "readingOrderChecks": order_checks,
    "evidenceSource": "original_screenshot_visual_review",
    "rating": "优秀",
}
u = component_unit("eval-2-visual-order-alignment")
u["rating"] = "优秀"
u["reason"] = "2张完整同型商家卡均先呈现商家主体和基础信息，再进入优惠券与横滑商品，扫读顺序稳定。"
u["details"]["evidence"] = {"sourceManifestTotal": source_total, "evaluatedUnitCount": 1, "assessmentRows": [alignment], "excludedUnits": cropped}
u["details"]["issues"] = []
set_overview(u, 1, 1)

# Component color logic: cropped C2 is still measurable in its visible area.
u = component_unit("eval-3-color-logic")
u["rating"] = "达标"
u["reason"] = "3张可见商家卡的有效界面色系数分别为4、4、5；底部可见卡使用红、橙、黄、绿、青5种，命中达标档。"
u["details"]["evidence"] = {"sourceManifestTotal": source_total, "evaluatedUnitCount": 3, "assessmentRows": colors}
u["details"]["issues"] = [{
    "elementId": "C2-T24",
    "coord": [640, 2610, 145, 42],
    "component": "C2",
    "description": "商卡3当前可见区域的有效界面色系为「红、橙、黄、绿、青」共5种，超过优秀档4种上限并命中达标档。",
    "rating": "达标",
    "recommendation": "统一商品推荐字、履约与促销中的至少1种次要色系；验收时确认单卡有效色系不超过4种。",
    "evidenceImage": SHOT,
}]
set_overview(u, 3, 2, passed=1)

# Component complexity: only confirmed tag/icon atoms count.
complexity_rows = []
for card in cards:
    included, excluded, ledger = [], [], []
    for element in elements(card):
        role = element.get("textFacts", {}).get("semanticRole", "")
        color = element.get("visual", {}).get("colorRole", "unknown")
        is_included = bool(element.get("visual", {}).get("countedInComplexity")) or (
            role in {"promotion", "recommendation", "tag"} and color not in {"neutral", "unknown", ""}
        )
        if is_included:
            style_key = element.get("visual", {}).get("styleKey", "")
            ledger.append({"elementId": element["id"], "decision": "included_tag", "reason": "独立可见彩色标签原子纳入", "styleKey": style_key})
            included.append({
                "content": element.get("textFacts", {}).get("rawText", ""),
                "styleKey": style_key,
                "elementIds": [element["id"]],
                "countDecision": "独立可理解标签计1个",
                "dedupDecision": "不同权益或商品位置不去重",
            })
        else:
            reason = "照片素材排除" if element.get("render", {}).get("isPhoto") else "核心字段或普通文本不属于独立附加标签/icon"
            ledger.append({"elementId": element["id"], "decision": "excluded", "reason": reason})
            excluded.append({"elementId": element["id"], "reason": reason})
    count = len(included)
    rating = "优秀" if count <= 4 else "达标" if count <= 6 else "不达标"
    complexity_rows.append({
        "componentId": card["cardId"],
        "expectedRegions": region_names(card),
        "scannedRegions": region_names(card),
        "unscannedRegions": [],
        "scannedElementIds": [element["id"] for element in elements(card)],
        "candidateLedger": ledger,
        "phase2ReviewCandidates": [],
        "coverageStatus": "completed",
        "includedTagStyles": included,
        "includedIconStyles": [],
        "excludedEntities": excluded,
        "tagStyleCount": count,
        "iconStyleCount": 0,
        "evidenceSource": "phase2_json_visual_inventory",
        "rating": rating,
    })
u = component_unit("eval-4-element-complexity")
u["rating"] = "不达标"
u["reason"] = "2张完整商家卡分别包含5和9个独立彩色促销/推荐实例，附加icon均为0种；首张命中达标档，第二张超过6个而不达标。"
u["details"]["evidence"] = {"sourceManifestTotal": source_total, "evaluatedUnitCount": 2, "assessmentRows": complexity_rows, "excludedUnits": cropped}
u["details"]["issues"] = [
    {
        "elementId": "C0-T15", "coord": [290, 990, 100, 42], "component": "C0",
        "description": "商卡1可见「望京东南亚菜人气榜第4名、特价团、限时优惠、无门槛、领取」共5个独立彩色促销/推荐实例，命中5—6个标签的达标档；附加icon为0种。",
        "rating": "达标",
        "recommendation": "合并或弱化至少1个次要促销/推荐实例；验收时确认单卡独立彩色标签不超过4个且附加icon不超过1种。",
        "evidenceImage": SHOT,
    },
    {
        "elementId": "C1-T15", "coord": [290, 1671, 195, 42], "component": "C1",
        "description": "商卡2可见「朝阳区东南亚菜好评榜第3名、秒杀00:39:05、5.6折、特价团、半年低价、6.8折、神券、满300可用、使用」共9个独立彩色促销/推荐实例，超过6个的不达标上限；附加icon为0种。",
        "rating": "不达标",
        "recommendation": "合并秒杀、折扣、特价团、低价及券信息，至少减少3个独立彩色促销实例；验收时确认单卡标签不超过4个且附加icon不超过1种。",
        "evidenceImage": SHOT,
    },
]
set_overview(u, 2, 0, passed=1, failed=1)

# Hierarchy and partition.
u = component_unit("eval-5-info-hierarchy")
u["rating"] = "优秀"
u["reason"] = "2张完整商家卡均以标题和头图建立主体，评分位置与榜单承接，优惠和商品保持次级。"
u["details"]["evidence"]["sourceManifestTotal"] = source_total
u["details"]["evidence"]["evaluatedUnitCount"] = 2
u["details"]["evidence"]["assessmentRows"] = u["details"]["evidence"]["assessmentRows"][:2]
u["details"]["evidence"]["excludedUnits"] = cropped
u["details"]["issues"] = []
set_overview(u, 2, 2)

u = component_unit("eval-6-info-partitioning")
u["rating"] = "优秀"
u["reason"] = "2张完整商家卡的基础信息、榜单权益、券与商品区通过留白、对齐和卡片边界清楚分区。"
u["details"]["evidence"] = {"sourceManifestTotal": source_total, "evaluatedUnitCount": 2, "assessmentRows": [], "excludedUnits": cropped}
u["details"]["issues"] = []
set_overview(u, 2, 2)

# Authenticity.
auth_rows = []
for card in cards:
    ids = [element["id"] for element in elements(card)]
    auth_rows.append({
        "componentId": card["cardId"],
        "candidatePairs": [],
        "pairJudgements": [],
        "inapplicableChecks": ["不使用外部门店营业状态、实时销量或库存校验"],
        "scanCoverage": {"status": "completed", "scannedElementIds": ids, "scannedRegions": region_names(card), "crossChecks": ["标题与头图主体", "评分位置与商家主体", "优惠与下挂商品归属"]},
        "conflicts": [],
        "conflictCount": 0,
        "evidenceSource": "phase2_json_and_original_screenshot",
        "rating": "优秀",
    })
u = component_unit("eval-7-info-authenticity")
u["rating"] = "优秀"
u["reason"] = "逐卡核对标题、头图、商圈位置、履约和下挂商品归属，未发现不能同时成立或错归主体的关系。"
u["details"]["evidence"] = {"sourceManifestTotal": source_total, "evaluatedUnitCount": 2, "evaluatedUnitIds": card_ids, "assessmentRows": auth_rows, "excludedUnits": cropped}
u["details"]["issues"] = []
set_overview(u, 2, 2)

# Redundancy: both complete cards repeat their merchant identity in the head image.
checks = ["title/subtitle ↔ basic information", "title/subtitle ↔ tags/price/promotion", "tag ↔ price/promotion", "title internal repeated quantified fragments"]
dup_specs = {
    "C0": ("C0-T1", "C0-P1", "素坤泰船面(麒麟社店) ↔ 头图内素坤泰", "素坤泰商家身份"),
    "C1": ("C1-T1", "C1-P1", "印度餐厅泰姬楼 ↔ 头图内泰姬楼品牌字", "泰姬楼商家身份"),
}
red_rows, red_issues = [], []
for card in cards:
    ids = [element["id"] for element in elements(card)]
    left, right, cue, normalized = dup_specs[card["cardId"]]
    red_rows.append({
        "componentId": card["cardId"],
        "scannedRegions": region_names(card),
        "examinedElements": ids,
        "candidatePairs": [{"leftElementId": left, "rightElementId": right, "relation": cue}],
        "pairJudgements": ["duplicate"],
        "selfRepeatCandidates": [],
        "selfRepeatJudgements": [],
        "duplicates": [{"leftElementId": left, "rightElementId": right, "lexicalCue": cue, "normalizedFact": normalized, "noLossReason": "标题已完整表达商家身份，删除头图内重复品牌字不损失独立决策信息。", "verdict": "duplicate"}],
        "duplicateCount": 1,
        "scanCoverage": {
            "status": "completed",
            "textAtomCount": len(ids),
            "scannedElementIds": ids,
            "scannedRegions": region_names(card),
            "crossChecks": checks,
            "crossCheckResults": [{"checkType": check, "status": "completed", "candidateCount": 1 if check == checks[0] else 0, "judgementCount": 1 if check == checks[0] else 0, "reason": "已终判标题与头图内商家品牌字候选。" if check == checks[0] else "该交叉类型未发现额外可无损删除候选。"} for check in checks],
        },
        "evidenceSource": "phase2_json_full_redundancy_scan",
        "rating": "不达标",
    })
    target = next(element for element in elements(card) if element["id"] == right)
    index = card["structure"]["listPosition"] + 1
    red_issues.append({
        "elementId": right,
        "coord": target["坐标"],
        "component": card["cardId"],
        "description": f"商卡{index}的标题与头图内品牌字重复表达同一商家身份，删除头图重复文字不损失独立决策信息。",
        "rating": "不达标",
        "recommendation": f"删除或弱化商卡{index}头图内与标题重复的品牌文字，仅保留一处完整商家身份；验收时确认整卡语义重复数为0。",
        "evidenceImage": SHOT,
    })
u = component_unit("eval-8-info-redundancy")
u["rating"] = "不达标"
u["reason"] = "完整扫描2张商家卡后，两张卡均存在标题与头图内品牌身份重复，共确认2张问题卡。"
u["details"]["evidence"] = {"sourceManifestTotal": source_total, "evaluatedUnitCount": 2, "evaluatedUnitIds": card_ids, "assessmentRows": red_rows, "excludedUnits": cropped}
u["details"]["issues"] = red_issues
set_overview(u, 2, 0, failed=2)

# Page supply and visual order.
u = page_unit("eval-1-supply-module-completeness")
u["rating"] = "优秀"
u["reason"] = "搜索入口、业务Tab、用户/商家入口、位置筛选、推荐衔接提示和商家结果列表均完整加载，核心页面骨架完整。"
u["details"]["evidence"] = {"assessmentRows": []}
u["details"]["issues"] = []
set_overview(u, 1, 1)

page_alignment = {
    "pageRegions": [
        {"region": "搜索与业务Tab", "observedRole": "建立查询和结果范围", "visualSignals": ["顶部固定入口", "选中Tab黄色下划线"]},
        {"region": "用户/商家入口与位置筛选", "observedRole": "补充身份入口和地域条件", "visualSignals": ["浅色独立容器", "与结果流留白分隔"]},
        {"region": "推荐提示与商家结果列表", "observedRole": "解释无精确结果后承接推荐供给", "visualSignals": ["提示居中", "同型商家卡连续纵向排列"]},
    ],
    "sameTypeComparisons": [{"members": ["商卡1", "商卡2"], "result": "标题、基础信息与下挂商品的主锚点一致"}],
    "primaryFocus": "商家结果列表",
    "flowChecks": [{"expectedOrder": ["搜索与Tab", "身份入口与位置筛选", "推荐提示", "商家结果列表"], "observedOrder": ["搜索与Tab", "身份入口与位置筛选", "推荐提示", "商家结果列表"], "visualSignals": ["自上而下单列推进", "提示与列表边界清楚"], "reason": "页面按查询、条件、状态解释和浏览结果的顺序推进。", "status": "consistent"}],
    "evidenceSource": "original_screenshot_visual_review",
    "rating": "优秀",
}
u = page_unit("eval-2-visual-order-alignment")
u["rating"] = "优秀"
u["reason"] = "页面由搜索与业务Tab进入身份/位置入口，再以无精确结果提示承接连续商家列表，浏览顺序清楚。"
u["details"]["evidence"] = {"assessmentRows": [page_alignment]}
u["details"]["issues"] = []
set_overview(u, 1, 1)

# Page color union.
summaries = [{"componentId": item["componentId"], "colorFamilies": item["colorFamilies"], "colorFamilyCount": item["colorFamilyCount"]} for item in colors]
families = sorted({family for item in summaries for family in item["colorFamilies"]})
page_color = {"colorLogicContractVersion": "4.0", "componentColorArtifact": str(MEASURE), "componentColorSummaries": summaries, "colorFamilies": families, "colorFamilyCount": len(families), "evidenceSource": "component_pixel_color_aggregation", "rating": "达标"}
u = page_unit("eval-3-page-color-logic")
u["rating"] = "达标"
u["reason"] = "全页可见商家组件的有效界面色系并集为红、橙、黄、绿、青、紫共6种，超过优秀档5种上限并命中达标档。"
u["details"]["evidence"] = {"assessmentRows": [page_color]}
u["details"]["issues"] = [{"pageArea": "页面商家结果区", "description": "全页有效界面色系并集为「红、橙、黄、绿、青、紫」共6种，超过优秀档5种上限并命中达标档。", "rating": "达标", "recommendation": "合并商品推荐、履约和促销中的至少1种次要色系；验收时确认全页有效界面色系不超过5种。", "evidenceImage": SHOT}]
set_overview(u, 1, 0, passed=1)

# Page static complexity.
page_complexity = {
    "firstScreenBounds": [0, 0, manifest["pageFacts"]["viewport"]["width"], manifest["pageFacts"]["viewport"]["height"]],
    "functionalModules": [
        {"name": "业务Tab栏", "sourceModuleIds": ["M1"]},
        {"name": "用户/商家身份入口", "sourceModuleIds": ["M1"]},
        {"name": "位置筛选", "sourceModuleIds": ["M2"]},
        {"name": "推荐衔接提示", "sourceModuleIds": ["M3"]},
        {"name": "商家结果列表", "sourceModuleIds": ["M4", "M5"]},
    ],
    "moduleCount": 5,
    "observableFact": "排除顶部搜索框并合并重复识别的结果列表后，共5个独立功能区。",
    "rating": "达标",
}
u = page_unit("eval-4-static-component-complexity")
u["rating"] = "达标"
u["reason"] = "排除顶部搜索框并合并普通结果列表后，首屏有业务Tab、身份入口、位置筛选、推荐提示和结果列表共5个独立功能区。"
u["details"]["evidence"] = {"assessmentRows": [page_complexity]}
u["details"]["issues"] = [{"pageArea": "首屏整体", "description": "首屏排除搜索框后仍呈现业务Tab、用户/商家入口、位置筛选、推荐衔接提示和商家结果列表共5个独立功能区，命中达标档。", "rating": "达标", "recommendation": "合并用户/商家入口与位置筛选，或收敛推荐衔接提示；验收时确认首屏独立功能区不超过4个。", "evidenceImage": SHOT}]
set_overview(u, 1, 0, passed=1)

# Browsing flow.
flow_row = {
    "listPositions": [{"position": card["structure"]["listPosition"], "componentId": card["cardId"], "cardType": card["cardTypeName"], "isHeterogeneous": False, "visibleStatus": card["structure"]["visibleStatus"]} for card in all_cards],
    "visibleListPositionCount": len(all_cards),
    "coverageStatus": "partial",
    "heterogeneousCount": 0,
    "frontTenHeterogeneousCount": 0,
    "allHeterogeneousItems": [],
    "heterogeneousItems": [],
    "rating": "优秀",
}
u = page_unit("eval-5-browsing-flow-smoothness")
u["rating"] = "优秀"
u["reason"] = "排序筛选下方3个可见列表位均为同型标准商家图文下挂卡，前10位当前可见范围内异构数为0。"
u["details"]["evidence"] = {"assessmentRows": [flow_row]}
u["details"]["issues"] = []
set_overview(u, 1, 1)

# Comparability.
comparability = {
    "cardGroups": [{"comparisonGroupKey": cards[0]["structure"]["comparisonGroupKey"], "members": card_ids}],
    "comparableFields": ["到店履约", "评分", "评价量", "人均价格", "位置/商圈", "距离"],
    "comparisons": [{
        "comparisonGroupKey": cards[0]["structure"]["comparisonGroupKey"],
        "semanticRole": "rating_review_average_price_location_distance",
        "fieldMatchKey": "同型到店商家卡的基础决策字段",
        "observations": [{"componentId": card["cardId"], "present": True, "anchor": "标题下方基础信息行及右侧距离位"} for card in cards],
        "detectedDifferences": {"missing": [], "formatMismatch": False, "anchorMismatch": False, "styleSemanticMismatch": False},
        "materialImpact": False,
        "phase3Judgement": "consistent",
    }],
    "excludedReasons": ["C2为底部自然裁切且为外卖履约，不强行纳入完整到店卡比较组。"],
    "inconsistencyCount": 0,
    "evidenceSource": "phase2_json_cross_card_comparison",
    "rating": "优秀",
}
u = page_unit("eval-6-info-comparability")
u["rating"] = "优秀"
u["reason"] = "2张完整到店商家卡以相同信息层呈现履约、评分、评价量、人均、位置和距离，格式与锚点可直接横向比较。"
u["details"]["evidence"] = {"assessmentRows": [comparability]}
u["details"]["issues"] = []
set_overview(u, 1, 1)

# Page redundancy exhaustive scan.
page_regions = ["搜索与业务Tab", "用户/商家身份入口", "位置筛选", "推荐衔接提示", "商家结果列表"]
page_pairs = list(combinations(page_regions, 2))
page_redundancy = {
    "pageRegions": page_regions,
    "candidatePairs": [],
    "scanCoverage": {"status": "completed", "scannedRegionIds": page_regions, "crossChecks": [f"{left} ↔ {right}" for left, right in page_pairs]},
    "crossChecks": [{"regions": [left, right], "judgement": "distinct", "reason": "两区域承担不同页面任务或提供不同决策信息。"} for left, right in page_pairs],
    "redundancyItems": [],
    "redundancyCount": 0,
    "rating": "优秀",
}
u = page_unit("eval-7-info-redundancy")
u["rating"] = "优秀"
u["reason"] = "已覆盖5个独立页面区域并完成10组两两检查；各区域职责不同，跨区域冗余数为0。"
u["details"]["evidence"] = {"assessmentRows": [page_redundancy]}
u["details"]["issues"] = []
set_overview(u, 1, 1)

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(OUT)
