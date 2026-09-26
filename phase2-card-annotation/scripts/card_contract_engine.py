#!/usr/bin/env python3
"""Evaluate result-card facts against explicit recognition contracts.

The engine is deterministic and screenshot-local. It never consumes golden
answers or search-word-specific expected types. The title-semantic stage may
establish a known family when compatible reviewed topology proves its shape;
otherwise a known type must satisfy its minimum structural contract. Explicit
advertising then precedes the heterogeneous fallback.
"""
from __future__ import annotations

import re
from typing import Any

from card_type_registry import known_result_types
from phase2_contract import fulfillment_semantic_kind


KNOWN_RESULT_TYPES = known_result_types()


def _title_text(card: dict[str, Any], facts: dict[str, Any]) -> tuple[str, str]:
    """Read the title owned by this card, never the query or neighbouring copy.

    A current-pixel title field is strongest. Without one, accept a single
    upper-card OCR title candidate; multiple plausible lines are ambiguous and
    deliberately leave classification to the content/topology resolver.
    """
    coord = card.get("coord", [])
    if not isinstance(coord, list) or len(coord) != 4:
        return "", ""
    card_id = card.get("id")
    texts = [
        item for item in facts.get("candidates", {}).get("text", [])
        if _usable(item) and isinstance(item.get("coord"), list)
        and len(item["coord"]) == 4 and _overlap(item["coord"], coord)
    ]
    reviewed = [
        item for item in texts
        if isinstance(item.get("visualReview"), dict)
        and item["visualReview"].get("cardId") == card_id
        and item["visualReview"].get("role") == "title"
        and item["visualReview"].get("topologySlot") in {"title", "entity_title"}
        and str(item.get("text", "")).strip()
    ]
    if len(reviewed) == 1:
        return str(reviewed[0]["text"]).strip(), str(reviewed[0].get("id", ""))
    if reviewed:
        return "", ""
    x, y, width, height = coord
    candidates = [
        item for item in texts
        if not item.get("visualReview")
        and item["coord"][1] < y + max(100, height * 0.42)
        and (item["coord"][0] > x + width * 0.18 or item["coord"][2] > width * 0.40)
        and len(_meaningful(str(item.get("text", "")))) >= 3
        and not re.search(r"[¥￥]\s*\d|\d+(?:\.\d+)?\s*(?:元|公里|km|分钟|分|条)|月售|已售|起送|配送费", str(item.get("text", "")), re.I)
    ]
    if len(candidates) == 1:
        return str(candidates[0]["text"]).strip(), str(candidates[0].get("id", ""))
    return "", ""


def title_semantic_family(card: dict[str, Any], facts: dict[str, Any]) -> dict[str, str]:
    """High-precision, title-only card family; empty means use card contents.

    Merchant attachment variants and the primary-point result position are
    intentionally *not* inferred from a name. Those require topology/context.
    Domain terms must describe the title's head entity, rather than a product
    modifier such as "酒店用品" or "电影周边".
    """
    title, source_id = _title_text(card, facts)
    if not title:
        return {"family": "", "title": "", "sourceId": ""}
    compact = re.sub(r"\s+", "", title)
    # Explicit bundles precede lodging, since their titles often contain 酒店.
    if re.search(r"酒店套餐|度假套餐|自由行|跟团游|\d+天\d+晚|机票.{0,12}酒店", compact):
        family = "度假酒店套餐卡片"
    elif re.search(r"(?:酒店|宾馆|客栈|民宿|旅馆|公寓酒店)(?:[（(].*[）)])?$", compact) or re.search(r"(?:酒店|民宿|宾馆)[（(]", compact):
        family = "酒店卡片"
    elif re.search(r"演唱会|音乐会|话剧|舞台剧|脱口秀|歌剧|音乐剧|电影《|影片《|《[^》]+》(?:电影|演出|话剧)|(?:演出|电影|观影)门票", compact):
        family = "演出电影卡片"
    elif re.search(r"(?:地铁站|大学|医院|景区|主题乐园|博物馆|公园|机场|火车站)$", compact):
        family = "主点卡片"
    elif re.search(r"(?:餐厅|饭店|餐馆|火锅店|烧烤店|便利店|超市|购物中心|商场|美发店|理发店|健身房|洗浴中心)$", compact):
        family = "商家卡片"
    elif re.search(r"(?:耳机|手机|充电器|数据线|洗发水|面膜|纸巾|牛奶|啤酒|饼干|蛋糕|药片|颗粒|胶囊)(?:[（(].*[）)])?$", compact) or re.search(r"\d+(?:\.\d+)?\s*(?:g|kg|ml|L|片|粒|瓶|盒|包|袋|支|罐|听)(?:[xX*×]\d+)?$", compact, re.I):
        family = "商品卡片"
    else:
        family = ""
    return {"family": family, "title": title, "sourceId": source_id}


