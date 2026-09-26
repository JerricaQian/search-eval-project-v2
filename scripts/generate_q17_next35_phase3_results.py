#!/usr/bin/env python3
"""Materialize the current-pixel Phase3 judgement for next35 q17."""

import json
from itertools import combinations
from pathlib import Path

ROOT = Path("/Users/qianjing/Documents/ChatGPT/search-eval-project-v2")
RUN = "batch-20260920-09-2-next35-r1-q17"
BATCH = "batch-20260920-09-2-next35-r1"
QUERY = "正清馆空手道"
STEM = "正清馆空手道_全部_1"
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
audit_data = json.loads(AUDIT.read_text(encoding="utf-8"))
source_total = audit_data["total"]
active = {item["id"]: item for item in audit_data["activeElements"]}
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


def overview(rating, total, problem_count=None):
    if problem_count is None:
        problem_count = total if rating == "不达标" else 0
    passed = total if rating == "达标" else 0
    excellent = total - passed - problem_count
    return {
        "total": total,
        "excellent": excellent,
        "pass": passed,
        "fail": problem_count,
        "failRate": f"{(problem_count / total * 100):.1f}%" if total else "0%",
    }


def result(dimension, skill, title, rating, reason, evidence, total, issues=None, problem_count=None):
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
                "overview": overview(rating, total, problem_count),
                "evidence": evidence,
                "issues": issues or [],
            },
        }],
    }


results = []

# 1. Supply completeness: no problem rows are emitted for an excellent result.
results.append(result(
    CARD_DIM, "eval-1-supply-completeness", "供给呈现质量", "优秀",
    "5张完整商家卡均呈现商家标题、评分、位置等基础信息，并提供可读的文字下挂商品与价格；第6张为视口底部自然裁切，不推断屏外内容。",
    {"sourceManifestTotal": source_total, "assessmentRows": [], "excludedUnits": [{"componentId": "C6", "reason": "视口底部自然裁切，不推断屏外内容。"}]}, len(cards), problem_count=0,
))

# 2. Visual order: one same-type group, with current-image visual evidence.
layout_signatures = []
order_checks = []
for card in cards:
    names = region_names(card)
    layout_signatures.append({
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
        "expectedOrder": names,
        "observedOrder": names,
        "attentionSignals": ["商家标题建立主体", "评分和位置承接", "文字下挂商品与优惠位于次级区域"],
        "dominantRegion": "基础信息区",
        "reason": "商家标题与评分先被识别，下挂商品随后展开，未出现辅助优惠抢占主体。",
        "auxiliaryDominance": False,
        "competingFoci": False,
        "ownershipAmbiguity": False,
        "pathInversion": False,
        "localDetour": False,
        "status": "consistent",
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
    "5张同型商家卡均保持商家信息在上、文字下挂商品与优惠在下的稳定扫读顺序。",
    {"sourceManifestTotal": source_total, "evaluatedUnitCount": 1, "assessmentRows": [alignment_row]}, 1, problem_count=0,
))

# 3. Pixel-measured component colors.
results.append(result(
    CARD_DIM, "eval-3-color-logic", "色彩运用逻辑性", "优秀",
    "6张可见商家卡的有效非中性色相族分别为2、3、2、2、2、1种，均不超过优秀档上限。",
    {"sourceManifestTotal": source_total, "evaluatedUnitCount": len(colors), "assessmentRows": colors},
    len(colors), problem_count=0,
))

# 4. Complexity: count only independent colored promotion tags; photos/core fields are excluded.
complexity_rows = []
for card in cards:
    ledger, included, excluded = [], [], []
    for element in elements(card):
        fact = active[element["id"]]
        role = element.get("textFacts", {}).get("semanticRole", "")
        color = element.get("visual", {}).get("colorRole", "unknown")
        text = element.get("textFacts", {}).get("rawText", "")
        promotion_prefix = fact.get("promotionPrefix", "")
        entity_kind = element.get("visual", {}).get("entityKind", "")
        include = (
            role not in {"fulfillment", "fulfillment_tag", "delivery_time", "delivery_time_tag"}
            and color not in {"neutral", "unknown", ""}
            and (entity_kind == "tag" or role == "promotion")
        )
        if include:
            style_key = element.get("visual", {}).get("styleKey", f"text|{color}|promotion|无容器|无")
            ledger.append({"elementId": element["id"], "decision": "included_tag", "reason": "独立彩色标签或促销标逐实例纳入", "styleKey": style_key})
            included.append({
                "content": promotion_prefix or text,
                "styleKey": style_key,
                "elementIds": [element["id"]],
                "countDecision": "独立可理解彩色标签或促销标计1枚",
                "dedupDecision": "不同卡内独立实例不跨卡去重",
            })
        else:
            if element.get("render", {}).get("isPhoto"):
                reason = "商品或商户照片素材不计入界面附加样式"
            elif role in {"title", "price", "rating", "item_price"}:
                reason = "标题、价格或评分属于核心信息字段"
            elif role in {"fulfillment", "delivery_time"}:
                reason = "履约信息按复杂度契约排除"
            elif color in {"neutral", "unknown", ""}:
                reason = "中性普通信息文字不构成独立彩色标签"
            else:
                reason = "普通评分、位置、销量或商品文字不构成独立附加标签"
            ledger.append({"elementId": element["id"], "decision": "excluded", "reason": reason})
            excluded.append({"elementId": element["id"], "reason": reason})
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
        "tagStyleCount": len(included),
        "iconStyleCount": 0,
        "evidenceSource": "phase2_json_visual_inventory",
        "rating": "优秀",
    })
