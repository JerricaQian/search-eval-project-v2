#!/usr/bin/env python3
"""Map assembled result cards to card-type and region candidates.

No region is emitted as present merely because its card type defines it. A
region needs local geometry/text evidence; unknown card type leaves every
region unresolved rather than filling a generic template.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from card_contract_engine import (
    KNOWN_RESULT_TYPES, evaluate_contract, extract_features, price_evidence_items,
    resolve_card_type, title_semantic_family,
)
from card_type_registry import validate_phase2_taxonomy
from classify_search_card_types import classify_card_types
from phase2_contract import MERCHANT_HEAD_AND_INFO, reviewed_card_type, topology_errors, topology_parts


VERSION = "phase2.result-card-semantics.v4"


def _overlap(box: list[int], container: list[int]) -> bool:
    return box[0] < container[0] + container[2] and box[0] + box[2] > container[0] and box[1] < container[1] + container[3] and box[1] + box[3] > container[1]


def _owned_by_card(box: list[int], container: list[int]) -> bool:
    center_y = box[1] + box[3] / 2
    return _overlap(box, container) and container[1] <= center_y < container[1] + container[3]


def _region_evidence(card: dict[str, Any], facts: dict[str, Any], definition: dict[str, Any]) -> list[dict[str, Any]]:
    x, y, w, h = card["coord"]
    texts = [item for item in facts.get("candidates", {}).get("text", []) if item.get("route") != "rejected" and _owned_by_card(item["coord"], card["coord"])]
    photos = [item for item in facts.get("candidates", {}).get("photos", []) if item.get("route") != "rejected" and _owned_by_card(item["coord"], card["coord"])]
    regions: list[dict[str, Any]] = []
    is_hotel = definition.get("id") == "酒店卡片"
    is_grid_cell = "two_column_grid_cell_boundary" in set(card.get("evidence", [])) and is_hotel
    for index, region in enumerate(definition["regions"]):
        name = region["name"]
        evidence_ids: list[str] = []
        # Images support a head-image candidate only when they occupy card left
        # or upper area. Text evidence is intentionally spatial, not lexical.
        if "头图" in name:
            explicit_head = str(card.get("headPhotoId", ""))
            if explicit_head:
                evidence_ids = [item["id"] for item in photos if item["id"] == explicit_head]
            else:
                candidates = [item for item in photos if item["coord"][0] < x + w * 0.45 and item["coord"][1] < y + h * 0.6]
                evidence_ids = [min(candidates, key=lambda item: (item["coord"][1], item["coord"][0]))["id"]] if candidates else []
        elif is_grid_cell:
            # The room-grid element annotation establishes five mutually
            # exclusive vertical bands. Ratios are deliberately broad and
            # relative to each current cell, so head-image height can vary.
            grid_bands = {
                "位置信息": (0.36, 0.56),
                "标题区": (0.52, 0.64),
                "基础信息区（双列变体）": (0.62, 0.79),
                "价格区": (0.77, 0.90),
                "评分与推荐理由": (0.88, 1.01),
                "标签区": (0.60, 0.78),
            }
            lower, upper = grid_bands.get(name, (0.0, 0.0))
            evidence_ids = [
                item["id"] for item in texts
                if lower <= ((item["coord"][1] + item["coord"][3] / 2 - y) / max(1, h)) < upper
            ] if upper > lower else []
            if name == "价格区":
                evidence_ids = [item["id"] for item in price_evidence_items([item for item in texts if item["id"] in evidence_ids], card["coord"])]
            elif name == "评分与推荐理由":
                evidence_ids = [item["id"] for item in texts if item["id"] in evidence_ids and re.search(r"\d(?:\.\d)?\s*分|暂无评分", str(item.get("text", "")))]
        elif is_hotel and "评分" in name:
            evidence_ids = [item["id"] for item in texts if re.search(r"\d(?:\.\d)?\s*分|暂无评分", str(item.get("text", "")))]
        elif is_hotel and "位置" in name:
            evidence_ids = [item["id"] for item in texts if re.search(r"距您|\d+(?:\.\d+)?\s*(?:km|公里|m|米)|近(?:地铁|机场|车站|商圈|大学|学院|公园|医院)", str(item.get("text", "")), re.I)]
        elif is_hotel and "基础信息" in name:
            evidence_ids = []
        elif "标题" in name:
            structured = re.compile(r"月售|已售|评分|\d(?:\.\d)?\s*分|\d+(?:\.\d+)?\s*(?:km|公里|分钟|元)|[¥￥]\s*\d|起送|配送费|\d{4}[-/.年]\d{1,2}")
            title_candidates = []
            for item in texts:
                value = str(item.get("text", ""))
                chinese = sum("\u4e00" <= char <= "\u9fff" for char in value)
                upper_ratio = 0.72 if "two_column_grid_cell_boundary" in set(card.get("evidence", [])) else 0.42
                upper = item["coord"][1] < y + max(100, h * upper_ratio)
                text_side = item["coord"][0] > x + w * 0.18 or item["coord"][2] > w * 0.40
                if upper and text_side and chinese >= 2 and not structured.search(value):
                    title_candidates.append(item)
            evidence_ids = [min(title_candidates, key=lambda item: (item["coord"][1], -sum("\u4e00" <= char <= "\u9fff" for char in str(item.get("text", "")))))["id"]] if title_candidates else []
        elif "价格" in name:
            price_items = price_evidence_items(texts, card["coord"])
            if is_hotel:
                # Hotel price regions also contain red/orange urgency and
                # discount copy. Only exact/contextual price grammar becomes
                # the primary price field; visual-only numbers stay promotion
                # facts and must not be validated as prices.
                price_items = [
                    item for item in price_items
                    if re.search(r"[¥￥]\s*\d|[Yy#*]\s*\d.{0,8}起|\d+(?:\.\d+)?\s*起", str(item.get("text", "")), re.I)
                ]
            evidence_ids = [item["id"] for item in price_items]
        else:
            vertical_start = y + int(h * (0.22 + min(index, 5) * 0.10))
            evidence_ids = [item["id"] for item in texts if item["coord"][1] >= vertical_start]
        confidence = 0.82 if evidence_ids else 0.0
        regions.append({"regionId": region["id"], "region": name, "status": "confirmed" if evidence_ids else "uncertain", "confidence": confidence, "evidenceSourceIds": evidence_ids})
    return regions


def _topology_type_candidate(card: dict[str, Any], facts: dict[str, Any], structure_blocks: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """Recognize the two merchant down-hang frameworks from local topology."""
    member_ids = card.get("memberBlockIds", [])
    if not member_ids:
        return None
    seed = structure_blocks.get(card.get("seedBlockId", ""))
    if seed:
        seed_bottom = seed["coord"][1] + seed["coord"][3]
    else:
        # Merchant-head interval recovery deliberately has no OCR block seed:
        # its start is the verified repeated square head photo. That is still
        # a valid topology anchor for the attached horizontal product rail.
        head_id = str(card.get("headPhotoId", ""))
        head = next((item for item in facts.get("candidates", {}).get("photos", []) if item.get("id") == head_id), None)
        if not head:
            return None
        seed_bottom = head["coord"][1] + head["coord"][3]
    attached = [structure_blocks[item_id] for item_id in member_ids if item_id in structure_blocks and structure_blocks[item_id]["coord"][1] >= seed_bottom]
    attached_text_blocks = [block for block in attached if block.get("layoutCandidate") == "text_only"]
    card_text = [item for item in facts.get("candidates", {}).get("text", []) if _overlap(item["coord"], card["coord"])]
    joined_text = "\n".join(str(item.get("text", "")) for item in card_text)
    attached_photos = [item for item in facts.get("candidates", {}).get("photos", []) if item.get("route") == "accepted" and item["coord"][1] >= seed_bottom and _overlap(item["coord"], card["coord"])]
    if attached_photos and len(card_text) >= 2:
        return {"cardType": "商家卡片_图文下挂", "confidence": 0.82, "evidence": ["topology:merchant_body_plus_attached_product_image", "local_text_present"]}
    merchant_anchor = re.search(r"(?:\d(?:\.\d)?\s*分|暂无评分|新店(?:入驻)?|\d+\s*条|人均)", joined_text, re.I)
    service_anchor = re.search(r"(?:预约|可约|取号|排队|服务|体验|门票|团购|套餐|美发|理发|剪发|洗护|清洗|保洁|家电|维修|按摩|体检|露营|漂流|游乐|剧本)", joined_text)
    if attached_text_blocks and len(card_text) >= 2 and merchant_anchor and service_anchor:
        return {"cardType": "商家卡片_文字下挂", "confidence": 0.82, "evidence": ["topology:merchant_body_plus_text_attachment", "merchant_information_anchor", "service_attachment_anchor"]}
    # The product contract requires one product image, title-side text and a
    # price. A single image-left/text-right seed with no down-hang topology is
    # stronger evidence than waiting for OCR to recover a unit/specification.
    card_photos = [item for item in facts.get("candidates", {}).get("photos", []) if item.get("route") == "accepted" and _overlap(item["coord"], card["coord"])]
    left_head_photos = [item for item in card_photos if item["coord"][0] < card["coord"][0] + card["coord"][2] * 0.42]
    price_text = [item for item in card_text if item.get("route") == "accepted" and ("¥" in str(item.get("text", "")) or "￥" in str(item.get("text", "")))]
    accepted_text = [item for item in card_text if item.get("route") == "accepted"]
    if len(left_head_photos) == 1 and price_text and len(accepted_text) >= 3 and not (merchant_anchor and service_anchor):
        return {
            "cardType": "商品卡片", "confidence": 0.82,
            "evidence": ["topology:single_left_head_image", "local_price_present", "no_graphic_or_service_downhang"],
        }
    return None


def _reviewed_merchant_attachment_state(card: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve a reviewed merchant card without lexical service-name gates.

    Current-pixel review has established merchant ownership and every visible
    attachment. A closed service-word list must not reclassify KTV or SPA
    merchants as products. The state machine stays fail-closed for a declared
    but unenumerated downhang, or a graphic downhang without a CV image anchor.
    """
    topology = card.get("reviewedTopology")
    if not isinstance(topology, dict):
        return None
    slots, items = topology_parts(topology)
    if not MERCHANT_HEAD_AND_INFO.issubset(slots):
        return None

    attachment_slots = {"attached_goods", "text_attachment"} & slots
    if not items:
        if attachment_slots:
            return None
        return {
            "cardType": "商家卡片_无下挂",
            "confidence": 1.0,
            "evidence": ["reviewed_merchant_attachment_state:no_attached_items"],
        }

    # A generic CV photo candidate is not sufficient for a graphic downhang:
    # sale badges and other decorative marks can look image-like. The anchor
    # must be confirmed in the current-pixel review and explicitly owned by
    # this card's attached-goods rail.
    accepted_photos = [
        item for item in facts.get("candidates", {}).get("photos", [])
        if item.get("route") == "accepted"
        and isinstance(item.get("coord"), list)
        and isinstance(item.get("visualReview"), dict)
        and item["visualReview"].get("cardId") == card.get("id")
        and item["visualReview"].get("topologySlot") == "attached_goods"
    ]
    has_item_photo_anchor = any(
        _overlap(photo["coord"], attachment["coord"])
        for attachment in items if isinstance(attachment.get("coord"), list)
        for photo in accepted_photos
    )
    if has_item_photo_anchor:
        if "attached_goods" not in slots:
            return None
        card_type = "商家卡片_图文下挂"
        evidence = ["reviewed_merchant_attachment_state:attached_item_cv_photo_anchor"]
    else:
        if "text_attachment" not in slots:
            return None
        reviewed_text = [
            item for item in facts.get("candidates", {}).get("text", [])
            if item.get("route") == "accepted"
            and isinstance(item.get("visualReview"), dict)
            and item["visualReview"].get("cardId") == card.get("id")
            and item["visualReview"].get("topologySlot") == "text_attachment"
            and item["visualReview"].get("itemIndex") is not None
            and str(item.get("text", "")).strip()
        ]
        reviewed_item_indexes = {int(item["visualReview"]["itemIndex"]) for item in reviewed_text}
        required_indexes = {int(item.get("itemIndex", index)) for index, item in enumerate(items, 1)}
        if not required_indexes.issubset(reviewed_item_indexes):
            return None
        card_type = "商家卡片_文字下挂"
        evidence = ["reviewed_merchant_attachment_state:independent_text_items_without_cv_photo_anchor"]

    if topology_errors(card_type, topology):
        return None
    return {"cardType": card_type, "confidence": 1.0, "evidence": evidence}