def _overlap(box: list[int], container: list[int]) -> bool:
    return box[0] < container[0] + container[2] and box[0] + box[2] > container[0] and box[1] < container[1] + container[3] and box[1] + box[3] > container[1]


def _usable(item: dict[str, Any]) -> bool:
    return item.get("route") != "rejected"


def _intersection_area(first: list[int], second: list[int]) -> int:
    x0, y0 = max(first[0], second[0]), max(first[1], second[1])
    x1 = min(first[0] + first[2], second[0] + second[2])
    y1 = min(first[1] + first[3], second[1] + second[3])
    return max(0, x1 - x0) * max(0, y1 - y0)


def _photo_is_fulfillment_badge(photo: dict[str, Any], texts: list[dict[str, Any]]) -> bool:
    """Resolve compact fulfillment UI before using a CV box as media.

    Photo detectors routinely return a coloured pill/label as an image.  A
    taxonomy-backed fulfillment field occupying most of that candidate is
    stronger evidence than generic texture.  Relative coverage keeps this from
    suppressing a real photograph that merely contains a small overlay label.
    """
    box = photo.get("coord", [])
    if not isinstance(box, list) or len(box) != 4 or box[2] <= 0 or box[3] <= 0:
        return False
    photo_area = box[2] * box[3]
    for text in texts:
        text_box = text.get("coord", [])
        if not fulfillment_semantic_kind(str(text.get("text", ""))) or not isinstance(text_box, list) or len(text_box) != 4:
            continue
        text_area = max(1, text_box[2] * text_box[3])
        shared = _intersection_area(box, text_box)
        if shared / text_area >= 0.70 and photo_area / text_area <= 12:
            return True
    return False


def _meaningful(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff¥￥]+", "", value)


def price_evidence(item: dict[str, Any], card_coord: list[int]) -> dict[str, bool]:
    """Recognize price evidence without correcting or replacing OCR text."""
    text = str(item.get("text", ""))
    exact = bool(re.search(r"[¥￥]\s*\d|\d+(?:\.\d+)?\s*元", text))
    contextual = bool(re.search(
        r"(?:到手价|到手从|神价|低价|特价|券后|票价|价格|前\d+件).{0,10}[#¥￥Yy半*]?[A-Z]?(?:\d|[OoQ])"
        r"|\d+(?:\.\d+)?\s*起(?:\D|$)"
        r"|[Yy][A-Z]?(?:\d+(?:\.\d+)?)\s*(?:起|/人)",
        text, re.I,
    ))
    x, y, width, height = card_coord
    tx, ty, _, th = item.get("coord", [0, 0, 0, 0])
    color = item.get("visualHint", {}).get("colorRole", "unknown")
    numeric_range = color in {"red", "orange"} and not re.search(r"20\d{2}[-/.年]\d{1,2}", text) and bool(re.search(r"\d{2,4}\s*[-–]\s*\d{2,4}", text))
    contextual = contextual or numeric_range
    digits = sum(char.isdigit() for char in text)
    # Full-width list cards usually place price in the right information
    # column, while two-column hotel cells place it near the cell's left edge.
    # Geometry therefore rejects only text outside the card, not the first
    # fifth of a valid narrow cell.
    lower_price_x = x + width * (0.02 if width < 800 else 0.20)
    horizontally_plausible = lower_price_x <= tx <= x + width * 0.92
    vertically_plausible = ty + th >= y + height * 0.20
    obvious_non_price = bool(re.search(r"分钟|公里|\bkm\b|评分|\d(?:\.\d+)?\s*分|\d+(?:\.\d+)?万?条|起送|配送费|月售|已售|20\d{2}[-/.年]|\d+(?:\.\d+)?\s*(?:ml|kg|g|片|包|袋|听|瓶|盒)|酒精|浓度|保质期", text, re.I)) and not contextual
    coupon_threshold_only = bool(re.search(r"神券.{0,8}(?:减|至)\s*\d+", text)) and not contextual
    # A bare 0–5 decimal beside the rating star is often orange.  Colour and
    # digits alone must not turn that score into a product price; a visual
    # price needs currency/context unless the value is outside score range.
    bare_rating_shape = bool(re.fullmatch(r"[0-5](?:\.\d+)?", text.strip()))
    visual = color in {"red", "orange"} and digits >= 2 and horizontally_plausible and vertically_plausible and not obvious_non_price and not coupon_threshold_only and not bare_rating_shape
    return {"exact": exact, "contextual": contextual, "visual": visual}


