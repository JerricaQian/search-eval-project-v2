#!/usr/bin/env python3
"""Block bad CV recognition before it becomes a Phase3 manifest.

This is a batch gate, not a per-field confidence router: it never asks a
vision model to read rejected OCR.  A failure means re-run the local CV/OCR
pipeline with another bounded configuration, or stop the batch.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from recognition_gate_hooks import run_hooks
from phase2_contract import fulfillment_semantic_kind, merchant_variant, reviewed_card_type


def overlap(a: list[int], b: list[int]) -> bool:
    return a[0] < b[0] + b[2] and a[0] + a[2] > b[0] and a[1] < b[1] + b[3] and a[1] + a[3] > b[1]


def malformed_text(value: str) -> bool:
    compact = value.strip()
    meaningful = [char for char in compact if char.isalnum() or "\u4e00" <= char <= "\u9fff"]
    return not meaningful or (len(meaningful) == 1 and not meaningful[0].isdigit()) or any(token in compact for token in ("[[", "]]", "{{", "}}"))


def _role_from_card_region(region_name: str) -> str | None:
    mappings = (
        ("标题", "title"), ("价格", "price"), ("评分", "rating"),
        ("位置", "location"), ("履约", "fulfillment"), ("销量", "sales"),
        ("基础信息", "subtitle"), ("主要信息", "title"), ("标签", "tag"),
    )
    return next((role for marker, role in mappings if marker in region_name), None)


def _structured_role_dominates_text(role: str, value: str) -> bool:
    """Allow page hints to override a card region only for field-shaped text.

    OCR often merges a merchant title with a trailing delivery time.  A weak
    substring match must not turn that whole title into a fulfillment field.
    """
    text = value.strip()
    compact = re.sub(r"\s+", "", text)
    if role == "fulfillment":
        return bool(fulfillment_semantic_kind(text))
    rules = {
        "location": r"^\d+(?:\.\d+)?(?:km|公里|m|米)$",
        "rating": r"^(?:\d(?:\.\d)?分|暂无评分)$",
        "sales": r"^(?:月售|已售|年售|回购|加购).{0,10}\d.{0,3}$",
        "price": r"^(?:[¥￥#Yy]\s*\d|(?:到手价|神价|低价|券后价?|票价|起价)[:：]?\s*[¥￥#Yy]?\d)",
        "tag": r"^.{1,8}$",
    }
    pattern = rules.get(role)
    return bool(pattern and re.search(pattern, compact, re.I))


def _reviewed_topology_expected_type(card: dict[str, Any]) -> str:
    """Return only card types proved unambiguously by reviewed topology."""
    topology = card.get("reviewedTopology", {})
    if not isinstance(topology, dict):
        return ""
    return reviewed_card_type(str(card.get("reviewedCardType", "")), topology)


def _golden_structure_gaps(facts: dict[str, Any], candidates: dict[str, Any], semantics: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn golden *structure* into screenshot-specific repair directions.

    This comparison deliberately never reads a golden value, coordinate or
    item count.  Its purpose is to say which current-pixel proof is missing
    for the selected card structure, so a reviewer can repair the candidate
    pass instead of treating a schema failure as an opaque stop signal.
    """
    text = facts.get("candidates", {}).get("text", [])
    photos = {str(item.get("id")): item for item in facts.get("candidates", {}).get("photos", [])}
    component_read_completed = bool(facts.get("routing", {}).get("boundedCardReprocess", {}).get("targets"))
    gaps: list[dict[str, Any]] = []
    for card in candidates.get("resultCards", []):
        card_id = str(card.get("id", ""))
        if semantics.get(card_id, {}).get("partialCardPolicy", {}).get("applied") is True:
            # A bottom-edge continuation has no obligation to prove the
            # off-screen carousel structure. Visible malformed text remains
            # governed by the ordinary hooks above.
            continue
        selected = semantics.get(card_id, {}).get("selectedCardType", {})
        card_type = str(selected.get("cardType", ""))
        if card_type != "商家卡片_图文下挂":
            continue
        bounds = card.get("coord", [])
        attached_ids = [str(item) for item in card.get("attachedProductPhotoIds", [])]
        attached = [photos[item] for item in attached_ids if item in photos and photos[item].get("route") != "rejected"]
        local = [item for item in text if isinstance(bounds, list) and len(bounds) == 4 and overlap(item.get("coord", []), bounds)]
        image_inner = [item.get("id") for item in local if any("photo_inner_text_not_ui_atom" in reason for reason in item.get("rejectionReasons", []))]
        # A merged Paddle line remains a blocking problem only while it has
        # not been replaced by a narrower, recorded local-pixel observation.
        # The old line must stay rejected for audit, but must not keep a card
        # permanently blocked after the replacement atoms have been reviewed.
        merged = [
            item.get("id") for item in local
            if "superseded_by_main_session_local_visual_review" not in item.get("rejectionReasons", [])
            and any(
                "container_line_requires_local_pixel_split" in reason
                or "multiple_independent_visual_entities_require_local_pixel_split" in reason
                for reason in item.get("rejectionReasons", [])
            )
        ]
        product_meta = [item for item in local if item.get("boundedReprocess", {}).get("region") == "product_meta"]
        meta_accepted = [item for item in product_meta if item.get("route") == "accepted"]
        meta_rejected = [item.get("id") for item in product_meta if item.get("route") == "rejected"]
        # A recorded current-pixel review can replace a rejected Paddle line
        # with separately bounded product title/price atoms.  The replacement
        # has no ``boundedReprocess`` marker by design, so use its own crop
        # and the attached-media lower edge as the evidence boundary.
        attached_bottom = max((item["coord"][1] + item["coord"][3] for item in attached), default=0)
        reviewed_meta = [
            item for item in local
            if isinstance(item.get("visualReview"), dict)
            and item.get("coord", [0, 0, 0, 0])[1] >= attached_bottom
            and str(item.get("text", "")).strip()
        ]
        if not attached:
            gaps.append({"cardId": card_id, "reference": "golden_structure_exemplars.v1.md#3", "kind": "missing_graphic_item_anchor", "blocking": True, "action": "重建当前截图下挂商品图片边界；每个可见图片项必须先有自己的图片候选，再分配标题/价格。", "sourceIds": []})
        if image_inner:
            gaps.append({"cardId": card_id, "reference": "golden_structure_exemplars.v1.md#5", "kind": "photo_inner_text", "blocking": False, "action": "保持这些 OCR 为拒绝审计；仅对有独立平台容器的覆盖标做局部像素复核，禁止把包装/招牌字发布为 UI 文本。", "sourceIds": image_inner})
        if merged:
            gaps.append({"cardId": card_id, "reference": "golden_structure_exemplars.v1.md#7", "kind": "merged_visual_entities", "blocking": True, "action": "按颜色、间距和圆角容器拆成独立 chip；未取得单个边界与逐项文字前不得发布整行。", "sourceIds": merged})
        if component_read_completed and attached and meta_rejected and not (meta_accepted or reviewed_meta):
            gaps.append({"cardId": card_id, "reference": "golden_structure_exemplars.v1.md#3", "kind": "unresolved_product_metadata", "blocking": True, "action": "读取当前卡的 product_meta 局部区域，逐项建立可见商品名/价格；右侧或底部裁切项只保留可见字形并标 naturally_cropped。", "sourceIds": meta_rejected})
    return gaps


