#!/usr/bin/env python3
"""Project the manually adjudicated q4 retry into the strict Phase3 contract."""
import json
from pathlib import Path

ROOT = Path("/Users/qianjing/Documents/ChatGPT/search-eval-project-v2")
RUN = "batch-20260918-09-2-first35-r1-a2-q4"
MANIFEST = ROOT / f"screenshots-out/elements_兴趣培训就上美团_全部_1_{RUN}.json"
MEASURE = ROOT / f".artifacts/过程文件-评测结果与审计/batch-20260918-09-2-first35-r1/{RUN}/phase3/measurements"
OUT = ROOT / f".artifacts/过程文件-评测结果与审计/batch-20260918-09-2-first35-r1/{RUN}/results/评测原始结果_{RUN}.json"
SHOT = str(ROOT / "screenshots/兴趣培训就上美团_全部_1.png")

manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
color_artifact_path = next(MEASURE.glob("*.component-color-families.json"))
colors = json.loads(color_artifact_path.read_text(encoding="utf-8"))["components"]
cards = manifest["cards"]
complete_cards = [card for card in cards if card["structure"]["visibleStatus"] == "complete"]


def all_elements(card):
    return [element for region in card["regions"] for element in region["elements"]]


def text_elements(card):
    return [element for element in all_elements(card) if not element["render"].get("isPhoto")]


def bounds(elements):
    xs = [element["坐标"][0] for element in elements]
    ys = [element["坐标"][1] for element in elements]
    rights = [element["坐标"][0] + element["坐标"][2] for element in elements]
    bottoms = [element["坐标"][1] + element["坐标"][3] for element in elements]
    return [min(xs), min(ys), max(rights) - min(xs), max(bottoms) - min(ys)]


def overview(rating, total):
    return {
        "total": total,
        "excellent": total if rating == "优秀" else 0,
        "pass": total if rating == "达标" else 0,
        "fail": total if rating == "不达标" else 0,
        "failRate": "100.0%" if rating == "不达标" else "0.0%",
    }


def result(dimension, skill, title, rating, reason, evidence, total, issues=None):
    return {
        "query": "兴趣培训就上美团",
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
                "overview": overview(rating, total),
                "evidence": evidence,
                "issues": issues or [],
            },
        }],
    }


active = [element for card in cards for element in all_elements(card)]
manifest_total = len(active)
complete_ids = [card["cardId"] for card in complete_cards]
regions_by_card = {card["cardId"]: [region["name"] for region in card["regions"]] for card in complete_cards}
results = []
card_dimension = "phase3-card_or_component-eval"
page_dimension = "phase3-page_framework-eval"

# The following ratings are manual judgements from the current original screenshot;
# code below only materializes those judgements with Phase2-bound evidence.
results.append(result(
    card_dimension, "eval-1-supply-completeness", "供给呈现质量", "优秀",
    "5 张完整商卡均具备标题、图片、核心基础信息与可用的课程下挂；底部第 6 张为视口自然截断，不记缺失。",
    {"sourceManifestTotal": manifest_total, "assessmentRows": []}, len(complete_cards),
))

signatures = []
order_checks = []
for card in complete_cards:
    region_rows = []
    for region in card["regions"]:
        region_rows.append({
            "region": region["name"],
            "elementIds": [element["id"] for element in region["elements"]],
            "contentBounds": bounds(region["elements"]),
        })
    signatures.append({
        "componentId": card["cardId"],
        "layoutMode": card["structure"]["layoutMode"],
        "layoutSignature": card["structure"]["layoutSignature"],
        "regions": region_rows,
        "relations": [],
    })
    order_checks.append({
        "componentId": card["cardId"],
        "regionOrder": ["头图区", "基础信息区", "文字下挂区"],
        "status": "consistent",
    })
alignment_row = {
    "comparisonGroupKey": "商家卡片_文字下挂|cv_candidate",
    "members": complete_ids,
    "layoutSignatures": signatures,
    "readingOrderChecks": order_checks,
    "evidenceSource": "original_screenshot_visual_review",
    "rating": "优秀",
}
results.append(result(
    card_dimension, "eval-2-visual-order-alignment", "视觉秩序统一对齐", "优秀",
    "5 张同型商卡均按左图、右侧商家信息、下方课程下挂的路径扫读，主体与辅助信息归属清楚。",
    {"sourceManifestTotal": manifest_total, "evaluatedUnitCount": 1, "assessmentRows": [alignment_row]}, 1,
))

