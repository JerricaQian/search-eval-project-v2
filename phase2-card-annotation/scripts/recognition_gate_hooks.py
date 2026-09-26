#!/usr/bin/env python3
"""Pluggable semantic hooks for Phase2 recognition gating.

Hooks validate OCR meaning and context; they never rewrite recognized text.
Each hook returns explicit findings so a caller can retry local OCR or block.
"""
from __future__ import annotations

import re
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from semantic_atomicity import merged_tag_reason
from phase2_contract import fulfillment_semantic_kind


Hook = Callable[[dict[str, Any]], list[dict[str, str]]]


def _meaningful(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff¥￥.+%折减]", "", value)


def field_schema_hook(context: dict[str, Any]) -> list[dict[str, str]]:
    patterns = {
        "price": r"[¥￥]\s*\d{1,5}(?:\.\d+)?|\d{1,5}(?:\.\d+)?\s*元|\d{1,5}(?:\.\d+)?\s*起|[Yy#*]\s*\d{1,5}(?:\.\d+)?\s*(?:起|/人)|(?:到手价?|神价|冰爽价|前\d+件).{0,10}[#¥￥Yy*]?\d{1,5}",
        # Search result cards commonly render the score as a bare decimal
        # beside a star icon (for example ``4.6``), rather than ``4.6分``.
        # The role is already constrained by card geometry or a recorded
        # current-pixel review, so this accepts that real UI form without
        # treating an arbitrary numeric token as a rating.
        "rating": r"(?:[0-4](?:\.\d+)?|5(?:\.0+)?)(?:\s*分)?|暂无评分",
        "sales": r"(?:月售|已售|年售|回购|加购).{0,8}\d|\d+\+?消费",
    }
    findings = []
    for item in context["semanticItems"]:
        role, text = item["role"], item["text"]
        if role == "fulfillment":
            if not fulfillment_semantic_kind(text):
                findings.append({"hook": "field_schema", "sourceId": item["sourceId"], "reason": f"{role}_text_does_not_match_field_grammar:{text}"})
            continue
        pattern = patterns.get(role)
        if not pattern:
            continue
        # Rating is a standalone semantic field.  A substring match would
        # accept the "2" in a duration such as "21分钟" after an upstream role
        # mistake, which hides rather than surfaces the Phase2 mismatch.
        matches = re.fullmatch(pattern, text.strip()) if role == "rating" else re.search(pattern, text)
        if not matches:
            findings.append({"hook": "field_schema", "sourceId": item["sourceId"], "reason": f"{role}_text_does_not_match_field_grammar:{text}"})
    return findings


def lexical_coherence_hook(context: dict[str, Any]) -> list[dict[str, str]]:
    findings = []
    for item in context["semanticItems"]:
        if context["factsById"].get(item["sourceId"], {}).get("visualReview"):
            # This hook diagnoses OCR noise. A recorded current-pixel local
            # read is primary evidence; retain structural/atomicity hooks
            # below but do not score its typography as an OCR failure.
            continue
        text = item["text"].strip()
        compact = _meaningful(text)
        chinese = sum("\u4e00" <= char <= "\u9fff" for char in compact)
        latin = sum(char.isascii() and char.isalpha() for char in compact)
        punctuation = sum(not (char.isalnum() or "\u4e00" <= char <= "\u9fff" or char in "¥￥.,+-%折减/×* ") for char in text)
        if len(compact) < 2:
            findings.append({"hook": "lexical_coherence", "sourceId": item["sourceId"], "reason": f"too_short_to_be_semantic_field:{text}"})
        elif text and punctuation / len(text) > 0.35:
            findings.append({"hook": "lexical_coherence", "sourceId": item["sourceId"], "reason": f"punctuation_ratio_too_high:{text}"})
        elif chinese >= 2 and latin >= 5 and latin / max(1, chinese + latin) > 0.35 and not re.search(r"(?:ml|kg|g|cm|mm|km|Na\s*c?Cl|SOHO|S\W*K\W*U|SPA|KTV|Plus|Pro|Heineken|\d+(?:\.\d+)?°P)", text, re.I) and not re.match(r"^[\d\s|@#¥￥.,()+-]*[A-Za-z][A-Za-z0-9.-]{1,15}\s*[\u4e00-\u9fff]", text):
            findings.append({"hook": "lexical_coherence", "sourceId": item["sourceId"], "reason": f"unexplained_mixed_script_text:{text}"})
        elif re.search(r"(.)\1{3,}", compact):
            findings.append({"hook": "lexical_coherence", "sourceId": item["sourceId"], "reason": f"abnormal_character_repetition:{text}"})
    return findings


