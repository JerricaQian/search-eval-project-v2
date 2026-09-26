#!/usr/bin/env python3
"""Enumerate and conservatively adjudicate Phase3 semantic relation cues.

Phase2 supplies atomic ownership and visible facts.  This module first exposes
the complete candidate ledger, then offers a deliberately small set of
deterministic adjudicators for relations whose meaning can be normalized from
the JSON alone.  Generic exact/containment matches remain candidates and never
become findings automatically.
"""
from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
from pathlib import Path
from typing import Any

SHARED_SCRIPTS_DIR = Path(__file__).resolve().parents[4] / "scripts"
if str(SHARED_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_SCRIPTS_DIR))

from phase2_bundle_loader import load_phase2_facts


DOWNHANG_REGIONS = {
    "下挂商品区", "文字下挂区", "下挂区", "服务下挂", "特殊下挂", "领域下挂区",
    "append_items", "text_append", "service_append",
}
CONSISTENCY_ROLES = {"subtitle", "size", "specification", "product_attribute"}
TITLE_ROLES = {"title", "subtitle"}
SEMANTIC_ALIAS_GROUPS = {
    "no_added_sucrose": ("无蔗糖", "0蔗糖", "零蔗糖", "0添加蔗糖", "零添加蔗糖", "不添加蔗糖"),
    "type_c": ("type-c", "type c", "typec", "usb-c", "usb c"),
}


def _semantic_alias_hits(text: str) -> dict[str, list[str]]:
    normalized = text.casefold()
    return {
        fact: [alias for alias in aliases if alias.casefold() in normalized]
        for fact, aliases in SEMANTIC_ALIAS_GROUPS.items()
        if any(alias.casefold() in normalized for alias in aliases)
    }


def _semantic_alias_candidate(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any] | None:
    """Expose common rewordings as candidates without auto-declaring redundancy."""
    left_hits = _semantic_alias_hits(left["text"])
    right_hits = _semantic_alias_hits(right["text"])
    shared = sorted(set(left_hits) & set(right_hits))
    if not shared:
        return None
    return {
        "left": left,
        "right": right,
        "lexicalCue": "semantic_alias_overlap",
        "sharedFacts": shared,
        "phase3JudgementRequired": True,
    }


def _normalized_quantity_tokens(text: str) -> set[str]:
    """Return a conservative set of quantities that can describe a spec.

    This deliberately creates *candidates*, not redundancy conclusions.  In
    particular, the same number can describe different facts, so the Phase3
    skill must still verify semantic role and whether either occurrence adds a
    decision-relevant qualifier.
    """
    normalized = text.lower().replace("°", "度")
    matches = re.findall(
        r"\d+(?:\.\d+)?(?:[-~]\d+(?:\.\d+)?)?\s*(?:度|p|ml|l|g|kg|斤|两|罐|瓶|包|条|片|个|份|箱)",
        normalized,
    )
    return {re.sub(r"\s+", "", item) for item in matches}


def _attribute_number_candidate(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any] | None:
    """Find title/basic-information overlaps such as 11.4度 vs 麦汁浓度11.4°P."""
    if not ({left.get("semanticRole"), right.get("semanticRole")} & TITLE_ROLES):
        return None
    if not (
        {left.get("semanticRole"), right.get("semanticRole")} & CONSISTENCY_ROLES
        or {left.get("region"), right.get("region")} & {"base_info", "基础信息区", "基础信息"}
    ):
        return None
    left_numbers = re.findall(r"\d+(?:\.\d+)?", left["text"])
    right_numbers = re.findall(r"\d+(?:\.\d+)?", right["text"])
    overlap = sorted(set(left_numbers) & set(right_numbers))
    if not overlap:
        return None
    title = left if left.get("semanticRole") in TITLE_ROLES else right
    attribute = right if title is left else left
    title_text, attribute_text = title["text"].lower(), attribute["text"].lower()
    # A shared `12` is not enough: it could be "12 bottles" in the title and
    # "12 months" in the attributes.  Require the same value to occur in a
    # beer-degree expression in the title and in a named beer-strength field.
    matching_brewing_values = [
        value for value in overlap
        if re.search(re.escape(value) + r"\s*(?:度|°p|p)", title_text)
        and re.search(r"(?:麦汁浓度|酒精度)[^0-9]{0,8}" + re.escape(value), attribute_text)
    ]
    if not matching_brewing_values:
        return None
    return {
        "left": left,
        "right": right,
        "lexicalCue": "same_numeric_attribute",
        "sharedValues": matching_brewing_values,
        "phase3JudgementRequired": True,
    }