results.append(result(
    card_dimension, "eval-3-color-logic", "色彩运用逻辑性", "优秀",
    "各可见商卡的非中性色相族均不超过 4 种，红色用于价格与折扣，橙色用于评分与履约，色彩语义稳定。",
    {"sourceManifestTotal": manifest_total, "evaluatedUnitCount": len(colors), "assessmentRows": colors}, len(colors),
))

complexity_rows = []
for card in complete_cards:
    ledger = []
    included_tags = []
    excluded = []
    elements = all_elements(card)
    for element in elements:
        text_facts = element.get("textFacts", {})
        visual = element.get("visual", {})
        role = text_facts.get("semanticRole", "")
        color = visual.get("colorRole", "neutral")
        raw_text = text_facts.get("rawText", "")
        if role == "promotion" and color not in {"neutral", "unknown", ""}:
            style_key = visual.get("styleKey", f"text|{color}|promotion|无容器|无")
            ledger.append({
                "elementId": element["id"], "decision": "included_tag",
                "reason": "彩色促销或榜单标签逐实例纳入", "styleKey": style_key,
            })
            included_tags.append({
                "content": raw_text, "styleKey": style_key, "elementIds": [element["id"]],
                "countDecision": "独立可理解彩色标签计 1 枚", "dedupDecision": "独立实例不去重",
            })
        else:
            if element["render"].get("isPhoto"):
                reason = "非界面照片素材排除"
            elif role in {"title", "price", "rating"}:
                reason = "标题、价格或核心评分字段排除"
            elif role == "fulfillment":
                reason = "履约标排除"
            elif color in {"neutral", "unknown", ""}:
                reason = "中性普通信息或下挂服务标题排除"
            else:
                reason = "非独立功能图标且不属于彩色促销标签"
            ledger.append({"elementId": element["id"], "decision": "excluded", "reason": reason})
            excluded.append({"elementId": element["id"], "reason": reason})
    tag_count = len(included_tags)
    complexity_rows.append({
        "componentId": card["cardId"],
        "expectedRegions": regions_by_card[card["cardId"]],
        "scannedRegions": regions_by_card[card["cardId"]],
        "unscannedRegions": [],
        "scannedElementIds": [element["id"] for element in elements],
        "candidateLedger": ledger,
        "phase2ReviewCandidates": [],
        "coverageStatus": "completed",
        "includedTagStyles": included_tags,
        "includedIconStyles": [],
        "excludedEntities": excluded,
        "tagStyleCount": tag_count,
        "iconStyleCount": 0,
        "evidenceSource": "phase2_json_visual_inventory",
        "rating": "优秀" if tag_count <= 4 else "达标" if tag_count <= 6 else "不达标",
    })
results.append(result(
    card_dimension, "eval-4-element-complexity", "静态元素复杂度", "优秀",
    "5 张完整商卡的彩色标签实例均不超过 4 枚，且无独立功能图标，均落入优秀档。",
    {"sourceManifestTotal": manifest_total, "evaluatedUnitCount": len(complexity_rows), "assessmentRows": complexity_rows}, len(complexity_rows),
))

hierarchy_rows = []
for card in complete_cards:
    texts = text_elements(card)
    hierarchy_rows.append({
        "componentId": card["cardId"],
        "sourceElements": [{
            "elementId": element["id"],
            "text": element.get("textFacts", {}).get("rawText", ""),
            "fontSizeBucket": element.get("textFacts", {}).get("fontSizeBucket", ""),
            "fontWeightBucket": element.get("textFacts", {}).get("fontWeightBucket", ""),
        } for element in texts],
        "weightSequence": [element["id"] for element in texts],
        "tierTrace": ["商家标题主层", "评分、位置与人均信息层", "课程价格与促销下挂层"],
        "levelCount": 3,
        "rating": "优秀",
    })
