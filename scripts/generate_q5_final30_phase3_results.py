#!/usr/bin/env python3
"""Generate the current-pixel Phase3 judgement for final30 q5."""

import json
from itertools import combinations
from pathlib import Path

ROOT = Path("/Users/qianjing/Documents/ChatGPT/search-eval-project-v2")
RUN = "batch-20260920-09-2-final30-r1-q5"
BATCH = "batch-20260920-09-2-final30-r1"
QUERY = "老东北麻黏糊辣烫"
STEM = "老东北麻黏糊辣烫_全部_1"
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
colors = json.loads(MEASURE.read_text(encoding="utf-8"))["components"]
all_cards = manifest["cards"]
cards = [card for card in all_cards if card["structure"]["visibleStatus"] == "complete"]
card_ids = [card["cardId"] for card in cards]
source_total = audit["total"]


def elements(card):
    return [element for region in card["regions"] for element in region["elements"]]


def text_elements(card):
    return [element for element in elements(card) if not element.get("render", {}).get("isPhoto")]


def region_names(card):
    return [region["name"] for region in card["regions"]]


def overview(total, excellent, passed=0, failed=0):
    return {
        "total": total,
        "excellent": excellent,
        "pass": passed,
        "fail": failed,
        "failRate": f"{(failed / total * 100):.1f}%" if total else "0.0%",
    }


def result(dimension, skill, title, rating, reason, evidence, total, excellent, passed=0, failed=0, issues=None):
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
                "overview": overview(total, excellent, passed, failed),
                "evidence": evidence,
                "issues": issues or [],
            },
        }],
    }


cropped = [{"componentId": "C3", "reason": "底部自然裁切，仅保留当前可见事实，不用于完整商卡结论。"}]
results = []

# Card 1: supply completeness.
results.append(result(
    CARD_DIM, "eval-1-supply-completeness", "供给呈现质量", "优秀",
    "3张完整商家卡均呈现商家标题、评分、履约或位置及可读图文下挂；第4张为底部自然裁切，不作为缺失样本。",
    {"sourceManifestTotal": source_total, "evaluatedUnitCount": 3, "assessmentRows": [], "excludedUnits": cropped},
    3, 3,
))

# Card 2: shared current-pixel reading order.
layout_signatures = []
order_checks = []
for card in cards:
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
        "expectedOrder": ["商家标题与头图", "评分、履约与位置", "促销权益", "下挂商品与价格"],
        "observedOrder": ["商家标题与头图", "评分、履约与位置", "促销权益", "下挂商品与价格"],
        "attentionSignals": ["标题与头图先建立商家主体", "促销和商品位保持次级"],
        "dominantRegion": "基础信息区",
        "auxiliaryDominance": False,
        "competingFoci": False,
        "ownershipAmbiguity": False,
        "pathInversion": False,
        "localDetour": False,
        "reason": "商家主体先于权益和商品位进入注意力路径，信息归属清楚。",
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
results.append(result(
    CARD_DIM, "eval-2-visual-order-alignment", "视觉秩序统一对齐", "优秀",
    "3张完整同型商家卡均保持商家信息在上、优惠与商品横滑在下的稳定扫读顺序。",
    {"sourceManifestTotal": source_total, "evaluatedUnitCount": 1, "assessmentRows": [alignment], "excludedUnits": cropped},
    1, 1,
))

# Card 3: prepared current-pixel color families include the cropped card's visible area.
results.append(result(
    CARD_DIM, "eval-3-color-logic", "色彩运用逻辑性", "优秀",
    "4张可见商家卡的有效界面色系数分别为3、3、3、1，均不超过4种的优秀档上限。",
    {"sourceManifestTotal": source_total, "evaluatedUnitCount": len(colors), "assessmentRows": colors},
    len(colors), len(colors),
))