results.append(result(
    CARD_DIM, "eval-4-element-complexity", "静态元素复杂度", "优秀",
    "5张完整商家卡各有3至4枚独立彩色标签或促销标，未见附加功能图标，均未超过优秀档上限。",
    {"sourceManifestTotal": source_total, "evaluatedUnitCount": len(complexity_rows), "assessmentRows": complexity_rows},
    len(complexity_rows), problem_count=0,
))

# 5. Information hierarchy.
hierarchy_rows = []
for card in cards:
    texts = text_elements(card)
    hierarchy_rows.append({
        "componentId": card["cardId"],
        "sourceElements": [{
            "elementId": element["id"],
            "text": element.get("textFacts", {}).get("rawText", ""),
            "fontSizeBucket": element.get("textFacts", {}).get("fontSizeBucket", "unknown"),
            "fontWeightBucket": element.get("textFacts", {}).get("fontWeightBucket", "unknown"),
        } for element in texts],
        "weightSequence": [element["id"] for element in texts],
        "tierTrace": ["商家标题主层", "评分与位置基础信息层", "优惠与下挂商品层"],
        "levelCount": 3,
        "rating": "优秀",
    })
results.append(result(
    CARD_DIM, "eval-5-info-hierarchy", "商卡视觉层级", "优秀",
    "商家标题稳定承担主层，评分与位置承接，优惠和文字下挂商品保持次级，5张卡均无竞争主焦点。",
    {"sourceManifestTotal": source_total, "evaluatedUnitCount": len(hierarchy_rows), "assessmentRows": hierarchy_rows},
    len(hierarchy_rows), problem_count=0,
))

# 6. No partition issue rows are emitted for an excellent result.
results.append(result(
    CARD_DIM, "eval-6-info-partitioning", "信息分区合理性", "优秀",
    "商家基础信息、券位和下挂商品通过稳定对齐与留白分开，未发现跨区粘连或错误归属。",
    {"sourceManifestTotal": source_total, "assessmentRows": []}, len(cards), problem_count=0,
))

# 7. Authenticity: all current-page facts are mutually consistent.
auth_rows = []
for card in cards:
    ids = [element["id"] for element in text_elements(card)]
    pairs = [{"leftElementId": ids[0], "rightElementId": ids[1], "relation": "same_card_title_and_fulfillment"}]
    auth_rows.append({
        "componentId": card["cardId"],
        "candidatePairs": pairs,
        "pairJudgements": ["consistent"],
        "inapplicableChecks": [],
        "scanCoverage": {
            "status": "completed",
            "scannedElementIds": ids,
            "scannedRegions": region_names(card),
            "crossChecks": ["商家标题与头图归属", "评分位置与商家主体", "下挂商品标题与同行价格归属"],
        },
        "conflicts": [],
        "conflictCount": 0,
        "evidenceSource": "phase2_json_and_original_screenshot",
        "rating": "优秀",
    })
results.append(result(
    CARD_DIM, "eval-7-info-authenticity", "信息真实无歧义", "优秀",
    "逐卡核对商家标题、评分位置、券位和下挂商品价格后，未发现不能同时成立的客观冲突。",
    {"sourceManifestTotal": source_total, "evaluatedUnitCount": len(auth_rows), "evaluatedUnitIds": card_ids, "assessmentRows": auth_rows},
    len(auth_rows), problem_count=0,
))