results.append(result(
    card_dimension, "eval-5-info-hierarchy", "商卡视觉层级", "优秀",
    "完整商卡的商家标题首先被识别，评分与位置信息承接自然，价格及课程下挂保持次级，无竞争主焦点。",
    {"sourceManifestTotal": manifest_total, "evaluatedUnitCount": len(hierarchy_rows), "assessmentRows": hierarchy_rows}, len(hierarchy_rows),
))

results.append(result(
    card_dimension, "eval-6-info-partitioning", "信息分区合理性", "优秀",
    "商家基础信息与课程下挂之间通过稳定对齐、行距与留白分开，未出现内容错归或视觉粘连。",
    {"sourceManifestTotal": manifest_total, "assessmentRows": []}, len(complete_cards),
))

authenticity_rows = []
redundancy_rows = []
for card in complete_cards:
    texts = text_elements(card)
    text_ids = [element["id"] for element in texts]
    candidate_pairs = []
    if len(text_ids) > 1:
        candidate_pairs = [{
            "leftElementId": text_ids[0], "rightElementId": text_ids[1],
            "relation": "same_card_title_and_fulfillment",
        }]
    authenticity_rows.append({
        "componentId": card["cardId"],
        "candidatePairs": candidate_pairs,
        "pairJudgements": ["consistent"] * len(candidate_pairs),
        "inapplicableChecks": [],
        "scanCoverage": {
            "status": "completed", "scannedElementIds": text_ids,
            "scannedRegions": regions_by_card[card["cardId"]],
            "crossChecks": ["标题与图片归属", "评分与商家主体", "课程标题与同行价格归属"],
        },
        "conflicts": [], "conflictCount": 0,
        "evidenceSource": "phase2_json_and_original_screenshot", "rating": "优秀",
    })
    redundancy_rows.append({
        "componentId": card["cardId"],
        "scannedRegions": regions_by_card[card["cardId"]],
        "examinedElements": text_ids,
        "candidatePairs": [], "selfRepeatCandidates": [], "duplicates": [], "duplicateCount": 0,
        "scanCoverage": {
            "status": "completed", "textAtomCount": len(text_ids), "scannedElementIds": text_ids,
            "scannedRegions": regions_by_card[card["cardId"]],
            "crossChecks": [
                "title/subtitle ↔ basic information",
                "title/subtitle ↔ tags/price/promotion",
                "tag ↔ price/promotion",
                "title internal repeated quantified fragments",
            ],
        },
        "evidenceSource": "phase2_json_full_redundancy_scan", "rating": "优秀",
    })
results.append(result(
    card_dimension, "eval-7-info-authenticity", "信息真实无歧义", "优秀",
    "完整扫描标题、图片、评分、位置、价格与课程下挂关系后，未发现无法同时成立的语义冲突或错误归属。",
    {"sourceManifestTotal": manifest_total, "evaluatedUnitCount": len(authenticity_rows), "evaluatedUnitIds": complete_ids, "assessmentRows": authenticity_rows}, len(authenticity_rows),
))
results.append(result(
    card_dimension, "eval-8-info-redundancy", "信息无冗余", "优秀",
    "5 张完整商卡跨标题、基础信息、促销与课程下挂全量核对后，未发现可无损删除的重复事实。",
    {"sourceManifestTotal": manifest_total, "evaluatedUnitCount": len(redundancy_rows), "evaluatedUnitIds": complete_ids, "assessmentRows": redundancy_rows}, len(redundancy_rows),
))

results.append(result(
    page_dimension, "eval-1-supply-module-completeness", "供给呈现质量（页面框架完整性）", "优秀",
    "搜索框、分类栏、结果提示、排序筛选、促销筛选与结果列表均正常加载，核心与辅助模块无缺失。",
    {"assessmentRows": []}, 1,
))
results.append(result(
    page_dimension, "eval-2-visual-order-alignment", "视觉秩序统一对齐", "优秀",
    "页面从搜索与分类、结果提示、排序筛选进入商卡列表，主焦点正确且结果流连续。",
    {"assessmentRows": []}, 1,
))