def price_evidence_items(items: list[dict[str, Any]], card_coord: list[int]) -> list[dict[str, Any]]:
    return [item for item in items if any(price_evidence(item, card_coord).values())]


def _geometry_validation(card: dict[str, Any], facts: dict[str, Any], profile: dict[str, Any] | None) -> dict[str, Any]:
    """Return a soft type-specific geometry signal learned from clean goldens.

    Geometry can separate otherwise-passing types, but it can never satisfy a
    missing semantic/structural minimum group or reject a novel layout alone.
    """
    if not profile or profile.get("status") != "learned":
        return {"available": False, "withinLearnedRange": None, "matchedRatio": 0.0, "checks": {}}
    viewport = facts.get("viewport", {})
    viewport_width = float(viewport.get("width", 0))
    viewport_height = float(viewport.get("height", 0))
    coord = card.get("coord", [])
    if viewport_width <= 0 or viewport_height <= 0 or not isinstance(coord, list) or len(coord) != 4 or coord[3] <= 0:
        return {"available": False, "withinLearnedRange": None, "matchedRatio": 0.0, "checks": {}}
    values = {
        "widthRatio": coord[2] / viewport_width,
        "heightRatio": coord[3] / viewport_height,
        "aspectRatio": coord[2] / coord[3],
    }
    checks: dict[str, Any] = {}
    for field, value in values.items():
        distribution = profile.get("distributions", {}).get(field)
        if not distribution:
            continue
        observed_min = float(distribution["minimum"])
        observed_max = float(distribution["maximum"])
        span = max(observed_max - observed_min, abs(observed_max) * 0.10, 0.02 if field != "aspectRatio" else 0.20)
        lower = max(0.0, observed_min - span * 0.35)
        upper = observed_max + span * 0.35
        checks[field] = {
            "value": round(value, 4), "learnedRangeWithMargin": [round(lower, 4), round(upper, 4)],
            "matched": lower <= value <= upper,
        }
    matched_count = sum(bool(item["matched"]) for item in checks.values())
    matched_ratio = matched_count / len(checks) if checks else 0.0
    return {
        "available": bool(checks), "withinLearnedRange": bool(checks) and matched_count == len(checks),
        "matchedRatio": round(matched_ratio, 4), "checks": checks,
        "source": "approved_golden_aggregate_geometry",
    }


