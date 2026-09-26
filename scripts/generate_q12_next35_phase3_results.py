#!/usr/bin/env python3
"""Materialize the current-pixel Phase3 judgement for next35 q12."""

import json
from itertools import combinations
from pathlib import Path

ROOT = Path("/Users/qianjing/Documents/ChatGPT/search-eval-project-v2")
RUN = "batch-20260920-09-2-next35-r1-q12"
BATCH = "batch-20260920-09-2-next35-r1"
QUERY = "普雷吉奥红葡萄酒"
STEM = "普雷吉奥红葡萄酒_全部_1"
SHOT = str(ROOT / f"screenshots/{STEM}.png")
MANIFEST = ROOT / f"screenshots-out/elements_{STEM}_{RUN}.json"
AUDIT = ROOT / f"screenshots-out/elements_{STEM}_{RUN}.audit.json"
BASE = ROOT / f".artifacts/过程文件-评测结果与审计/{BATCH}/{RUN}"
MEASURE = BASE / f"phase3/measurements/elements_{STEM}_{RUN}.component-color-families.json"
OUT = BASE / f"results/评测原始结果_{RUN}.json"

CARD_DIM = "phase3-card_or_component-eval"
PAGE_DIM = "phase3-page_framework-eval"
REDUNDANCY_CHECKS = [
    "title/subtitle ↔ basic information",
    "title/subtitle ↔ tags/price/promotion",
    "tag ↔ price/promotion",
    "title internal repeated quantified fragments",
]

manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
audit = json.loads(AUDIT.read_text(encoding="utf-8"))
source_total = audit["total"]
active = {item["id"]: item for item in audit["activeElements"]}
colors = json.loads(MEASURE.read_text(encoding="utf-8"))["components"]
all_cards = manifest["cards"]
cards = [card for card in all_cards if card["structure"]["visibleStatus"] == "complete"]
card_ids = [card["cardId"] for card in cards]


def elements(card):
    return [element for region in card["regions"] for element in region["elements"]]


def text_elements(card):
    return [element for element in elements(card) if not element.get("render", {}).get("isPhoto")]


def region_names(card):
    return [region["name"] for region in card["regions"]]


def overview(total, excellent, passed, failed):
    return {
        "total": total,
        "excellent": excellent,
        "pass": passed,
        "fail": failed,
        "failRate": f"{(failed / total * 100):.1f}%" if total else "0%",
    }


def result(dimension, skill, title, rating, reason, evidence, counts, issues=None):
    return {
        "query": QUERY,
        "dimension": dimension,
        "skill": skill,
        "title": title,
        "units": [{
            "tab": "全部",
            "rating": rating,
            "reason": reason,
            "details": {
                "screenshot": SHOT,
                "evidenceMode": "original-page",
                "overview": overview(*counts),
                "evidence": evidence,
                "issues": issues or [],
            },
        }],
    }


def issue(element_id, component, description, recommendation, rating="不达标"):
    return {
        "elementId": element_id,
        "coord": active[element_id]["coord"],
        "component": component,
        "description": description,
        "rating": rating,
        "recommendation": recommendation,
        "evidenceImage": SHOT,
    }


results = []

# 1. Supply completeness: the fifth card is naturally cropped and excluded.
results.append(result(
    CARD_DIM, "eval-1-supply-completeness", "供给呈现质量", "优秀",
    "4张完整商品卡的标题、主图、价格、商家与履约信息均可读；第5张卡底部自然出屏，不推断屏外内容。",
    {"sourceManifestTotal": source_total, "evaluatedUnitCount": 4, "assessmentRows": [], "excludedUnits": [{"componentId": "C5", "reason": "卡片底部自然出屏，不推断屏外内容。"}]},
    (4, 4, 0, 0),
))