def _layout_texts_compatible(role: str, primary: str, secondary: str) -> bool:
    left, right = _meaningful(primary), _meaningful(secondary)
    # PSM11 deliberately emits sparse fragments. Empty, one-glyph, or very
    # short secondary text is non-evidence rather than a contradiction.
    if not left or not right:
        return True
    if left == right:
        return True
    if role == "price":
        # OCR commonly confuses the currency glyph with #/Y while preserving
        # the numeric value.  Consensus may accept that layout disagreement,
        # but it never rewrites the published primary text or price number.
        left_values = re.findall(r"[¥￥#Yy]\s*(\d+(?:\.\d+)?)", primary)
        right_values = re.findall(r"[¥￥#Yy]\s*(\d+(?:\.\d+)?)", secondary)
        return bool(left_values and right_values and left_values[0] == right_values[0])
    if role == "rating":
        left_values = re.findall(r"\d(?:\.\d)?", primary)
        right_values = re.findall(r"\d(?:\.\d)?", secondary)
        return bool(left_values and right_values and left_values[0] == right_values[0])
    shorter, longer = sorted((left, right), key=len)
    if len(shorter) <= 1 or len(shorter) / len(longer) < 0.28:
        return True
    containment = len(shorter) >= 4 and shorter in longer and len(shorter) / len(longer) >= 0.35
    common_prefix = 0
    for left_char, right_char in zip(left, right):
        if left_char != right_char:
            break
        common_prefix += 1
    if common_prefix >= 4 and len(shorter) / len(longer) < 0.75:
        return True
    similarity = SequenceMatcher(None, left, right).ratio()
    # Natural-language fields often differ only because PSM 11 returns a
    # shorter crop. Structured numeric fields above deliberately stay strict.
    return containment or similarity >= 0.62


def ocr_consensus_hook(context: dict[str, Any]) -> list[dict[str, str]]:
    """Block core semantics when two independent OCR layouts disagree.

    A fluent-looking Chinese string can still be a hallucinated glyph
    assembly. Regex cannot detect that class reliably; repeatability under a
    second segmentation/layout is a stronger local signal. Missing consensus
    is tolerated for imported legacy facts, while newly extracted facts always
    carry this object.
    """
    findings = []
    core_roles = {"title", "subtitle", "price", "rating", "sales", "fulfillment", "location", "promotion"}
    for item in context["semanticItems"]:
        if item["role"] not in core_roles:
            continue
        source = context["factsById"].get(item["sourceId"], {})
        consensus = source.get("ocrConsensus")
        if not isinstance(consensus, dict):
            continue
        status = consensus.get("status")
        if status and status != "confirmed":
            primary = str(consensus.get("primaryText", item["text"]))
            secondary = str(consensus.get("secondaryText", ""))
            if _layout_texts_compatible(item["role"], primary, secondary):
                continue
            findings.append({
                "hook": "ocr_consensus",
                "sourceId": item["sourceId"],
                "reason": f"independent_layouts_{status}:{primary}|{secondary}",
            })
    return findings