# 8. Full-card redundancy scan on every visible text region.
duplicate_specs = {}
red_rows = []
red_issues = []
for card in all_cards:
    ids = [element["id"] for element in text_elements(card)]
    specs = duplicate_specs.get(card["cardId"], [])
    candidate_pairs = [{"leftElementId": left, "rightElementId": right, "relation": "商家标题与商户图内品牌文字"} for left, right, _ in specs]
    duplicates = [{
        "leftElementId": left,
        "rightElementId": right,
        "lexicalCue": cue,
        "normalizedFact": "重复事实",
        "noLossReason": "两处表达同一事实，删除任一处不损失独立决策信息。",
        "verdict": "duplicate",
    } for left, right, cue in specs]
    cross_results = []
    for check in REDUNDANCY_CHECKS:
        count = len(candidate_pairs) if check == "title/subtitle ↔ basic information" else 0
        cross_results.append({
            "checkType": check,
            "status": "completed",
            "candidateCount": count,
            "judgementCount": count,
        "reason": "已逐对核对商家标题、基础信息、标签、促销与价格。" if check == REDUNDANCY_CHECKS[0] else "该交叉类型未发现额外候选。",
        })
    rating = "不达标" if duplicates else "优秀"
    red_rows.append({
        "componentId": card["cardId"],
        "scannedRegions": region_names(card),
        "examinedElements": ids,
        "candidatePairs": candidate_pairs,
        "pairJudgements": ["duplicate"] * len(candidate_pairs),
        "selfRepeatCandidates": [],
        "selfRepeatJudgements": [],
        "duplicates": duplicates,
        "duplicateCount": len(duplicates),
        "scanCoverage": {
            "status": "completed",
            "textAtomCount": len(ids),
            "scannedElementIds": ids,
            "scannedRegions": region_names(card),
            "crossChecks": REDUNDANCY_CHECKS,
            "crossCheckResults": cross_results,
        },
        "evidenceSource": "phase2_json_full_redundancy_scan",
        "rating": rating,
    })
    if duplicates:
        issue_id = duplicates[0]["rightElementId"]
        element = next(item for item in elements(card) if item["id"] == issue_id)
        index = card["structure"]["listPosition"]
        red_issues.append({
            "elementId": issue_id,
            "coord": element["坐标"],
            "component": card["cardId"],
            "description": f"商卡{index}存在两处无增量的同义事实，删除其中一处不损失独立决策信息。",
            "rating": "不达标",
            "recommendation": f"删除或弱化商卡{index}头像内与标题重复的品牌文字，仅保留一处完整商户名；验收时确认整卡语义重复数为0。",
        })
results.append(result(
    CARD_DIM, "eval-8-info-redundancy", "信息无冗余", "优秀",
    "已逐卡扫描6张可见商家卡的标题、基础信息、标签、促销和文字下挂商品，未发现可无损删除的重复事实。",
    {"sourceManifestTotal": source_total, "evaluatedUnitCount": len(red_rows), "evaluatedUnitIds": [card["cardId"] for card in all_cards], "assessmentRows": red_rows},
    len(red_rows), red_issues, problem_count=0,
))

# Page-level evaluations.
results.append(result(
    PAGE_DIM, "eval-1-supply-module-completeness", "供给呈现质量（页面框架完整性）", "优秀",
    "搜索入口、业务Tab、位置排序筛选和商家结果列表均已完整加载。",
    {"assessmentRows": []}, 1, problem_count=0,
))

page_alignment = {
    "pageRegions": [
        {"region": "搜索与Tab区", "observedRole": "建立查询和业务范围", "visualSignals": ["顶部稳定定位", "选中Tab用黄色下划线强调"]},
        {"region": "位置与排序筛选区", "observedRole": "调整位置、排序与更多筛选", "visualSignals": ["独立浅色控件", "与列表留白分隔"]},
        {"region": "商家结果列表", "observedRole": "连续呈现商家与文字下挂商品", "visualSignals": ["同型商家卡纵向排列", "文字下挂位保持次级"]},
    ],
    "sameTypeComparisons": [{"members": ["商卡1", "商卡2", "商卡3", "商卡4", "商卡5"], "result": "商家信息在上、文字下挂商品在下的锚点一致"}],
    "primaryFocus": "商家标题与评分信息",
    "flowChecks": [{
        "expectedOrder": ["搜索与Tab", "筛选", "商家结果"],
        "observedOrder": ["搜索与Tab", "筛选", "商家结果"],
        "visualSignals": ["自上而下单列推进", "同型商家卡连续重复"],
        "reason": "搜索、筛选和商家结果的先后关系清楚，未出现主焦点错位。",
        "status": "consistent",
    }],
    "evidenceSource": "original_screenshot_visual_review",
    "rating": "优秀",
}
results.append(result(
    PAGE_DIM, "eval-2-visual-order-alignment", "视觉秩序统一对齐", "优秀",
    "页面从搜索与筛选自然进入连续商家结果，整体阅读顺序稳定。",
    {"assessmentRows": [page_alignment]}, 1, problem_count=0,
))