# 2. Visual order: one complete same-type group.
layout_signatures, order_checks = [], []
for card in cards:
    names = region_names(card)
    layout_signatures.append({
        "componentId": card["cardId"],
        "layoutMode": card["structure"]["layoutMode"],
        "layoutSignature": card["structure"]["layoutSignature"],
        "regions": [{"region": region["name"], "elementIds": [e["id"] for e in region["elements"]], "contentBounds": region["coord"]} for region in card["regions"]],
        "relations": [card["structure"]["layoutAnchorRelation"]],
    })
    order_checks.append({
        "componentId": card["cardId"],
        "expectedOrder": names,
        "observedOrder": names,
        "attentionSignals": ["左侧商品图建立主体", "标题与属性位于右上", "价格、优惠与商家信息依序向下"],
        "dominantRegion": "标题区",
        "reason": "商品标题先被识别，价格和履约随后进入扫读，没有辅助内容抢主位。",
        "auxiliaryDominance": False, "competingFoci": False, "ownershipAmbiguity": False,
        "pathInversion": False, "localDetour": False, "status": "consistent",
    })
alignment_row = {
    "comparisonGroupKey": cards[0]["structure"]["comparisonGroupKey"],
    "members": card_ids,
    "layoutSignatures": layout_signatures,
    "readingOrderChecks": order_checks,
    "evidenceSource": "original_screenshot_visual_review",
    "rating": "优秀",
}
results.append(result(
    CARD_DIM, "eval-2-visual-order-alignment", "视觉秩序统一对齐", "优秀",
    "4张完整商品卡均保持左图右文、标题优先、价格与履约随后的稳定扫读顺序。",
    {"sourceManifestTotal": source_total, "evaluatedUnitCount": 1, "assessmentRows": [alignment_row], "excludedUnits": [{"componentId": "C5", "reason": "底部自然裁切，不进入完整卡对齐比较。"}]},
    (1, 1, 0, 0),
))

# 3. Pixel-measured colors. C5 contains five non-neutral families and is a pass row.
color_issue = issue(
    "C5-T12", "C5",
    "商卡5的可见界面色系为红、橙、黄、绿、蓝共5种，到达色彩逻辑的达标档，强调色角色偏多。",
    "统一商卡5中促销、履约和商家标识的强调色，减少低频色彩角色；验收时确认有效界面色系不超过4种。",
    "达标",
)
results.append(result(
    CARD_DIM, "eval-3-color-logic", "色彩运用逻辑性", "达标",
    "5张卡的有效界面色系数分别为4、3、3、3、5；前4张优秀，第5张因5种色系达标。",
    {"sourceManifestTotal": source_total, "evaluatedUnitCount": len(colors), "assessmentRows": colors},
    (5, 4, 1, 0), [color_issue],
))

# 4. Complexity: full JSON inventory on the four complete cards.
complexity_rows = []
for card in cards:
    ledger, included, excluded = [], [], []
    for element in elements(card):
        fact = active[element["id"]]
        role, color = fact.get("semanticRole", ""), fact.get("colorRole", "unknown")
        content = fact.get("content", "").removeprefix("原文:")
        prefix = fact.get("promotionPrefix", "")
        include = bool(prefix) or (role == "promotion" and color not in {"neutral", "unknown", ""})
        if include:
            style_key = f"tag|{color}|促销|有容器|文字"
            ledger.append({"elementId": element["id"], "decision": "included_tag", "reason": "彩色促销标签逐实例纳入", "styleKey": style_key})
            included.append({
                "content": prefix or content, "styleKey": style_key, "elementIds": [element["id"]],
                "countDecision": "独立可理解彩色促销标签计1枚", "dedupDecision": "同卡独立实例不合并",
            })
        else:
            if fact.get("isPhoto"):
                reason = "商品照片素材不计入界面附加样式"
            elif role in {"title", "price", "rating"}:
                reason = "标题、价格或评分属于核心信息字段"
            elif role in {"fulfillment", "fulfillment_tag", "delivery_time"}:
                reason = "履约信息按复杂度契约排除"
            elif fact.get("entityKind") == "image":
                reason = "商品图像素材不计入界面附加样式"
            else:
                reason = "普通属性、商家或包装文字不构成独立界面标签"
            ledger.append({"elementId": element["id"], "decision": "excluded", "reason": reason})
            excluded.append({"elementId": element["id"], "reason": reason})
    complexity_rows.append({
        "componentId": card["cardId"], "expectedRegions": region_names(card), "scannedRegions": region_names(card),
        "unscannedRegions": [], "scannedElementIds": [e["id"] for e in elements(card)], "candidateLedger": ledger,
        "phase2ReviewCandidates": [], "coverageStatus": "completed", "includedTagStyles": included,
        "includedIconStyles": [], "excludedEntities": excluded, "tagStyleCount": len(included), "iconStyleCount": 0,
        "evidenceSource": "phase2_json_visual_inventory", "rating": "优秀",
    })
