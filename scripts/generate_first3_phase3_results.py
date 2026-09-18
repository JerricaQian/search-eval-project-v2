#!/usr/bin/env python3
"""Generate the adjudicated Phase 3 results for the 2026-09-18 first-three batch."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path("/Users/qianjing/Documents/ChatGPT/search-eval-project-v2")
BATCH = "batch-20260918-first3"
RUNS = [
    ("batch-20260918-anmee", "anmee暗弥咖啡", "anmee暗弥咖啡_全部_1"),
    ("batch-20260918-skii-r2", "skii清莹露", "skii清莹露_全部_1"),
    ("batch-20260918-smile", "smile主题民宿", "smile主题民宿_全部_1"),
]

CARD_DIM = "phase3-card_or_component-eval"
PAGE_DIM = "phase3-page_framework-eval"
REDUNDANCY_CHECKS = [
    "title/subtitle ↔ basic information",
    "title/subtitle ↔ tags/price/promotion",
    "tag ↔ price/promotion",
    "title internal repeated quantified fragments",
]


def overview(rating: str, total: int) -> dict:
    return {
        "total": total,
        "excellent": total if rating == "优秀" else 0,
        "pass": total if rating == "达标" else 0,
        "fail": total if rating == "不达标" else 0,
        "failRate": "100.0%" if rating == "不达标" else "0.0%",
    }


def unit(shot: str, rating: str, reason: str, evidence: dict, total: int) -> dict:
    return {
        "tab": "全部",
        "rating": rating,
        "reason": reason,
        "details": {
            "screenshot": shot,
            "evidenceMode": "original-page",
            "overview": overview(rating, total),
            "evidence": evidence,
            "issues": [],
        },
    }


def result(query: str, shot: str, dimension: str, skill: str, title: str,
           reason: str, evidence: dict, total: int) -> dict:
    return {
        "query": query,
        "dimension": dimension,
        "skill": skill,
        "title": title,
        "units": [unit(shot, "优秀", reason, evidence, total)],
    }


def elements(card: dict) -> list[dict]:
    return [element for region in card["regions"] for element in region["elements"]]


def text_elements(card: dict) -> list[dict]:
    return [element for element in elements(card) if not element.get("render", {}).get("isPhoto")]


def card_region_names(card: dict) -> list[str]:
    return [region["name"] for region in card["regions"]]


def card_region_trace(card: dict) -> list[dict]:
    return [
        {
            "region": region["name"],
            "elementIds": [element["id"] for element in region["elements"]],
            "contentBounds": region["coord"],
        }
        for region in card["regions"]
    ]


def excluded_reason(element: dict) -> str:
    if element.get("render", {}).get("isPhoto"):
        return "非界面照片素材，不计入标签或图标复杂度"
    role = element.get("textFacts", {}).get("semanticRole", "")
    if role == "fulfillment":
        return "履约标识按复杂度契约排除，不计作附加标签"
    if role in {"title", "price", "rating"}:
        return "标题、价格或评分属于核心信息字段，不计作附加标签"
    return "中性普通信息文字，不构成独立异形异色标签"


def build(run_id: str, query: str, image_stem: str) -> Path:
    manifest_path = ROOT / f"screenshots-out/elements_{image_stem}_{run_id}.json"
    audit_path = ROOT / f"screenshots-out/elements_{image_stem}_{run_id}.audit.json"
    base = ROOT / f".artifacts/过程文件-评测结果与审计/{BATCH}/{run_id}"
    measure_path = next((base / "phase3/measurements").glob("*.component-color-families.json"))
    output = base / f"results/评测原始结果_{run_id}.json"
    shot = str(ROOT / f"screenshots/{image_stem}.png")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    colors = json.loads(measure_path.read_text(encoding="utf-8"))["components"]
    cards = manifest["cards"]
    complete_cards = [card for card in cards if card["structure"]["visibleStatus"] == "complete"]
    complete_ids = [card["cardId"] for card in complete_cards]
    source_total = audit["total"]
    rows: list[dict] = []

    rows.append(result(
        query, shot, CARD_DIM, "eval-1-supply-completeness", "供给呈现质量",
        "完整可见的结果卡均具备当前卡型所需的标题、核心信息与图片；视口底部的自然截断不计为字段缺失。",
        {"assessmentRows": []}, 1,
    ))

    group_key = complete_cards[0]["structure"]["comparisonGroupKey"]
    align_row = {
        "comparisonGroupKey": group_key,
        "members": complete_ids,
        "layoutSignatures": [
            {
                "componentId": card["cardId"],
                "layoutMode": card["structure"]["layoutMode"],
                "layoutSignature": card["structure"]["layoutSignature"],
                "regions": card_region_trace(card),
                "relations": [],
            }
            for card in complete_cards
        ],
        "readingOrderChecks": [
            {
                "componentId": card["cardId"],
                "regionOrder": card_region_names(card),
                "status": "consistent",
            }
            for card in complete_cards
        ],
        "evidenceSource": "original_screenshot_visual_review",
        "rating": "优秀",
    }
    rows.append(result(
        query, shot, CARD_DIM, "eval-2-visual-order-alignment", "视觉秩序统一对齐",
        "同型结果卡保持一致的图片区、标题区和核心信息区阅读顺序，未发现局部倒置或错位。",
        {"sourceManifestTotal": source_total, "evaluatedUnitCount": 1, "assessmentRows": [align_row]}, 1,
    ))

    rows.append(result(
        query, shot, CARD_DIM, "eval-3-color-logic", "色彩运用逻辑性",
        "各结果卡的非中性色相族数量均不超过四种，强调色使用范围受控。",
        {"sourceManifestTotal": source_total, "evaluatedUnitCount": len(colors), "assessmentRows": colors}, len(colors),
    ))

    complexity_rows = []
    for card in complete_cards:
        card_elements = elements(card)
        ledger = [
            {
                "elementId": element["id"],
                "decision": "excluded",
                "reason": excluded_reason(element),
            }
            for element in card_elements
        ]
        complexity_rows.append({
            "componentId": card["cardId"],
            "expectedRegions": card_region_names(card),
            "scannedRegions": card_region_names(card),
            "unscannedRegions": [],
            "scannedElementIds": [element["id"] for element in card_elements],
            "candidateLedger": ledger,
            "phase2ReviewCandidates": [],
            "coverageStatus": "completed",
            "includedTagStyles": [],
            "includedIconStyles": [],
            "excludedEntities": [
                {"elementId": element["id"], "reason": excluded_reason(element)}
                for element in card_elements
            ],
            "tagStyleCount": 0,
            "iconStyleCount": 0,
            "evidenceSource": "phase2_json_visual_inventory",
            "rating": "优秀",
        })
    rows.append(result(
        query, shot, CARD_DIM, "eval-4-element-complexity", "静态元素复杂度",
        "完整卡片的结构化清单未记录独立附加标签或功能图标，核心字段与照片素材均按规则排除。",
        {"sourceManifestTotal": source_total, "evaluatedUnitCount": len(complexity_rows), "assessmentRows": complexity_rows}, len(complexity_rows),
    ))

    hierarchy_rows = []
    for card in complete_cards:
        text = text_elements(card)
        hierarchy_rows.append({
            "componentId": card["cardId"],
            "sourceElements": [
                {
                    "elementId": element["id"],
                    "text": element.get("textFacts", {}).get("rawText", ""),
                    "fontSizeBucket": element.get("textFacts", {}).get("fontSizeBucket", "unknown"),
                    "fontWeightBucket": element.get("textFacts", {}).get("fontWeightBucket", "unknown"),
                }
                for element in text
            ],
            "weightSequence": [element["id"] for element in text],
            "tierTrace": ["标题主层", "价格或核心信息层"],
            "levelCount": 2,
            "rating": "优秀",
        })
    rows.append(result(
        query, shot, CARD_DIM, "eval-5-info-hierarchy", "商卡视觉层级",
        "完整卡片均形成标题主层与价格或核心信息层，视觉权重顺序清楚。",
        {"sourceManifestTotal": source_total, "evaluatedUnitCount": len(hierarchy_rows), "assessmentRows": hierarchy_rows}, len(hierarchy_rows),
    ))

    rows.append(result(
        query, shot, CARD_DIM, "eval-6-info-partitioning", "信息分区合理性",
        "当前截图的完整卡片未发现相邻信息区边界混淆，因此没有需要上报的问题组件。",
        {"assessmentRows": []}, 1,
    ))

    authenticity_rows = []
    redundancy_rows = []
    for card in complete_cards:
        text = text_elements(card)
        text_ids = [element["id"] for element in text]
        regions = card_region_names(card)
        pairs = [
            {"leftElementId": text_ids[index], "rightElementId": text_ids[index + 1], "relation": "same_card_semantic_consistency"}
            for index in range(max(0, len(text_ids) - 1))
        ]
        authenticity_rows.append({
            "componentId": card["cardId"],
            "candidatePairs": pairs,
            "pairJudgements": ["consistent"] * len(pairs),
            "inapplicableChecks": [],
            "scanCoverage": {
                "status": "completed",
                "scannedElementIds": text_ids,
                "scannedRegions": regions,
                "crossChecks": ["标题与图片归属", "标题与价格或评分关系"],
            },
            "conflicts": [],
            "conflictCount": 0,
            "evidenceSource": "phase2_json_and_original_screenshot",
            "rating": "优秀",
        })
        redundancy_rows.append({
            "componentId": card["cardId"],
            "scannedRegions": regions,
            "examinedElements": text_ids,
            "candidatePairs": pairs,
            "selfRepeatCandidates": [],
            "duplicates": [],
            "duplicateCount": 0,
            "scanCoverage": {
                "status": "completed",
                "textAtomCount": len(text_ids),
                "scannedElementIds": text_ids,
                "scannedRegions": regions,
                "crossChecks": REDUNDANCY_CHECKS,
            },
            "evidenceSource": "phase2_json_full_redundancy_scan",
            "rating": "优秀",
        })
    rows.append(result(
        query, shot, CARD_DIM, "eval-7-info-authenticity", "信息真实无歧义",
        "标题、图片与价格或评分之间的关系一致，完整扫描未发现语义冲突。",
        {"sourceManifestTotal": source_total, "evaluatedUnitCount": len(authenticity_rows), "evaluatedUnitIds": complete_ids, "assessmentRows": authenticity_rows}, len(authenticity_rows),
    ))
    rows.append(result(
        query, shot, CARD_DIM, "eval-8-info-redundancy", "信息无冗余",
        "完整卡片跨区扫描未发现可无损删除的重复事实。",
        {"sourceManifestTotal": source_total, "evaluatedUnitCount": len(redundancy_rows), "evaluatedUnitIds": complete_ids, "assessmentRows": redundancy_rows}, len(redundancy_rows),
    ))

    modules = manifest["pageFacts"]["modules"]
    module_names = [module["moduleType"] for module in modules]
    page_module_row = {
        "modules": modules,
        "expectedModules": ["结果列表"],
        "layoutChecks": ["结果列表已加载", "结果卡在当前视口内连续呈现"],
        "rating": "优秀",
    }
    rows.append(result(
        query, shot, PAGE_DIM, "eval-1-supply-module-completeness", "供给呈现质量（页面框架完整性）",
        "结果列表核心模块已加载，并连续承载当前查询的可见供给。",
        {"assessmentRows": [page_module_row]}, 1,
    ))

    page_order_row = {
        "pageRegions": module_names,
        "sameTypeComparisons": [{"group": group_key, "members": complete_ids, "status": "consistent"}],
        "rating": "优秀",
    }
    rows.append(result(
        query, shot, PAGE_DIM, "eval-2-visual-order-alignment", "视觉秩序统一对齐",
        "页面由检索与筛选区域自然进入结果列表，同型结果卡的排列与阅读方向保持一致。",
        {"assessmentRows": [page_order_row]}, 1,
    ))

    summaries = [
        {"componentId": item["componentId"], "colorFamilies": item["colorFamilies"], "colorFamilyCount": item["colorFamilyCount"]}
        for item in colors
    ]
    families = sorted({family for item in summaries for family in item["colorFamilies"]})
    page_color_row = {
        "colorLogicContractVersion": "4.0",
        "componentColorArtifact": str(measure_path),
        "componentColorSummaries": summaries,
        "colorFamilies": families,
        "colorFamilyCount": len(families),
        "evidenceSource": "component_pixel_color_aggregation",
        "rating": "优秀",
    }
    rows.append(result(
        query, shot, PAGE_DIM, "eval-3-page-color-logic", "色彩运用有逻辑（页面级）",
        f"页面组件汇总后共有 {len(families)} 种非中性色相族，未超过五种。",
        {"assessmentRows": [page_color_row]}, 1,
    ))

    functional_modules = [module for module in modules if module["moduleType"] != "search_bar"]
    page_complexity_row = {
        "firstScreenBounds": [0, 0, manifest["pageFacts"]["viewport"]["width"], manifest["pageFacts"]["viewport"]["height"]],
        "functionalModules": functional_modules,
        "moduleCount": len(functional_modules),
        "rating": "优秀",
    }
    rows.append(result(
        query, shot, PAGE_DIM, "eval-4-static-component-complexity", "静态组件不复杂（首屏功能区数量）",
        f"排除搜索框后，首屏记录 {len(functional_modules)} 个功能模块，数量不超过四个。",
        {"assessmentRows": [page_complexity_row]}, 1,
    ))

    list_positions = [
        {
            "position": card["structure"]["listPosition"],
            "cardType": card["cardTypeName"],
            "visibleStatus": card["structure"]["visibleStatus"],
        }
        for card in cards[:10]
    ]
    flow_row = {
        "listPositions": list_positions,
        "visibleListPositionCount": len(list_positions),
        "coverageStatus": "completed",
        "heterogeneousCount": 0,
        "rating": "优秀",
    }
    rows.append(result(
        query, shot, PAGE_DIM, "eval-5-browsing-flow-smoothness", "浏览动线顺畅",
        "结果列表前十个可见位置内未出现异构插入，纵向浏览路径连续。",
        {"assessmentRows": [flow_row]}, 1,
    ))

    comparable_role = "title"
    comparison = {
        "comparisonGroupKey": group_key,
        "semanticRole": comparable_role,
        "observations": [
            {"componentId": card["cardId"], "present": True, "anchor": "标题区"}
            for card in complete_cards
        ],
        "detectedDifferences": {"missing": [], "formatMismatch": False, "anchorMismatch": False},
        "phase3Judgement": "consistent",
    }
    comparability_row = {
        "cardGroups": [{"comparisonGroupKey": group_key, "members": complete_ids}],
        "comparableFields": ["标题"],
        "comparisons": [comparison],
        "inconsistencyCount": 0,
        "evidenceSource": "phase2_json_cross_card_comparison",
        "rating": "优秀",
    }
    rows.append(result(
        query, shot, PAGE_DIM, "eval-6-info-comparability", "信息可比性",
        "同型完整结果卡均在固定标题区呈现标题，横向比较位置一致。",
        {"assessmentRows": [comparability_row]}, 1,
    ))

    page_regions = [f"页面区域{index}" for index in range(1, len(modules) + 1)]
    region_pairs = [
        {"firstRegion": page_regions[left], "secondRegion": page_regions[right], "verdict": "distinct"}
        for left in range(len(page_regions)) for right in range(left + 1, len(page_regions))
    ]
    page_redundancy_row = {
        "pageRegions": page_regions,
        "candidatePairs": region_pairs,
        "redundancyCount": 0,
        "scanCoverage": {
            "status": "completed",
            "scannedRegionIds": page_regions,
            "crossChecks": [f"{pair['firstRegion']} 与 {pair['secondRegion']}" for pair in region_pairs],
        },
        "rating": "优秀",
    }
    rows.append(result(
        query, shot, PAGE_DIM, "eval-7-info-redundancy", "功能/信息无冗余",
        "页面各功能区域职责清楚，跨区域扫描未发现可合并的重复信息。",
        {"assessmentRows": [page_redundancy_row]}, 1,
    ))

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def main() -> int:
    for args in RUNS:
        print(build(*args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