def gate(facts: dict[str, Any], candidates: dict[str, Any], card_semantics: dict[str, Any], text_semantics: dict[str, Any]) -> dict[str, Any]:
    text = facts.get("candidates", {}).get("text", [])
    accepted = [item for item in text if item.get("route") == "accepted"]
    rejected = [item for item in text if item.get("route") == "rejected"]
    malformed = [item for item in accepted if malformed_text(str(item.get("text", "")))]
    cards = candidates.get("resultCards", [])
    semantics = {item.get("cardId"): item for item in card_semantics.get("cards", [])}
    golden_gaps = _golden_structure_gaps(facts, candidates, semantics)
    all_semantic_candidates = {item.get("sourceId"): item for item in text_semantics.get("candidates", [])}
    mapped = {source_id: item for source_id, item in all_semantic_candidates.items() if item.get("status") == "confirmed"}
    # Card-local region mapping is more precise than page-block position for
    # titles/prices on tall cards. Reuse only confirmed region evidence and
    # still send the underlying OCR text through every semantic hook below.
    accepted_by_id = {item.get("id"): item for item in accepted}
    text_ids = set(accepted_by_id)
    # A current-pixel reviewer has already established item ownership for a
    # text downhang.  That topology evidence must outrank the page-level
    # lexical heuristic: labels such as “特价团” can look price-like, but are
    # the service title of their attached item rather than a price field.
    # Preserve the explicit attachment role before page/block semantics are
    # allowed to assign a structured role and trigger a false grammar error.
    for source_id, source in accepted_by_id.items():
        review = source.get("visualReview")
        if (isinstance(review, dict)
                and review.get("topologySlot") == "text_attachment"
                and review.get("role") in {"attachment", "subtitle"}):
            mapped[source_id] = {
                "sourceId": source_id,
                "semanticRoleCandidate": "attachment",
                "status": "confirmed",
                "evidence": ["main_session_local_visual_read_text_attachment"],
            }
    # Page-block roles are deliberately coarse. Inside a confirmed card,
    # discard a structured page role unless the text itself has that field's
    # grammar; precise card regions below may then assign the correct role.
    for source_id, item in list(mapped.items()):
        source = accepted_by_id.get(source_id)
        if not source:
            continue
        inside_card = any(overlap(source.get("coord", []), card.get("coord", [])) for card in candidates.get("resultCards", []))
        hinted_role = str(item.get("semanticRoleCandidate", ""))
        if inside_card and hinted_role in {"price", "rating", "sales", "location", "fulfillment", "tag"} and not _structured_role_dominates_text(hinted_role, str(source.get("text", ""))):
            del mapped[source_id]
    for semantic_card in card_semantics.get("cards", []):
        for region in semantic_card.get("regions", []):
            if region.get("status") != "confirmed":
                continue
            role = _role_from_card_region(str(region.get("region", "")))
            if not role:
                continue
            for source_id in region.get("evidenceSourceIds", []):
                if source_id in text_ids:
                    source_role = role
                    page_hint = all_semantic_candidates.get(source_id, {})
                    hinted_role = page_hint.get("semanticRoleCandidate")
                    source_text = str(accepted_by_id.get(source_id, {}).get("text", ""))
                    if (hinted_role in {"price", "rating", "sales", "location", "fulfillment", "tag"}
                            and float(page_hint.get("confidence", 0)) >= 0.72
                            and _structured_role_dominates_text(str(hinted_role), source_text)):
                        source_role = str(hinted_role)
                    mapped[source_id] = {
                        "sourceId": source_id, "semanticRoleCandidate": source_role, "status": "confirmed",
                        "evidence": ["confirmed_card_region_evidence"],
                    }
    # A current-screenshot main-session local read is an explicit primary
    # observation, with its crop and read ID recorded in the audit. It is not
    # OCR correction and therefore carries its supplied semantic role.
    for source_id, source in accepted_by_id.items():
        review = source.get("visualReview")
        if isinstance(review, dict) and review.get("visibleStatus", "confirmed") == "confirmed" and review.get("role") in {"title", "subtitle", "price", "rating", "sales", "fulfillment", "location", "tag"}:
            mapped[source_id] = {"sourceId": source_id, "semanticRoleCandidate": review["role"], "status": "confirmed", "evidence": ["main_session_local_visual_read"]}
    errors: list[str] = []
    reprocess: list[str] = []
    if not accepted:
        errors.append("no_usable_ocr_text")
        reprocess.append("使用本地 PaddleOCR 对已定位的卡片文字列分区识别；不得将整页送入模型。")
    # High rejection is not itself a failure: it can mean the hygiene pass
    # correctly discarded OCR over photos/product rails. The gate evaluates
    # the remaining published facts and each card's semantic anchors below.
    if malformed:
        errors.append(f"malformed_text_published:{','.join(str(item.get('id')) for item in malformed)}")
        reprocess.append("清除异常标点/单字碎片后重跑；不得把碎片直接写入 Phase3 元素。")
    if not cards:
        errors.append("no_result_cards")
        reprocess.append("重跑页面结构与结果卡边界识别。")
    for card in cards:
        card_id, bounds = str(card.get("id", "")), card.get("coord", [])
        local_text = [item for item in accepted if isinstance(bounds, list) and len(bounds) == 4 and overlap(item["coord"], bounds)]
        semantic_card = semantics.get(card_id, {})
        card_type = semantic_card.get("selectedCardType", {})
        partial_allowed = semantic_card.get("partialCardPolicy", {}).get("applied") is True
        reviewed_expected_type = _reviewed_topology_expected_type(card)
        if reviewed_expected_type and not partial_allowed and card_type.get("cardType") != reviewed_expected_type:
            errors.append(f"{card_id}:reviewed_topology_selected_card_type_conflict")
        if len(local_text) < 2 and not partial_allowed:
            errors.append(f"{card_id}:insufficient_usable_text")
        if card_type.get("status") != "confirmed":
            errors.append(f"{card_id}:card_type_unresolved")
        contract_validation = semantic_card.get("contractValidation")
        if isinstance(contract_validation, dict) and contract_validation.get("minimumSatisfied") is not True and not partial_allowed:
            errors.append(f"{card_id}:known_or_fallback_contract_not_satisfied")
        # A card needs at least one deterministic semantic anchor. It may be a
        # title, price, rating, fulfillment, or tag; exact field requirements
        # are card-type-specific and remain Phase3-neutral here.
        if not any(item.get("id") in mapped for item in local_text) and not partial_allowed:
            errors.append(f"{card_id}:no_confirmed_semantic_anchor")
    facts_by_id = {item.get("id"): item for item in accepted}
    semantic_items = [{
        "sourceId": source_id,
        "text": str(facts_by_id.get(source_id, {}).get("text", item.get("text", ""))),
        "role": str(item.get("semanticRoleCandidate", "other")),
        "region": str(item.get("regionCandidate", "")),
    } for source_id, item in mapped.items()]
    roles_by_card: dict[str, set[str]] = {}
    semantic_items_by_card: dict[str, list[dict[str, str]]] = {}
    for card in cards:
        card_id, bounds = str(card.get("id", "")), card.get("coord", [])
        owned_items = [item for item in semantic_items if item["sourceId"] in facts_by_id and isinstance(bounds, list) and len(bounds) == 4 and overlap(facts_by_id[item["sourceId"]]["coord"], bounds)]
        semantic_items_by_card[card_id] = owned_items
        roles_by_card[card_id] = {item["role"] for item in owned_items}
    hook_findings = run_hooks({"semanticItems": semantic_items, "factsById": facts_by_id, "acceptedText": accepted,
                               "rolesByCard": roles_by_card, "semanticItemsByCard": semantic_items_by_card,
                               "cards": cards, "cardSemantics": semantics})
    errors.extend(f"semantic_hook:{item['hook']}:{item['sourceId']}:{item['reason']}" for item in hook_findings)
    role_by_source = {item["sourceId"]: item["role"] for item in semantic_items}
    reprocess_targets = [
        {"sourceId": item["sourceId"], "role": role_by_source.get(item["sourceId"], ""), "hook": item["hook"], "reason": item["reason"], "action": "rerun_bounded_local_ocr_or_rebuild_card_boundary"}
        for item in hook_findings
    ]
    if hook_findings:
        reprocess.append("仅对 semanticHookFindings 中的 sourceId 重跑裁剪 OCR/卡边界；语言纠错候选只能作为异常信号，不得改写原文。")
    if golden_gaps:
        errors.extend(f"golden_structure_gap:{item['cardId']}:{item['kind']}" for item in golden_gaps if item["blocking"])
        reprocess.extend(item["action"] for item in golden_gaps if item["blocking"])
    if any(error.endswith("reviewed_topology_selected_card_type_conflict") for error in errors):
        reprocess.append("重新合并本卡当前图片复核拓扑并重算卡型一次；不得回退异构卡，也不得重复运行无关 OCR。")
        reprocess_targets.extend({
            "cardId": str(card.get("id", "")), "reason": "reviewed_topology_selected_card_type_conflict",
            "action": "rerun_current_pixel_topology_review_and_card_type_mapping",
        } for card in cards if f"{card.get('id')}:reviewed_topology_selected_card_type_conflict" in errors)
    if any(error.endswith(("insufficient_usable_text", "no_confirmed_photo_candidate", "card_type_unresolved", "no_confirmed_semantic_anchor")) for error in errors):
        reprocess.append("按失败卡逐卡重跑本地 CV/OCR；只复用当前截图的卡片边界，禁止跨图坐标套用。")
    return {
        "contract": "phase2.recognition-gate", "valid": not errors,
        "summary": {"ocrTextCandidates": len(text), "acceptedTextCandidates": len(accepted), "rejectedTextCandidates": len(rejected), "resultCards": len(cards)},
        "errors": errors, "semanticHookFindings": hook_findings, "goldenStructureGaps": golden_gaps,
        "reprocessTargets": reprocess_targets, "reprocess": list(dict.fromkeys(reprocess)),
        "rule": "No model-reading escalation. Gate failure blocks manifest publication and requires local CV/OCR reprocessing.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate Phase2 CV recognition before manifest publication")
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--result-candidates", type=Path, required=True)
    parser.add_argument("--card-semantics", type=Path, required=True)
    parser.add_argument("--text-semantics", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = gate(
        *(json.loads(path.read_text(encoding="utf-8")) for path in (args.facts, args.result_candidates, args.card_semantics, args.text_semantics)),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