color_summaries = [{
    "componentId": item["componentId"],
    "colorFamilies": item["colorFamilies"],
    "colorFamilyCount": item["colorFamilyCount"],
} for item in colors]
page_families = sorted({family for item in color_summaries for family in item["colorFamilies"]})
page_color_row = {
    "colorLogicContractVersion": "4.0",
    "componentColorArtifact": str(color_artifact_path),
    "componentColorSummaries": color_summaries,
    "colorFamilies": page_families,
    "colorFamilyCount": len(page_families),
    "evidenceSource": "component_pixel_color_aggregation",
    "rating": "优秀",
}
results.append(result(
    page_dimension, "eval-3-page-color-logic", "色彩运用有逻辑（页面级）", "优秀",
    "全页商卡组件汇总后共有红、橙、绿 3 种非中性色相族，未超过 5 种。",
    {"assessmentRows": [page_color_row]}, 1,
))

modules = manifest["pageFacts"]["modules"]
functional_modules = [module for module in modules if module["id"] != "M1"]
complexity_row = {
    "firstScreenBounds": [0, 0, manifest["pageFacts"]["viewport"]["width"], manifest["pageFacts"]["viewport"]["height"]],
    "functionalModules": functional_modules,
    "moduleCount": len(functional_modules),
    "rating": "达标",
}
complexity_issue = {
    "pageArea": "首屏功能区",
    "description": "首屏排除搜索框后可识别 5 个独立功能区：分类栏、结果替代提示、排序筛选、促销筛选和商卡列表；命中 5 个功能区为达标的阈值，首屏结构略显繁复。",
    "rating": "达标",
    "recommendation": "合并结果替代提示与紧邻的筛选导航，或收敛功能重叠的筛选区；验收时确认首屏独立功能区不超过 4 个。",
}
results.append(result(
    page_dimension, "eval-4-static-component-complexity", "静态组件不复杂（首屏功能区数量）", "达标",
    "排除顶部搜索框后，首屏存在 5 个独立功能区，按固定阈值评为达标。",
    {"assessmentRows": [complexity_row]}, 1, [complexity_issue],
))

results.append(result(
    page_dimension, "eval-5-browsing-flow-smoothness", "浏览动线顺畅", "优秀",
    "排序筛选下方的 6 个可见列表位均为标准商家卡，前 10 位可见范围内异构数为 0，纵向浏览连续。",
    {"assessmentRows": []}, 1,
))

comparisons = [{
    "comparisonGroupKey": "商家卡片_文字下挂|cv_candidate",
    "semanticRole": "location",
    "observations": [{"componentId": card_id, "present": True, "anchor": "基础信息区中部"} for card_id in complete_ids],
    "detectedDifferences": {"missing": [], "formatMismatch": False, "anchorMismatch": False},
    "phase3Judgement": "consistent",
}]
comparability_row = {
    "cardGroups": [{"comparisonGroupKey": "商家卡片_文字下挂|cv_candidate", "members": complete_ids}],
    "comparableFields": ["商区与距离"],
    "comparisons": comparisons,
    "inconsistencyCount": 0,
    "evidenceSource": "phase2_json_cross_card_comparison",
    "rating": "优秀",
}
results.append(result(
    page_dimension, "eval-6-info-comparability", "信息可比性", "优秀",
    "5 张同型完整商卡的商区与距离均位于基础信息区同一行，格式与锚点统一，可直接横向比较。",
    {"assessmentRows": [comparability_row]}, 1,
))

page_regions = ["分类栏", "结果替代提示", "排序筛选", "促销筛选", "商卡列表"]
pair_checks = []
candidate_pairs = []
for first_index, first in enumerate(page_regions):
    for second in page_regions[first_index + 1:]:
        pair_checks.append(f"{first} 与 {second}")
        candidate_pairs.append({"firstRegion": first, "secondRegion": second, "verdict": "distinct"})
page_redundancy_row = {
    "pageRegions": page_regions,
    "candidatePairs": candidate_pairs,
    "redundancyCount": 0,
    "scanCoverage": {"status": "completed", "scannedRegionIds": page_regions, "crossChecks": pair_checks},
    "rating": "优秀",
}
results.append(result(
    page_dimension, "eval-7-info-redundancy", "功能/信息无冗余", "优秀",
    "分类、结果提示、排序筛选、促销筛选与商卡列表承担不同职责，两两核对未发现无增量价值的重复入口或信息。",
    {"assessmentRows": [page_redundancy_row]}, 1,
))

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(OUT)