def _count_quantity_variant_candidate(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any] | None:
    """Emit a title/base-info candidate when the same item count is reworded.

    `3条` and `3片` are not automatically identical units, so this is kept as
    a candidate for a reviewer to judge in the product's actual context.
    """
    if not ({left.get("semanticRole"), right.get("semanticRole")} & TITLE_ROLES):
        return None
    if not ({left.get("region"), right.get("region")} & {"base_info", "基础信息区", "基础信息"}):
        return None
    title = left if left.get("semanticRole") in TITLE_ROLES else right
    attribute = right if title is left else left
    title_counts = set(re.findall(r"\d+\s*(?:条|片|包|个|件)", title["text"]))
    attribute_counts = set(re.findall(r"\d+\s*(?:条|片|包|个|件)", attribute["text"]))
    title_values = {re.match(r"\d+", value).group(0) for value in title_counts}
    attribute_values = {re.match(r"\d+", value).group(0) for value in attribute_counts}
    overlap = sorted(title_values & attribute_values)
    if not overlap:
        return None
    return {
        "left": left,
        "right": right,
        "lexicalCue": "same_count_quantity_variant",
        "sharedValues": overlap,
        "phase3JudgementRequired": True,
    }


def _size_code_candidate(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any] | None:
    """Find a title size code repeated by a standalone base-information code."""
    if not ({left.get("semanticRole"), right.get("semanticRole")} & TITLE_ROLES):
        return None
    if not ({left.get("region"), right.get("region")} & {"base_info", "基础信息区", "基础信息"}):
        return None
    title = left if left.get("semanticRole") in TITLE_ROLES else right
    attribute = right if title is left else left
    title_codes = set(re.findall(r"(?<![a-z])(?:xxl|xl|[sml])(?=码|号|\b)", title["text"].lower()))
    attribute_code = attribute["text"].strip().lower()
    if attribute_code not in title_codes or attribute_code not in {"s", "m", "l", "xl", "xxl"}:
        return None
    return {
        "left": left,
        "right": right,
        "lexicalCue": "same_size_code",
        "sharedValues": [attribute_code.upper()],
        "phase3JudgementRequired": True,
    }