def extract_features(card: dict[str, Any], facts: dict[str, Any], structure_blocks: dict[str, dict[str, Any]]) -> dict[str, bool]:
    coord = card.get("coord", [0, 0, 0, 0])
    x, y, width, height = coord
    texts = [item for item in facts.get("candidates", {}).get("text", []) if _usable(item) and _overlap(item.get("coord", [0, 0, 0, 0]), coord)]
    raw_photos = [item for item in facts.get("candidates", {}).get("photos", []) if _usable(item) and _overlap(item.get("coord", [0, 0, 0, 0]), coord)]
    photos = [item for item in raw_photos if not _photo_is_fulfillment_badge(item, texts)]
    joined = "\n".join(str(item.get("text", "")) for item in texts)
    title_like = []
    structured_only = re.compile(r"^(?:[¥￥]?\d[\d.]*|\d+(?:\.\d+)?(?:km|公里|分钟|条|分)|月售\d+|已售\d+)$", re.I)
    boundary_evidence = set(card.get("evidence", []))
    reviewed_topology = card.get("reviewedTopology", {}) if isinstance(card.get("reviewedTopology"), dict) else {}
    topology_regions = {str(item.get("slot", "")) for item in reviewed_topology.get("regions", []) if isinstance(item, dict)}
    topology_items = [item for item in reviewed_topology.get("attachedItems", []) if isinstance(item, dict)]
    reviewed_product_topology = (
        str(card.get("reviewedCardType", "")) == "商品卡片"
        and {"head_media", "title", "price"}.issubset(topology_regions)
        and not topology_items
    )
    reviewed_merchant_variant = str(card.get("reviewedMerchantVariant", ""))
    reviewed_text_downhang = (
        {"merchant_head", "merchant_info", "text_attachment"}.issubset(topology_regions)
        and bool(topology_items)
    )
    title_ceiling = y + max(100, height * (0.72 if "two_column_grid_cell_boundary" in boundary_evidence else 0.45))
    for item in texts:
        value = str(item.get("text", "")).strip()
        if item.get("coord", [0, 0, 0, 0])[1] <= title_ceiling and len(_meaningful(value)) >= 2 and not structured_only.fullmatch(value):
            title_like.append(item)
    left_heads = [item for item in photos if item["coord"][0] < x + width * 0.42 and item["coord"][1] < y + height * 0.68]
    seed = structure_blocks.get(str(card.get("seedBlockId", "")))
    seed_bottom = seed["coord"][1] + seed["coord"][3] if seed else y + height * 0.45
    member_ids = card.get("memberBlockIds", [])
    attached_blocks = [structure_blocks[item_id] for item_id in member_ids if item_id in structure_blocks and structure_blocks[item_id]["coord"][1] >= seed_bottom]
    attached_text_blocks = [block for block in attached_blocks if block.get("layoutCandidate") == "text_only"]
    attached_texts = [item for item in texts if any(_overlap(item.get("coord", [0, 0, 0, 0]), block["coord"]) for block in attached_text_blocks)]
    attached_joined = "\n".join(str(item.get("text", "")) for item in attached_texts)
    service_pattern = r"预约|可约|取号|排队|上门服务|到店体验|美发|理发|剪发|洗护|保洁|家电维修|手机维修|按摩|体检|露营|漂流|游乐|剧本|问诊"
    attached_photos = [item for item in photos if item["coord"][1] >= seed_bottom and item["coord"][0] >= x + width * 0.18]
    graphic_hint = (
        card.get("classificationHint", {}).get("cardType") == "商家卡片_图文下挂"
        or bool(card.get("attachedProductPhotoIds"))
        or ("merchant_head" in topology_regions and "attached_goods" in topology_regions and bool(topology_items))
    ) and not reviewed_text_downhang
    poster_media = any(item["coord"][3] >= item["coord"][2] * 1.18 and item["coord"][2] <= width * 0.45 for item in photos)
    price_signals = [price_evidence(item, coord) for item in texts]
    repeated_list_boundary = bool({"repeated_left_image_right_text_seed", "learned_repeat_interval_backfill", "left_media_anchor_split"} & boundary_evidence)
    merchant_graphic_boundary = (
        ("merchant_head" in topology_regions and "merchant_info" in topology_regions
         and "attached_goods" in topology_regions and bool(topology_items))
        or (
            not reviewed_text_downhang
            and "left_square_merchant_head" in boundary_evidence
            and "right_side_attached_product_image_group" in boundary_evidence
        )
    )
    viewport_width = float(facts.get("viewport", {}).get("width", 0))
    hotel_room_title = bool(re.search(r"电竞.*房|双人.*房|双床房|大床房?|整套\s*\d+\s*室|可长租", joined))
    hotel_room_specs = bool(re.search(r"\d+(?:-\d+)?\s*m[²2]?|\d+\s*人|双床|大床|有窗|无窗", joined, re.I))
    hotel_room_device = bool(re.search(r"\d+\s*台|\d+\s*Hz|i[3579]\s*\d+|显卡|独立音响|PS5|专线", joined, re.I))
    homestay_identity = bool(re.search(r"民宿|金牌房源|超赞房东|入住经历", joined)) or bool(
        re.search(r"三居|租房|整套\s*\d+\s*室", joined)
        and re.search(r"24小时热水|免费停车|洗衣机|寄存行李|立即确认|可洗衣", joined)
    )
    # A duration in a promotion ("30天低价") is not an itinerary. Package
    # summaries describe a stay/trip or an explicitly bundled set of services.
    package_summary_text = "\n".join(
        str(item.get("text", "")) for item in texts
        if (item.get("visualReview") or {}).get("role") not in {"promotion", "price", "tag", "location"}
        and (item.get("visualReview") or {}).get("topologySlot") not in {"tag", "price"}
    )
    features = {
        "stable_boundary": card.get("status", "confirmed") == "confirmed" and isinstance(coord, list) and len(coord) == 4 and width > 0 and height > 0,
        "has_visible_text": bool(texts),
        "has_media": bool(photos),
        "left_head_media": bool(left_heads),
        "title_like_text": bool(title_like),
        "price_exact_text": any(item["exact"] for item in price_signals),
        "price_context_text": any(item["contextual"] for item in price_signals),
        "price_visual_text": any(item["visual"] for item in price_signals),
        "price_text": any(any(item.values()) for item in price_signals),
        "product_spec_text": bool(re.search(r"\d+(?:\.\d+)?\s*(?:g|kg|ml|L|片|粒|瓶|盒|包|袋|支|个|罐|听)(?:\s*[xX*×]\s*\d+)?", joined, re.I)),
        "merchant_metrics": bool(re.search(r"(?:\d(?:\.\d)?\s*分|暂无评分|新店(?:入驻)?|\d+\s*条|人均)", joined, re.I)),
        "merchant_fulfillment": any(fulfillment_semantic_kind(str(item.get("text", ""))) for item in texts),
        "reviewed_product_topology": reviewed_product_topology,
        "graphic_downhang": graphic_hint or bool(attached_photos),
        "text_downhang": reviewed_text_downhang or (bool(attached_text_blocks) and bool(re.search(service_pattern, attached_joined))),
        "service_language": bool(re.search(service_pattern, joined)),
        "hotel_identity": bool(re.search(r"酒店|民宿|住宿|经济型|舒适型|高档型|豪华型", joined)),
        "hotel_room_identity": hotel_room_title and hotel_room_specs and (hotel_room_device or "two_column_grid_cell_boundary" in boundary_evidence),
        "homestay_identity": homestay_identity,
        "hotel_status_or_location": bool(re.search(r"满房|预订|房型|早餐|近地铁|距您|影音房|电竞房", joined)),
        "performance_identity": bool(re.search(r"演出|电影|影院|影城|剧场|场馆|票务", joined)),
        "performance_schedule": bool(re.search(r"近期场次|开售|抢票|\d{1,2}:\d{2}|\d{4}[-/.年]\d{1,2}", joined)),
        "poster_media": poster_media,
        "package_identity": bool(re.search(r"旅游|自由行|跟团游|酒店套餐|度假套餐", joined)),
        "package_summary": bool(re.search(r"\d+天(?:\d+晚|游|行程|套餐|度假)|出发|住[:：]|景[:：]|享[:：]|吃[:：]|行[:：]|无购物|无自费|先囤后兑|过期自动退", package_summary_text)),
        # 景点 POI 结果常以具体业态而非“景点”二字呈现，例如主题乐园、
        # 漂流或某某乐园；这些不是商品卡的商品规格信号。
        "poi_identity": bool(re.search(r"地铁站|大学|商场|医院|景点|度假区|公立三甲|主题乐园|(?:^|[^\u4e00-\u9fff])乐园|漂流", joined)),
        "poi_domain_detail": bool(re.search(r"路线|挂号|科室|医生|游客量|门票|行政区|地址|拍照点|游玩", joined)),
        "explicit_ad_marker": bool(re.search(r"(?:^|[^不])广告|推广", joined)),
        "result_list_position": True,
        "pre_results_position": False,
    }
    features["scenic_ticket_downhang"] = bool(
        features["poi_identity"]
        and re.search(r"门票|成人票|学生票|亲子票", joined)
        and re.search(r"无需换票|已售|成人票|学生票|亲子票", joined)
    )
    features["scenic_merchant_identity"] = bool(features["poi_identity"] and features["poi_domain_detail"])
    # A semantic identity is not itself a boundary.  These compound features
    # require the card candidate to carry the geometry/topology evidence for
    # that type's documented cutting strategy.
    features.update({
        "product_repeat_boundary": reviewed_product_topology or (repeated_list_boundary and not graphic_hint),
        "merchant_graphic_boundary": merchant_graphic_boundary,
        "merchant_text_boundary": reviewed_text_downhang or (repeated_list_boundary and (features["text_downhang"] or features["scenic_ticket_downhang"])),
        # The canonical contract records the merchant base form after a complete
        # current-pixel review.  It is a known card type, not an ambiguous
        # shape that should fall through to ``异构卡``.
        "merchant_plain_boundary": reviewed_merchant_variant == "商家卡片_无下挂" or (
            repeated_list_boundary and not reviewed_product_topology and not features["product_spec_text"]
            and not graphic_hint and not features["text_downhang"] and not features["scenic_ticket_downhang"]
        ),
        "hotel_list_boundary": repeated_list_boundary and (features["hotel_identity"] or features["homestay_identity"]),
        "hotel_grid_boundary": "two_column_grid_cell_boundary" in boundary_evidence and (features["hotel_identity"] or features["hotel_room_identity"] or features["homestay_identity"]),
        "performance_poster_boundary": poster_media and features["performance_schedule"] and (repeated_list_boundary or bool(left_heads)),
        "movie_schedule_boundary": features["performance_schedule"] and features["performance_identity"] and repeated_list_boundary,
        "package_bundle_boundary": repeated_list_boundary and features["package_identity"] and features["package_summary"],
    })
    return features


