#!/usr/bin/env python3
"""Validate the phase2 element manifest and emit a deterministic audit JSON."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# Contract tests load this file with an import spec, which does not add the
# repository's shared scripts directory to ``sys.path``.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
SHARED_SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SHARED_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_SCRIPTS_DIR))

from phase2_bundle_loader import load_phase2_facts


def load_card_type_registry() -> dict[str, str]:
    path = PROJECT_ROOT / "card-type-registry.v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {str(item["id"]): str(item["displayName"]) for item in payload["resultCardTypes"]}

TOP_LEVEL_KEYS = {"query", "screenshot", "cards"}
REQUIRED_PHASE3_FACT_KEYS = {"pageFacts", "pageFactInventory", "relations", "recognition"}
OPTIONAL_TOP_LEVEL_FACT_KEYS = REQUIRED_PHASE3_FACT_KEYS | {"annotatedImage"}
CARD_KEYS = {"cardId", "卡片类型", "coord", "regions"}
OPTIONAL_CARD_BUSINESS_KEYS = {"ownershipScope", "businessCode", "businessName", "businessConfidence"}
OPTIONAL_CARD_FACT_KEYS = {
    "cardTypeCode", "cardTypeName", "resultType", "classificationEvidence", "visualInventory",
    "structure", "factInventory",
}
OPTIONAL_CARD_GOVERNANCE_KEYS = OPTIONAL_CARD_BUSINESS_KEYS | OPTIONAL_CARD_FACT_KEYS
BUSINESS_CODES = {
    "dine_in", "food_delivery", "flash_delivery", "service_retail", "healthcare", "hotel_travel",
    "xiaoxiang", "maoyan", "bike", "youxuan", "errand", "finance", "power_bank",
    "ride_hailing", "xiaoxiang_supermarket", "dianping_overseas",
    "topup_game_ecommerce",
}
OWNERSHIP_SCOPES = {"business", "platform", "mixed", "unknown"}
CONFIDENCE_LEVELS = {"high", "medium", "low", "unknown"}
REGION_KEYS = {"name", "coord", "elements"}
OPTIONAL_REGION_KEYS = {"itemGroups"}
ELEMENT_REQUIRED_KEYS = {"id", "所属组件", "元素类型", "坐标", "isExcluded"}
OPTIONAL_ELEMENT_COMPAT_KEYS = {"内容简述", "excludeReason"}
OPTIONAL_ELEMENT_VISUAL_KEYS = {"visual", "render", "textFacts"}
VISUAL_ENTITY_KINDS = {"tag", "icon", "text", "image"}
VISUAL_STATUSES = {"confirmed", "uncertain"}
COLOR_ROLES = {"neutral", "red", "orange", "yellow", "green", "cyan", "blue", "purple", "multicolor", "unknown"}
TAG_SCAN_STATUSES = {"found", "not_found", "uncertain"}
REQUIRED_BASE_VISUAL_FIELDS = {"containerShape", "graphicAssistRole"}


def style_key_ok(value: Any) -> bool:
    """A complexity style key must preserve kind, colour, semantic, shape and graphic role."""
    return isinstance(value, str) and len([part for part in value.split("|") if part.strip()]) == 5


def valid_tag_scan_checklist(value: Any, known_ids: set[str]) -> bool:
    if not isinstance(value, list) or not value:
        return False
    for item in value:
        if not isinstance(item, dict):
            return False
        if item.get("status") not in TAG_SCAN_STATUSES:
            return False
        if not isinstance(item.get("candidate"), str) or not item["candidate"].strip():
            return False
        if not isinstance(item.get("checkedRegions"), list) or not item["checkedRegions"]:
            return False
        ids = item.get("elementIds", [])
        if not isinstance(ids, list) or any(not isinstance(element_id, str) or element_id not in known_ids for element_id in ids):
            return False
        if item["status"] == "found" and not ids:
            return False
        if item["status"] != "found" and ids:
            return False
    return True
CARD_TYPE_REGISTRY = load_card_type_registry()
CARD_TYPES = set(CARD_TYPE_REGISTRY.values()) | {"宏观组件", "酒店卡片（商家商品卡）"}
REGION_NAMES = {
    "头图区", "标题区", "副标题区", "基础信息区", "商家信息区", "评分与推荐理由",
    "位置信息", "标签区", "价格区", "商家区", "下挂商品区", "特殊下挂", "服务下挂",
    "下挂区", "文字下挂区", "AI推荐理由", "实体标题区", "实体信息区", "领域下挂区", "演出信息区", "套餐概要",
    "头图区（演出）", "商家信息区（电影）", "基础信息区（双列变体）",
    "媒体区", "主要信息区", "辅助信息区", "操作区",
}
ELEMENT_TYPES = {"文本", "图片", "标签"}
GENERIC_TEXTS = {
    "原文:商家名称", "原文:评分", "原文:评分 距离 人均", "原文:标签", "原文:基础信息",
    "原文:文字下挂促销", "原文:商品缩略图横滑", "原文:商品图", "原文:价格", "原文:内容未知",
}
PLACEHOLDER_MARKERS = ("待人工核", "待确认", "未知", "占位", "场景脚本验证", "标题区", "价格区", "标签区", "商家区")


def coord_ok(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 4 and all(isinstance(v, (int, float)) for v in value) and value[2] > 0 and value[3] > 0


def intersects(a: list[float], b: list[float]) -> bool:
    return max(a[0], b[0]) < min(a[0] + a[2], b[0] + b[2]) and max(a[1], b[1]) < min(a[1] + a[3], b[1] + b[3])


def intersection_area(a: list[float], b: list[float]) -> float:
    width = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    height = max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    return width * height


def is_within(inner: list[float], outer: list[float], tolerance: float = 2) -> bool:
    return (
        inner[0] >= outer[0] - tolerance
        and inner[1] >= outer[1] - tolerance
        and inner[0] + inner[2] <= outer[0] + outer[2] + tolerance
        and inner[1] + inner[3] <= outer[1] + outer[3] + tolerance
    )


def text_downhang_has_inline_price(group: dict[str, Any], elements: list[dict[str, Any]]) -> bool:
    """Return whether a reviewed text downhang item exposes its price inline."""
    text_ids = {str(item) for item in group.get("textElementIds", [])}
    return any(
        isinstance(element, dict)
        and str(element.get("id", "")) in text_ids
        and re.search(
            r"(?:[¥￥]\s*\d|\d+(?:\.\d+)?\s*元(?:起)?|\d+(?:\.\d+)?\s*折)",
            str(element.get("textFacts", {}).get("rawText", "")),
        )
        for element in elements
    )


def normalized_visible_text(value: str) -> str:
    """Normalize copied visible text only for conservative duplicate-supply candidates."""
    return re.sub(r"[\s\W_]+", "", value.removeprefix("原文:")).lower()


def element_visible_text(element: dict[str, Any]) -> str:
    """Read canonical text; retain legacy ``内容简述`` only as an input fallback."""
    facts = element.get("textFacts")
    if isinstance(facts, dict) and isinstance(facts.get("rawText"), str):
        return facts["rawText"].strip()
    content = element.get("内容简述")
    return content.removeprefix("原文:").strip() if isinstance(content, str) else ""


def active_audit_entry(element: dict[str, Any]) -> dict[str, Any]:
    """Publish the minimal semantic/visual trace Phase3 classification needs."""
    text_facts = element.get("textFacts") if isinstance(element.get("textFacts"), dict) else {}
    visual = element.get("visual") if isinstance(element.get("visual"), dict) else {}
    render = element.get("render") if isinstance(element.get("render"), dict) else {}
    return {
        "id": element["id"],
        "coord": element["坐标"],
        "component": element["所属组件"],
        "elementType": element["元素类型"],
        "content": f"原文:{element_visible_text(element)}",
        "semanticRole": str(text_facts.get("semanticRole") or visual.get("semanticRole") or ""),
        "promotionPrefix": str(text_facts.get("promotionPrefix") or ""),
        "entityKind": str(visual.get("entityKind") or ""),
        "colorRole": str(visual.get("colorRole") or text_facts.get("textColorRole") or "unknown"),
        "isPhoto": bool(render.get("isPhoto")),
        "countedInComplexity": bool(visual.get("countedInComplexity", False)),
    }


def semantic_tag_group_count(text: str) -> int:
    groups = (
        r"神券|立减|最高膨",
        r"全程保",
        r"公益商家",
        r"好评率|回头客|浏览",
        r"榜第\d+名",
        r"免费停车|免费水果|泰式手法|精油SPA",
    )
    return sum(bool(re.search(pattern, text)) for pattern in groups)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a phase2 element manifest")
    parser.add_argument("manifest", type=Path, nargs="?")
    parser.add_argument("--normalized-input", type=Path, help="Validate compact golden truth directly")
    parser.add_argument("--evidence-input", type=Path, help="Evidence sidecar paired with --normalized-input")
    parser.add_argument("--audit", type=Path, help="Write the audit JSON to this path")
    parser.add_argument("--recognition-audit", type=Path, help="Require and validate Phase2 key-field recognition audit")
    parser.add_argument("--require-current-image-calibration", action="store_true", help="Require exhaustive current-pixel review using the golden-structure calibration contract")
    parser.add_argument("--require-hierarchy-facts", action="store_true", help="Require complete visual facts for every complete result-list card before visual-hierarchy evaluation")
    parser.add_argument("--require-complexity-facts", action="store_true", help="Require complete visual inventories before static-element-complexity evaluation")
    parser.add_argument("--require-authenticity-relations", action="store_true", help="Require confirmed title-to-image and title-to-append relations before authenticity evaluation")
    parser.add_argument("--require-alignment-facts", action="store_true", help="Require deterministic comparison groups before visual-order-alignment evaluation")
    parser.add_argument("--require-alignment-anchors", action="store_true", help="Require layout anchors and a pairwise relation verdict for every comparable complete result-card group")
    args = parser.parse_args()

    if args.normalized_input:
        if args.manifest is not None:
            parser.error("manifest cannot be combined with --normalized-input")
        if not args.evidence_input:
            parser.error("--evidence-input is required with --normalized-input")
    elif args.manifest is None or args.evidence_input:
        parser.error("provide manifest or --normalized-input with --evidence-input")

    errors: list[str] = []
    warnings: list[str] = []
    try:
        data = load_phase2_facts(
            manifest_path=args.manifest,
            normalized_path=args.normalized_input,
            evidence_path=args.evidence_input,
        )
    except Exception as exc:
        result = {"valid": False, "total": 0, "elementIds": [], "errors": [f"json_parse:{exc}"], "warnings": [], "hierarchyFactAudit": [], "complexityFactAudit": [], "authenticityRelationAudit": [], "alignmentFactAudit": []}
        print(json.dumps(result, ensure_ascii=False))
        return 2

    if not isinstance(data, dict) or not TOP_LEVEL_KEYS.issubset(data) or not set(data).issubset(TOP_LEVEL_KEYS | OPTIONAL_TOP_LEVEL_FACT_KEYS):
        errors.append("top_level_keys_must_include_base_schema_and_only_allow_phase3_fact_extensions")
    elif not REQUIRED_PHASE3_FACT_KEYS.issubset(data):
        errors.append("phase3_fact_extensions_missing:pageFacts,pageFactInventory,relations,recognition")
    recognition = data.get("recognition", {}) if isinstance(data, dict) else {}
    required_recognition = {"contractVersion", "status", "phase3Ready", "wholePageGate", "blockingCardIds", "backends", "errors", "semanticHookFindings", "reprocessTargets", "reprocess"}
    if not isinstance(recognition, dict) or not required_recognition.issubset(recognition):
        errors.append("whole_page_recognition_schema_invalid")
    else:
        if recognition.get("status") not in {"confirmed", "blocked"} or not isinstance(recognition.get("phase3Ready"), bool) or recognition.get("wholePageGate") is not True:
            errors.append("whole_page_recognition_state_invalid")
        if recognition.get("phase3Ready") is not True or recognition.get("status") != "confirmed":
            errors.append("whole_page_recognition_blocked")
        if recognition.get("phase3Ready") is True and (recognition.get("blockingCardIds") or recognition.get("errors")):
            errors.append("phase3_ready_manifest_must_have_no_blockers")
    cards = data.get("cards") if isinstance(data, dict) else None
    if not isinstance(cards, list) or not cards:
        errors.append("cards_must_be_non_empty_array")
        cards = []

    element_ids: list[str] = []
    active: list[dict[str, Any]] = []
    card_ids: set[str] = set()
    card_title_evidence: dict[str, list[str]] = {}
    card_bounds: dict[str, list[float]] = {}
    hierarchy_fact_audit: list[dict[str, Any]] = []
    complexity_fact_audit: list[dict[str, Any]] = []
    authenticity_relation_audit: list[dict[str, Any]] = []
    alignment_fact_audit: list[dict[str, Any]] = []
    alignment_anchor_audit: list[dict[str, Any]] = []
    card_elements_by_id: dict[str, list[dict[str, Any]]] = {}
    card_metadata_by_id: dict[str, dict[str, Any]] = {}
    for ci, card in enumerate(cards, 1):
        prefix = f"cards[{ci}]"
        if not isinstance(card, dict) or not CARD_KEYS.issubset(card) or not set(card).issubset(CARD_KEYS | OPTIONAL_CARD_GOVERNANCE_KEYS):
            errors.append(f"{prefix}:card_keys_invalid")
            continue
        # 业务归属不是 Phase2 的必填职责。历史清单若携带业务字段，才校验其自洽；
        # 卡型、结构与视觉事实可独立存在，不能被误当成业务归属声明。
        business_keys = set(card) & OPTIONAL_CARD_BUSINESS_KEYS
        if business_keys:
            required_governance = {"ownershipScope", "businessCode", "businessName", "businessConfidence", "cardTypeCode", "cardTypeName", "classificationEvidence"}
            if not required_governance.issubset(card):
                errors.append(f"{prefix}:governance_fields_incomplete")
            scope = card.get("ownershipScope")
            if scope not in OWNERSHIP_SCOPES:
                errors.append(f"{prefix}:ownershipScope_invalid")
            if card.get("businessConfidence") not in CONFIDENCE_LEVELS:
                errors.append(f"{prefix}:businessConfidence_invalid")
            if not isinstance(card.get("classificationEvidence"), list) or not all(isinstance(item, str) and item.strip() for item in card.get("classificationEvidence", [])):
                errors.append(f"{prefix}:classificationEvidence_invalid")
            if scope == "business":
                if card.get("businessCode") not in BUSINESS_CODES:
                    errors.append(f"{prefix}:businessCode_invalid")
                if not isinstance(card.get("businessName"), str) or not card.get("businessName").strip():
                    errors.append(f"{prefix}:businessName_required")
                if not isinstance(card.get("cardTypeCode"), str) or not card.get("cardTypeCode").strip():
                    errors.append(f"{prefix}:cardTypeCode_required")
            elif card.get("businessCode") not in {"platform", "mixed", "unknown", ""}:
                errors.append(f"{prefix}:non_business_card_must_not_use_business_code")
        structure = card.get("structure")
        if not isinstance(structure, dict):
            errors.append(f"{prefix}:structure_required_for_phase3")
        else:
            required_structure = {"visibleStatus", "cardTypeCode", "layoutMode", "layoutSignature", "isResultListItem", "isHeterogeneous", "listPosition", "regions"}
            missing_structure = required_structure - structure.keys()
            if missing_structure:
                errors.append(f"{prefix}:structure_missing_fields:{','.join(sorted(missing_structure))}")
            elif not isinstance(structure.get("regions"), list):
                errors.append(f"{prefix}:structure_regions_must_be_array")
        fact_inventory = card.get("factInventory")
        if not isinstance(fact_inventory, dict) or not isinstance(fact_inventory.get("complete"), bool) or not isinstance(fact_inventory.get("scanned"), list) or not isinstance(fact_inventory.get("uncertainElementIds"), list):
            errors.append(f"{prefix}:factInventory_required_for_phase3")
        if (args.require_alignment_facts or args.require_alignment_anchors) and isinstance(structure, dict) and structure.get("isResultListItem") and structure.get("visibleStatus") == "complete":
            comparison_group_key = structure.get("comparisonGroupKey")
            alignment_complete = isinstance(comparison_group_key, str) and bool(comparison_group_key.strip()) and isinstance(fact_inventory, dict) and fact_inventory.get("complete") is True and not fact_inventory.get("uncertainElementIds")
            alignment_fact_audit.append({"cardId": card.get("cardId"), "eligible": True, "comparisonGroupKey": comparison_group_key, "complete": alignment_complete})
            if not isinstance(comparison_group_key, str) or not comparison_group_key.strip():
                errors.append(f"{prefix}:alignment_comparisonGroupKey_required")
            if not isinstance(fact_inventory, dict) or fact_inventory.get("complete") is not True or fact_inventory.get("uncertainElementIds"):
                errors.append(f"{prefix}:alignment_facts_incomplete")
        card_id = card.get("cardId")
        card_metadata_by_id[str(card_id)] = {"structure": structure, "factInventory": fact_inventory, "card": card}
        if not isinstance(card_id, str) or not card_id or card_id in card_ids:
            errors.append(f"{prefix}:cardId_missing_or_duplicate")
        card_ids.add(str(card_id))
        if card.get("卡片类型") not in CARD_TYPES:
            errors.append(f"{prefix}:card_type_not_allowed")
        code, name = card.get("cardTypeCode"), card.get("cardTypeName")
        if isinstance(code, str) and code in CARD_TYPE_REGISTRY and name != CARD_TYPE_REGISTRY[code]:
            errors.append(f"{prefix}:card_type_registry_name_mismatch")
        if not coord_ok(card.get("coord")):
            errors.append(f"{prefix}:card_coord_invalid")
        else:
            card_bounds[str(card_id)] = card["coord"]
        regions = card.get("regions")
        if not isinstance(regions, list) or not regions:
            errors.append(f"{prefix}:regions_must_be_non_empty_array")
            continue
        card_elements: list[dict[str, Any]] = []
        card_elements_by_id[str(card_id)] = card_elements
        for ri, region in enumerate(regions, 1):
            rprefix = f"{prefix}.regions[{ri}]"
            if not isinstance(region, dict) or not REGION_KEYS.issubset(region) or not set(region).issubset(REGION_KEYS | OPTIONAL_REGION_KEYS):
                errors.append(f"{rprefix}:region_keys_invalid")
                continue
            if region.get("name") not in REGION_NAMES:
                errors.append(f"{rprefix}:region_name_not_allowed")
            if not coord_ok(region.get("coord")):
                errors.append(f"{rprefix}:region_coord_invalid")
            elements = region.get("elements")
            if not isinstance(elements, list):
                errors.append(f"{rprefix}:elements_must_be_array")
                continue
            if region.get("name") == "标题区":
                titles = [
                    f"原文:{element_visible_text(element)}" for element in elements
                    if isinstance(element, dict)
                    and not element.get("isExcluded")
                    and normalized_visible_text(element_visible_text(element))
                ]
                if titles:
                    card_title_evidence.setdefault(str(card_id), []).extend(titles)
            for ei, element in enumerate(elements, 1):
                eprefix = f"{rprefix}.elements[{ei}]"
                if not isinstance(element, dict) or not ELEMENT_REQUIRED_KEYS.issubset(element) or not set(element).issubset(ELEMENT_REQUIRED_KEYS | OPTIONAL_ELEMENT_COMPAT_KEYS | OPTIONAL_ELEMENT_VISUAL_KEYS):
                    errors.append(f"{eprefix}:element_keys_invalid")
                    continue
                element_id = element.get("id")
                if not isinstance(element_id, str) or not element_id or element_id in element_ids:
                    errors.append(f"{eprefix}:element_id_missing_or_duplicate")
                else:
                    element_ids.append(element_id)
                if element.get("所属组件") != card_id:
                    errors.append(f"{eprefix}:component_must_equal_cardId")
                if element.get("元素类型") not in ELEMENT_TYPES:
                    errors.append(f"{eprefix}:element_type_not_allowed")
                if not coord_ok(element.get("坐标")):
                    errors.append(f"{eprefix}:element_coord_invalid")
                elif coord_ok(card.get("coord")) and not is_within(element["坐标"], card["coord"]):
                    errors.append(f"{eprefix}:element_coord_must_be_within_card")
                if not isinstance(element.get("isExcluded"), bool):
                    errors.append(f"{eprefix}:isExcluded_must_be_boolean")
                    continue
                raw_text = element_visible_text(element)
                content = f"原文:{raw_text}" if raw_text else ""
                reason = element.get("excludeReason")
                is_image = element.get("元素类型") == "图片" or element.get("render", {}).get("isPhoto") is True
                if not is_image and not raw_text:
                    errors.append(f"{eprefix}:text_element_requires_textFacts_rawText_or_legacy_content")
                if reason is not None and not isinstance(reason, str):
                    errors.append(f"{eprefix}:excludeReason_must_be_string")
                if element["isExcluded"] and (not isinstance(reason, str) or not reason.strip()):
                    errors.append(f"{eprefix}:excluded_element_requires_reason")
                if not element["isExcluded"]:
                    if reason not in {None, ""}:
                        errors.append(f"{eprefix}:active_element_excludeReason_must_be_empty")
                    if content in GENERIC_TEXTS or any(marker in content for marker in PLACEHOLDER_MARKERS):
                        errors.append(f"{eprefix}:content_is_placeholder_or_generic")
                    # 标签/徽标必须是最小独立视觉元素；分隔符通常意味着多个独立 chip 被错误合并。
                    # 连续文本允许包含普通标点，故仅对标签元素的明确 UI 分隔符阻断。
                    raw = content.removeprefix("原文:") if isinstance(content, str) else ""
                    compact_raw = re.sub(r"\s+", "", raw)
                    if element.get("元素类型") in {"文本", "标签"} and len(compact_raw) == 1:
                        errors.append(f"{eprefix}:one_character_semantic_element_forbidden")
                    if element.get("元素类型") == "标签" and any(separator in raw for separator in ("｜", "|", "；")):
                        errors.append(f"{eprefix}:tag_must_be_split_into_minimum_independent_elements")
                    if region.get("name") in {"基础信息区", "商家信息区", "标签区"}:
                        atomic_parts = [part.strip() for part in re.split(r"[｜|；]", raw) if part.strip()]
                        if len(atomic_parts) > 1:
                            errors.append(f"{eprefix}:semantic_fields_must_be_atomic_not_delimited_bundle")
                        # Text tokens such as “回头客榜第2名” or “神券最高膨至30”
                        # can form one visual chip. Phase3 must not re-split an
                        # atom by business words; Phase2 owns pixel atomicity.
                    active.append(element)
                    card_elements.append(element)
                render = element.get("render")
                if not isinstance(render, dict) or not {"visibleStatus", "renderState", "isPhoto", "isSystemUi"}.issubset(render):
                    errors.append(f"{eprefix}:render_required_for_phase3")
                elif not isinstance(render.get("isPhoto"), bool) or not isinstance(render.get("isSystemUi"), bool):
                    errors.append(f"{eprefix}:render_schema_invalid")
                if element.get("元素类型") == "文本":
                    text_facts = element.get("textFacts")
                    required_text_facts = {"rawText", "textStatus", "semanticRole", "emphasisLevel", "fontSizeBucket", "fontWeightBucket", "textColorRole"}
                    if not isinstance(text_facts, dict) or not required_text_facts.issubset(text_facts):
                        errors.append(f"{eprefix}:textFacts_required_for_text_element")
                visual = element.get("visual")
                if visual is not None:
                    required_visual = {"entityKind", "visualStatus", "colorRole", "graphicType", "styleKey"}
                    if not isinstance(visual, dict) or not required_visual.issubset(visual):
                        errors.append(f"{eprefix}:visual_schema_invalid")
                    else:
                        if visual.get("entityKind") not in VISUAL_ENTITY_KINDS:
                            errors.append(f"{eprefix}:visual_entityKind_invalid")
                        if visual.get("visualStatus") not in VISUAL_STATUSES:
                            errors.append(f"{eprefix}:visual_status_invalid")
                        if visual.get("colorRole") not in COLOR_ROLES:
                            errors.append(f"{eprefix}:visual_colorRole_invalid")
                        if visual.get("visualStatus") == "confirmed" and visual.get("entityKind") in {"tag", "icon"}:
                            if visual.get("styleKey") is not None and not style_key_ok(visual.get("styleKey")):
                                errors.append(f"{eprefix}:visual_styleKey_if_present_must_have_five_segments")
                            missing_visual_fields = [key for key in REQUIRED_BASE_VISUAL_FIELDS if key not in visual]
                            if missing_visual_fields:
                                errors.append(f"{eprefix}:visual_base_fields_missing:{','.join(sorted(missing_visual_fields))}")
                            elif (
                                not isinstance(visual.get("containerShape"), str) or not visual["containerShape"].strip()
                                or not isinstance(visual.get("graphicAssistRole"), str) or not visual["graphicAssistRole"].strip()
                            ):
                                errors.append(f"{eprefix}:visual_base_fields_invalid")
                        elif visual.get("dedupWithElementIds") is not None and any(not isinstance(item, str) or not item.strip() for item in visual.get("dedupWithElementIds", [])):
                            errors.append(f"{eprefix}:visual_dedup_reference_invalid")

            if region.get("name") in {"下挂商品区", "文字下挂区", "下挂区", "服务下挂"} and elements:
                groups = region.get("itemGroups")
                if not isinstance(groups, list) or not groups:
                    errors.append(f"{rprefix}:appended_elements_must_be_owned_by_item_groups")
                else:
                    region_ids = [str(item.get("id")) for item in elements if isinstance(item, dict)]
                    grouped_ids: list[str] = []
                    for gi, group in enumerate(groups, 1):
                        gprefix = f"{rprefix}.itemGroups[{gi}]"
                        required = {"itemIndex", "coord", "elementIds", "imageElementIds", "textElementIds", "priceElementIds", "visibleStatus"}
                        if not isinstance(group, dict) or set(group) != required:
                            errors.append(f"{gprefix}:item_group_schema_invalid")
                            continue
                        if group.get("itemIndex") != gi or not coord_ok(group.get("coord")) or group.get("visibleStatus") not in {"confirmed", "naturally_cropped", "uncertain"}:
                            errors.append(f"{gprefix}:item_group_identity_invalid")
                        ids = group.get("elementIds")
                        role_lists = [group.get(key) for key in ("imageElementIds", "textElementIds", "priceElementIds")]
                        if not isinstance(ids, list) or not all(isinstance(values, list) for values in role_lists):
                            errors.append(f"{gprefix}:item_group_element_lists_invalid")
                            continue
                        if set(ids) != set().union(*(set(values) for values in role_lists)) or any(item not in region_ids for item in ids):
                            errors.append(f"{gprefix}:item_group_roles_must_partition_owned_elements")
                        # A text/service downhang can publish its price inline
                        # in the one visible service string (for example
                        # “小包2小时38元起”). That is direct price evidence,
                        # not a missing-price defect. Graphic product rows
                        # still require a separate price atom.
                        inline_text_price = (
                            card.get("卡片类型") == "商家卡片-文字下挂"
                            and text_downhang_has_inline_price(group, elements)
                        )
                        if group.get("visibleStatus") == "confirmed" and (not group.get("textElementIds") or (not group.get("priceElementIds") and not inline_text_price)):
                            errors.append(f"{gprefix}:appended_item_requires_text_and_price")
                        if group.get("visibleStatus") == "naturally_cropped" and not group.get("elementIds"):
                            errors.append(f"{gprefix}:naturally_cropped_item_requires_visible_atom")
                        if group.get("visibleStatus") == "uncertain" and not group.get("elementIds"):
                            errors.append(f"{gprefix}:cropped_appended_item_requires_visible_element")
                        if card.get("卡片类型") == "商家卡片-图文下挂" and not group.get("imageElementIds"):
                            errors.append(f"{gprefix}:graphic_appended_item_requires_image")
                        grouped_ids.extend(str(item) for item in ids)
                    if sorted(grouped_ids) != sorted(region_ids) or len(grouped_ids) != len(set(grouped_ids)):
                        errors.append(f"{rprefix}:every_appended_element_must_belong_to_exactly_one_item")

        if isinstance(structure, dict) and structure.get("isResultListItem") and structure.get("visibleStatus") == "complete" and card.get("卡片类型") not in {"特殊广告卡", "异构卡", "宏观组件"}:
            title_elements = [
                item for item in card_elements
                if isinstance(item.get("textFacts"), dict)
                and item["textFacts"].get("semanticRole") == "title"
            ]
            if not title_elements:
                errors.append(f"{prefix}:complete_known_card_requires_title_element")

        if args.require_hierarchy_facts and isinstance(structure, dict) and structure.get("isResultListItem") and structure.get("visibleStatus") == "complete":
            missing: list[str] = []
            uncertain: list[str] = []
            if not isinstance(fact_inventory, dict) or fact_inventory.get("complete") is not True:
                missing.append("factInventory.complete")
            if isinstance(fact_inventory, dict) and fact_inventory.get("uncertainElementIds"):
                uncertain.extend(str(item) for item in fact_inventory["uncertainElementIds"])
            for element in card_elements:
                element_id = str(element.get("id", ""))
                render = element.get("render")
                if not isinstance(render, dict) or render.get("visibleStatus") != "confirmed" or render.get("renderState") in {"uncertain", "garbled", "abnormal_clipped", "load_failed", "blank", "placeholder"}:
                    missing.append(f"{element_id}.render")
                if element.get("元素类型") == "文本":
                    facts = element.get("textFacts")
                    required_values = ("semanticRole", "emphasisLevel", "fontSizeBucket", "fontWeightBucket", "textColorRole")
                    if not isinstance(facts, dict) or any(not facts.get(key) or facts.get(key) == "unknown" for key in required_values):
                        missing.append(f"{element_id}.textFacts.visual_spec")
                    elif facts.get("textStatus") == "uncertain":
                        uncertain.append(element_id)
                if element.get("元素类型") == "标签":
                    visual = element.get("visual")
                    if not isinstance(visual, dict) or visual.get("visualStatus") != "confirmed" or visual.get("colorRole") == "unknown":
                        missing.append(f"{element_id}.visual")
            hierarchy_fact_audit.append({"cardId": card_id, "eligible": True, "complete": not missing and not uncertain, "missing": missing, "uncertainElementIds": uncertain})
            if missing or uncertain:
                errors.append(f"{prefix}:hierarchy_facts_incomplete:missing={','.join(missing) or '-'}:uncertain={','.join(uncertain) or '-'}")
        inventory = card.get("visualInventory")
        if args.require_complexity_facts and isinstance(structure, dict) and structure.get("visibleStatus") == "complete":
            missing: list[str] = []
            uncertain: list[str] = []
            if not isinstance(fact_inventory, dict) or fact_inventory.get("complete") is not True:
                missing.append("factInventory.complete")
            elif fact_inventory.get("uncertainElementIds"):
                uncertain.extend(str(item) for item in fact_inventory["uncertainElementIds"])
            if not isinstance(inventory, dict) or inventory.get("complete") is not True or not isinstance(inventory.get("regions"), dict):
                missing.append("visualInventory.complete")
            else:
                inventory_regions = inventory["regions"]
                known_ids = {item.get("id") for region in regions if isinstance(region, dict) for item in (region.get("elements") or []) if isinstance(item, dict)}
                if not valid_tag_scan_checklist(inventory.get("tagScanChecklist"), known_ids):
                    missing.append("visualInventory.tagScanChecklist")
                visible_region_names = {region.get("name") for region in regions if isinstance(region, dict) and region.get("name") in REGION_NAMES}
                for region_name in visible_region_names:
                    if region_name not in inventory_regions or not isinstance(inventory_regions[region_name], list):
                        missing.append(f"visualInventory.regions.{region_name}")
                inventory_ids = {entry.get("elementId") for entries in inventory_regions.values() if isinstance(entries, list) for entry in entries if isinstance(entry, dict)}
                for element in card_elements:
                    visual = element.get("visual")
                    element_id = str(element.get("id", ""))
                    if isinstance(visual, dict) and visual.get("entityKind") in {"tag", "icon"}:
                        if visual.get("visualStatus") != "confirmed":
                            uncertain.append(element_id)
                        elif not isinstance(visual.get("styleKey"), str) or not visual.get("styleKey").strip():
                            missing.append(f"{element_id}.visual.styleKey")
                        elif element_id not in inventory_ids:
                            missing.append(f"{element_id}.visualInventory")
            complexity_fact_audit.append({"cardId": card_id, "eligible": True, "complete": not missing and not uncertain, "missing": missing, "uncertainElementIds": uncertain})
            if missing or uncertain:
                errors.append(f"{prefix}:complexity_facts_incomplete:missing={','.join(missing) or '-'}:uncertain={','.join(uncertain) or '-'}")
        if inventory is not None:
            if not isinstance(inventory, dict) or not isinstance(inventory.get("complete"), bool) or not isinstance(inventory.get("regions"), dict):
                errors.append(f"{prefix}:visualInventory_schema_invalid")
            else:
                known_ids = {item.get("id") for region in regions if isinstance(region, dict) for item in (region.get("elements") or []) if isinstance(item, dict)}
                if not valid_tag_scan_checklist(inventory.get("tagScanChecklist"), known_ids):
                    errors.append(f"{prefix}:visualInventory_tagScanChecklist_invalid")
                for name, entries in inventory["regions"].items():
                    if name not in REGION_NAMES or not isinstance(entries, list):
                        errors.append(f"{prefix}:visualInventory_region_invalid:{name}")
                        continue
                    for entry in entries:
                        if not isinstance(entry, dict) or entry.get("elementId") not in known_ids:
                            errors.append(f"{prefix}:visualInventory_element_invalid:{name}")
                        elif not isinstance(entry.get("styleKey"), str) or not isinstance(entry.get("countedInComplexity"), bool):
                            errors.append(f"{prefix}:visualInventory_entry_missing_style_or_count_decision:{name}")

    if isinstance(data, dict) and OPTIONAL_TOP_LEVEL_FACT_KEYS.issubset(data):
        page_facts = data.get("pageFacts")
        page_inventory = data.get("pageFactInventory")
        relations = data.get("relations")
        if not isinstance(page_facts, dict) or not isinstance(page_facts.get("modules"), list) or not page_facts.get("modules"):
            errors.append("pageFacts_modules_required_for_phase3")
        if not isinstance(page_inventory, dict) or not isinstance(page_inventory.get("complete"), bool) or not isinstance(page_inventory.get("scanned"), list):
            errors.append("pageFactInventory_required_for_phase3")
        if not isinstance(relations, list):
            errors.append("relations_must_be_array")
        else:
            known_element_ids = set(element_ids)
            allowed_relation_types = {"same_card", "same_field_across_cards", "title_to_image", "title_to_append", "overlapping_annotation", "same_supply_candidate"}
            for index, relation in enumerate(relations, start=1):
                required_relation = {"relationType", "from", "to", "status"}
                if not isinstance(relation, dict) or not required_relation.issubset(relation):
                    errors.append(f"relations_{index}_schema_invalid")
                elif relation.get("from") not in known_element_ids or relation.get("to") not in known_element_ids:
                    errors.append(f"relations_{index}_element_reference_invalid")
                elif relation.get("relationType") not in allowed_relation_types or relation.get("status") not in {"confirmed", "uncertain"}:
                    errors.append(f"relations_{index}_enum_invalid")

            if args.require_authenticity_relations:
                relation_index: dict[tuple[str, str], list[dict[str, Any]]] = {}
                for relation in relations:
                    if isinstance(relation, dict):
                        relation_index.setdefault((str(relation.get("from")), str(relation.get("to"))), []).append(relation)
                        relation_index.setdefault((str(relation.get("to")), str(relation.get("from"))), []).append(relation)
                for card_id, elements in card_elements_by_id.items():
                    metadata = card_metadata_by_id.get(card_id, {})
                    structure = metadata.get("structure")
                    fact_inventory = metadata.get("factInventory")
                    if not isinstance(structure, dict) or not structure.get("isResultListItem") or structure.get("visibleStatus") != "complete":
                        continue
                    missing: list[str] = []
                    uncertain: list[str] = []
                    if not isinstance(fact_inventory, dict) or fact_inventory.get("complete") is not True:
                        missing.append("factInventory.complete")
                    elif fact_inventory.get("uncertainElementIds"):
                        uncertain.extend(str(item) for item in fact_inventory["uncertainElementIds"])
                    titles = [element for element in elements if isinstance(element.get("textFacts"), dict) and element["textFacts"].get("semanticRole") == "title"]
                    images = [element for element in elements if element.get("元素类型") == "图片"]
                    append_regions = {"下挂商品区", "文字下挂区", "下挂区", "服务下挂", "特殊下挂", "领域下挂区"}
                    append_elements = [
                        element
                        for region in metadata.get("regions", [])
                        if isinstance(region, dict) and region.get("name") in append_regions
                        for element in region.get("elements", [])
                        if isinstance(element, dict)
                    ]
                    for title in titles:
                        title_id = str(title.get("id"))
                        for relation_type, targets in (("title_to_image", images), ("title_to_append", append_elements)):
                            if not targets:
                                continue
                            matches = [relation for target in targets for relation in relation_index.get((title_id, str(target.get("id"))), []) if relation.get("relationType") == relation_type]
                            if not matches:
                                missing.append(f"{title_id}.{relation_type}")
                            elif not any(relation.get("status") == "confirmed" for relation in matches):
                                uncertain.append(f"{title_id}.{relation_type}")
                    authenticity_relation_audit.append({"cardId": card_id, "eligible": True, "complete": not missing and not uncertain, "missing": missing, "uncertainElementIds": uncertain})
                    if missing or uncertain:
                        errors.append(f"cards[{card_id}]:authenticity_relations_incomplete:missing={','.join(missing) or '-'}:uncertain={','.join(uncertain) or '-'}")

    # Result cards are separate rendered units. Significant overlap indicates reused or
    # invented coordinates and must be resolved before any Phase3 calculation.
    for left_id, left_coord in card_bounds.items():
        for right_id, right_coord in card_bounds.items():
            if left_id >= right_id:
                continue
            overlap = intersection_area(left_coord, right_coord)
            smaller_area = min(left_coord[2] * left_coord[3], right_coord[2] * right_coord[3])
            if smaller_area and overlap / smaller_area > 0.05:
                errors.append(f"card_bounds_overlap_exceeds_5_percent:{left_id}:{right_id}")

    if args.require_alignment_anchors:
        comparable_groups: dict[str, list[str]] = {}
        for card_id, metadata in card_metadata_by_id.items():
            structure = metadata.get("structure")
            fact_inventory = metadata.get("factInventory")
            if not isinstance(structure, dict) or not isinstance(fact_inventory, dict):
                continue
            if not structure.get("isResultListItem") or structure.get("visibleStatus") != "complete" or fact_inventory.get("complete") is not True:
                continue
            key = structure.get("comparisonGroupKey")
            if isinstance(key, str) and key.strip():
                comparable_groups.setdefault(key, []).append(card_id)
        for group_key, member_ids in comparable_groups.items():
            if len(member_ids) < 2:
                continue
            missing_members: list[str] = []
            for card_id in member_ids:
                card = card_metadata_by_id[card_id]["card"]
                structure = card_metadata_by_id[card_id]["structure"]
                anchors = structure.get("layoutAnchors") if isinstance(structure, dict) else None
                required_anchor_keys = {"image", "title", "primaryInfo"}
                if not isinstance(anchors, dict) or not required_anchor_keys.issubset(anchors) or not all(coord_ok(anchors.get(key)) for key in required_anchor_keys):
                    missing_members.append(card_id)
                    continue
                card_elements = card_elements_by_id.get(card_id, [])
                anchor_candidates = {
                    "image": [element for element in card_elements if isinstance(element.get("render"), dict) and element["render"].get("isPhoto")],
                    "title": [element for element in card_elements if isinstance(element.get("textFacts"), dict) and element["textFacts"].get("semanticRole") == "title"],
                    "primaryInfo": [element for element in card_elements if isinstance(element.get("textFacts"), dict) and element["textFacts"].get("semanticRole") in {"fulfillment", "rating", "sales", "price", "location", "subtitle"}],
                }
                if any(not any(element.get("坐标") == anchors[anchor_name] for element in candidates) for anchor_name, candidates in anchor_candidates.items()):
                    missing_members.append(card_id)
                    continue
                if not isinstance(structure.get("layoutAnchorRelation"), str) or not structure["layoutAnchorRelation"].strip():
                    missing_members.append(card_id)
            alignment_anchor_audit.append({"comparisonGroupKey": group_key, "members": member_ids, "complete": not missing_members, "missingMembers": missing_members})
            if missing_members:
                errors.append(f"alignment_anchor_facts_missing:{group_key}:{','.join(missing_members)}")

    if args.require_current_image_calibration and not args.recognition_audit:
        errors.append("current_image_calibration_requires_recognition_audit")

    if args.recognition_audit:
        try:
            recognition_audit = json.loads(args.recognition_audit.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"recognition_audit_unreadable:{exc}")
        else:
            required_audit_keys = {"query", "screenshot", "manifest", "fullImageReadCount", "localReviewReadCount", "totalImageReadCount", "fields"}
            if not isinstance(recognition_audit, dict) or not required_audit_keys.issubset(recognition_audit):
                errors.append("recognition_audit_schema_invalid")
            else:
                if recognition_audit.get("manifest") != str(args.manifest):
                    errors.append("recognition_audit_manifest_mismatch")
                full_reads = recognition_audit.get("fullImageReadCount")
                local_reads = recognition_audit.get("localReviewReadCount")
                total_reads = recognition_audit.get("totalImageReadCount")
                if not all(isinstance(value, int) and value >= 0 for value in (full_reads, local_reads, total_reads)):
                    errors.append("recognition_audit_read_count_invalid")
                elif full_reads != 1 or total_reads != full_reads + local_reads or total_reads > 12:
                    errors.append("recognition_audit_read_limit_invalid")
                fields = recognition_audit.get("fields")
                if not isinstance(fields, list) or not fields:
                    errors.append("recognition_audit_fields_missing")
                else:
                    required_field_keys = {"cardId", "elementId", "field", "visibleText", "status", "source", "reason"}
                    for index, field in enumerate(fields, 1):
                        if not isinstance(field, dict) or not required_field_keys.issubset(field):
                            errors.append(f"recognition_audit_field_{index}_schema_invalid")
                            continue
                        if field.get("status") not in {"confirmed", "uncertain"}:
                            errors.append(f"recognition_audit_field_{index}_status_invalid")
                        if field.get("source") not in {"full_image", "local_review"}:
                            errors.append(f"recognition_audit_field_{index}_source_invalid")
                        if not all(isinstance(field.get(key), str) for key in required_field_keys):
                            errors.append(f"recognition_audit_field_{index}_value_invalid")

                if args.require_current_image_calibration:
                    required_calibration_keys = {
                        "contractVersion", "strategy", "reviewedAgainstCurrentPixels",
                        "goldenValueInjection", "localReviewPaths",
                    }
                    if not required_calibration_keys.issubset(recognition_audit):
                        errors.append("current_image_calibration_schema_invalid")
                    else:
                        if recognition_audit.get("contractVersion") != "phase2.current-image-calibration.v1":
                            errors.append("current_image_calibration_contract_invalid")
                        if recognition_audit.get("strategy") != "golden_structure_current_pixels":
                            errors.append("current_image_calibration_strategy_invalid")
                        if recognition_audit.get("reviewedAgainstCurrentPixels") is not True:
                            errors.append("current_image_calibration_not_reviewed")
                        if recognition_audit.get("goldenValueInjection") is not False:
                            errors.append("current_image_calibration_golden_value_injection_forbidden")
                        if recognition_audit.get("query") != data.get("query"):
                            errors.append("current_image_calibration_query_mismatch")
                        if recognition_audit.get("screenshot") != data.get("screenshot"):
                            errors.append("current_image_calibration_screenshot_mismatch")

                        local_paths = recognition_audit.get("localReviewPaths")
                        if not isinstance(local_paths, list) or any(not isinstance(path, str) or not path for path in local_paths):
                            errors.append("current_image_calibration_local_paths_invalid")
                            local_paths = []
                        elif len(local_paths) != recognition_audit.get("localReviewReadCount") or len(set(local_paths)) != len(local_paths):
                            errors.append("current_image_calibration_local_path_count_mismatch")

                        expected: dict[str, tuple[str, dict[str, Any]]] = {}
                        for card in cards:
                            if not isinstance(card, dict):
                                continue
                            card_id = str(card.get("cardId", ""))
                            for region in card.get("regions", []):
                                if not isinstance(region, dict):
                                    continue
                                for element in region.get("elements", []):
                                    if isinstance(element, dict) and not element.get("isExcluded"):
                                        expected[str(element.get("id", ""))] = (card_id, element)

                        seen: set[str] = set()
                        if isinstance(fields, list):
                            for index, field in enumerate(fields, 1):
                                if not isinstance(field, dict):
                                    continue
                                element_id = field.get("elementId")
                                if element_id in seen:
                                    errors.append(f"current_image_calibration_duplicate_element:{element_id}")
                                    continue
                                seen.add(element_id)
                                if element_id not in expected:
                                    errors.append(f"current_image_calibration_unknown_element:{element_id}")
                                    continue
                                expected_card_id, element = expected[element_id]
                                render = element.get("render")
                                is_photo = element.get("元素类型") == "图片" or (isinstance(render, dict) and render.get("isPhoto") is True)
                                expected_text = "" if is_photo else element_visible_text(element)
                                if field.get("cardId") != expected_card_id:
                                    errors.append(f"current_image_calibration_card_mismatch:{element_id}")
                                if field.get("coord") != element.get("坐标"):
                                    errors.append(f"current_image_calibration_coord_mismatch:{element_id}")
                                if field.get("field") != ("photo" if is_photo else "visible_text"):
                                    errors.append(f"current_image_calibration_field_type_mismatch:{element_id}")
                                if field.get("visibleText") != expected_text:
                                    errors.append(f"current_image_calibration_visible_text_mismatch:{element_id}")
                                if field.get("status") != "confirmed":
                                    errors.append(f"current_image_calibration_element_unconfirmed:{element_id}")
                                source = field.get("source")
                                evidence_path = field.get("evidencePath")
                                if source == "full_image" and evidence_path != data.get("screenshot"):
                                    errors.append(f"current_image_calibration_full_image_evidence_mismatch:{element_id}")
                                if source == "local_review" and evidence_path not in local_paths:
                                    errors.append(f"current_image_calibration_local_evidence_unregistered:{element_id}")
                                if not isinstance(field.get("reason"), str) or not field["reason"].strip() or field["reason"] == "pending_current_pixel_review":
                                    errors.append(f"current_image_calibration_reason_invalid:{element_id}")
                        missing = sorted(set(expected) - seen)
                        if missing:
                            errors.append(f"current_image_calibration_missing_elements:{','.join(missing)}")

    if not active:
        errors.append("no_active_elements")
    for i, left in enumerate(active):
        for right in active[i + 1:]:
            if left.get("所属组件") == right.get("所属组件") and element_visible_text(left) == element_visible_text(right) and intersects(left["坐标"], right["坐标"]):
                errors.append(f"overlapping_duplicate_visual_entity:{left['id']}:{right['id']}")

    duplicate_supply_candidates: list[dict[str, Any]] = []
    title_groups: dict[str, dict[str, Any]] = {}
    for card_id, titles in card_title_evidence.items():
        # A candidate requires exactly the same normalized visible title. It is an
        # audit cue only: business/addresses may still prove different supplies.
        normalized = normalized_visible_text("".join(titles))
        if normalized:
            group = title_groups.setdefault(normalized, {"titleEvidence": titles, "cardIds": []})
            group["cardIds"].append(card_id)
    for normalized, group in title_groups.items():
        if len(group["cardIds"]) > 1:
            duplicate_supply_candidates.append({
                "normalizedTitle": normalized,
                "titleEvidence": group["titleEvidence"],
                "cardIds": group["cardIds"],
                "status": "needs_manual_semantic_review",
                "rule": "同一截图内主标题完全一致；需继续核对门店、地址、业态与套餐/商品，不能直接判为重复供给",
            })

    result = {
        "valid": not errors,
        "query": data.get("query", "") if isinstance(data, dict) else "",
        "total": len(active),
        "elementIds": element_ids,
        "activeElements": [active_audit_entry(item) for item in active],
        "errors": errors,
        "warnings": warnings,
        "duplicateSupplyCandidates": duplicate_supply_candidates,
        "recognitionAudit": str(args.recognition_audit) if args.recognition_audit else "",
        "hierarchyFactAudit": hierarchy_fact_audit,
        "complexityFactAudit": complexity_fact_audit,
        "authenticityRelationAudit": authenticity_relation_audit,
        "alignmentFactAudit": alignment_fact_audit,
        "alignmentAnchorAudit": alignment_anchor_audit,
    }
    if args.audit:
        args.audit.parent.mkdir(parents=True, exist_ok=True)
        args.audit.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