def line_fragmentation_hook(context: dict[str, Any]) -> list[dict[str, str]]:
    """Reject a semantic field when OCR split its visual line into fragments."""
    findings = []
    facts_by_id = context["factsById"]
    all_text = context["acceptedText"]
    for item in context["semanticItems"]:
        if item["role"] not in {"title", "subtitle", "promotion"}:
            continue
        source = facts_by_id.get(item["sourceId"])
        if not source:
            continue
        if source.get("visualReview"):
            continue
        if source.get("atomSplit", {}).get("method") == "delimiter_and_local_foreground_segments":
            # These are intentionally separate fields, proven by local
            # foreground segmentation rather than accidental OCR fragments.
            continue
        x, y, w, h = source["coord"]
        neighbours = []
        for other in all_text:
            if other["id"] == source["id"]:
                continue
            ox, oy, ow, oh = other["coord"]
            vertical_overlap = max(0, min(y + h, oy + oh) - max(y, oy))
            same_line = vertical_overlap >= min(h, oh) * 0.55
            horizontal_gap = max(0, max(x, ox) - min(x + w, ox + ow))
            if same_line and horizontal_gap <= max(h, oh) * 2.2:
                neighbours.append(other["id"])
        structured_short = bool(re.fullmatch(r"(?:\d{1,3}\s*分钟|\d+(?:\.\d+)?\s*(?:km|公里|m|米|小时|分|元))", item["text"].strip(), re.I))
        if neighbours and len(_meaningful(item["text"])) <= 6 and not structured_short:
            findings.append({"hook": "line_fragmentation", "sourceId": item["sourceId"], "reason": f"short_semantic_field_has_same_line_fragments:{','.join(neighbours[:8])}"})
    return findings


def semantic_atomicity_hook(context: dict[str, Any]) -> list[dict[str, str]]:
    """Block merged fields; OCR boxes are evidence units, not UI atoms."""
    findings = []
    for item in context["semanticItems"]:
        text = item["text"].strip()
        region = item.get("region", "")
        if len(_meaningful(text)) == 1:
            findings.append({"hook": "semantic_atomicity", "sourceId": item["sourceId"], "reason": f"one_character_element_forbidden:{text}"})
            continue
        if region not in {"基础信息区", "商家信息区", "标签区"}:
            continue
        parts = [part.strip() for part in re.split(r"[｜|；]", text) if part.strip()]
        if len(parts) > 1:
            findings.append({"hook": "semantic_atomicity", "sourceId": item["sourceId"], "reason": f"delimited_fields_must_be_split:{text}"})
            continue
        if region == "标签区":
            source = context.get("factsById", {}).get(item["sourceId"], {})
            segments = source.get("visualHint", {}).get("horizontalForegroundSegments", [])
            reason = merged_tag_reason(text, segments if isinstance(segments, list) else [])
            if reason:
                findings.append({"hook": "semantic_atomicity", "sourceId": item["sourceId"], "reason": f"multiple_independent_tags_merged:{reason}:{text}"})
    return findings