def evaluate_contract(contract: dict[str, Any], features: dict[str, bool], candidate_score: float = 0.0,
                      geometry_validation: dict[str, Any] | None = None) -> dict[str, Any]:
    groups = contract.get("minimumEvidenceGroups", [])
    missing = [group for group in groups if not any(features.get(feature, False) for feature in group)]
    forbidden = [feature for feature in contract.get("forbiddenFeatures", []) if features.get(feature, False)]
    supporting = [feature for feature in contract.get("supportingFeatures", []) if features.get(feature, False)]
    hard_ratio = (len(groups) - len(missing)) / len(groups) if groups else 0.0
    support_total = len(contract.get("supportingFeatures", []))
    support_ratio = len(supporting) / support_total if support_total else 0.0
    # Learned geometry is deliberately a small tie-breaker. It cannot make a
    # failed minimum contract pass and never imposes a hard rejection.
    geometry_bonus = 0.02 * float((geometry_validation or {}).get("matchedRatio", 0.0))
    score = max(0.0, min(1.0, 0.70 * hard_ratio + 0.18 * support_ratio + 0.10 * candidate_score + geometry_bonus - 0.20 * len(forbidden)))
    return {
        "cardType": contract["cardType"],
        "minimumSatisfied": not missing and not forbidden,
        "score": round(score, 4),
        "matchedFeatures": sorted(feature for feature, matched in features.items() if matched),
        "supportingFeatures": supporting,
        "missingEvidenceGroups": missing,
        "forbiddenFeaturesHit": forbidden,
        "geometryValidation": geometry_validation or {"available": False, "withinLearnedRange": None, "matchedRatio": 0.0, "checks": {}},
    }