results.append(result(
    CARD_DIM, "eval-4-element-complexity", "静态元素复杂度", "优秀",
    "4张完整商品卡各自仅有0至2枚独立彩色促销标签，未见附加功能图标，静态元素复杂度受控。",
    {"sourceManifestTotal": source_total, "evaluatedUnitCount": 4, "assessmentRows": complexity_rows, "excludedUnits": [{"componentId": "C5", "reason": "底部自然裁切，不进入完整组件复杂度计数。"}]},
    (4, 4, 0, 0),
))

# 5. Information hierarchy.
hierarchy_rows = []
for card in cards:
    texts = text_elements(card)
    hierarchy_rows.append({
        "componentId": card["cardId"],
        "sourceElements": [{
            "elementId": e["id"], "text": e.get("textFacts", {}).get("rawText", ""),
            "fontSizeBucket": e.get("textFacts", {}).get("fontSizeBucket", "unknown"),
            "fontWeightBucket": e.get("textFacts", {}).get("fontWeightBucket", "unknown"),
            "semanticRole": e.get("textFacts", {}).get("semanticRole", ""),
        } for e in texts],
        "weightSequence": ["商品标题与主图", "价格、想买人数与时效", "优惠、商家与配送信息"],
        "tierTrace": [
            {"tier": 1, "elements": ["商品标题与主图"], "reason": "字号、位置和留白共同形成主权重。"},
            {"tier": 2, "elements": ["价格、想买人数与时效"], "reason": "价格强调色与履约对齐承接决策信息。"},
            {"tier": 3, "elements": ["优惠、商家与配送信息"], "reason": "辅助信息维持次级字号和稳定分区。"},
        ],
        "levelCount": 3, "rating": "优秀",
    })
results.append(result(
    CARD_DIM, "eval-5-info-hierarchy", "商卡视觉层级", "优秀",
    "4张完整卡的商品标题与主图建立主层，价格与时效承接，优惠和商家履约保持次级。",
    {"sourceManifestTotal": source_total, "evaluatedUnitCount": 4, "assessmentRows": hierarchy_rows, "excludedUnits": [{"componentId": "C5", "reason": "底部自然裁切，不用于完整卡层级结论。"}]},
    (4, 4, 0, 0),
))

# 6. Partitioning: no problem rows for an excellent result.
results.append(result(
    CARD_DIM, "eval-6-info-partitioning", "信息分区合理性", "优秀",
    "完整商品卡的图片、标题属性、价格优惠和商家履约通过留白与对齐清楚分区，归属明确。",
    {"sourceManifestTotal": source_total, "evaluatedUnitCount": 4, "assessmentRows": []},
    (4, 4, 0, 0),
))

# 7. Authenticity: no contradictory facts on the four complete cards.
auth_rows = []
for card in cards:
    ids = [e["id"] for e in elements(card)]
    auth_rows.append({
        "componentId": card["cardId"],
        "candidatePairs": [{"leftElementId": f"{card['cardId']}-T1", "rightElementId": f"{card['cardId']}-P1", "relation": "标题与商品主图主体对应"}],
        "pairJudgements": ["consistent"], "inapplicableChecks": ["未发现同身份跨卡核心事实冲突"],
        "scanCoverage": {"status": "completed", "scannedElementIds": ids, "scannedRegions": region_names(card), "crossChecks": ["标题与主图", "价格与促销条件", "规格与作用对象", "商家履约与商品主体"]},
        "conflicts": [], "conflictCount": 0, "evidenceSource": "phase2_json_and_original_screenshot", "rating": "优秀",
    })