def _reviewed_topology_contract_validation(resolved: dict[str, Any], card_type: str, evidence: list[str],
                                           mode: str = "reviewed_current_pixel_topology") -> dict[str, Any]:
    """Record topology-backed proof without pretending lexical evidence exists."""
    existing = next(
        (item for item in resolved["contractEvaluations"] if item.get("cardType") == card_type),
        {"cardType": card_type, "score": 0.0, "matchedFeatures": [], "missingEvidenceGroups": []},
    )
    return {
        **existing,
        "minimumSatisfied": True,
        "matchedFeatures": sorted(set(existing.get("matchedFeatures", [])) | set(evidence)),
        "missingEvidenceGroups": [],
        "forbiddenFeaturesHit": [],
        "lexicalContractDiagnostics": {
            "missingEvidenceGroups": existing.get("missingEvidenceGroups", []),
            "forbiddenFeaturesHit": existing.get("forbiddenFeaturesHit", []),
        },
        "validationMode": mode,
    }


def _title_semantic_selection(card: dict[str, Any], facts: dict[str, Any],
                              title_semantics: dict[str, str],
                              reviewed_merchant: dict[str, Any] | None) -> dict[str, Any] | None:
    """Use a decisive title only when the card's structure can own that type."""
    family = title_semantics["family"]
    if not family or card.get("reviewedCardType") == "广告卡":
        return None
    # Explicit ad identity is an independent card-level exclusion, not a
    # competing product/merchant content classifier.
    if any(
        item.get("route") != "rejected"
        and isinstance(item.get("coord"), list) and len(item["coord"]) == 4
        and _owned_by_card(item["coord"], card["coord"])
        and re.search(r"(?:^|[^不])广告|推广", str(item.get("text", "")))
        for item in facts.get("candidates", {}).get("text", [])
    ):
        return None
    if family == "商家卡片":
        # Title can establish merchant identity, not whether its attachments
        # are graphic, textual, or absent.
        if not reviewed_merchant:
            return None
        card_type = reviewed_merchant["cardType"]
    else:
        card_type = family
    topology = card.get("reviewedTopology")
    has_reviewed_topology = isinstance(topology, dict) and bool(topology.get("regions"))
    # A clear title is enough for the family, but it cannot invent card
    # boundaries/ownership. Without current-pixel topology, use the ordinary
    # content/contract fallback below.
    if not has_reviewed_topology or topology_errors(card_type, topology):
        return None
    # A primary-point title does not turn a normal results-list card into a
    # pre-results entity; that page-context fact remains mandatory.
    if card_type == "主点卡片" and card.get("preResultsPosition") is not True:
        return None
    return {
        "cardType": card_type, "confidence": 1.0,
        "status": "confirmed", "classificationMode": "title_semantics_with_structure_v1",
        "evidence": [f"title_semantics:{title_semantics['sourceId']}", f"title_family:{family}"],
    }


