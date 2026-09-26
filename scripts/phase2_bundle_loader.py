#!/usr/bin/env python3
"""Load Phase2 facts for Phase3 without persisting an expanded projection."""
from __future__ import annotations

import argparse
import importlib.util
import hashlib
import json
import sys
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
COMPILER = ROOT / "phase2-card-annotation" / "scripts" / "compile_golden_phase3_manifest.py"
ATOMIC_VALIDATOR = ROOT / "phase2-card-annotation" / "scripts" / "validate_atomic_manifest_v3.py"

CARD_NAMES = {
    "merchant_text_append": "商家卡片-文字下挂",
    "merchant_plain": "商家卡片-无下挂",
    "merchant_graphic_append": "商家卡片-图文下挂",
    "merchant_product_card": "商品卡片",
    "product": "商品卡片",
    "hotel": "酒店卡片",
    "performance_movie": "演出/电影卡片",
    "primary_point": "主点卡片",
    "heterogeneous": "异构卡",
    "advertisement": "特殊广告卡",
}
SLOT_ROLES = {
    "title": "title", "subtitle": "subtitle", "price": "price", "original_price": "price",
    "price_and_sales": "price", "price_and_trade": "price", "sales": "sales", "monthly_sales": "sales",
    "rating": "rating", "location": "location", "distance": "location", "address": "location", "city": "location",
    "recommendation": "recommendation", "review_reason": "recommendation", "hotel_class": "hotel_class",
    "fulfillment": "fulfillment", "fulfillment_tag": "fulfillment", "delivery_time": "fulfillment",
    "promotion": "promotion", "promotion_tag": "promotion", "coupon_type_tag": "promotion",
    "coupon_value_tag": "promotion", "guarantee_tag": "guarantee",
    "price_promotion_tag": "promotion", "recommendation_tag": "recommendation",
    "delivery_time_tag": "fulfillment", "live_status_tag": "sales",
    "merchant_tag": "merchant", "merchant_feature_tag": "merchant_feature",
    "product_attribute_tag": "product_attribute", "scenic_rating_tag": "scenic_rating",
    "gift_tag": "gift", "generic_tag": "tag", "other_tag": "tag",
    "size_info": "size", "size": "size", "specification": "size",
}