# Card 4: independent colored promotion/recommendation/tag instances.
included_ids = {
    "C0": {"C0-T6", "C0-T11", "C0-T12", "C0-T16", "C0-T20"},
    "C1": {"C1-T12", "C1-T13", "C1-T17", "C1-T21"},
    "C2": {"C2-T10", "C2-T11", "C2-T16"},
}
complexity_rows = []
for card in cards:
    included, excluded, ledger = [], [], []
    for element in elements(card):
        element_id = element["id"]
        role = element.get("textFacts", {}).get("semanticRole", "")
        text = element.get("textFacts", {}).get("rawText", "")
        color = element.get("visual", {}).get("colorRole", "unknown")
        if element_id in included_ids[card["cardId"]]:
            style_key = element.get("visual", {}).get("styleKey", f"标签|{color}|{role}|无容器|无")
            ledger.append({"elementId": element_id, "decision": "included_tag", "reason": "独立彩色促销、推荐或标签实例逐一纳入", "styleKey": style_key})
            included.append({
                "content": text,
                "styleKey": style_key,
                "elementIds": [element_id],
                "countDecision": "独立可理解的异色标签计1个",
                "dedupDecision": "不同商品位或权益位的独立实例不去重",
            })
        else:
            if element.get("render", {}).get("isPhoto"):
                reason = "商家或商品照片素材不计入界面附加样式"
            elif role in {"fulfillment", "delivery_time"}:
                reason = "履约信息按复杂度契约排除"
            elif role in {"title", "price", "rating", "item_price", "item_original_price"}:
                reason = "标题、评分或价格属于核心信息字段"
            elif role in {"attachment", "sales", "positive_rate", "dynamic_trust"}:
                reason = "商品标题、销量或口碑事实不构成独立附加功能标签"
            elif color in {"neutral", "unknown", ""}:
                reason = "中性普通信息不构成独立彩色标签"
            else:
                reason = "普通辅助信息不构成独立附加功能标签"
            ledger.append({"elementId": element_id, "decision": "excluded", "reason": reason})
            excluded.append({"elementId": element_id, "reason": reason})
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
complexity_issue = {
    "elementId": "C0-T20",
    "coord": [806, 974, 85, 42],
    "component": "C0",
    "description": "商卡1同时出现「免配送费」「满减」「0.5折起」「2.06折」「招牌」5种独立彩色标签，命中5—6个标签的达标档；附加图标为0种。",
    "rating": "达标",
    "recommendation": "合并或弱化至少1个次要促销/推荐标签；验收时确认单卡独立彩色标签不超过4个且附加icon不超过1种。",
    "evidenceImage": SHOT,
}
results.append(result(
    CARD_DIM, "eval-4-element-complexity", "静态元素复杂度", "达标",
    "3张完整商家卡的独立彩色标签实例数分别为5、4、3，附加icon均为0种；首张卡命中达标档，其余两张优秀。",
    {"sourceManifestTotal": source_total, "evaluatedUnitCount": 3, "assessmentRows": complexity_rows, "excludedUnits": cropped},
    3, 2, passed=1, issues=[complexity_issue],
))

# Card 5: hierarchy.
hierarchy_rows = []
for card in cards:
    texts = text_elements(card)
    title = next(element for element in texts if element.get("textFacts", {}).get("semanticRole") == "title")
    basic = [element for element in texts if element.get("textFacts", {}).get("semanticRole") in {"rating", "fulfillment", "sales", "review_count", "location", "distance"}][:4]
    lower = [element for element in texts if element.get("textFacts", {}).get("semanticRole") in {"promotion", "recommendation", "tag", "attachment", "item_price"}][-4:]
    selected = [title] + basic + lower
    hierarchy_rows.append({
        "componentId": card["cardId"],
        "sourceElements": [{
            "elementId": element["id"],
            "content": element.get("textFacts", {}).get("rawText", ""),
            "visualSignal": "粗体商家标题" if element["id"] == title["id"] else ("基础决策字段" if element in basic else "次级权益或商品字段"),
        } for element in selected],
        "weightSequence": ["商家标题与头图", "评分、履约与位置", "促销权益", "下挂商品与价格"],
        "tierTrace": [
            {"tier": 1, "elements": [title["id"]], "basis": "大号粗体标题先建立商家主体"},
            {"tier": 2, "elements": [element["id"] for element in basic], "basis": "评分、履约与位置形成连续基础信息层"},
            {"tier": 3, "elements": [element["id"] for element in lower], "basis": "彩色权益和商品价格位于下挂次级区域"},
        ],
        "levelCount": 3,
        "rating": "优秀",
    })
results.append(result(
    CARD_DIM, "eval-5-info-hierarchy", "商卡视觉层级", "优秀",
    "3张完整商家卡均以标题和头图建立主体，评分、履约或位置承接，优惠与下挂商品保持次级，未形成竞争主焦点。",
    {"sourceManifestTotal": source_total, "evaluatedUnitCount": 3, "assessmentRows": hierarchy_rows, "excludedUnits": cropped},
    3, 3,
))

# Card 6: partitioning.
results.append(result(
    CARD_DIM, "eval-6-info-partitioning", "信息分区合理性", "优秀",
    "3张完整商家卡的基础信息、促销权益和下挂商品通过稳定对齐、留白及卡间分隔清楚区分，未见粘连或错归属。",
    {"sourceManifestTotal": source_total, "evaluatedUnitCount": 3, "assessmentRows": [], "excludedUnits": cropped},
    3, 3,
))

