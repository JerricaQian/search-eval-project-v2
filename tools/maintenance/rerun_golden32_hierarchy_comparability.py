#!/usr/bin/env python3
"""Re-evaluate hierarchy and page comparability for the Golden32 corpus.

The run is append-only.  It inherits the other 17 validated full-19 rows,
re-runs the current hierarchy pixel tool, rebuilds hierarchy tiers with the
whole append area treated as one visual block, and derives page comparability
directly from each current Atomic v3 manifest.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


PROJECT = Path(__file__).resolve().parents[2]
ARTIFACT_ROOT = PROJECT / ".artifacts/过程文件-评测结果与审计"
RUNS_ROOT = PROJECT / "runs"
REPORT_ROOT = PROJECT / "reports"
LOADER = PROJECT / "scripts/phase2_bundle_loader.py"
VALIDATOR = PROJECT / "scripts/validate_eval_results.py"
EVIDENCE = PROJECT / "phase4-issue-evidence/scripts/generate_issue_evidence.py"
FINALIZER = PROJECT / "workflow/eval_cli.py"
HIERARCHY_TOOL = PROJECT / "phase3-evaluation/dimensions/card-component/skills/eval-5-info-hierarchy/scripts/extract_component_metrics.py"
BASE_SCRIPT = PROJECT / "tools/maintenance/rerun_golden32_semantics.py"
TARGET_SKILLS = {
    ("phase3-card_or_component-eval", "eval-5-info-hierarchy"),
    ("phase3-page_framework-eval", "eval-6-info-comparability"),
}
APPEND_REGIONS = {"text_append", "append_items"}
FORMAL_CARD_TYPES = {
    "merchant_product_card", "merchant_text_append", "merchant_graphic_append",
    "hotel", "performance_movie",
}
FIELD_LABELS = {
    "main_price": "主价格", "transaction_price": "到手价/优惠价", "unit_price": "单位价格",
    "rating": "评分", "distance": "距离", "duration": "履约时长", "sales": "销量",
    "average_spend": "人均价格", "delivery_fee": "配送费", "minimum_order": "起送价",
    "fulfillment": "履约信息",
}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot_import:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = load_module("golden32_semantic_base", BASE_SCRIPT)


def run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=PROJECT, check=True, text=True, capture_output=capture)


def text_of(element: dict[str, Any]) -> str:
    return str(element.get("text") or element.get("semanticDescription") or "")


def result_list_card_ids(atomic: dict[str, Any]) -> list[str]:
    return [
        card_id
        for module in atomic["modulesById"].values()
        if module.get("type") == "result_list"
        for card_id in module.get("cardIds", [])
    ]


def standard_card_number(card_id: str, ordered_ids: list[str]) -> int:
    return ordered_ids.index(card_id) + 1


def build_weight_units(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    regular: list[dict[str, Any]] = []
    append_members: list[dict[str, Any]] = []
    for block in blocks:
        if block["region"] in APPEND_REGIONS:
            append_members.append(block)
        else:
            regular.append({
                "members": [block],
                "representativeGlyphHeightPx": int(block["glyphHeightPx"]),
                "chromatic": bool(block["chromatic"]),
                "kind": "atomic",
            })
    if append_members:
        regular.append({
            "members": append_members,
            "representativeGlyphHeightPx": max(int(row["glyphHeightPx"]) for row in append_members),
            "chromatic": any(bool(row["chromatic"]) for row in append_members),
            "kind": "append_area",
        })
    return regular


def build_tiers(blocks: list[dict[str, Any]], threshold: int) -> list[dict[str, Any]]:
    units = sorted(build_weight_units(blocks), key=lambda row: row["representativeGlyphHeightPx"], reverse=True)
    height_clusters: list[list[dict[str, Any]]] = []
    for unit in units:
        if not height_clusters:
            height_clusters.append([unit])
            continue
        reference = int(height_clusters[-1][0]["representativeGlyphHeightPx"])
        current = int(unit["representativeGlyphHeightPx"])
        if reference - current >= threshold:
            height_clusters.append([unit])
        else:
            height_clusters[-1].append(unit)

    tiers: list[dict[str, Any]] = []
    for cluster in height_clusters:
        for chromatic in (True, False):
            members = [unit for unit in cluster if bool(unit["chromatic"]) is chromatic]
            if not members:
                continue
            atomic_members = [block for unit in members for block in unit["members"]]
            append_merged = any(unit["kind"] == "append_area" for unit in members)
            heights = [int(unit["representativeGlyphHeightPx"]) for unit in members]
            tiers.append({
                "tier": len(tiers) + 1,
                "members": [row["id"] for row in atomic_members],
                "representativeGlyphHeightPx": max(heights),
                "chromatic": chromatic,
                "basis": (
                    f"代表字形高度差低于{threshold}px且颜色强调一致，归入同一档；"
                    + ("下挂区域全部可读元素已先合并为一个下挂权重块，不比较其内部字形高差或颜色跳变。" if append_merged else "未命中下挂区域强制合并。")
                ),
                "appendAreaMerged": append_merged,
            })
    return tiers


def hierarchy_result(
    atomic: dict[str, Any], screenshot: Path, query: str, artifact_path: Path,
    title: str, run_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    run([
        sys.executable, str(HIERARCHY_TOOL), "--project-dir", str(PROJECT),
        "--scenes", query, "--suffix", run_id, "--skill", "eval-5-info-hierarchy",
        "--manifest-input", atomic["_manifestPath"], "--output", str(artifact_path),
    ])
    payload = base.read_json(artifact_path)
    cards = atomic["cardsById"]
    elements = atomic["elementsById"]
    ordered_result_ids = result_list_card_ids(atomic)
    complete_ids = [
        card_id for card_id in ordered_result_ids
        if cards[card_id].get("visibility") == "complete" and cards[card_id].get("cardType") in FORMAL_CARD_TYPES
    ]
    component_map = {str(row.get("cardId")): row for row in payload["components"]}
    rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    audit_cards: list[dict[str, Any]] = []
    for card_id in complete_ids:
        component = component_map.get(card_id)
        if not component:
            raise RuntimeError(f"hierarchy_component_missing:{query}:{card_id}")
        measurement = component["hierarchyMeasurement"]
        source_blocks = [
            block for block in measurement["weightBlocks"]
            if elements.get(str(block.get("id") or ""), {}).get("kind") in {"text", "tag"}
        ]
        invalid = [row["id"] for row in source_blocks if int(row.get("glyphHeightPx") or 0) <= 0]
        if invalid:
            raise RuntimeError(f"hierarchy_zero_glyph:{query}:{card_id}:{','.join(invalid)}")
        threshold = int(measurement["glyphHeightGapThresholdPx"])
        tiers = build_tiers(source_blocks, threshold)
        level_count = len(tiers)
        rating = "优秀" if 3 <= level_count <= 5 else "不达标"
        append_ids = {row["id"] for row in source_blocks if row["region"] in APPEND_REGIONS}
        source_elements = [{
            "elementId": row["id"], "text": row["text"], "region": row["region"],
            "glyphHeightPx": int(row["glyphHeightPx"]), "chromatic": bool(row["chromatic"]),
            "appendAreaMember": row["id"] in append_ids,
        } for row in source_blocks]
        row = {
            "componentId": card_id,
            "sourceElements": source_elements,
            "weightSequence": [element_id for tier in tiers for element_id in tier["members"]],
            "tierTrace": tiers,
            "levelCount": level_count,
            "calibrationProfile": measurement["calibrationProfile"],
            "glyphHeightGapThresholdPx": threshold,
            "rating": rating,
            "measurement": {
                "tool": str(HIERARCHY_TOOL), "artifactPath": str(artifact_path),
                "parameters": {
                    "skill": "eval-5-info-hierarchy", "mode": "hierarchy_only", "scene": query,
                    "appendAreaPolicy": "whole_append_area_one_visual_tier",
                },
            },
        }
        rows.append(row)
        audit_cards.append({
            "componentId": card_id, "levelCount": level_count, "rating": rating,
            "appendElementIds": sorted(append_ids), "tierTrace": tiers,
        })
        if rating == "不达标":
            anchor_id = source_blocks[0]["id"]
            element = elements[anchor_id]
            number = standard_card_number(card_id, complete_ids)
            description = f"商卡{number}经当前字形阈值校准并合并整个下挂区域后共有{level_count}个可感知层级，商卡视觉层级评级为不达标。"
            issues.append({
                "elementId": anchor_id, "coord": element["bounds"], "component": card_id,
                "elementType": "标签" if element.get("kind") == "tag" else "文本",
                "content": text_of(element), "dimension": "商卡视觉层级",
                "description": description, "rating": "不达标", "priority": "P1",
                "priorityReason": "该卡层级数量超出稳定扫读区间，影响核心结果卡的主次识别",
                "finding": {
                    "observableFact": f"商卡{number}实测得到{level_count}个可感知层级，整个下挂区域已合并为一个层级",
                    "ruleOrThreshold": "3至5层为优秀，2层及以下或6层及以上为不达标",
                    "verdictReason": f"当前{level_count}层不在3至5层区间，因此评级为不达标",
                    "userImpact": "用户难以快速建立标题、价格、辅助信息和下挂内容之间的稳定阅读顺序",
                },
                "recommendation": f"调整商卡{number}主信息与辅助信息的字号或强调色，使合并下挂区域后的可感知层级稳定在3至5层。",
            })
    ratings = [row["rating"] for row in rows]
    rating = "不达标" if "不达标" in ratings else "优秀"
    evidence = {
        "sourceManifestTotal": len(elements), "evaluatedUnitCount": len(rows),
        "evaluatedUnitIds": [row["componentId"] for row in rows],
        "excludedUnits": [{"id": card_id, "reason": "naturally_cropped_or_not_complete_formal_result_card"} for card_id in ordered_result_ids if card_id not in complete_ids],
        "assessmentRows": rows,
    }
    result = base.result_row(
        "phase3-card_or_component-eval", "eval-5-info-hierarchy", title,
        rating, 1 if rating == "优秀" else -1, screenshot, ratings, evidence, issues,
        "当前截图宽度校准后3至5层为优秀，2层及以下或6层及以上为不达标；整个下挂区域只计一个层级。",
        "完整结果卡已重新运行字形像素测量；颜色强调来自当前 JSON，所有下挂内部元素均保留但不再互相拆档。",
    )
    return result, {"measurementArtifact": str(artifact_path), "cards": audit_cards}


def chromatic(element: dict[str, Any]) -> bool:
    visual = element.get("visual") if isinstance(element.get("visual"), dict) else {}
    for field in ("textColor", "backgroundColor", "borderColor"):
        value = str(visual.get(field) or "").lstrip("#")
        if len(value) not in {6, 8}:
            continue
        try:
            red, green, blue = (int(value[index:index + 2], 16) for index in (0, 2, 4))
        except ValueError:
            continue
        highest = max(red, green, blue)
        if highest and (highest - min(red, green, blue)) / highest >= 0.12:
            return True
    return False


def semantic_fields(slot: str, text: str) -> list[str]:
    compact = re.sub(r"\s+", "", text)
    fields: list[str] = []
    if slot in {"rating"}:
        fields.append("rating")
    if slot in {"distance"} or re.search(r"\d(?:\.\d+)?(?:km|公里|米)\b", compact, re.I):
        fields.append("distance")
    if any(token in compact for token in ("分钟前有人", "前有人预订", "刚刚预订")):
        return list(dict.fromkeys(fields))
    if slot in {"delivery_time"} or "送达" in compact or re.search(r"(?:约)?\d+(?:-\d+)?(?:分钟|小时)$", compact):
        fields.append("duration")
    if slot == "sales" or any(token in compact for token in ("月售", "已售", "销量", "消费")):
        fields.append("sales")
    if slot in {"average_spend"} or "人均" in compact:
        fields.append("average_spend")
    if slot in {"price", "price_and_trade", "price_and_sales"}:
        if any(token in compact for token in ("到手价", "会员价", "神券价", "券后")):
            fields.append("transaction_price")
        if "每" in compact and ("￥" in compact or "¥" in compact):
            fields.append("unit_price")
        if "￥" in compact or "¥" in compact:
            fields.append("main_price")
    if slot == "fulfillment":
        if "配送费" in compact:
            fields.append("delivery_fee")
        elif "起送" in compact:
            fields.append("minimum_order")
        elif not fields:
            fields.append("fulfillment")
    return list(dict.fromkeys(fields))


def format_class(field: str, text: str) -> str:
    compact = re.sub(r"\s+", "", text)
    if field in {"main_price", "transaction_price", "unit_price", "average_spend"}:
        if field == "unit_price":
            return "per_unit"
        price_expression = compact
        if "起" in price_expression and "到手价" in price_expression:
            return "start_and_to_hand"
        if "到手价" in compact or "券后" in compact:
            return "to_hand"
        if "起" in price_expression:
            return "start"
        if re.search(r"\d\s*[-~至]\s*\d", price_expression):
            return "range"
        return "exact"
    if field == "rating":
        if "%" in compact or "好评率" in compact:
            return "positive_rate"
        if "分" in compact:
            return "five_point"
        return "rating_unspecified_scale"
    if field == "distance":
        if re.search(r"(?:km|公里)", compact, re.I):
            return "kilometres"
        if "米" in compact:
            return "metres"
        return "distance_unspecified_unit"
    if field == "duration":
        if "送达" in compact and re.search(r"\d{1,2}:\d{2}", compact):
            return "expected_arrival_clock"
        if "小时" in compact:
            return "hours"
        if "分钟" in compact:
            return "minutes"
        return "duration_unspecified_unit"
    if field == "sales":
        if "月售" in compact:
            return "monthly_sales"
        if "已售" in compact:
            return "cumulative_sales"
        return "sales_unspecified_period"
    return field


def field_records(atomic: dict[str, Any], card_id: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    card = atomic["cardsById"][card_id]
    for region_id in card["regionIds"]:
        region = atomic["regionsById"][region_id]
        region_name = str(region.get("name") or "")
        entity = "subordinate" if region_name in APPEND_REGIONS else "primary"
        sources = [(region.get("slots") or {}, None)]
        sources.extend(((item.get("slots") or {}), item.get("index")) for item in region.get("items") or [])
        for slots, item_index in sources:
            for slot, element_ids in slots.items():
                for element_id in element_ids:
                    element = atomic["elementsById"][element_id]
                    if element.get("kind") == "media":
                        continue
                    text = text_of(element)
                    for field in semantic_fields(str(slot), text):
                        records.append({
                            "cardId": card_id, "elementId": element_id, "text": text,
                            "semanticRole": field, "serviceObject": entity, "slot": str(slot),
                            "region": region_name, "itemIndex": item_index,
                            "formatClass": format_class(field, text),
                            "styleSemantic": {
                                "container": "tag" if element.get("kind") == "tag" else "plain_text",
                                "emphasis": "chromatic" if chromatic(element) else "neutral",
                            },
                        })
    return records


def material_differences(observations: list[dict[str, Any]]) -> tuple[dict[str, bool], list[str]]:
    formats = {row["formatClass"] for row in observations}
    regions = {row["region"] for row in observations}
    containers = {row["styleSemantic"]["container"] for row in observations}
    differences = {
        "format": len(formats) > 1,
        "positionAnchor": len(regions) > 1,
        "styleSemantic": len(containers) > 1,
    }
    impacts: list[str] = []
    if differences["format"]:
        impacts.append("需要换算或重新解释同一字段的口径/单位")
    if differences["positionAnchor"] and any(region in APPEND_REGIONS or region in {"promotion_and_guarantee", "tags"} for region in regions):
        impacts.append("同一字段在主决策区与附属条件区之间改变阅读锚点")
    if differences["styleSemantic"]:
        impacts.append("同一字段在标签容器与普通文本之间改变语义编码")
    return differences, impacts


def comparability_result(
    atomic: dict[str, Any], screenshot: Path, title: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    cards = atomic["cardsById"]
    ordered_ids = result_list_card_ids(atomic)
    complete = [
        card_id for card_id in ordered_ids
        if cards[card_id].get("visibility") == "complete" and cards[card_id].get("cardType") in FORMAL_CARD_TYPES
    ]
    grouped: dict[str, list[str]] = defaultdict(list)
    excluded_reasons: list[str] = []
    for card_id in ordered_ids:
        card = cards[card_id]
        if card_id not in complete:
            excluded_reasons.append(f"{card_id}:自然裁切、异构或非完整正式结果卡")
            continue
        grouped[f"{card['cardType']}|{card.get('variant') or 'default'}"].append(card_id)
    card_groups: list[dict[str, Any]] = []
    comparisons: list[dict[str, Any]] = []
    comparable_fields: set[str] = set()
    for group_key, members in grouped.items():
        if len(members) < 2:
            excluded_reasons.append(f"{group_key}:仅一张完整同类卡，无横向比较对象")
            continue
        card_groups.append({
            "comparisonGroupKey": group_key, "cardIds": members,
            "businessSemantic": cards[members[0]].get("variant") or "default",
            "cardType": cards[members[0]]["cardType"],
        })
        by_key: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
        for card_id in members:
            for record in field_records(atomic, card_id):
                key = f"{record['semanticRole']}|{record['serviceObject']}|{record['slot']}"
                by_key[key][card_id].append(record)
        for field_key, card_observations in sorted(by_key.items()):
            if len(card_observations) < 2:
                excluded_reasons.append(f"{group_key}|{field_key}:只在一张卡出现，不进入比较")
                continue
            observations: list[dict[str, Any]] = []
            for card_id, records in card_observations.items():
                if field_key.startswith("main_price|"):
                    records = records[:1]
                observations.append({
                    "cardId": card_id,
                    "elementIds": [row["elementId"] for row in records],
                    "texts": [row["text"] for row in records],
                    "formatClass": "+".join(sorted({row["formatClass"] for row in records})),
                    "region": "+".join(sorted({row["region"] for row in records})),
                    "styleSemantic": {
                        "container": "+".join(sorted({row["styleSemantic"]["container"] for row in records})),
                        "emphasis": "+".join(sorted({row["styleSemantic"]["emphasis"] for row in records})),
                    },
                    "serviceObject": records[0]["serviceObject"], "slot": records[0]["slot"],
                })
            differences, impacts = material_differences(observations)
            judgement = "inconsistent" if impacts else "not_material"
            semantic_role = field_key.split("|", 1)[0]
            comparable_fields.add(field_key)
            comparisons.append({
                "comparisonGroupKey": group_key, "fieldMatchKey": field_key,
                "semanticRole": semantic_role, "observations": observations,
                "detectedDifferences": differences,
                "materialImpactEvidence": impacts,
                "phase3Judgement": judgement,
                "exclusionReason": "" if impacts else "实际数值差异、轻微样式/位置变化或相同表达不构成实质比较障碍",
            })
    inconsistent = [row for row in comparisons if row["phase3Judgement"] == "inconsistent"]
    rating = "不达标" if inconsistent else "优秀"
    assessment = {
        "cardGroups": card_groups, "comparableFields": sorted(comparable_fields),
        "comparisons": comparisons, "excludedReasons": excluded_reasons,
        "inconsistencyCount": len(inconsistent),
        "evidenceSource": "phase2_json_cross_card_comparison", "rating": rating,
        "finding": {
            "observableFact": f"当前页面形成{len(card_groups)}个有效同类比较组，确认{len(inconsistent)}个实质不一致字段",
            "ruleOrThreshold": "同一字段只有在需要换算、破坏横向对齐、混淆服务对象/条件或改变扫读优先级时才计不一致",
            "verdictReason": f"本页确认的实质不一致字段数为{len(inconsistent)}，因此评级为{rating}",
            "userImpact": "表达一致时可直接横向比较；存在实质差异时需要额外换算或寻找同一字段",
        },
    }
    issues: list[dict[str, Any]] = []
    if inconsistent:
        fields = "、".join(sorted({FIELD_LABELS.get(row["semanticRole"], "决策字段") for row in inconsistent}))
        issues.append({
            "pageArea": "页面同类结果列表", "dimension": "信息可比性",
            "description": f"页面中同类商卡的{fields}存在{len(inconsistent)}项实质表达差异，信息可比性评级为不达标。",
            "rating": "不达标", "priority": "P1",
            "priorityReason": "同类卡的核心决策字段需要额外换算或重新寻找，影响整页横向选择",
            "finding": {
                "observableFact": f"同卡型、同业务语义比较组中确认{len(inconsistent)}个字段存在实质格式、位置或样式语义差异",
                "ruleOrThreshold": "任一同字段差异导致换算、失去横向对齐、混淆对象/条件或改变扫读优先级即不达标",
                "verdictReason": f"当前{len(inconsistent)}项差异命中实质影响门槛，因此评级为不达标",
                "userImpact": "用户无法沿相同位置和口径直接比较同类结果，需要额外解释后才能选择",
            },
            "recommendation": f"统一当前页面同类商卡的{fields}表达口径、信息锚点和语义编码；验收时同一字段无需换算且可在一致层级直接横向对齐。",
            "evidenceImage": str(screenshot),
        })
    result = base.result_row(
        "phase3-page_framework-eval", "eval-6-info-comparability", title,
        rating, 1 if rating == "优秀" else -1, screenshot, [rating],
        {"sourceManifestTotal": len(atomic["elementsById"]), "evaluatedUnitCount": 1,
         "evaluatedUnitIds": ["page"], "excludedUnits": [], "assessmentRows": [assessment]},
        issues,
        "只比较至少两张完整、同业务语义、同卡型、同实体层和同槽位商卡；任一实质表达障碍即不达标。",
        "已直接遍历当前 JSON 建组和匹配字段；数值差异、字段缺失、自然裁切、不同卡型及无实质影响的样式位置差异均已排除。",
    )
    return result, {"cardGroups": card_groups, "comparisons": comparisons, "inconsistent": inconsistent, "excludedReasons": excluded_reasons}


def html_report(query: str, run_id: str, results: list[dict[str, Any]], output: Path) -> None:
    rows = "".join(
        f"<tr><td>{row['skill']}</td><td>{row['units'][0]['rating']}</td><td>{row['units'][0]['weightedScore']}</td><td>{row['units'][0]['details']['summary']}</td></tr>"
        for row in results
    )
    issues = "".join(
        f"<article><h3>{issue['dimension']} · {issue['rating']}</h3><p>{issue['description']}</p><p><b>建议：</b>{issue['recommendation']}</p>"
        + (f"<img src='file://{issue['evidenceImage']}' alt='问题证据'>" if issue.get("evidenceImage") else "") + "</article>"
        for row in results for unit in row["units"] for issue in unit["details"]["issues"]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "<!doctype html><html lang='zh-CN'><meta charset='utf-8'>"
        f"<title>{query}层级与可比性复评</title><style>body{{font-family:-apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif;background:#f7f8fa;color:#18212f;margin:0}}main{{max-width:1120px;margin:auto;padding:32px}}header,section,article{{background:#fff;border-radius:12px;padding:22px;margin-bottom:18px;box-shadow:0 4px 18px #18212f0d}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:10px;border-bottom:1px solid #e8ebf0;vertical-align:top}}img{{width:420px;max-height:900px;object-fit:contain;object-position:top;border:1px solid #e8ebf0;border-radius:8px}}</style>"
        f"<main><header><h1>{query} · 层级与可比性复评</h1><p>本轮重新执行商卡视觉层级与页面信息可比性；其余17项继承已验收批次。runId={run_id}</p></header>"
        f"<section><h2>19项结果</h2><table><tr><th>评测项</th><th>评级</th><th>分值</th><th>摘要</th></tr>{rows}</table></section>"
        f"<section><h2>待优化项</h2>{issues or '<p>本轮未发现待优化项。</p>'}</section></main></html>",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Rerun Golden32 hierarchy and comparability")
    parser.add_argument("--source-batch", default="golden32-semantic-rereview-final3-v2.1-20260828")
    parser.add_argument("--batch-id", default="golden32-hierarchy-comparability-rereview-v2.1-20260831")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    target_root = ARTIFACT_ROOT / args.batch_id
    if target_root.exists():
        raise ValueError(f"refuse_to_overwrite_batch:{target_root}")
    source_index = base.read_json(ARTIFACT_ROOT / args.source_batch / "task-index.json")
    tasks = source_index["tasks"][: args.limit] if args.limit else source_index["tasks"]
    sys.path.insert(0, str(PROJECT / "scripts"))
    from phase2_bundle_loader import load_phase2_facts

    first_source = base.read_json(ARTIFACT_ROOT / args.source_batch / tasks[0]["query"] / "phase3/eval-results.json")
    titles = {(row["dimension"], row["skill"]): row["units"][0]["reason"].split("覆盖", 1)[0] for row in first_source}
    target_index = {"batchId": args.batch_id, "sourceBatch": args.source_batch, "count": len(tasks), "tasks": []}
    changes: list[dict[str, Any]] = []

    for task_row in tasks:
        sequence, query = int(task_row["sequence"]), task_row["query"]
        source_task = base.read_json(Path(task_row["taskPath"]))
        manifest = Path(source_task["workflowArgs"]["goldenManifest"])
        atomic = base.read_json(manifest)
        atomic["_manifestPath"] = str(manifest)
        screenshot = Path(atomic["source"]["screenshot"])
        if not screenshot.is_absolute():
            screenshot = PROJECT / screenshot
        if base.sha256(screenshot) != atomic["source"]["sha256"]:
            raise RuntimeError(f"source_hash_mismatch:{query}")
        facts = load_phase2_facts(manifest_path=manifest)
        active = base.active_inventory(facts)
        if len({row["id"] for row in active}) != len(atomic["elementsById"]):
            raise RuntimeError(f"atomic_projection_incomplete:{query}")

        run_id = f"{args.batch_id}-{sequence:02d}"
        artifact = target_root / query
        phase2, phase3 = artifact / "phase2", artifact / "phase3"
        loader_audit = phase2 / "phase2-fact-view.audit.json"
        run([sys.executable, str(LOADER), str(manifest), "--audit", str(loader_audit)])
        acceptance = {
            "valid": True, "protocol": "GOLDEN_ATOMIC_V3_ACCEPTANCE_V1", "runId": run_id, "query": query,
            "manifest": str(manifest), "manifestSha256": base.sha256(manifest), "sourceScreenshot": str(screenshot),
            "sourceScreenshotActualSha256": base.sha256(screenshot), "sourceScreenshotExpectedSha256": atomic["source"]["sha256"],
            "sourceScreenshotHashMatches": True, "publishedAtomicElementCount": len(atomic["elementsById"]),
            "phase3ActiveElementCount": len(active), "total": len(active), "activeElements": active, "errors": [],
            "loaderAudit": str(loader_audit),
        }
        acceptance_path = phase2 / "golden-acceptance-audit.json"
        base.write_json(acceptance_path, acceptance)

        measurement_path = phase3 / "measurements/eval-5-info-hierarchy.json"
        hierarchy, hierarchy_audit = hierarchy_result(
            atomic, screenshot, query, measurement_path,
            titles[("phase3-card_or_component-eval", "eval-5-info-hierarchy")], run_id,
        )
        comparability, comparability_audit = comparability_result(
            atomic, screenshot, titles[("phase3-page_framework-eval", "eval-6-info-comparability")],
        )
        rebuilt = {
            (hierarchy["dimension"], hierarchy["skill"]): hierarchy,
            (comparability["dimension"], comparability["skill"]): comparability,
        }
        source_results_path = ARTIFACT_ROOT / args.source_batch / query / "phase3/eval-results.json"
        source_results = base.read_json(source_results_path)
        old_target: dict[tuple[str, str], dict[str, Any]] = {}
        results: list[dict[str, Any]] = []
        for source_row in source_results:
            key = (source_row["dimension"], source_row["skill"])
            if key in TARGET_SKILLS:
                old_target[key] = source_row
                results.append(rebuilt[key])
            else:
                results.append(copy.deepcopy(source_row))
        if set(old_target) != set(TARGET_SKILLS):
            raise RuntimeError(f"target_skill_mismatch:{query}")

        result_path = phase3 / "eval-results.json"
        audit_path = phase3 / "eval-audit.json"
        review_path = phase3 / "phase2-review.json"
        decision_path = phase3 / "hierarchy-comparability-decisions.json"
        base.write_json(result_path, results)
        base.write_json(decision_path, {
            "valid": True, "query": query, "manifest": str(manifest),
            "hierarchy": hierarchy_audit, "comparability": comparability_audit,
        })
        run([sys.executable, str(VALIDATOR), "--manifest-audit", str(acceptance_path), "--results", str(result_path), "--audit", str(audit_path), "--phase2-review", str(review_path)])

        evidence_run = run([sys.executable, str(EVIDENCE), "--results", str(result_path), "--manifest", str(manifest)], capture=True)
        evidence_info = json.loads(evidence_run.stdout.strip().splitlines()[-1])
        run([sys.executable, str(VALIDATOR), "--manifest-audit", str(acceptance_path), "--results", str(result_path), "--audit", str(audit_path), "--phase2-review", str(review_path), "--require-evidence"])

        report = REPORT_ROOT / f"meituan_eval_report_{query}_{run_id}_full19.html"
        html_report(query, run_id, base.read_json(result_path), report)
        run_dir = RUNS_ROOT / run_id
        task_path, agent_result_path = run_dir / "task.json", run_dir / "agent-result.json"
        task = {
            "protocol": "MEITUAN_EVAL_TASK", "runId": run_id, "projectDir": str(PROJECT),
            "workflowArgs": {**source_task["workflowArgs"], "runId": run_id, "batchId": args.batch_id, "tag": run_id,
                             "rerunId": run_id, "artifactRunDir": str(artifact), "query": query,
                             "evaluationSelection": {"mode": "full_19"}},
            "contractFiles": [str(PROJECT / "workflow/contracts/phase234-query-pipeline.md"), str(PROJECT / "workflow/contracts/evaluation-result.schema.json")],
            "resultPath": str(agent_result_path),
            "completionCommand": [sys.executable, str(FINALIZER), "finalize-evaluate", "--task", str(task_path), "--result", str(agent_result_path)],
            "hostInstructions": ["Offline Golden Atomic v3 hierarchy/comparability re-evaluation; validate loader, current pixel artifact and all Stage A-D outputs."],
        }
        base.write_json(task_path, task, refuse_existing=True)
        agent_result = {
            "ok": True, "query": query,
            "stageA": {"elementListPaths": [str(manifest)], "elementAuditPaths": [str(acceptance_path)], "elementCount": len(active), "annotated": []},
            "stageB": {"evalResultFile": str(result_path), "evalAuditFile": str(audit_path), "evalCount": 19},
            "stageC": {"evidenceImages": evidence_info.get("referenced", []), "skipped": evidence_info.get("skipped", [])},
            "stageD": {"reportPath": str(report), "summary": []}, "blockedAt": "", "error": "",
        }
        base.write_json(agent_result_path, agent_result, refuse_existing=True)
        run(task["completionCommand"])

        query_changes = []
        for key in sorted(TARGET_SKILLS):
            before, after = old_target[key]["units"][0], rebuilt[key]["units"][0]
            query_changes.append({
                "dimension": key[0], "skill": key[1], "beforeRating": before["rating"], "afterRating": after["rating"],
                "beforeIssueCount": len(before["details"]["issues"]), "afterIssueCount": len(after["details"]["issues"]),
            })
        changes.append({"query": query, "runId": run_id, "changes": query_changes, "decisionAudit": str(decision_path), "report": str(report)})
        target_index["tasks"].append({"sequence": sequence, "query": query, "taskPath": str(task_path), "runId": run_id})
        print(json.dumps({"completed": len(changes), "query": query}, ensure_ascii=False), flush=True)

    base.write_json(target_root / "task-index.json", target_index)
    audit_path = target_root / "hierarchy-comparability-rereview-batch-audit.json"
    base.write_json(audit_path, {"valid": True, "batchId": args.batch_id, "sourceBatch": args.source_batch, "count": len(changes), "queries": changes})
    base.write_json(target_root / "batch-completion.json", {"batchId": args.batch_id, "count": len(changes), "completed": changes})
    print(json.dumps({"valid": True, "batchId": args.batch_id, "count": len(changes), "audit": str(audit_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