def resolve_card_type(card: dict[str, Any], facts: dict[str, Any], structure_blocks: dict[str, dict[str, Any]],
                      contracts_payload: dict[str, Any], classifier_candidates: list[dict[str, Any]],
                      geometry_profiles_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    features = extract_features(card, facts, structure_blocks)
    scores = {item.get("cardType"): float(item.get("confidence", 0)) for item in classifier_candidates}
    contracts = {item["cardType"]: item for item in contracts_payload["contracts"]}
    geometry_profiles = {item["cardType"]: item for item in (geometry_profiles_payload or {}).get("profiles", [])}
    evaluations = [
        evaluate_contract(
            contract, features, scores.get(card_type, 0.0),
            _geometry_validation(card, facts, geometry_profiles.get(card_type)),
        )
        for card_type, contract in contracts.items() if card_type in KNOWN_RESULT_TYPES
    ]
    type_priority = {
        "商家卡片_图文下挂": 60 if features.get("merchant_graphic_boundary") else 0,
        "商家卡片_文字下挂": 55 if features.get("merchant_text_boundary") else 0,
        "商家卡片_无下挂": 50 if features.get("merchant_plain_boundary") else 0,
        "演出电影卡片": 52 if (features.get("performance_poster_boundary") or features.get("movie_schedule_boundary")) and (features.get("performance_identity") or not (features.get("hotel_list_boundary") or features.get("hotel_grid_boundary"))) else 0,
        "度假酒店套餐卡片": 50 if features.get("package_bundle_boundary") else 0,
        "酒店卡片": 48 if features.get("hotel_list_boundary") or features.get("hotel_grid_boundary") else 0,
        "商品卡片": 58 if features.get("reviewed_product_topology") else 10 if features.get("product_repeat_boundary") else 0,
    }
    passing = sorted(
        (item for item in evaluations if item["minimumSatisfied"]),
        key=lambda item: (type_priority.get(item["cardType"], 0), item["score"]),
        reverse=True,
    )
    if passing:
        # A current-pixel review contributes topology and a high-confidence
        # candidate score above, but it cannot bypass the canonical contract
        # resolver.  In particular, product and hotel cards share the basic
        # head-media/title/price topology; accepting a reviewer label as an
        # unconditional tie-breaker let a mistaken product hint turn hotel
        # urgency copy (for example "低价房" / "立减") into product-price
        # evidence.  Keep one resolution policy for every card type; an
        # eventual review/result conflict is surfaced by the recognition gate
        # for bounded correction instead of silently changing contracts.
        best = passing[0]
        selected = {"cardType": best["cardType"], "confidence": best["score"], "status": "confirmed",
                    "classificationMode": "known_minimum_contract_priority",
                    "evidence": best["matchedFeatures"]}
        return {"selected": selected, "features": features, "contractValidation": best, "contractEvaluations": evaluations,
                "nearestKnownCardType": best["cardType"]}
    ad = evaluate_contract(contracts["广告卡"], features, scores.get("广告卡", 0.0))
    if ad["minimumSatisfied"]:
        selected = {"cardType": "广告卡", "confidence": ad["score"], "status": "confirmed", "classificationMode": "explicit_ad_contract", "evidence": ad["matchedFeatures"]}
        return {"selected": selected, "features": features, "contractValidation": ad, "contractEvaluations": evaluations + [ad], "nearestKnownCardType": ""}
    nearest = max(evaluations, key=lambda item: item["score"], default={"cardType": "", "score": 0.0})
    hetero = evaluate_contract(contracts["异构卡"], features, scores.get("异构卡", 0.0))
    status = "confirmed" if hetero["minimumSatisfied"] else "uncertain"
    selected = {"cardType": "异构卡", "confidence": hetero["score"], "status": status,
                "classificationMode": "heterogeneous_fallback", "evidence": hetero["matchedFeatures"]}
    return {"selected": selected, "features": features, "contractValidation": hetero, "contractEvaluations": evaluations + [ad, hetero],
            "nearestKnownCardType": nearest.get("cardType", "")}