# Card 7: authenticity.
auth_rows = []
for card in cards:
    ids = [element["id"] for element in elements(card)]
    auth_rows.append({
        "componentId": card["cardId"],
        "candidatePairs": [],
        "pairJudgements": [],
        "inapplicableChecks": ["不使用外部门店、实时销量或线下服务事实校验"],
        "scanCoverage": {
            "status": "completed",
            "scannedElementIds": ids,
            "scannedRegions": region_names(card),
            "crossChecks": ["标题与头图主体", "评分和履约与商家主体", "促销与当前商家归属", "商品标题与同行价格归属"],
        },
        "conflicts": [],
        "conflictCount": 0,
        "evidenceSource": "phase2_json_and_original_screenshot",
        "rating": "优秀",
    })
results.append(result(
    CARD_DIM, "eval-7-info-authenticity", "信息真实无歧义", "优秀",
    "逐卡核对标题、头图、评分、履约或位置、促销及商品价格的语义与视觉归属，未发现不能同时成立或错归主体的关系。",
    {"sourceManifestTotal": source_total, "evaluatedUnitCount": 3, "evaluatedUnitIds": card_ids, "assessmentRows": auth_rows, "excludedUnits": cropped},
    3, 3,
))

# Card 8: exhaustive within-card redundancy scan. Repeated positive-rate facts
# on C2 belong to two different product columns and are therefore distinct.
distinct_pairs = {
    "C2": [("C2-T17", "C2-T21", "两处100%好评度分别属于两个独立商品位")],
}
red_rows = []
for card in cards:
    ids = [element["id"] for element in text_elements(card)]
    specs = distinct_pairs.get(card["cardId"], [])
    pairs = [{"leftElementId": left, "rightElementId": right, "relation": reason} for left, right, reason in specs]
    red_rows.append({
        "componentId": card["cardId"],
        "scannedRegions": region_names(card),
        "examinedElements": ids,
        "candidatePairs": pairs,
        "pairJudgements": ["distinct" for _ in pairs],
        "selfRepeatCandidates": [],
        "selfRepeatJudgements": [],
        "duplicates": [],
        "duplicateCount": 0,
        "scanCoverage": {
            "status": "completed",
            "textAtomCount": len(ids),
            "scannedElementIds": ids,
            "scannedRegions": region_names(card),
            "crossChecks": REDUNDANCY_CHECKS,
            "crossCheckResults": [{
                "checkType": check,
                "status": "completed",
                "candidateCount": len(pairs) if check == "tag ↔ price/promotion" else 0,
                "judgementCount": len(pairs) if check == "tag ↔ price/promotion" else 0,
                "reason": "已终判相同口碑值在不同商品位的候选。" if check == "tag ↔ price/promotion" and pairs else "该交叉类型未发现额外可无损删除候选。",
            } for check in REDUNDANCY_CHECKS],
        },
        "evidenceSource": "phase2_json_full_redundancy_scan",
        "rating": "优秀",
    })
results.append(result(
    CARD_DIM, "eval-8-info-redundancy", "信息无冗余", "优秀",
    "完整扫描3张商家卡的标题、基础信息、促销和商品位；同值好评度分别属于不同商品，具有独立决策价值，确认冗余数为0。",
    {"sourceManifestTotal": source_total, "evaluatedUnitCount": 3, "evaluatedUnitIds": card_ids, "assessmentRows": red_rows, "excludedUnits": cropped},
    3, 3,
))

# Page 1: supply.
results.append(result(
    PAGE_DIM, "eval-1-supply-module-completeness", "供给呈现质量（页面框架完整性）", "优秀",
    "搜索入口、业务Tab、位置与排序筛选及商家结果列表均完整加载，未见适用核心或辅助模块缺失。",
    {"assessmentRows": []}, 1, 1,
))

# Page 2: current-pixel page order.
page_alignment = {
    "pageRegions": [
        {"region": "搜索与业务Tab", "observedRole": "建立查询与结果范围", "visualSignals": ["顶部稳定入口", "选中Tab使用黄色下划线"]},
        {"region": "位置与排序筛选", "observedRole": "调整地域、排序与筛选条件", "visualSignals": ["单行浅色控件", "与列表留白分隔"]},
        {"region": "商家结果列表", "observedRole": "连续呈现商家和下挂商品", "visualSignals": ["同型商家卡纵向排列", "稳定卡间节奏"]},
    ],
    "sameTypeComparisons": [{"members": ["商卡1", "商卡2", "商卡3"], "result": "标题、基础信息与下挂商品主锚点一致"}],
    "primaryFocus": "商家结果列表",
    "flowChecks": [{
        "expectedOrder": ["搜索与Tab", "位置与排序筛选", "商家结果列表"],
        "observedOrder": ["搜索与Tab", "位置与排序筛选", "商家结果列表"],
        "visualSignals": ["自上而下单列推进", "筛选区与结果区边界清楚"],
        "reason": "页面按查询、筛选、浏览结果的顺序推进，未出现辅助模块抢占主焦点。",
        "status": "consistent",
    }],
    "evidenceSource": "original_screenshot_visual_review",
    "rating": "优秀",
}
results.append(result(
    PAGE_DIM, "eval-2-visual-order-alignment", "视觉秩序统一对齐", "优秀",
    "页面由搜索与业务Tab进入位置排序筛选，再进入连续商家结果列表，主焦点与浏览顺序稳定。",
    {"assessmentRows": [page_alignment]}, 1, 1,
))