@lru_cache(maxsize=1)
def _compiler() -> ModuleType:
    script_dir = str(COMPILER.parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    spec = importlib.util.spec_from_file_location("phase2_golden_bundle_compiler", COMPILER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Phase2 bundle compiler: {COMPILER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def _atomic_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("phase2_atomic_v3_validator", ATOMIC_VALIDATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Phase2 atomic validator: {ATOMIC_VALIDATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _compat_element(element_id: str, source: dict[str, Any], owner_id: str, slot: str, owner_type: str) -> dict[str, Any]:
    kind = source.get("kind")
    visual_source = source.get("visual") if isinstance(source.get("visual"), dict) else {}
    visibility = source.get("visibility")
    naturally_cropped = visibility == "naturally_cropped"
    entity_kind = "image" if kind == "media" else kind
    visual = {
        "entityKind": entity_kind,
        "visualStatus": "confirmed",
        "colorRole": visual_source.get("colorRole", "unknown"),
        "backgroundColor": visual_source.get("backgroundColor", ""),
        "textColor": visual_source.get("textColor", ""),
        "borderColor": visual_source.get("borderColor", ""),
        "containerShape": visual_source.get("container", "none"),
        "graphicAssistRole": visual_source.get("graphicAssist", "none") if kind == "tag" else "none",
    }
    render = {
        "visibleStatus": "confirmed",
        "renderState": "naturally_cropped" if naturally_cropped else (visibility or "normal"),
        "isPhoto": kind == "media" and source.get("mediaType") == "photo",
        "isSystemUi": kind != "media",
    }
    text = str(source.get("text", ""))
    output = {
        "id": element_id,
        "所属组件": owner_id,
        "ownerType": owner_type,
        "元素类型": "图片" if kind == "media" else ("标签" if kind == "tag" else "图标" if kind == "icon" else "文本"),
        "内容简述": f"原文:{text}" if text else str(source.get("semanticDescription") or "原文:[图片]"),
        "坐标": source["bounds"],
        "isExcluded": False,
        "excludeReason": "",
        "render": render,
        "visual": visual,
    }
    if kind in {"text", "tag"}:
        semantic_role = SLOT_ROLES.get(slot, slot[:-4] if slot.endswith("_tag") else "other")
        output["textFacts"] = {
            "rawText": text,
            "textStatus": "naturally_ellipsized" if naturally_cropped else "complete",
            "semanticRole": semantic_role,
            "textColorRole": visual_source.get("colorRole", "unknown"),
        }
    elif kind == "media":
        output["mediaFacts"] = {
            "mediaType": source.get("mediaType"),
            "semanticDescription": source.get("semanticDescription"),
            "semanticStatus": source.get("semanticStatus"),
        }
    if kind == "icon":
        output["iconFacts"] = {
            "semanticDescription": source.get("semanticDescription"),
            "semanticStatus": source.get("semanticStatus"),
            "attachedTo": source.get("attachedTo"),
        }
    return output


def _atomic_to_phase3(payload: dict[str, Any]) -> dict[str, Any]:
    elements = payload["elementsById"]
    regions = payload["regionsById"]
    result_card_ids = {
        card_id
        for module in payload["modulesById"].values()
        if module.get("type") == "result_list"
        for card_id in module.get("cardIds", [])
    }
    list_positions = {
        card_id: position
        for module in payload["modulesById"].values()
        if module.get("type") == "result_list"
        for position, card_id in enumerate(module.get("cardIds", []), start=1)
    }
    cards = []
    for card_id, card in payload["cardsById"].items():
        converted_regions = []
        for region_id in card["regionIds"]:
            region = regions[region_id]
            converted = []
            if "slots" in region:
                for slot, element_ids in region["slots"].items():
                    converted.extend(_compat_element(element_id, elements[element_id], card_id, slot, "card") for element_id in element_ids)
            else:
                for item in region.get("items", []):
                    for slot, element_ids in item["slots"].items():
                        converted.extend(_compat_element(element_id, elements[element_id], card_id, slot, "card") for element_id in element_ids)
            converted_regions.append({"name": region["name"], "coord": region["bounds"], "elements": converted})
        region_signature = ">".join(region["name"] for region in converted_regions)
        card_type = str(card["cardType"])
        cards.append({
            "cardId": card_id,
            "卡片类型": CARD_NAMES.get(card_type, card_type),
            "cardTypeCode": card_type,
            "variant": card.get("variant", ""),
            "coord": card["bounds"],
            "listPosition": list_positions.get(card_id),
            "regions": converted_regions,
            "structure": {
                "visibleStatus": card["visibility"],
                "isResultListItem": card_id in result_card_ids,
                "isHeterogeneous": card_type == "heterogeneous",
                "regions": [region["name"] for region in converted_regions],
                "layoutSignature": region_signature,
            },
        })
    page_modules = []
    for module_id, module in payload["modulesById"].items():
        module_elements = [
            _compat_element(element_id, elements[element_id], module_id, slot, "module")
            for slot, element_ids in module.get("slots", {}).items()
            for element_id in element_ids
        ]
        referenced_filter_ids = list(module.get("itemIds", []))
        for panel in module.get("panels", []):
            referenced_filter_ids.extend(panel.get("itemIds", []))
        filter_items = []
        for item_id in dict.fromkeys(referenced_filter_ids):
            item = payload["filterItemsById"][item_id]
            item_elements = [
                _compat_element(element_id, elements[element_id], item_id, slot, "filter_item")
                for slot, element_ids in item.get("slots", {}).items()
                for element_id in element_ids
            ]
            filter_items.append({"id": item_id, "coord": item["bounds"], "elements": item_elements})
        page_modules.append({
            "id": module_id,
            "moduleType": module["type"],
            "coord": module["bounds"],
            "visibleStatus": module["visibility"],
            "contentRole": module["type"],
            "isListItem": False,
            "elements": module_elements,
            "filterItems": filter_items,
        })
    projected_ids = {
        element["id"]
        for card in cards
        for region in card["regions"]
        for element in region["elements"]
    }
    projected_ids.update(
        element["id"]
        for module in page_modules
        for element in module["elements"]
    )
    projected_ids.update(
        element["id"]
        for module in page_modules
        for item in module["filterItems"]
        for element in item["elements"]
    )
    screenshot = Path(str(payload["source"]["screenshot"]))
    if not screenshot.is_absolute():
        screenshot = ROOT / screenshot
    return {
        "query": payload["source"]["query"],
        "screenshot": str(screenshot.resolve()),
        "cards": cards,
        "pageFacts": {"screen": 1, "isContinuation": False, "viewport": {"size": payload["source"]["viewport"]}, "modules": page_modules},
        "atomicProjection": {
            "sourceElementCount": len(elements),
            "projectedElementCount": len(projected_ids),
            "complete": projected_ids == set(elements),
        },
        "recognition": {"contractVersion": "phase2.atomic-manifest.v3.compat-view", "status": "confirmed", "phase3Ready": True},
        "relations": [],
    }


def load_phase2_facts(
    *,
    manifest_path: Path | None = None,
    normalized_path: Path | None = None,
    evidence_path: Path | None = None,
) -> dict[str, Any]:
    """Return the Phase3 fact view from either input format.

    Normalized golden bundles are verified against their evidence sidecar and
    projected only in memory. No ``elements_*.json`` file is created.
    """
    if normalized_path is not None:
        if manifest_path is not None:
            raise ValueError("manifest_path cannot be combined with normalized_path")
        if evidence_path is None:
            raise ValueError("evidence_path is required with normalized_path")
        normalized_path = normalized_path.resolve()
        evidence_path = evidence_path.resolve()
        normalized = json.loads(normalized_path.read_text(encoding="utf-8"))
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        compiler = _compiler()
        errors = compiler.validate_normalized_bundle(normalized, evidence, evidence_path)
        if errors:
            raise ValueError("invalid normalized/evidence bundle: " + ",".join(errors))
        return compiler.compile_phase3(normalized)
    if evidence_path is not None:
        raise ValueError("evidence_path requires normalized_path")
    if manifest_path is None:
        raise ValueError("provide manifest_path or normalized_path with evidence_path")
    payload = json.loads(manifest_path.resolve().read_text(encoding="utf-8"))
    if payload.get("schemaVersion") == "phase2.atomic-manifest.v3":
        result = _atomic_validator().validate(payload)
        if not result["valid"]:
            raise ValueError("invalid atomic v3 manifest: " + ",".join(result["errors"]))
        if payload.get("publication", {}).get("status") != "ready":
            raise ValueError("atomic v3 manifest is not publication-ready")
        screenshot = Path(str(payload.get("source", {}).get("screenshot", "")))
        if not screenshot.is_absolute():
            screenshot = ROOT / screenshot
        if not screenshot.is_file():
            raise ValueError("atomic v3 source screenshot is missing")
        actual_hash = hashlib.sha256(screenshot.read_bytes()).hexdigest()
        if actual_hash != payload.get("source", {}).get("sha256"):
            raise ValueError("atomic v3 source screenshot sha256 mismatch")
        return _atomic_to_phase3(payload)
    return payload


def _projected_element_ids(facts: dict[str, Any]) -> set[str]:
    """Return the unique element ids exposed by the read-only Phase3 view."""
    element_ids = {
        str(element["id"])
        for card in facts.get("cards", [])
        for region in card.get("regions", [])
        for element in region.get("elements", [])
        if element.get("id")
    }
    for module in (facts.get("pageFacts") or {}).get("modules", []):
        element_ids.update(
            str(element["id"])
            for element in module.get("elements", [])
            if element.get("id")
        )
        for item in module.get("filterItems", []):
            element_ids.update(
                str(element["id"])
                for element in item.get("elements", [])
                if element.get("id")
            )
    return element_ids


def validate_atomic_fact_view(manifest_path: Path) -> dict[str, Any]:
    """Validate Atomic v3 and its complete, in-memory Phase3 projection."""
    resolved = manifest_path.resolve()
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != "phase2.atomic-manifest.v3":
        raise ValueError("atomic_v3_manifest_required")
    facts = load_phase2_facts(manifest_path=resolved)
    projection = facts.get("atomicProjection") or {}
    if projection.get("complete") is not True:
        raise ValueError("atomic_projection_incomplete")
    projected_ids = _projected_element_ids(facts)
    if len(projected_ids) != projection.get("projectedElementCount"):
        raise ValueError("atomic_projection_count_mismatch")
    return {
        "contractVersion": "phase3.phase2-fact-view-audit.v1",
        "valid": True,
        "manifest": str(resolved),
        "query": facts.get("query", ""),
        "sourceManifestTotal": projection.get("sourceElementCount", 0),
        "projectedElementCount": len(projected_ids),
        "atomicProjectionComplete": True,
        "errors": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate an Atomic v3 manifest through the current Phase3 read-only fact loader."
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    try:
        audit = validate_atomic_fact_view(args.manifest)
        exit_code = 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        audit = {
            "contractVersion": "phase3.phase2-fact-view-audit.v1",
            "valid": False,
            "manifest": str(args.manifest.resolve()),
            "query": "",
            "sourceManifestTotal": 0,
            "projectedElementCount": 0,
            "atomicProjectionComplete": False,
            "errors": [str(exc)],
        }
        exit_code = 2
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.audit.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