def _title_self_repeat_candidates(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Spot repeated title fragments (e.g. two occurrences of 3-4斤).

    We only emit quantified product fragments.  This keeps the candidate list
    auditable and avoids treating ordinary repeated stop words as a finding.
    """
    if item.get("semanticRole") not in TITLE_ROLES:
        return []
    text = item["text"]
    fragments = re.findall(r"\d+(?:[-~]\d+)?\s*(?:斤|两|kg|g|ml|l|罐|瓶|包|条|片|个|份|箱)", text.lower())
    repeated = sorted({frag for frag in fragments if fragments.count(frag) > 1})
    candidates = [{
        "element": item,
        "lexicalCue": "title_internal_repeated_quantified_fragment",
        "repeatedFragment": fragment,
        "occurrences": fragments.count(fragment),
        "phase3JudgementRequired": True,
    } for fragment in repeated]
    for fact, aliases in _semantic_alias_hits(text).items():
        if len(aliases) < 2:
            continue
        candidates.append({
            "element": item,
            "lexicalCue": "title_internal_semantic_alias_repeat",
            "normalizedFact": fact,
            "matchedAliases": aliases,
            "occurrences": len(aliases),
            "phase3JudgementRequired": True,
        })
    return candidates


def _quantity_range_conflict_candidate(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any] | None:
    """Emit a candidate when a title's weight range exceeds a card-level cap.

    The unit conversion is deliberately limited to jin/kg and only produces a
    Phase3 candidate.  For example, ``3-6斤`` is 1.5-3kg while ``约2kg以下``
    caps the same item at about 2kg; the overlap does not remove the ambiguity
    created by the title's 3kg upper bound.
    """
    if not ({left.get("semanticRole"), right.get("semanticRole")} & TITLE_ROLES):
        return None
    if not ({left.get("region"), right.get("region")} & {"base_info", "基础信息区", "基础信息"}):
        return None
    title = left if left.get("semanticRole") in TITLE_ROLES else right
    attribute = right if title is left else left
    range_match = re.search(r"(\d+(?:\.\d+)?)\s*[-~]\s*(\d+(?:\.\d+)?)\s*(斤|kg)", title["text"].lower())
    cap_match = re.search(r"(?:约\s*)?(\d+(?:\.\d+)?)\s*kg\s*(?:以下|以内)", attribute["text"].lower())
    if not range_match or not cap_match:
        return None
    lower, upper, unit = range_match.groups()
    multiplier = 0.5 if unit == "斤" else 1.0
    upper_kg = float(upper) * multiplier
    cap_kg = float(cap_match.group(1))
    if upper_kg <= cap_kg:
        return None
    return {
        "left": left,
        "right": right,
        "lexicalCue": "quantity_range_exceeds_card_cap",
        "normalizedTitleRangeKg": [float(lower) * multiplier, upper_kg],
        "normalizedCapKg": cap_kg,
        "phase3JudgementRequired": True,
    }


def _price_semantic_candidates(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Expose mixed price semantics inside one visible price line for Phase3.

    A starting price (``¥24.9起``) and an arrival-price label are not
    interchangeable.  The line may still be valid when the scope is made
    explicit, so this remains a candidate instead of an automatic verdict.
    """
    if item.get("semanticRole") != "price":
        return []
    text = item["text"]
    if not re.search(r"[¥￥]\s*\d+(?:\.\d+)?\s*起", text) or "到手价" not in text:
        return []
    return [{
        "element": item,
        "lexicalCue": "start_price_and_to_hand_price_in_same_claim",
        "phase3JudgementRequired": True,
    }]


def adjudicate_authenticity_candidate(candidate: dict[str, Any]) -> dict[str, Any] | None:
    """Return a deterministic conflict only for a closed, auditable cue set."""
    cue = candidate.get("lexicalCue")
    if cue == "quantity_range_exceeds_card_cap":
        left = candidate.get("left") or {}
        right = candidate.get("right") or {}
        title = left if left.get("semanticRole") in TITLE_ROLES else right
        attribute = right if title is left else left
        title_range = candidate.get("normalizedTitleRangeKg")
        cap = candidate.get("normalizedCapKg")
        if not (
            isinstance(title_range, list) and len(title_range) == 2
            and all(isinstance(value, (int, float)) for value in title_range)
            and isinstance(cap, (int, float)) and float(title_range[1]) > float(cap)
        ):
            return None
        return {
            "lexicalCue": cue,
            "leftElementId": left.get("elementId"),
            "rightElementId": right.get("elementId"),
            "titleElementId": title.get("elementId"),
            "attributeElementId": attribute.get("elementId"),
            "titleText": title.get("text"),
            "attributeText": attribute.get("text"),
            "normalizedTitleRangeKg": title_range,
            "normalizedCapKg": cap,
            "verdict": "conflict",
            "reason": "标题重量范围的上限超过基础信息给出的同商品重量上限，两种表述不能同时作为同一规格成立。",
        }
    if cue == "start_price_and_to_hand_price_in_same_claim":
        element = candidate.get("element") or {}
        text = str(element.get("text") or "")
        if not (re.search(r"[¥￥]\s*\d+(?:\.\d+)?\s*起", text) and "到手价" in text):
            return None
        return {
            "lexicalCue": cue,
            "elementId": element.get("elementId"),
            "text": text,
            "verdict": "conflict",
            "reason": "同一价格声明同时使用“起”和“到手价”，起步价被表述为确定到手价，价格口径不唯一。",
        }
    if cue == "same_visible_identity_conflicting_core_facts":
        conflicts = candidate.get("conflictingFacts") or []
        if not conflicts or normalized_text(str(candidate.get("leftIdentityText") or "")) != normalized_text(str(candidate.get("rightIdentityText") or "")):
            return None
        return {
            "lexicalCue": cue,
            "leftCardId": candidate.get("leftCardId"),
            "rightCardId": candidate.get("rightCardId"),
            "leftIdentityElementId": candidate.get("leftIdentityElementId"),
            "rightIdentityElementId": candidate.get("rightIdentityElementId"),
            "identityText": candidate.get("leftIdentityText"),
            "conflictingFacts": conflicts,
            "verdict": "conflict",
            "reason": "两个商卡展示同一商家与分店身份，但可直接比较的核心经营事实不一致，用户无法由可见信息区分两个供给对象。",
        }
    return None


def adjudicate_redundancy_candidate(candidate: dict[str, Any]) -> dict[str, Any] | None:
    """Return a deterministic duplicate only when deletion is demonstrably lossless."""
    cue = candidate.get("lexicalCue")
    left = candidate.get("left") or {}
    right = candidate.get("right") or {}
    title = left if left.get("semanticRole") in TITLE_ROLES else right
    attribute = right if title is left else left
    shared = candidate.get("sharedValues") or []

    if cue == "same_numeric_attribute":
        # Keep this closed to the beer wort-concentration wording represented
        # by the current golden contract.  Alcohol degree can be ambiguous and
        # must remain a manual candidate.
        if "麦汁浓度" not in str(attribute.get("text") or ""):
            return None
        normalized_fact = f"麦汁浓度={','.join(map(str, shared))}P"
    elif cue == "same_count_quantity_variant":
        title_text = str(title.get("text") or "")
        attribute_text = str(attribute.get("text") or "")
        title_units = set(re.findall(r"\d+\s*(条|片|包|个|件)", title_text))
        attribute_units = set(re.findall(r"\d+\s*(条|片|包|个|件)", attribute_text))
        same_unit = bool(title_units & attribute_units)
        contextual_equivalence = bool(re.search(r"安睡裤|安心裤|卫生巾|纸尿裤", title_text))
        if not (same_unit or contextual_equivalence):
            return None
        normalized_fact = f"商品件数={','.join(map(str, shared))}"
    elif cue == "same_size_code":
        normalized_fact = f"尺码={','.join(map(str, shared))}"
    else:
        # exact/containment only proves lexical overlap, not semantic
        # redundancy.  It is intentionally kept out of automatic findings.
        return None

    return {
        "lexicalCue": cue,
        "leftElementId": left.get("elementId"),
        "rightElementId": right.get("elementId"),
        "leftText": left.get("text"),
        "rightText": right.get("text"),
        "normalizedFact": normalized_fact,
        "verdict": "duplicate",
        "noLossReason": "两处均表达同一商品属性值，删除基础信息中的重复值不会损失新的决策信息。",
    }


def adjudicate_self_repeat_candidate(candidate: dict[str, Any]) -> dict[str, Any] | None:
    """Adjudicate a repeated quantified fragment inside one title."""
    if candidate.get("lexicalCue") != "title_internal_repeated_quantified_fragment":
        return None
    element = candidate.get("element") or {}
    occurrences = candidate.get("occurrences")
    fragment = candidate.get("repeatedFragment")
    if not isinstance(occurrences, int) or occurrences < 2 or not isinstance(fragment, str) or not fragment:
        return None
    return {
        "lexicalCue": candidate["lexicalCue"],
        "elementId": element.get("elementId"),
        "text": element.get("text"),
        "repeatedFragment": fragment,
        "occurrences": occurrences,
        "normalizedFact": f"标题规格={fragment}",
        "verdict": "duplicate",
        "noLossReason": "同一标题内的相同量化规格重复出现，删除其中一次不会损失信息。",
    }


def text_of(element: dict[str, Any]) -> str:
    facts = element.get("textFacts") if isinstance(element.get("textFacts"), dict) else {}
    if isinstance(facts.get("rawText"), str):
        return facts["rawText"].strip()
    return re.sub(r"^原文[:：]\s*", "", str(element.get("内容简述", ""))).strip()


def normalized_text(text: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text.lower())


def atom(card_id: str, region: str, element: dict[str, Any]) -> dict[str, Any]:
    facts = element.get("textFacts") if isinstance(element.get("textFacts"), dict) else {}
    return {
        "cardId": card_id,
        "region": region,
        "elementId": element.get("id"),
        "elementType": element.get("元素类型"),
        "text": text_of(element),
        "semanticRole": facts.get("semanticRole"),
        "coord": element.get("坐标"),
    }


def _merchant_identity_profile(card: dict[str, Any], atoms: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Extract exact visible merchant identity and closed comparable facts."""
    if "商家卡片" not in str(card.get("卡片类型") or ""):
        return None
    identities = [
        item for item in atoms
        if item.get("semanticRole") == "title" and item.get("region") not in DOWNHANG_REGIONS
    ]
    if not identities:
        return None
    identity = identities[0]
    facts: dict[str, dict[str, str]] = {}
    patterns = (
        ("评分", re.compile(r"\d+(?:\.\d+)?\s*分")),
        ("月售", re.compile(r"月售\s*\d+\+?")),
        ("距离", re.compile(r"\d+(?:\.\d+)?\s*km", re.I)),
    )
    for label, pattern in patterns:
        for item in atoms:
            match = pattern.search(str(item.get("text") or ""))
            if match:
                facts[label] = {"value": normalized_text(match.group(0)), "text": match.group(0), "elementId": str(item.get("elementId") or "")}
                break
    return {"cardId": str(card.get("cardId") or ""), "identity": identity, "facts": facts}


def _cross_card_authenticity_candidates(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for left, right in itertools.combinations(profiles, 2):
        left_identity = left["identity"]
        right_identity = right["identity"]
        if normalized_text(left_identity["text"]) != normalized_text(right_identity["text"]):
            continue
        conflicts = []
        for label in sorted(set(left["facts"]) & set(right["facts"])):
            left_fact, right_fact = left["facts"][label], right["facts"][label]
            if left_fact["value"] != right_fact["value"]:
                conflicts.append({
                    "factName": label,
                    "leftText": left_fact["text"],
                    "rightText": right_fact["text"],
                    "leftElementId": left_fact["elementId"],
                    "rightElementId": right_fact["elementId"],
                })
        if conflicts:
            candidates.append({
                "lexicalCue": "same_visible_identity_conflicting_core_facts",
                "leftCardId": left["cardId"],
                "rightCardId": right["cardId"],
                "leftIdentityElementId": left_identity["elementId"],
                "rightIdentityElementId": right_identity["elementId"],
                "leftIdentityText": left_identity["text"],
                "rightIdentityText": right_identity["text"],
                "conflictingFacts": conflicts,
                "phase3JudgementRequired": False,
            })
    return candidates


def derive_relation_candidates(manifest: dict[str, Any]) -> dict[str, Any]:
    authenticity: list[dict[str, Any]] = []
    redundancy: list[dict[str, Any]] = []
    merchant_profiles: list[dict[str, Any]] = []
    for card in manifest.get("cards", []):
        card_id = str(card.get("cardId", ""))
        atoms: list[dict[str, Any]] = []
        titles: list[dict[str, Any]] = []
        targets: list[dict[str, Any]] = []
        for region_payload in card.get("regions", []):
            region = str(region_payload.get("name", ""))
            for element in region_payload.get("elements", []):
                if not isinstance(element, dict) or element.get("isExcluded") is True:
                    continue
                render = element.get("render") if isinstance(element.get("render"), dict) else {}
                visual = element.get("visual") if isinstance(element.get("visual"), dict) else {}
                if render.get("visibleStatus") != "confirmed" or visual.get("visualStatus") == "uncertain":
                    continue
                current = atom(card_id, region, element)
                atoms.append(current)
                if current["semanticRole"] == "title":
                    titles.append(current)
                if (
                    element.get("元素类型") == "图片"
                    or region in DOWNHANG_REGIONS
                    or region in {"base_info", "基础信息区", "基础信息"}
                    or current["semanticRole"] in CONSISTENCY_ROLES
                ):
                    targets.append(current)
        authenticity.append({
            "cardId": card_id,
            "titleAtoms": titles,
            "targetAtoms": targets,
            "candidatePairs": [
                {
                    "title": title,
                    "target": target,
                    "relationType": (
                        "title_to_image" if target["elementType"] == "图片"
                        else "title_to_size" if target["semanticRole"] in {"size", "specification"}
                        else "title_to_attribute"
                    ),
                    "phase3JudgementRequired": True,
                }
                for title in titles for target in targets if title["elementId"] != target["elementId"]
            ],
        })

        # Images use the legacy placeholder `原文:[图片]`; it is annotation
        # metadata rather than page text and must never produce a false exact
        # match in an information-redundancy scan.
        text_atoms = [
            item for item in atoms
            if item["text"] and item.get("elementType") != "图片" and item["text"] != "原文:[图片]"
        ]
        pairs: list[dict[str, Any]] = []
        authenticity_internal: list[dict[str, Any]] = []
        for left, right in itertools.combinations(text_atoms, 2):
            left_norm = normalized_text(left["text"])
            right_norm = normalized_text(right["text"])
            if not left_norm or not right_norm:
                continue
            exact = left_norm == right_norm
            containment = min(len(left_norm), len(right_norm)) >= 2 and (left_norm in right_norm or right_norm in left_norm)
            if exact or containment:
                pairs.append({
                    "left": left,
                    "right": right,
                    "lexicalCue": "exact" if exact else "containment",
                    "phase3JudgementRequired": True,
                })
            semantic_candidate = _attribute_number_candidate(left, right)
            if semantic_candidate:
                pairs.append(semantic_candidate)
            quantity_candidate = _count_quantity_variant_candidate(left, right)
            if quantity_candidate:
                pairs.append(quantity_candidate)
            range_candidate = _quantity_range_conflict_candidate(left, right)
            if range_candidate:
                authenticity_internal.append(range_candidate)
            size_candidate = _size_code_candidate(left, right)
            if size_candidate:
                pairs.append(size_candidate)
            alias_candidate = _semantic_alias_candidate(left, right)
            if alias_candidate and not any(
                existing.get("left", {}).get("elementId") == left.get("elementId")
                and existing.get("right", {}).get("elementId") == right.get("elementId")
                and existing.get("lexicalCue") == alias_candidate["lexicalCue"]
                for existing in pairs
            ):
                pairs.append(alias_candidate)
        self_repeats = [candidate for item in text_atoms for candidate in _title_self_repeat_candidates(item)]
        authenticity_internal.extend(candidate for item in text_atoms for candidate in _price_semantic_candidates(item))
        authenticity[-1]["internalCandidates"] = authenticity_internal
        profile = _merchant_identity_profile(card, atoms)
        if profile:
            merchant_profiles.append(profile)
        redundancy.append({
            "cardId": card_id,
            "examinedAtoms": text_atoms,
            "candidatePairs": pairs,
            "selfRepeatCandidates": self_repeats,
            "scanCoverage": {
                "status": "completed",
                "textAtomCount": len(text_atoms),
                "scannedElementIds": [item.get("elementId") for item in text_atoms],
                "scannedRegions": sorted({str(item.get("region", "")) for item in text_atoms}),
                "crossChecks": [
                    "title/subtitle ↔ basic information",
                    "title/subtitle ↔ tags/price/promotion",
                    "tag ↔ price/promotion",
                    "title internal repeated quantified fragments",
                ],
                "crossCheckLedger": [
                    {
                        "checkType": check_type,
                        "status": "candidates_enumerated",
                        "candidateCount": (
                            len(self_repeats) if check_type == "title internal repeated quantified fragments"
                            else sum(1 for pair in pairs if pair.get("left", {}).get("region") != pair.get("right", {}).get("region"))
                        ),
                    }
                    for check_type in (
                        "title/subtitle ↔ basic information",
                        "title/subtitle ↔ tags/price/promotion",
                        "tag ↔ price/promotion",
                        "title internal repeated quantified fragments",
                    )
                ],
            },
        })
    return {
        "contractVersion": "phase3.relation-candidates.v4",
        "query": manifest.get("query", ""),
        "authenticityCandidates": authenticity,
        "crossCardAuthenticityCandidates": _cross_card_authenticity_candidates(merchant_profiles),
        "redundancyCandidates": redundancy,
        "notes": [
            "候选对不是真实性冲突或信息冗余结论，必须由对应 Phase3 Skill 终判",
            "candidatePairs=[] 仅表示没有字面或本扫描器可表达的候选，不是“无信息冗余”的充分证据。",
            "本文件是 Phase3 派生测量产物；绝不向 Atomic 黄金 JSON 写入 candidatePairs 或任何评测结论。",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract Phase3 semantic relation candidates")
    parser.add_argument("manifest", type=Path, nargs="?")
    parser.add_argument("--normalized-input", type=Path)
    parser.add_argument("--evidence-input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.normalized_input:
        if args.manifest or not args.evidence_input:
            parser.error("--normalized-input requires --evidence-input and cannot be combined with manifest")
        manifest = load_phase2_facts(normalized_path=args.normalized_input, evidence_path=args.evidence_input)
    else:
        if not args.manifest or args.evidence_input:
            parser.error("provide manifest, or --normalized-input with --evidence-input")
        manifest = load_phase2_facts(manifest_path=args.manifest)
    result = derive_relation_candidates(manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "cards": len(result["authenticityCandidates"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