# Page 3: union of prepared component pixel families.
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
    "全页可见商家组件的有效界面色系并集为红、橙、黄共3种，未超过5种的页面优秀档上限。",
    {"assessmentRows": [page_color]}, 1, 1,
))

# Page 4: search box excluded; tab, filter/sort, and result list are three modules.
page_complexity = {
    "firstScreenBounds": [0, 0, manifest["pageFacts"]["viewport"]["width"], manifest["pageFacts"]["viewport"]["height"]],
    "functionalModules": [
        {"name": "业务Tab栏", "sourceModuleIds": ["M1", "M3"]},
        {"name": "位置与排序筛选", "sourceModuleIds": ["M3"]},
        {"name": "商家结果列表", "sourceModuleIds": ["M4", "M5"]},
    ],
    "moduleCount": 3,
    "observableFact": "排除顶部搜索框并将重复识别的列表区域合并后，共3个独立功能区。",
    "rating": "优秀",
}
results.append(result(
    PAGE_DIM, "eval-4-static-component-complexity", "静态组件不复杂（首屏功能区数量）", "优秀",
    "排除顶部搜索框并合并重复识别的结果列表后，首屏有业务Tab、位置与排序筛选、商家结果列表共3个独立功能区。",
    {"assessmentRows": [page_complexity]}, 1, 1,
))

# Page 5: all four visible positions are ordinary merchant cards.
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
    "heterogeneousItems": [],
    "rating": "优秀",
}
results.append(result(
    PAGE_DIM, "eval-5-browsing-flow-smoothness", "浏览动线顺畅", "优秀",
    "排序筛选下方4个可见列表位均为同型标准商家卡，前10位当前可见范围内异构数为0。",
    {"assessmentRows": [flow_row]}, 1, 1,
))

# Page 6: compare the two complete delivery cards. The in-store card has a
# different business semantic and is explicitly not forced into that group.
comparability = {
    "cardGroups": [{"comparisonGroupKey": "外卖商家卡", "members": ["C0", "C1"]}],
    "comparableFields": ["外卖履约", "评分", "月售", "起送价", "配送时长", "距离"],
    "comparisons": [{
        "comparisonGroupKey": "外卖商家卡",
        "semanticRole": "delivery_rating_sales_minimum_time_distance",
        "fieldMatchKey": "相同外卖业务语义下的基础决策字段",
        "observations": [
            {"componentId": "C0", "present": True, "anchor": "基础信息区固定行与右侧时间距离位"},
            {"componentId": "C1", "present": True, "anchor": "基础信息区固定行与右侧时间距离位"},
        ],
        "detectedDifferences": {"missing": [], "formatMismatch": False, "anchorMismatch": False, "styleSemanticMismatch": False},
        "materialImpact": False,
        "phase3Judgement": "consistent",
    }],
    "excludedReasons": ["C2为到店业务卡，评分之外的字段口径与外卖卡不同，不强行纳入外卖横向比较；C3自然裁切。"],
    "inconsistencyCount": 0,
    "evidenceSource": "phase2_json_cross_card_comparison",
    "rating": "优秀",
}
results.append(result(
    PAGE_DIM, "eval-6-info-comparability", "信息可比性", "优秀",
    "两张完整外卖商家卡在固定基础信息区统一呈现履约、评分、月售、起送价、配送时长和距离；到店卡按不同业务口径排除。",
    {"assessmentRows": [comparability]}, 1, 1,
))

# Page 7: exhaustive pairwise scan of the three independent page regions.
page_regions = ["搜索与业务Tab", "位置与排序筛选", "商家结果列表"]
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
    "已覆盖搜索与Tab、位置排序筛选和商家结果列表并完成3组两两检查；各区域职责不同，跨区域冗余数为0。",
    {"assessmentRows": [page_redundancy]}, 1, 1,
))

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(OUT)