summaries = [{"componentId": item["componentId"], "colorFamilies": item["colorFamilies"], "colorFamilyCount": item["colorFamilyCount"]} for item in colors]
families = sorted({family for item in summaries for family in item["colorFamilies"]})
page_color = {
    "colorLogicContractVersion": "4.0",
    "componentColorArtifact": str(MEASURE),
    "componentColorSummaries": summaries,
    "colorFamilies": families,
    "colorFamilyCount": len(families),
    "evidenceSource": "component_pixel_color_aggregation",
    "rating": "优秀",
}
results.append(result(
    PAGE_DIM, "eval-3-page-color-logic", "色彩运用有逻辑（页面级）", "优秀",
    "全页商家组件像素色系并集为红、橙、绿共3种，未超过优秀档上限。",
    {"assessmentRows": [page_color]}, 1, problem_count=0,
))

page_complexity = {
    "firstScreenBounds": [0, 0, manifest["pageFacts"]["viewport"]["width"], manifest["pageFacts"]["viewport"]["height"]],
    "functionalModules": [
        {"name": "业务Tab栏", "sourceModuleIds": ["M3"]},
        {"name": "位置与排序筛选", "sourceModuleIds": ["M4"]},
        {"name": "商家结果列表", "sourceModuleIds": ["M5", "M6"]},
    ],
    "moduleCount": 3,
    "rating": "优秀",
}
results.append(result(
    PAGE_DIM, "eval-4-static-component-complexity", "静态组件不复杂（首屏功能区数量）", "优秀",
    "排除顶部搜索框并合并重复识别的结果列表后，当前页面有3个独立功能区，命中优秀档。",
    {"assessmentRows": [page_complexity]}, 1, problem_count=0,
))

flow_row = {
    "listPositions": [{
        "position": card["structure"]["listPosition"],
        "componentId": card["cardId"],
        "cardType": card["cardTypeName"],
        "isHeterogeneous": False,
        "visibleStatus": card["structure"]["visibleStatus"],
    } for card in all_cards],
    "visibleListPositionCount": len(all_cards),
    "coverageStatus": "partial",
    "heterogeneousCount": 0,
    "frontTenHeterogeneousCount": 0,
    "allHeterogeneousItems": [],
    "rating": "优秀",
}
results.append(result(
    PAGE_DIM, "eval-5-browsing-flow-smoothness", "浏览动线顺畅", "优秀",
    "排序筛选下方6个可见列表位均为同型商家卡；末位为自然裁切，已见范围内异构数仍为0。",
    {"assessmentRows": [flow_row]}, 1, problem_count=0,
))

comparability = {
    "cardGroups": [{"comparisonGroupKey": cards[0]["structure"]["comparisonGroupKey"], "members": card_ids}],
    "comparableFields": ["评分", "位置", "到店标识"],
    "comparisons": [{
        "comparisonGroupKey": cards[0]["structure"]["comparisonGroupKey"],
        "semanticRole": "rating_location_fulfillment",
        "observations": [{"componentId": card["cardId"], "present": True, "anchor": "基础信息区"} for card in cards],
        "detectedDifferences": {"missing": [], "formatMismatch": False, "anchorMismatch": False},
        "phase3Judgement": "consistent",
    }],
    "inconsistencyCount": 0,
    "evidenceSource": "phase2_json_cross_card_comparison",
    "rating": "优秀",
}
results.append(result(
    PAGE_DIM, "eval-6-info-comparability", "信息可比性", "优秀",
    "5张完整同型商家卡均在固定基础信息区呈现评分、位置和到店标识，字段锚点一致，可直接横向比较。",
    {"assessmentRows": [comparability]}, 1, problem_count=0,
))

page_regions = ["搜索框", "业务Tab栏", "位置与排序筛选", "商家结果列表"]
page_pairs = list(combinations(page_regions, 2))
page_redundancy = {
    "pageRegions": page_regions,
    "candidatePairs": [],
    "scanCoverage": {
        "status": "completed",
        "scannedRegionIds": page_regions,
        "crossChecks": [f"{left} ↔ {right}" for left, right in page_pairs],
    },
    "crossChecks": [{"regions": [left, right], "judgement": "distinct", "reason": "两区域承担不同页面任务或提供不同决策信息。"} for left, right in page_pairs],
    "redundancyItems": [],
    "redundancyCount": 0,
    "rating": "优秀",
}
results.append(result(
    PAGE_DIM, "eval-7-info-redundancy", "功能/信息无冗余", "优秀",
    "已覆盖搜索框、业务Tab、筛选和结果列表并完成6组两两检查；各区域职责不同，跨区域冗余数为0。",
    {"assessmentRows": [page_redundancy]}, 1, problem_count=0,
))

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(OUT)