def dense_numeric_atomicity_hook(context: dict[str, Any]) -> list[dict[str, str]]:
    """Reject common OCR joins in compact price, metric, and time rows.

    These are not language corrections: each rule only identifies an invalid
    publication shape and sends the bounded source line back for local OCR.
    In particular, a detected rating token must become a rating field instead
    of remaining the prefix of an otherwise generic merchant-information row.
    """
    findings = []
    facts_by_id = context.get("factsById", {})
    for item in context["semanticItems"]:
        text = re.sub(r"\s+", "", item["text"])
        role = item["role"]
        reason = ""
        # A score is only 0--5 and belongs in an independent rating field.
        # Check the current-pixel topology first: an attached service item may
        # legitimately contain a duration such as ``60分…`` or ``80分钟``.
        # Its final digit must never be treated as a one-digit rating.
        source = facts_by_id.get(item["sourceId"], {})
        review = source.get("visualReview", {}) if isinstance(source, dict) else {}
        attached_service_item = isinstance(review, dict) and (
            review.get("role") in {"attached_item", "attachment"}
            or review.get("topologySlot") == "text_attachment"
        )
        # A duration such as "1分钟前有人预订" contains the same glyphs as a
        # one-digit score prefix, but "分钟前" is not a rating suffix.
        score_token = r"(?<![\d.])(?:[0-4](?:\.\d+)?|5(?:\.0+)?)分(?!钟|前)"
        has_misplaced_score = bool(re.search(score_token, text)) and role != "rating" and not attached_service_item
        if (has_misplaced_score or ("暂无评分" in text and role != "rating" and not attached_service_item)):
            reason = "rating_token_must_be_a_standalone_rating_field"
        elif re.search(rf"{score_token}\d", text):
            reason = "rating_is_glued_to_following_numeric_field"
        elif (re.search(r"[^0-9.]\d+(?:\.\d+)?km$", text)
              and not re.fullmatch(r"\d+(?:\.\d+)?km", text)
              and not (role == "location" and re.fullmatch(r"距您直线\d+(?:\.\d+)?km", text))):
            reason = "distance_has_non_distance_prefix"
        elif re.search(r"\d{1,2}:\d{3,}", text):
            reason = "session_time_has_extra_trailing_digit"
        elif text.count("¥") + text.count("￥") >= 3:
            reason = "multiple_product_prices_are_merged_in_one_element"
        elif re.search(r"神券\d+减\d{3,}减\d+", text):
            reason = "adjacent_coupon_thresholds_are_merged"
        elif re.match(r"^\d约\d+分钟$", text):
            reason = "delivery_time_has_numeric_prefix"
        if reason:
            findings.append({"hook": "dense_numeric_atomicity", "sourceId": item["sourceId"], "reason": reason})
    return findings


def card_semantic_contract_hook(context: dict[str, Any]) -> list[dict[str, str]]:
    findings = []
    roles_by_card = context["rolesByCard"]
    for card in context["cards"]:
        card_id = str(card.get("id", ""))
        semantic_card = context["cardSemantics"].get(card_id, {})
        if semantic_card.get("partialCardPolicy", {}).get("applied") is True:
            continue
        selected = semantic_card.get("selectedCardType", {})
        card_type = selected.get("cardType", "")
        roles = roles_by_card.get(card_id, set())
        title_items = [item for item in context.get("semanticItemsByCard", {}).get(card_id, []) if item.get("role") == "title"]
        invalid_titles = [item for item in title_items if len(_meaningful(item.get("text", ""))) < 3 or item.get("text", "").strip() in {"到店", "外卖", "上门", "景点", "酒店", "民宿"}]
        for item in invalid_titles:
            findings.append({"hook": "card_semantic_contract", "sourceId": item["sourceId"], "reason": f"title_candidate_is_badge_or_fragment:{item.get('text', '')}"})
        known_complete = card_type and card_type not in {"广告卡", "异构卡"}
        if known_complete and ("title" not in roles or not title_items or len(invalid_titles) == len(title_items)):
            findings.append({"hook": "card_semantic_contract", "sourceId": card_id, "reason": f"complete_known_card_requires_title:cardType={card_type}:roles={','.join(sorted(roles))}"})
        if card_type == "商品卡片" and "price" not in roles:
            findings.append({"hook": "card_semantic_contract", "sourceId": card_id, "reason": f"product_card_requires_title_and_price:roles={','.join(sorted(roles))}"})
        elif card_type == "酒店卡片" and "price" not in roles:
            findings.append({"hook": "card_semantic_contract", "sourceId": card_id, "reason": f"hotel_card_requires_title_and_price:roles={','.join(sorted(roles))}"})
        elif card_type and not (roles & {"title", "price", "rating", "sales", "fulfillment", "location"}):
            findings.append({"hook": "card_semantic_contract", "sourceId": card_id, "reason": f"tag_only_or_no_core_semantic_anchor:roles={','.join(sorted(roles))}"})
    return findings


HOOKS: tuple[Hook, ...] = (
    field_schema_hook,
    lexical_coherence_hook,
    ocr_consensus_hook,
    line_fragmentation_hook,
    semantic_atomicity_hook,
    dense_numeric_atomicity_hook,
    card_semantic_contract_hook,
)


def run_hooks(context: dict[str, Any]) -> list[dict[str, str]]:
    return [finding for hook in HOOKS for finding in hook(context)]