results.append(result(
    CARD_DIM, "eval-7-info-authenticity", "信息真实无歧义", "优秀",
    "4张完整卡的标题、主图、规格、价格条件与履约归属一致，未发现无法同时成立的客观冲突。",
    {"sourceManifestTotal": source_total, "evaluatedUnitCount": 4, "evaluatedUnitIds": card_ids, "assessmentRows": auth_rows, "excludedUnits": [{"componentId": "C5", "reason": "底部自然裁切，不用不完整覆盖证明无冲突。"}]},
    (4, 4, 0, 0),
))

# 8. Full redundancy scan. Embedded image text is included for the cropped fifth card.
duplicate_specs = {
    "C1": [
        ("C1-T1", "C1-T16", "普雷吉奥 ↔ PREGIO", "品牌名普雷吉奥", "中英文表达同一品牌，删除任一处不损失独立决策信息。"),
    ],
    "C5": [
        ("C5-T1", "C5-T12", "优尼特 ↔ Riunite 优尼特", "品牌名优尼特", "标题与商品图表达同一品牌，删除任一处不损失独立决策信息。"),
        ("C5-T1", "C5-T14", "甜型红葡萄酒 ↔ 小甜酒", "甜型红葡萄酒类别", "标题与商品图均表达甜型酒类别，删除任一处不损失独立决策信息。"),
    ],
}
red_rows = [{
    "componentId": "M3", "scannedRegions": ["位置与排序筛选区"], "examinedElements": ["M3"],
    "candidatePairs": [], "pairJudgements": [], "selfRepeatCandidates": [], "selfRepeatJudgements": [],
    "duplicates": [], "duplicateCount": 0,
    "scanCoverage": {"status": "completed", "textAtomCount": 1, "scannedElementIds": ["M3"], "scannedRegions": ["位置与排序筛选区"], "crossChecks": REDUNDANCY_CHECKS,
                     "crossCheckResults": [{"checkType": check, "status": "completed", "candidateCount": 0, "judgementCount": 0, "reason": "该交叉类型未发现额外候选。"} for check in REDUNDANCY_CHECKS]},
    "evidenceSource": "phase2_json_full_redundancy_scan", "rating": "优秀",
}]
red_issues = []
for card in all_cards:
    ids = [e["id"] for e in text_elements(card)]
    specs = duplicate_specs.get(card["cardId"], [])
    pairs = [{"leftElementId": left, "rightElementId": right, "relation": "标题与商品图内文字"} for left, right, _, _, _ in specs]
    duplicates = [{"leftElementId": left, "rightElementId": right, "lexicalCue": cue, "normalizedFact": fact, "noLossReason": reason, "verdict": "duplicate"} for left, right, cue, fact, reason in specs]
    cross_results = []
    for check in REDUNDANCY_CHECKS:
        count = len(pairs) if check == REDUNDANCY_CHECKS[0] else 0
        cross_results.append({"checkType": check, "status": "completed", "candidateCount": count, "judgementCount": count,
                              "reason": "已逐对核对标题、商品图内文字、基础信息、促销与价格。" if check == REDUNDANCY_CHECKS[0] else "该交叉类型未发现额外候选。"})
    rating = "不达标" if duplicates else "优秀"
    red_rows.append({
        "componentId": card["cardId"], "scannedRegions": region_names(card), "examinedElements": ids,
        "candidatePairs": pairs, "pairJudgements": ["duplicate"] * len(pairs), "selfRepeatCandidates": [], "selfRepeatJudgements": [],
        "duplicates": duplicates, "duplicateCount": len(duplicates),
        "scanCoverage": {"status": "completed", "textAtomCount": len(ids), "scannedElementIds": ids, "scannedRegions": region_names(card), "crossChecks": REDUNDANCY_CHECKS, "crossCheckResults": cross_results},
        "evidenceSource": "phase2_json_full_redundancy_scan", "rating": rating,
    })
    if duplicates:
        index = card["structure"]["listPosition"]
        if card["cardId"] == "C1":
            description = "商卡1标题中的品牌“普雷吉奥”与商品图内英文品牌“PREGIO”重复同一品牌事实，删除其中一处不损失独立决策信息。"
        else:
            description = "商卡5标题与商品图重复“优尼特”品牌及“甜型红葡萄酒/小甜酒”酒类信息，两项均无新增决策价值。"
        red_issues.append(issue(
            duplicates[0]["rightElementId"], card["cardId"], description,
            f"删除或改写商卡{index}标题与商品图中无新增价值的重复品牌或品类文字，只保留一处完整表达；验收时确认整卡语义重复数为0。",
        ))