def _reviewed_product_state(card: dict[str, Any], resolved: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve a current-pixel product topology before generic merchant cues.

    Product result cards legitimately contain merchant fulfillment, sales and
    distance rows.  Those supporting fields must not outweigh the reviewed
    single-product structure of head media, product title and product price.
    """
    topology = card.get("reviewedTopology")
    if not isinstance(topology, dict):
        return None
    card_type = reviewed_card_type(str(card.get("reviewedCardType", "")), topology)
    if card_type != "商品卡片" or topology_errors(card_type, topology):
        return None
    # A reviewed shape is not permission to erase stronger domain identity.
    # Hotel cards share head-media/title/price, so a fully satisfied hotel
    # contract wins when the current text also establishes hotel/homestay
    # identity and hotel list/grid topology.
    hotel_contract = next(
        (item for item in resolved.get("contractEvaluations", []) if item.get("cardType") == "酒店卡片"),
        {},
    )
    features = resolved.get("features", {})
    if (
        hotel_contract.get("minimumSatisfied") is True
        and (features.get("hotel_identity") or features.get("hotel_room_identity") or features.get("homestay_identity"))
        and (features.get("hotel_list_boundary") or features.get("hotel_grid_boundary"))
    ):
        return None
    slots, items = topology_parts(topology)
    if items or not {"head_media", "title", "price"}.issubset(slots):
        return None
    return {
        "cardType": "商品卡片",
        "confidence": 1.0,
        "evidence": ["reviewed_product_topology:head_media_title_price"],
    }


def map_cards(facts: dict[str, Any], candidates: dict[str, Any], taxonomy: dict[str, Any], recognition_contracts: dict[str, Any],
              geometry_profiles: dict[str, Any] | None = None) -> dict[str, Any]:
    validate_phase2_taxonomy(taxonomy)
    definitions = {item["id"]: item for item in taxonomy["cardTypes"] if item.get("scope") == "results_list_card"}
    structure_blocks = {block["id"]: block for block in candidates.get("structureBlocks", [])}
    output: list[dict[str, Any]] = []
    result_cards = candidates.get("resultCards", [])
    viewport_height = int(facts.get("viewport", {}).get("height", 0))
    for card_index, card in enumerate(result_cards):
        title_semantics = title_semantic_family(card, facts)
        reviewed_merchant = _reviewed_merchant_attachment_state(card, facts)
        title_selected = _title_semantic_selection(card, facts, title_semantics, reviewed_merchant)
        topology = None
        if title_selected:
            # Title family is terminal for classification. Internal text is
            # still collected for downstream field gates, but the generic
            # card-type classifier and competing contracts are not consulted.
            features = extract_features(card, facts, structure_blocks)
            contract = next(item for item in recognition_contracts["contracts"] if item["cardType"] == title_selected["cardType"])
            evaluation = evaluate_contract(contract, features)
            resolved = {
                "selected": title_selected, "features": features,
                "contractValidation": evaluation, "contractEvaluations": [evaluation],
                "nearestKnownCardType": title_selected["cardType"],
            }
            type_result = {"candidates": [{"cardType": title_selected["cardType"], "confidence": 1.0, "evidence": title_selected["evidence"]}]}
            selected = title_selected
            resolved["contractValidation"] = _reviewed_topology_contract_validation(
                resolved, selected["cardType"], selected["evidence"], "title_semantics_plus_card_structure",
            )
        else:
            type_result = classify_card_types(facts, taxonomy, card["coord"])
            hint = card.get("classificationHint")
            if hint:
                type_result["candidates"].append({"cardType": hint["cardType"], "confidence": hint["confidence"], "evidence": list(card.get("evidence", []))})
                type_result["candidates"].sort(key=lambda item: item["confidence"], reverse=True)
            topology = _topology_type_candidate(card, facts, structure_blocks)
            if topology:
                type_result["candidates"].append(topology)
                type_result["candidates"].sort(key=lambda item: item["confidence"], reverse=True)
            resolved = resolve_card_type(card, facts, structure_blocks, recognition_contracts, type_result["candidates"], geometry_profiles)
            selected = resolved["selected"]
            reviewed_product = _reviewed_product_state(card, resolved)
            if reviewed_product:
                selected = {
                    "cardType": reviewed_product["cardType"],
                    "confidence": reviewed_product["confidence"],
                    "status": "confirmed",
                    "classificationMode": "reviewed_product_topology_v1",
                    "evidence": reviewed_product["evidence"],
                }
                resolved["contractValidation"] = _reviewed_topology_contract_validation(
                    resolved, selected["cardType"], selected["evidence"],
                )
                resolved["nearestKnownCardType"] = selected["cardType"]
            elif reviewed_merchant:
                selected = {
                    "cardType": reviewed_merchant["cardType"],
                    "confidence": reviewed_merchant["confidence"],
                    "status": "confirmed",
                    "classificationMode": "reviewed_merchant_attachment_state_machine_v3",
                    "evidence": reviewed_merchant["evidence"],
                }
                resolved["contractValidation"] = _reviewed_topology_contract_validation(
                    resolved, selected["cardType"], selected["evidence"],
                )
                resolved["nearestKnownCardType"] = selected["cardType"]
        partial_policy = {"applied": False}
        bottom = card["coord"][1] + card["coord"][3]
        grid_column = str(card.get("gridColumn", ""))
        is_bottom_partial = viewport_height > 0 and bottom >= viewport_height - max(20, round(viewport_height * 0.02)) and (card_index == len(result_cards) - 1 or bool(grid_column))
        reviewed_topology = card.get("reviewedTopology", {}) if isinstance(card.get("reviewedTopology"), dict) else {}
        reviewed_media_visible = any(
            isinstance(region, dict)
            and region.get("slot") in {"head_media", "media", "merchant_head"}
            and region.get("visibleStatus", "confirmed") in {"confirmed", "naturally_cropped"}
            for region in reviewed_topology.get("regions", [])
        )
        has_visible_media = resolved["features"].get("has_media") or reviewed_media_visible
        previous = output[-1] if output else None
        if grid_column:
            previous = next(
                (output[index] for index in range(len(output) - 1, -1, -1)
                 if str(result_cards[index].get("gridColumn", "")) == grid_column),
                None,
            )
        previous_selected = previous.get("selectedCardType", {}) if previous else {}
        previous_type = str(previous_selected.get("cardType", ""))
        if is_bottom_partial and has_visible_media:
            partial_policy = {
                "applied": True, "visibleStatus": "naturally_cropped", "screenEdge": "bottom",
                "waivedOnly": ["missing_required_field", "missing_semantic_anchor"],
                "stillBlocking": ["malformed_visible_text", "ocr_consensus_failure", "explicit_ad_conflict"],
                "unobservableReasons": ["viewport_bottom_natural_crop"],
            }
        if not title_selected and is_bottom_partial and has_visible_media and previous_selected.get("status") == "confirmed" and previous_type in KNOWN_RESULT_TYPES and not resolved["features"].get("explicit_ad_marker"):
            inherited_validation = next(
                (item for item in resolved["contractEvaluations"] if item.get("cardType") == previous_type),
                resolved["contractValidation"],
            )
            selected = {
                "cardType": previous_type,
                "confidence": round(float(previous_selected.get("confidence", 0.8)) * 0.92, 4),
                "status": "confirmed",
                "classificationMode": "bottom_partial_inherit_previous_repeated_type",
                "evidence": sorted(set(inherited_validation.get("matchedFeatures", [])) | {"screen_bottom_natural_crop", f"previous_card_type:{previous['cardId']}"}),
            }
            resolved["contractValidation"] = inherited_validation
            resolved["nearestKnownCardType"] = previous_type
            partial_policy.update({
                "applied": True, "visibleStatus": "naturally_cropped", "screenEdge": "bottom",
                "inheritedFromCardId": previous["cardId"], "inheritedCardType": previous_type,
                "waivedOnly": ["missing_required_field", "missing_semantic_anchor"],
                "stillBlocking": ["malformed_visible_text", "ocr_consensus_failure", "explicit_ad_conflict"],
            })
        definition = definitions.get(selected["cardType"]) if selected["status"] == "confirmed" else None
        output.append({
            "cardId": card["id"], "coord": card["coord"], "cardTypeCandidates": type_result["candidates"], "selectedCardType": selected,
            "topologyCandidate": topology,
            "titleSemanticDecision": title_semantics,
            "recognitionFeatures": resolved["features"], "contractValidation": resolved["contractValidation"],
            "contractEvaluations": resolved["contractEvaluations"], "nearestKnownCardType": resolved["nearestKnownCardType"],
            "partialCardPolicy": partial_policy,
            "regions": _region_evidence(card, facts, definition) if definition else [],
            "routing": "confirmed_card_type_required_for_region_mapping" if not definition else "region_evidence_required",
        })
    return {"contractVersion": VERSION, "sourceCvFacts": facts.get("screenshot", ""), "cards": output,
            "routing": {"rule": "Uncertain card type or region is not an absent element, defect, failing result, excellence, or human-review task."}}


def main() -> int:
    parser = argparse.ArgumentParser(description="Map result-card candidates to semantic candidates")
    parser.add_argument("cv_facts", type=Path)
    parser.add_argument("result_candidates", type=Path)
    parser.add_argument("--taxonomy", type=Path, default=Path(__file__).resolve().parents[1] / "references/search_card_taxonomy.v1.json")
    parser.add_argument("--recognition-contracts", type=Path, default=Path(__file__).resolve().parents[1] / "references/card_recognition_contracts.v1.json")
    parser.add_argument("--geometry-profiles", type=Path, default=Path(__file__).resolve().parents[1] / "references/learned_card_geometry_profiles.v1.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = map_cards(
        json.loads(args.cv_facts.read_text(encoding="utf-8")),
        json.loads(args.result_candidates.read_text(encoding="utf-8")),
        json.loads(args.taxonomy.read_text(encoding="utf-8")),
        json.loads(args.recognition_contracts.read_text(encoding="utf-8")),
        json.loads(args.geometry_profiles.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "cards": len(result["cards"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