results.append(result(
    CARD_DIM, "eval-8-info-redundancy", "信息无冗余", "不达标",
    "已扫描筛选区和5张可见商品卡；商卡1的普雷吉奥品牌文字在标题与商品图重复，商卡5的优尼特品牌及甜型酒类信息重复，共2张问题卡。",
    {"sourceManifestTotal": source_total, "evaluatedUnitCount": 6, "evaluatedUnitIds": ["M3", "C1", "C2", "C3", "C4", "C5"], "assessmentRows": red_rows},
    (6, 4, 0, 2), red_issues,
))

# 9-15. Page-level evaluations.
results.append(result(
    PAGE_DIM, "eval-1-supply-module-completeness", "供给呈现质量（页面框架完整性）", "优秀",
    "搜索框、业务Tab、位置排序筛选和商品结果列表均已正常加载。",
    {"assessmentRows": []}, (1, 1, 0, 0),
))

page_alignment = {
    "pageRegions": [
        {"region": "搜索与Tab区", "observedRole": "建立搜索任务和结果范围", "visualSignals": ["顶部稳定定位", "选中Tab用下划线强调"]},
        {"region": "筛选区", "observedRole": "调整位置、排序、价格和配送条件", "visualSignals": ["独立浅色控件", "与列表留白分隔"]},
        {"region": "商品结果列表", "observedRole": "连续呈现商品供给", "visualSignals": ["同型卡单列连续排列", "标题与价格对齐稳定"]},
    ],
    "sameTypeComparisons": [{"members": ["商卡1", "商卡2", "商卡3", "商卡4"], "result": "左图右文结构与阅读锚点一致"}],
    "primaryFocus": "商品标题与主图",
    "flowChecks": [{"expectedOrder": ["搜索与Tab", "筛选", "商品结果"], "observedOrder": ["搜索与Tab", "筛选", "商品结果"], "visualSignals": ["自上而下单列推进", "同型商品卡连续重复"], "reason": "搜索、筛选、结果三段职责清楚，结果列表保持稳定主焦点。", "status": "consistent"}],
    "evidenceSource": "original_screenshot_visual_review", "rating": "优秀",
}
results.append(result(PAGE_DIM, "eval-2-visual-order-alignment", "视觉秩序统一对齐", "优秀", "页面按搜索与Tab、筛选、商品结果列表顺序展开，列表内同型卡连续且主焦点稳定。", {"assessmentRows": [page_alignment]}, (1, 1, 0, 0)))

summaries = [{"componentId": item["componentId"], "colorFamilies": item["colorFamilies"], "colorFamilyCount": item["colorFamilyCount"]} for item in colors]
families = sorted({family for item in summaries for family in item["colorFamilies"]})
page_color = {"colorLogicContractVersion": "4.0", "componentColorArtifact": str(MEASURE), "componentColorSummaries": summaries, "colorFamilies": families, "colorFamilyCount": len(families), "evidenceSource": "component_pixel_color_aggregation", "rating": "达标"}
page_color_issue = {"pageArea": "商品结果列表", "description": "商品结果列表的卡片界面色系并集为红、橙、黄、绿、蓝、紫共6种，达到页面达标档，跨卡颜色角色偏多。", "rating": "达标", "recommendation": "统一商品卡状态、优惠和履约的色彩角色并减少低频强调色；验收时确认页面有效界面色系并集不超过5种。", "evidenceImage": SHOT}
results.append(result(PAGE_DIM, "eval-3-page-color-logic", "色彩运用有逻辑（页面级）", "达标", "5张结果卡的有效界面色系并集为红、橙、黄、绿、蓝、紫共6种，命中页面达标阈值。", {"assessmentRows": [page_color]}, (1, 0, 1, 0), [page_color_issue]))

page_complexity = {"firstScreenBounds": [0, 0, manifest["pageFacts"]["viewport"]["width"], manifest["pageFacts"]["viewport"]["height"]], "functionalModules": [{"name": "业务Tab栏", "sourceModuleIds": ["M2"]}, {"name": "位置与排序筛选", "sourceModuleIds": ["M3"]}, {"name": "商品结果列表", "sourceModuleIds": ["M5"]}], "moduleCount": 3, "rating": "优秀"}
results.append(result(PAGE_DIM, "eval-4-static-component-complexity", "静态组件不复杂（首屏功能区数量）", "优秀", "排除顶部搜索框后，页面只有业务Tab、位置排序筛选和商品结果列表3个独立功能模块，不超过4个的优秀阈值。", {"assessmentRows": [page_complexity]}, (1, 1, 0, 0)))

flow_row = {"listPositions": [{"position": card["structure"]["listPosition"], "componentId": card["cardId"], "cardType": card["cardTypeName"], "isHeterogeneous": False, "visibleStatus": card["structure"]["visibleStatus"]} for card in all_cards], "visibleListPositionCount": 5, "coverageStatus": "partial", "heterogeneousCount": 0, "frontTenHeterogeneousCount": 0, "heterogeneousItems": [], "rating": "优秀"}
results.append(result(PAGE_DIM, "eval-5-browsing-flow-smoothness", "浏览动线顺畅", "优秀", "排序筛选下方可见5个有效列表位，均为标准商品卡，已见范围内异构数为0；未覆盖位置不补位推断。", {"assessmentRows": [flow_row]}, (1, 1, 0, 0)))

delivery_values = {"C1": "51分钟", "C2": "20分钟", "C3": "45分钟", "C4": "25分钟"}
distance_values = {"C1": "7.4km", "C2": "2.8km", "C3": "2.3km", "C4": "4.4km"}
comparability = {"cardGroups": [{"comparisonGroupKey": cards[0]["structure"]["comparisonGroupKey"], "members": card_ids}], "comparableFields": ["配送时长", "距离"], "comparisons": [{"comparisonGroupKey": cards[0]["structure"]["comparisonGroupKey"], "semanticRole": "delivery_time", "observations": [{"componentId": cid, "value": delivery_values[cid], "slot": "右侧履约/底部商家信息"} for cid in card_ids], "detectedDifferences": {"format": False, "position": False, "styleSemantics": False, "materialImpact": False}, "phase3Judgement": "consistent"}, {"comparisonGroupKey": cards[0]["structure"]["comparisonGroupKey"], "semanticRole": "distance", "observations": [{"componentId": cid, "value": distance_values[cid], "slot": "右侧履约/底部商家信息"} for cid in card_ids], "detectedDifferences": {"format": False, "position": False, "styleSemantics": False, "materialImpact": False}, "phase3Judgement": "consistent"}], "excludedReasons": ["自然裁切卡不进入完整比较组"], "inconsistencyCount": 0, "evidenceSource": "phase2_json_cross_card_comparison", "rating": "优秀"}
results.append(result(PAGE_DIM, "eval-6-info-comparability", "信息可比性", "优秀", "4张完整同型商品卡的配送时长和距离使用相同单位、位置与样式语义，可直接横向比较。", {"assessmentRows": [comparability]}, (1, 1, 0, 0)))

page_regions = ["搜索框", "Tab栏", "位置与排序筛选区", "商品结果列表"]
page_pairs = list(combinations(page_regions, 2))
page_red = {"pageRegions": page_regions, "candidatePairs": [], "scanCoverage": {"status": "completed", "scannedRegionIds": page_regions, "crossChecks": [f"{a} ↔ {b}" for a, b in page_pairs]}, "crossChecks": [{"regions": [a, b], "judgement": "distinct", "reason": "两区域承担不同页面任务或提供不同决策信息。"} for a, b in page_pairs], "redundancyItems": [], "redundancyCount": 0, "rating": "优秀"}
results.append(result(PAGE_DIM, "eval-7-info-redundancy", "功能/信息无冗余", "优秀", "已覆盖搜索框、Tab栏、筛选区和商品结果列表4个区域并完成6组两两检查；各区域职责不同，页面冗余数为0。", {"assessmentRows": [page_red]}, (1, 1, 0, 0)))

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(OUT)
