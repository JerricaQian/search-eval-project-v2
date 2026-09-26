#!/usr/bin/env python3
"""Assemble CV/OCR candidate artifacts into the Phase3 element-manifest contract.

This adapter deliberately preserves uncertainty.  It supplies the complete
field shape Phase3 needs, but never upgrades a weak OCR/CV candidate into an
absence, quality, colour-complexity, or semantic-authenticity conclusion.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from card_type_registry import display_names
from semantic_ownership import canonical_module_type as canonical_page_module_type, same_supply_instance
from phase2_contract import fulfillment_semantic_kind, fulfillment_tag_values


VERSION = "phase2.page-manifest.v2"
TYPE_NAMES = display_names()
# These are only candidates.  Their region is determined by the current card's
# geometry/visual review, never by the label text alone.
TITLE_PREFIX_BUSINESS_LABEL_CANDIDATES = set(fulfillment_tag_values())
PROMOTION_LABEL_PATTERN = re.compile(
    r"^(?:【\s*)?(?:神抢手|神枪手|特价团|神券|限时秒杀|秒杀价|到手价|券后价|直播特惠|会员价|新客价)(?:\s*】)?"
)


def promotion_prefix(value: str) -> tuple[str, bool]:
    """Return an explicit promotion prefix and whether it owns the full atom."""
    match = PROMOTION_LABEL_PATTERN.search(str(value).strip())
    if not match:
        return "", False
    prefix = match.group(0).strip()
    remainder = str(value).strip()[match.end():]
    standalone = not re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", remainder)
    return prefix, standalone
# ``regions`` is a semantic reading sequence, not OCR discovery order.  In
# particular, an OCR engine may return a small "外卖" tag before the adjacent
# product title; publishing that order makes a human reader and a Phase3
# reviewer appear to skip the title.  Keep title first, then the card's
# supporting information; media remains a separately addressable region.
REGION_PUBLICATION_ORDER = {
    "标题区": 10, "实体标题区": 10,
    "副标题区": 20, "实体信息区": 20,
    "基础信息区": 30, "评分与推荐理由": 35, "位置信息": 36,
    "价格区": 40, "标签区": 50,
    "商家信息区": 60, "商家信息区（电影）": 60, "商家区": 60,
    "下挂商品区": 70, "文字下挂区": 70, "下挂区": 70, "服务下挂": 70,
    "特殊下挂": 75, "领域下挂区": 75, "演出信息区": 75, "套餐概要": 75,
    "头图区": 80, "头图区（演出）": 80, "媒体区": 80,
    "主要信息区": 30, "辅助信息区": 60, "操作区": 90, "AI推荐理由": 90,
}


def region_publication_key(item: tuple[str, list[dict[str, Any]]]) -> tuple[int, int, int, str]:
    """Give every region a stable semantic order and stable in-region tiebreak."""
    name, elements = item
    first_y = min((element["坐标"][1] for element in elements if element.get("坐标")), default=10**9)
    first_x = min((element["坐标"][0] for element in elements if element.get("坐标")), default=10**9)
    return (REGION_PUBLICATION_ORDER.get(name, 99), first_y, first_x, name)


def region_element_publication_key(region_name: str, element: dict[str, Any]) -> tuple[int, int, int, str]:
    """Keep title-prefix business tags before their adjacent product title."""
    facts = element.get("textFacts") if isinstance(element.get("textFacts"), dict) else {}
    is_title_prefix_tag = (
        region_name == "标题区"
        and element.get("元素类型") == "标签"
        and facts.get("semanticRole") == "fulfillment"
    )
    x, y = element["坐标"][0], element["坐标"][1]
    return (0 if is_title_prefix_tag else 1, y, x, element["id"])


def overlap(a: list[int], b: list[int]) -> bool:
    return a[0] < b[0] + b[2] and a[0] + a[2] > b[0] and a[1] < b[1] + b[3] and a[1] + a[3] > b[1]


def clip(box: list[int], container: list[int]) -> list[int] | None:
    """Keep a CV candidate inside its result-card ownership boundary."""
    x0, y0 = max(box[0], container[0]), max(box[1], container[1])
    x1 = min(box[0] + box[2], container[0] + container[2])
    y1 = min(box[1] + box[3], container[1] + container[3])
    if x1 <= x0 or y1 <= y0:
        return None
    return [x0, y0, x1 - x0, y1 - y0]


def union(boxes: list[list[int]], fallback: list[int]) -> list[int]:
    if not boxes:
        return fallback
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x1, y1 = max(b[0] + b[2] for b in boxes), max(b[1] + b[3] for b in boxes)
    return [x0, y0, x1 - x0, y1 - y0]


def status(candidate: dict[str, Any]) -> str:
    return "confirmed" if candidate.get("route") == "accepted" else "uncertain"


def usable_text(candidate: dict[str, Any], semantic: dict[str, Any]) -> bool:
    """Only turn accepted/confirmed recognition into Phase3 visual entities.

    Weak OCR remains in the recognition audit.  This prevents one-character
    fragments from becoming false UI atoms while keeping the evidence visible.
    """
    raw = str(candidate.get("text", "")).strip()
    # The current-pixel reviewer may record a visibly truncated product title
    # with typographic brackets/ellipsis. That is a valid visible atom, not
    # OCR debris; its render state remains naturally_cropped downstream.
    if candidate.get("visualReview"):
        return bool(raw)
    compact = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff¥￥.+%折减]", "", raw)
    chinese = sum("\u4e00" <= char <= "\u9fff" for char in compact)
    latin = sum(char.isascii() and char.isalpha() for char in compact)
    punctuation = sum(not (char.isalnum() or "\u4e00" <= char <= "\u9fff" or char in "¥￥.,+-%折减/×* ()[]") for char in raw)
    coherent = len(compact) >= 2 and punctuation / max(1, len(raw)) <= 0.35
    if chinese == 0 and latin and len(compact) <= 4:
        coherent = False
    if chinese >= 2 and latin >= 5 and latin / max(1, chinese + latin) > 0.45:
        coherent = False
    return bool(raw) and coherent and (status(candidate) == "confirmed" or semantic.get("status") == "confirmed")


def card_local_semantics(candidate: dict[str, Any], selected_type: str, text_candidates: list[dict[str, Any]], semantic_by_source: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Complete page-level rules with card-local geometry.

    Page OCR blocks can span an entire merchant card, so their top-text rule
    cannot reliably name the title. Card ownership is known here: select one
    upper, coherent, non-structured CJK line as title and place remaining
    untyped observations into the type-specific region without changing text.
    """
    x, y, width, height = candidate["coord"]
    output = {source_id: dict(value) for source_id, value in semantic_by_source.items()}
    # A recorded current-pixel review is the primary source for the semantic
    # role it explicitly observed.  Preserve that role through the later
    # geometry fallback instead of flattening tags, recommendation copy and
    # ticket rows into one generic text-downhang region.
    reviewed_region = {
        "title": "标题区", "price": "文字下挂区" if selected_type == "商家卡片_文字下挂" else "价格区",
        "rating": "基础信息区", "sales": "文字下挂区" if selected_type == "商家卡片_文字下挂" else "基础信息区",
        "location": "基础信息区", "fulfillment": "基础信息区", "recommendation": "标签区",
        "subtitle": "AI推荐理由", "attachment": "文字下挂区",
        "promotion": "文字下挂区" if selected_type == "商家卡片_文字下挂" else "价格区",
    }
    for item in text_candidates:
        review = item.get("visualReview")
        role = review.get("role") if isinstance(review, dict) else ""
        topology_slot = review.get("topologySlot") if isinstance(review, dict) else ""
        visible_text = str(item.get("text", "")).strip()
        detected_promotion_prefix, standalone_promotion = promotion_prefix(visible_text)
        # The semantic prefix remains observable even when an OCR/review box
        # also contains neutral product-title glyphs and its aggregate colour
        # collapses to neutral.  Colour describes style; it does not decide
        # whether an explicit attached promotion prefix exists.
        promotion_label = bool(detected_promotion_prefix)
        if selected_type == "商家卡片_图文下挂" and topology_slot == "attached_goods":
            output[item["id"]] = {
                **output.get(item["id"], {}), "semanticRoleCandidate": "promotion" if promotion_label and standalone_promotion else role or "other",
                "regionCandidate": "下挂商品区", "status": "confirmed",
                "evidence": ["main_session_local_visual_read"],
            }
            if promotion_label:
                output[item["id"]].update({
                    "promotionPrefix": detected_promotion_prefix,
                    "evidence": ["main_session_local_visual_read", "colored_attached_promotion_label"],
                })
                if standalone_promotion:
                    output[item["id"]]["elementTypeCandidate"] = "标签"
            continue
        # A current-pixel text-attachment slot is stronger evidence than the
        # generic OCR subtitle role.  Preserve it as an item atom so the
        # Phase2 manifest can prove each text-downhang row has text + price.
        if (selected_type == "商家卡片_文字下挂" and isinstance(review, dict)
                and review.get("topologySlot") == "text_attachment"
                and role in {"subtitle", "attachment"}):
            role = "attachment"
        if topology_slot == "text_attachment" and promotion_label and standalone_promotion:
            role = "promotion"
        # An explicitly reviewed merchant-info slot owns the complete merchant
        # summary, including facts that happen to be parsed as price, sales or
        # subtitle (for example 人均价、服务类目和权益标签). It is not a service
        # item merely because a text-downhang card also has purchasable rows
        # below it. Preserve that stronger current-pixel ownership before the
        # generic role-to-region map, otherwise the manifest creates bogus
        # itemGroups containing a lone summary price or category label.
        if isinstance(review, dict) and review.get("topologySlot") == "merchant_info":
            output[item["id"]] = {
                **output.get(item["id"], {}), "semanticRoleCandidate": role,
                "regionCandidate": "基础信息区", "status": "confirmed",
                "evidence": ["main_session_local_visual_read"],
            }
            continue
        if role in reviewed_region:
            region = reviewed_region[role]
            # A POI/category attribute (for example “主题乐园” or
            # “水上项目/水上体验”) can use the generic subtitle role but belongs
            # to base information when it is not a quoted recommendation.
            # Keeping it in AI-recommendation would overlap the same visible
            # row with location and fabricate a partitioning defect.
            visible_text = str(item.get("text", "")).strip()
            if role == "subtitle" and not visible_text.startswith(("“", "\"", "‘", "'")):
                region = "基础信息区"
            # A promotion belongs to a ticket downhang only when the current
            # row also has that item's visible price.  A POI-level statement
            # such as “免费入园” is base information, not a malformed
            # appended supply with a missing price.
            if role == "promotion" and selected_type == "商家卡片_文字下挂":
                iy, ih = item["coord"][1], item["coord"][3]
                has_row_price = any(
                    other.get("visualReview", {}).get("role") == "price"
                    and abs((other["coord"][1] + other["coord"][3] / 2) - (iy + ih / 2)) <= max(38, ih)
                    for other in text_candidates if isinstance(other.get("visualReview"), dict)
                )
                region = "文字下挂区" if has_row_price else "基础信息区"
            output[item["id"]] = {
                **output.get(item["id"], {}), "semanticRoleCandidate": role,
                "regionCandidate": region, "status": "confirmed",
                "evidence": ["main_session_local_visual_read"],
            }
            if promotion_label:
                output[item["id"]].update({
                    "promotionPrefix": detected_promotion_prefix,
                    "evidence": ["main_session_local_visual_read", "colored_attached_promotion_label"],
                })
                if standalone_promotion:
                    output[item["id"]]["elementTypeCandidate"] = "标签"
    structured = re.compile(r"月售|已售|评分|到店|外卖|上门|景点|酒店|民宿|\d(?:\.\d)?\s*分|\d+(?:\.\d+)?\s*(?:km|公里|分钟|元)|[¥￥]\s*\d|起送|配送费|\d{4}[-/.年]\d{1,2}")
    possible_titles = []
    for item in text_candidates:
        value = str(item.get("text", "")).strip()
        chinese = sum("\u4e00" <= char <= "\u9fff" for char in value)
        if item["coord"][1] <= y + max(100, height * 0.42) and chinese >= 2 and not structured.search(value):
            possible_titles.append(item)
    if possible_titles and not any(value.get("semanticRoleCandidate") == "title" and value.get("status") == "confirmed" for value in output.values()):
        top = min(item["coord"][1] for item in possible_titles)
        same_title_row = [item for item in possible_titles if item["coord"][1] <= top + max(28, item["coord"][3])]
        title = max(same_title_row, key=lambda item: (sum("\u4e00" <= char <= "\u9fff" for char in str(item.get("text", ""))), item["coord"][2]))
        output[title["id"]] = {**output.get(title["id"], {}), "semanticRoleCandidate": "title", "regionCandidate": "标题区", "status": "confirmed", "evidence": ["card_local_upper_cjk_title"]}
    title_items = [
        item for item in text_candidates
        if output.get(item["id"], {}).get("semanticRoleCandidate") == "title"
    ]
    # “外卖 / 团购 / 到店 / 闪购” can describe a fulfilment mode, but when it
    # is a compact label on the product-title row it is a title-prefix business
    # tag, not a base-information field.  Preserve that visible composition so
    # component and redundancy skills compare it against the title correctly.
    for title in title_items:
        tx, ty, tw, th = title["coord"]
        for item in text_candidates:
            value = str(item.get("text", "")).strip()
            ix, iy, iw, ih = item["coord"]
            same_title_row = iy < ty + th and iy + ih > ty
            left_or_overlapping_title = ix <= tx + max(tw * 0.30, 160)
            if value in TITLE_PREFIX_BUSINESS_LABEL_CANDIDATES and same_title_row and left_or_overlapping_title:
                previous = output.get(item["id"], {})
                output[item["id"]] = {
                    **previous,
                    "semanticRoleCandidate": "fulfillment",
                    "regionCandidate": "标题区",
                    "elementTypeCandidate": "标签",
                    "status": "confirmed",
                    "evidence": list(previous.get("evidence", [])) + ["card_local_title_prefix_business_tag"],
                }
    fallback_region = {
        "商家卡片_图文下挂": "下挂商品区",
        "商家卡片_文字下挂": "文字下挂区",
        "演出电影卡片": "演出信息区",
        "酒店卡片": "基础信息区",
        "度假酒店套餐卡片": "套餐概要",
        "商品卡片": "副标题区",
    }.get(selected_type, "基础信息区")
    for item in text_candidates:
        current = output.get(item["id"], {})
        if (current.get("regionCandidate") == "基础信息区"
                and "main_session_local_visual_read" in current.get("evidence", [])):
            continue
        if current.get("semanticRoleCandidate", "other") != "other":
            continue
        lower_content = item["coord"][1] >= y + height * 0.28
        output[item["id"]] = {**current, "semanticRoleCandidate": "other", "regionCandidate": fallback_region if lower_content else "基础信息区"}
    return output


def visual_hint(candidate: dict[str, Any], kind: str, region: str, role: str = "") -> dict[str, Any]:
    hint = candidate.get("visualHint", {})
    color = hint.get("colorRole", "unknown") if isinstance(hint, dict) else "unknown"
    median = hint.get("medianRgb") if isinstance(hint, dict) else None
    exact_text_color = ""
    if isinstance(median, list) and len(median) == 3 and all(isinstance(channel, int) and 0 <= channel <= 255 for channel in median):
        exact_text_color = "#" + "".join(f"{channel:02X}" for channel in median)
    background_color = ""
    container_shape = "unknown"
    if kind in {"tag", "icon"}:
        surface = hint.get("surfaceMedianRgb") if isinstance(hint, dict) else None
        if isinstance(surface, list) and len(surface) == 3 and all(isinstance(channel, int) and 0 <= channel <= 255 for channel in surface):
            sr, sg, sb = surface
            spread = max(surface) - min(surface)
            if spread >= 45 and sum(surface) / 3 < 235:
                background_color = "#" + "".join(f"{channel:02X}" for channel in surface)
                exact_text_color = "#FFFFFF" if sum(surface) / 3 < 205 else exact_text_color
                if sr > sg * 1.25 and sr > sb * 1.25:
                    color = "orange" if sg >= sr * 0.34 else "red"
                elif sb > sr * 1.18 and sb > sg * 1.05:
                    color = "blue"
                elif sg > sr * 1.15 and sg > sb * 1.08:
                    color = "green"
    confirmed = status(candidate) == "confirmed" and color != "unknown"
    value: dict[str, Any] = {
        "entityKind": kind, "visualStatus": "confirmed" if confirmed else "uncertain",
        "isColored": color not in {"neutral", "unknown"}, "isShaped": False,
        "colorRole": color, "backgroundColor": background_color, "textColor": exact_text_color, "borderColor": "",
        "hasGraphicAssist": False, "graphicType": "无", "styleKey": f"{kind}|{color}|{role or 'other'}|无容器|无",
        "sourceRegion": region, "colorEvidence": hint.get("evidence", "not_measured") if isinstance(hint, dict) else "not_measured",
    }
    if kind in {"tag", "icon"} and confirmed:
        raw = str(candidate.get("text", ""))
        semantic_role = "券标" if re.search(r"神券|券", raw) else "履约标" if fulfillment_semantic_kind(raw) else "业务类型标" if re.search(r"演出|景点", raw) else "推荐标" if re.search(r"推荐|必玩", raw) else role or "其他标签"
        value.update({"semanticRole": semantic_role, "containerShape": container_shape,
                      "graphicAssistRole": "无", "countedInComplexity": value["isColored"],
                      "dedupWithElementIds": []})
        value["styleKey"] = f"{kind}|{color}|{semantic_role}|{container_shape}|无"
    return value


def text_element(card_id: str, item: dict[str, Any], semantic: dict[str, Any], index: int) -> tuple[str, dict[str, Any]]:
    role = semantic.get("semanticRoleCandidate", "other")
    region = semantic.get("regionCandidate", "基础信息区")
    element_type = "标签" if semantic.get("elementTypeCandidate") == "标签" or role in {"tag", "recommendation"} else "文本"
    direct = item.get("phase3Facts", {}) if isinstance(item.get("phase3Facts"), dict) else {}
    render = dict(direct.get("render", {}))
    visible = render.get("visibleStatus") if render.get("visibleStatus") in {"confirmed", "naturally_cropped", "uncertain"} else status(item)
    render.update({"visibleStatus": visible, "renderState": "normal" if visible == "confirmed" else "partial" if visible == "naturally_cropped" else "uncertain", "sourceRegion": region, "isPhoto": False, "isSystemUi": True})
    element: dict[str, Any] = {
        "id": f"{card_id}-T{index}", "所属组件": card_id, "元素类型": element_type,
        "坐标": item["coord"], "isExcluded": False,
        "render": render,
    }
    review_item_index = item.get("visualReview", {}).get("itemIndex") if isinstance(item.get("visualReview"), dict) else None
    if isinstance(review_item_index, int) and review_item_index > 0:
        element["_reviewItemIndex"] = review_item_index
    if element_type in {"文本", "标签"}:
        facts = dict(direct.get("textFacts", {}))
        candidate_color = item.get("visualHint", {}).get("colorRole", "unknown")
        # A current-pixel visual review may carry a stronger colour fact in
        # ``phase3Facts`` while retaining the CV candidate's unknown hint.
        # Do not erase that reviewed fact during semantic assembly.
        color = candidate_color if candidate_color != "unknown" else facts.get("textColorRole", "unknown")
        facts.update({"rawText": item.get("text", ""), "textStatus": "complete" if visible == "confirmed" else "naturally_cropped" if visible == "naturally_cropped" else "uncertain",
                      "semanticRole": role, "emphasisLevel": "primary" if role in {"title", "price"} else "secondary", "textColorRole": color})
        if semantic.get("promotionPrefix"):
            facts["promotionPrefix"] = semantic["promotionPrefix"]
        facts.setdefault("fontSizeBucket", "unknown"); facts.setdefault("fontWeightBucket", "unknown")
        element["textFacts"] = facts
    if element_type == "文本":
        visual = dict(direct.get("visual", {}))
        if not visual:
            visual = visual_hint(item, "text", region, role)
        visual.update({"entityKind": "text", "sourceRegion": region, "styleKey": f"text|{color}|{role or 'other'}|无容器|无"})
        element["visual"] = visual
    else:
        # Keep confirmed current-pixel facts where supplied, but normalize the
        # entity into the tag contract required by Phase3.
        visual = visual_hint(item, "tag", region, "其他标签")
        if isinstance(direct.get("visual"), dict):
            visual.update(direct["visual"])
        color = visual.get("colorRole", "unknown")
        semantic_role = "履约标" if role == "fulfillment" or fulfillment_semantic_kind(str(item.get("text", ""))) else "促销标" if role == "promotion" else "其他标签"
        counted = semantic_role != "履约标" and color not in {"neutral", "unknown"}
        visual.update({
            "entityKind": "tag",
            "containerShape": visual.get("containerShape", "unknown"),
            "graphicAssistRole": visual.get("graphicAssistRole", "无"),
            "countedInComplexity": bool(visual.get("countedInComplexity", False)) or counted,
            "styleKey": f"标签|{color}|{semantic_role}|{visual.get('containerShape', 'unknown')}|{visual.get('graphicAssistRole', '无')}",
        })
        element["visual"] = visual
    return region, element


def image_element(card_id: str, item: dict[str, Any], index: int, region: str = "头图区") -> dict[str, Any]:
    direct = item.get("phase3Facts", {}) if isinstance(item.get("phase3Facts"), dict) else {}
    render = dict(direct.get("render", {}))
    visible = render.get("visibleStatus") if render.get("visibleStatus") in {"confirmed", "naturally_cropped", "uncertain"} else status(item)
    render.update({"visibleStatus": visible, "renderState": "normal" if visible == "confirmed" else "partial" if visible == "naturally_cropped" else "uncertain", "sourceRegion": region, "isPhoto": True, "isSystemUi": False})
    visual = dict(direct.get("visual", {})) or visual_hint(item, "image", region, "photo")
    visual.update({"entityKind": "image", "sourceRegion": region, "styleKey": f"image|unknown|photo|{region}|无"})
    element = {"id": f"{card_id}-P{index}", "所属组件": card_id, "元素类型": "图片",
        "坐标": item["coord"], "isExcluded": False,
        "render": render, "visual": visual}
    review_item_index = item.get("visualReview", {}).get("itemIndex") if isinstance(item.get("visualReview"), dict) else None
    if isinstance(review_item_index, int) and review_item_index > 0:
        element["_reviewItemIndex"] = review_item_index
    return element


def append_item_groups(region: str, elements: list[dict[str, Any]], card_type: str) -> list[dict[str, Any]]:
    """Keep image/text/price facts owned by one visible appended item.

    The flat ``elements`` array remains for Phase3 compatibility; itemGroups is
    the lossless ownership layer and every appended element must occur in
    exactly one group.  Text-hang rows are clustered vertically. Graphic-hang
    products use their image columns as anchors.
    """
    if region not in {"下挂商品区", "文字下挂区", "下挂区", "服务下挂"} or not elements:
        return []
    images = [item for item in elements if item.get("元素类型") == "图片"]
    texts = [item for item in elements if item.get("元素类型") != "图片"]
    anchors: list[list[dict[str, Any]]]
    declared_items = {item.get("_reviewItemIndex") for item in elements if isinstance(item.get("_reviewItemIndex"), int) and item.get("_reviewItemIndex") > 0}
    if card_type in {"商家卡片_图文下挂", "商家卡片_文字下挂"} and declared_items:
        # The current-pixel review explicitly associates every visible image,
        # title and price with one item. Use that ownership before geometric
        # proximity; geometry is only the fallback for an ungrouped atom.
        anchors = [[item for item in elements if item.get("_reviewItemIndex") == item_index] for item_index in sorted(declared_items)]
        ungrouped = [item for item in elements if item.get("_reviewItemIndex") not in declared_items]
        axis = 0 if card_type == "商家卡片_图文下挂" else 1
        for item in ungrouped:
            center = item["坐标"][axis] + item["坐标"][axis + 2] / 2
            target = min(anchors, key=lambda group: abs(center - (group[0]["坐标"][axis] + group[0]["坐标"][axis + 2] / 2)))
            target.append(item)
    elif card_type == "商家卡片_图文下挂" and images:
        anchors = [[item] for item in sorted(images, key=lambda value: value["坐标"][0])]
        for item in texts:
            center = item["坐标"][0] + item["坐标"][2] / 2
            target = min(anchors, key=lambda group: abs(center - (group[0]["坐标"][0] + group[0]["坐标"][2] / 2)))
            target.append(item)
    else:
        anchors = []
        for item in sorted(elements, key=lambda value: (value["坐标"][1], value["坐标"][0])):
            center = item["坐标"][1] + item["坐标"][3] / 2
            target = next((group for group in anchors if abs(center - sum(value["坐标"][1] + value["坐标"][3] / 2 for value in group) / len(group)) <= max(item["坐标"][3], 28)), None)
            if target is None:
                anchors.append([item])
            else:
                target.append(item)
    groups = []
    for index, members in enumerate(anchors, 1):
        # The first element was accidentally duplicated by neither branch: the
        # expression above appends only when an existing row is found.
        members = list(dict.fromkeys(item["id"] for item in members))
        resolved = [next(item for item in elements if item["id"] == member_id) for member_id in members]
        image_ids = [item["id"] for item in resolved if item.get("元素类型") == "图片"]
        price_ids = [item["id"] for item in resolved if item.get("textFacts", {}).get("semanticRole") == "price"]
        text_ids = [item["id"] for item in resolved if item["id"] not in image_ids and item["id"] not in price_ids]
        price_confirmed = any(item.get("render", {}).get("visibleStatus") == "confirmed" for item in resolved if item["id"] in price_ids)
        requires_price_confirmation = region == "下挂商品区" and bool(image_ids)
        # Keep this object deliberately within the Phase3 item-group contract.
        # Observability of a missing price is represented by ``visibleStatus``;
        # the validator intentionally disallows extra per-group keys so that a
        # downstream consumer cannot silently ignore them.
        member_statuses = {item.get("render", {}).get("visibleStatus") for item in resolved}
        visible_status = (
            "confirmed" if member_statuses == {"confirmed"} and (not requires_price_confirmation or price_confirmed)
            else "naturally_cropped" if "uncertain" not in member_statuses and "naturally_cropped" in member_statuses
            else "uncertain"
        )
        groups.append({
            "itemIndex": index,
            "coord": union([item["坐标"] for item in resolved], resolved[0]["坐标"]),
            "elementIds": [item["id"] for item in resolved],
            "imageElementIds": image_ids,
            "textElementIds": text_ids,
            "priceElementIds": price_ids,
            "visibleStatus": visible_status,
        })
    return groups


def build_card(candidate: dict[str, Any], semantic: dict[str, Any], facts: dict[str, Any], text_semantics: dict[str, Any]) -> dict[str, Any]:
    card_id, coord = candidate["id"], candidate["coord"]
    selected = semantic.get("selectedCardType", {})
    selected_type = selected.get("cardType", "")
    confirmed_type = selected.get("status") == "confirmed"
    card_type = TYPE_NAMES.get(selected_type, "异构卡")
    regions: dict[str, list[dict[str, Any]]] = {}
    # Rejected OCR/CV observations are audit evidence only. They must never
    # leak back into the published element array simply because they overlap a
    # card boundary.
    text_candidates = [x for x in facts["candidates"]["text"] if x.get("route") == "accepted" and overlap(x["coord"], coord)]
    photo_candidates = [x for x in facts["candidates"]["photos"] if x.get("route") == "accepted" and overlap(x["coord"], coord)]
    semantic_by_source = card_local_semantics(
        candidate, selected_type, text_candidates,
        {item.get("sourceId"): item for item in text_semantics.get("candidates", [])},
    )
    unresolved_ids = [item["id"] for item in text_candidates + photo_candidates if status(item) != "confirmed"]
    for index, item in enumerate(text_candidates, 1):
        source_semantic = semantic_by_source.get(item["id"], {})
        if not usable_text(item, source_semantic):
            continue
        item = {**item, "coord": clip(item["coord"], coord)}
        if item["coord"] is None:
            continue
        region, element = text_element(card_id, item, source_semantic, index)
        regions.setdefault(region, []).append(element)
    head_photo_id = str(candidate.get("headPhotoId", ""))
    attached_photo_ids = {str(value) for value in candidate.get("attachedProductPhotoIds", [])}
    emitted_head_image_ids: list[str] = []
    for index, item in enumerate(photo_candidates, 1):
        if status(item) != "confirmed":
            continue
        if item["id"] in attached_photo_ids or (selected_type == "商家卡片_图文下挂" and item["id"] != head_photo_id):
            image_region = "下挂商品区"
        elif item["id"] == head_photo_id or (not head_photo_id and not emitted_head_image_ids):
            image_region = "头图区"
        else:
            image_region = "特殊下挂"
        item = {**item, "coord": clip(item["coord"], coord)}
        if item["coord"] is None:
            continue
        element = image_element(card_id, item, index, image_region)
        regions.setdefault(image_region, []).append(element)
        if image_region == "头图区":
            emitted_head_image_ids.append(element["id"])
    if not regions:
        regions["基础信息区"] = []
    region_rows = []
    for name, region_elements in sorted(regions.items(), key=region_publication_key):
        region_elements.sort(key=lambda element: region_element_publication_key(name, element))
        row = {"name": name, "coord": union([e["坐标"] for e in region_elements], coord), "elements": region_elements}
        groups = append_item_groups(name, region_elements, selected_type)
        if groups:
            row["itemGroups"] = groups
        for element in region_elements:
            element.pop("_reviewItemIndex", None)
        region_rows.append(row)
    elements = [element for row in region_rows for element in row["elements"]]
    uncertain = unresolved_ids + [element["id"] for element in elements if element["render"]["visibleStatus"] == "uncertain"]
    naturally_cropped = [element["id"] for element in elements if element["render"]["visibleStatus"] == "naturally_cropped"]
    titles = [e for e in elements if e.get("textFacts", {}).get("semanticRole") == "title"]
    head_images = [e for row in region_rows if row["name"] == "头图区" for e in row["elements"] if e["元素类型"] == "图片"]
    inventory_regions = {row["name"]: [{"elementId": e["id"], "styleKey": e.get("visual", {}).get("styleKey", ""), "countedInComplexity": bool(e.get("visual", {}).get("countedInComplexity", False))} for e in row["elements"] if e.get("visual", {}).get("entityKind") in {"tag", "icon"}] for row in region_rows}
    tags = [e for e in elements if e.get("visual", {}).get("entityKind") in {"tag", "icon"}]
    complete = confirmed_type and not uncertain and bool(elements)
    # A clipped carousel item is a property of that item, not evidence that
    # the merchant card itself is incomplete.  Only a card-level crop policy
    # (normally a bottom-edge continuation) downgrades the card structure.
    partial = semantic.get("partialCardPolicy", {}).get("applied") is True
    classification_evidence = selected.get("evidence", [])
    if not isinstance(classification_evidence, list):
        classification_evidence = []
    classification_evidence = [str(item) for item in classification_evidence if str(item).strip()] or ["phase2_local_cv_card_candidate"]
    layout_mode = "left_image_right_text" if selected_type in {
        "商品卡片", "商家卡片_图文下挂", "商家卡片_文字下挂", "酒店卡片", "演出电影卡片", "度假酒店套餐卡片"
    } and bool(head_images) else "other"
    layout_anchors: dict[str, list[int]] = {}
    if complete and layout_mode == "left_image_right_text":
        image = next((element for element in elements if element.get("render", {}).get("isPhoto")), None)
        title = next((element for element in elements if element.get("textFacts", {}).get("semanticRole") == "title"), None)
        primary = next((element for element in elements if element.get("textFacts", {}).get("semanticRole") in {"price", "fulfillment", "sales", "rating", "location", "subtitle"}), None)
        if image and title and primary:
            layout_anchors = {"image": image["坐标"], "title": title["坐标"], "primaryInfo": primary["坐标"]}
    layout_relation = "image_left_of_text;title_above_primaryInfo" if layout_anchors else ""
    return {"cardId": card_id, "卡片类型": card_type, "coord": coord, "regions": region_rows,
        "cardTypeCode": selected_type or "unknown", "cardTypeName": card_type, "resultType": "result_card",
        "classificationEvidence": classification_evidence,
        "structure": {"visibleStatus": "naturally_cropped" if partial else "complete" if complete else "uncertain", "cardTypeCode": selected_type or "unknown",
            "layoutMode": layout_mode,
            "layoutSignature": "cv_candidate", "comparisonGroupKey": f"{selected_type or 'unknown'}|cv_candidate",
            "isResultListItem": True, "isHeterogeneous": card_type == "异构卡", "listPosition": int(card_id.removeprefix("C")) if card_id.removeprefix("C").isdigit() else 0,
            "layoutAnchors": layout_anchors, "layoutAnchorRelation": layout_relation,
            "regions": [{"region": row["name"], "coord": row["coord"], "visibleStatus": "confirmed" if row["elements"] else "uncertain", "hasPhysicalBoundary": False, "hasBackgroundSeparation": False} for row in region_rows]},
        "factInventory": {"complete": complete, "scanned": ["card_boundary", "regions", "images", "text", "render_state", "visual_spec", "layout", "relations"], "uncertainElementIds": uncertain, "naturallyCroppedElementIds": naturally_cropped, "notes": ["assembled_from_local_cv_candidates"] + (["bottom_partial_card_type_inherited_from_previous_confirmed_repeated_type"] if partial else [])},
        "visualInventory": {"complete": complete and all(e.get("visual", {}).get("visualStatus") == "confirmed" for e in tags), "regions": inventory_regions,
            "tagScanChecklist": [{"candidate": "local_cv_tag_icon_candidates", "status": "found" if tags else "not_found", "checkedRegions": list(regions), "elementIds": [e["id"] for e in tags]}]},
        "_relations": (
            [{"relationType": "title_to_image", "from": title["id"], "to": image["id"], "status": "confirmed"} for title in titles for image in head_images]
            + [{"relationType": "title_to_append", "from": title["id"], "to": element_id, "status": "confirmed"}
               for title in titles for row in region_rows for group in row.get("itemGroups", []) for element_id in group["elementIds"]]
        )}


def recognition_state(facts: dict[str, Any], card_semantics: dict[str, Any], gate: dict[str, Any] | None, card_ids: list[str]) -> dict[str, Any]:
    if gate is None:
        selected = [item.get("selectedCardType", {}) for item in card_semantics.get("cards", [])]
        derived_valid = bool(selected) and all(item.get("status") == "confirmed" for item in selected) and not facts.get("routing", {}).get("unresolvedCandidateIds", [])
        gate = {"valid": derived_valid, "errors": [] if derived_valid else ["recognition_gate_not_supplied_or_derived_incomplete"],
                "semanticHookFindings": [], "reprocessTargets": [], "reprocess": []}
    valid = gate.get("valid") is True
    errors = [str(item) for item in gate.get("errors", [])]
    blocking = sorted({match.group(1) for error in errors if (match := re.match(r"^(C\d+):", error))})
    if not valid and not blocking:
        blocking = list(card_ids)
    return {
        "contractVersion": VERSION,
        "status": "confirmed" if valid else "blocked",
        "phase3Ready": valid,
        "wholePageGate": True,
        "blockingCardIds": blocking,
        "backends": facts.get("backends", {}),
        "errors": errors,
        "semanticHookFindings": gate.get("semanticHookFindings", []),
        "reprocessTargets": gate.get("reprocessTargets", []),
        "reprocess": gate.get("reprocess", []),
    }


def compact_phase3_publication(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove Phase2-only duplicate measurements from the Phase3 fact view.

    Pixel-level colour samples, extraction evidence and repeated region ownership
    remain available in the retained CV/OCR and calibration audit artifacts.  The
    published manifest keeps only the semantic colour role and style signature
    needed by Phase3.
    """
    payload.pop("annotatedImage", None)
    for card in payload.get("cards", []):
        for region in card.get("regions", []):
            for element in region.get("elements", []):
                render = element.get("render")
                if isinstance(render, dict):
                    render.pop("sourceRegion", None)
                visual = element.get("visual")
                if isinstance(visual, dict):
                    for key in (
                        "isColored", "isShaped", "backgroundColor", "textColor",
                        "borderColor", "hasGraphicAssist", "sourceRegion", "colorEvidence",
                        "semanticRole",
                    ):
                        visual.pop(key, None)
    return payload


def merge_page_modules(cv_modules: list[dict[str, Any]], review_modules: Any,
                       derived_result_list: dict[str, Any] | None = None,
                       result_cards: list[dict[str, Any]] | None = None,
                       rejected_modules: Any = None) -> list[dict[str, Any]]:
    """Prefer current-pixel modules over CV candidates of the same type.

    An explicit complete current-pixel module inventory owns page modules;
    unselected CV hints stay in the candidate audit and cannot become page
    facts. Older reviews without a modules inventory retain CV candidates for
    compatibility. The result list uses its reviewed box, then the card-derived
    box, then a CV candidate.
    """
    inventory_complete = isinstance(review_modules, list)
    reviewed = [module for module in review_modules
                if isinstance(module, dict) and isinstance(module.get("coord"), list)
                and len(module["coord"]) == 4] if isinstance(review_modules, list) else []
    reviewed_types = {canonical_page_module_type(module.get("moduleType")) for module in reviewed}
    filter_bottoms = [module["coord"][1] + module["coord"][3] for module in reviewed
                      if canonical_page_module_type(module.get("moduleType")) == "sort_filter"]
    filter_bottom = max(filter_bottoms) if filter_bottoms else None
    modules = []
    for module in cv_modules:
        module_type = canonical_page_module_type(module.get("module"))
        if inventory_complete:
            continue
        if any(
            isinstance(rejected, dict)
            and canonical_page_module_type(rejected.get("moduleType")) == module_type
            and same_supply_instance(rejected.get("coord"), module.get("coord"))
            for rejected in (rejected_modules if isinstance(rejected_modules, list) else [])
        ):
            continue
        if module_type in reviewed_types or (module_type == "result_list" and derived_result_list):
            continue
        # A list card below the sort/filter row cannot also be a pre-list main
        # POI.  Require a near-identical confirmed result-card footprint, not
        # just a shared image or nearby text, before suppressing the CV hint.
        if module_type == "main_poi_card" and any(
            card.get("structure", {}).get("isResultListItem") is True
            and card.get("卡片类型") != "主点卡片"
            and (filter_bottom is None or module.get("coord", [0, 0])[1] >= filter_bottom)
            and same_supply_instance(module.get("coord", []), card.get("coord", []))
            for card in (result_cards or [])
        ):
            continue
        if module_type == "result_list" and any(item["moduleType"] == "result_list" for item in modules):
            continue
        modules.append({"moduleType": module_type, "coord": module["coord"],
                        "visibleStatus": module.get("status", "uncertain"),
                        "contentRole": ";".join(module.get("evidence", [])),
                        "isListPrefix": False, "isListItem": False})
    known = {(item["moduleType"], tuple(item["coord"])) for item in modules}
    for module in reviewed:
        coord = module.get("coord")
        module_type = canonical_page_module_type(module.get("moduleType"))
        if not isinstance(coord, list) or len(coord) != 4 or (module_type, tuple(coord)) in known:
            continue
        if module_type == "result_list" and any(item["moduleType"] == "result_list" for item in modules):
            continue
        modules.append({"moduleType": module_type, "coord": coord,
                        "visibleStatus": module.get("visibleStatus", "confirmed"),
                        "contentRole": module.get("contentRole", ""),
                        "isListPrefix": False if module_type == "result_list" else bool(module.get("isListPrefix", True)),
                        "isListItem": bool(module.get("isListItem", False))})
        known.add((module_type, tuple(coord)))
    if derived_result_list and not any(item["moduleType"] == "result_list" for item in modules):
        modules.append(dict(derived_result_list))
    for index, module in enumerate(modules, 1):
        module["id"] = f"M{index}"
    return modules


def reconcile_interstitial_list_modules(modules: list[dict[str, Any]], cards: list[dict[str, Any]]) -> None:
    """Count a confirmed related-search block only when it interrupts known list cards.

    A suggestion block above the first result or after the last visible result
    may be a preface or footer.  Its list ownership cannot be inferred from
    type or wording alone, so those positions remain outside the list.
    """
    list_cards = sorted((card for card in cards if card.get("structure", {}).get("isResultListItem") is True),
                        key=lambda card: card["coord"][1])
    filter_bottoms = [module["coord"][1] + module["coord"][3] for module in modules
                      if module.get("moduleType") == "sort_filter"]
    filter_bottom = max(filter_bottoms) if filter_bottoms else None
    interstitials = []
    for module in modules:
        if module.get("moduleType") not in {"related_search", "related_searches"}:
            continue
        box = module.get("coord", [])
        if not isinstance(box, list) or len(box) != 4 or module.get("visibleStatus") != "confirmed":
            continue
        before = [card for card in list_cards if card["coord"][1] + card["coord"][3] <= box[1]]
        after = [card for card in list_cards if card["coord"][1] >= box[1] + box[3]]
        if before and after and (filter_bottom is None or box[1] >= filter_bottom):
            interstitials.append(module)
    for module in sorted(interstitials, key=lambda item: item["coord"][1]):
        module["isListItem"] = True
        module["isListPrefix"] = False
        position = 1 + sum(card["coord"][1] < module["coord"][1] for card in list_cards)
        position += sum(other["coord"][1] < module["coord"][1] for other in interstitials)
        module["listPosition"] = position
    for card in list_cards:
        card["structure"]["listPosition"] += sum(
            module["coord"][1] < card["coord"][1] for module in interstitials
        )


def build(query: str, facts: dict[str, Any], candidates: dict[str, Any], card_semantics: dict[str, Any], text_semantics: dict[str, Any], gate: dict[str, Any] | None = None) -> dict[str, Any]:
    semantic_by_card = {item["cardId"]: item for item in card_semantics.get("cards", [])}
    cards = [build_card(card, semantic_by_card.get(card["id"], {}), facts, text_semantics) for card in candidates.get("resultCards", [])]
    # Candidate IDs are local handles, not result-flow ordinal numbers.  A
    # reviewed first card may be C0; list positions must follow visible order.
    for list_position, card in enumerate(sorted(
        (card for card in cards if card.get("structure", {}).get("isResultListItem") is True),
        key=lambda item: (item["coord"][1], item["coord"][0]),
    ), 1):
        card["structure"]["listPosition"] = list_position
    relations = [relation for card in cards for relation in card.pop("_relations")]
    current_review = facts.get("routing", {}).get("visualReview", {})
    review_modules = current_review.get("modules") if current_review.get("moduleInventoryComplete") else None
    derived_result_list = ({"moduleType": "result_list", "coord": union([card["coord"] for card in cards],
                            [0, 0, facts["viewport"]["width"], facts["viewport"]["height"]]),
                            "visibleStatus": "confirmed", "contentRole": "结果供给",
                            "isListPrefix": False, "isListItem": False} if cards else None)
    modules = merge_page_modules(candidates.get("pageModules", []), review_modules, derived_result_list, cards,
                                 current_review.get("rejectedModules", []))
    reconcile_interstitial_list_modules(modules, cards)
    if not any(module["moduleType"] == "result_list" for module in modules):
        modules.append({"id": f"M{len(modules)+1}", "moduleType": "result_list",
                        "coord": [0, 0, facts["viewport"]["width"], facts["viewport"]["height"]],
                        "visibleStatus": "uncertain", "contentRole": "结果供给",
                        "isListPrefix": False, "isListItem": False})
    recognition = recognition_state(facts, card_semantics, gate, [card["cardId"] for card in cards])
    payload = {"query": query, "screenshot": facts["screenshot"], "cards": cards,
        "recognition": recognition,
        "pageFacts": {"screen": 1, "isContinuation": False, "viewport": facts["viewport"], "modules": modules},
        "pageFactInventory": {"complete": bool(cards) and recognition["phase3Ready"], "scanned": ["modules", "visual_review_page_modules", "result_cards", "cv_candidates", "whole_page_gate"], "uncertainElementIds": list(facts.get("routing", {}).get("unresolvedCandidateIds", [])), "notes": ["assembled_from_phase2_cv_facts.v1", f"recognition:{recognition['status']}"]},
        "relations": relations}
    return compact_phase3_publication(payload)


def recognition_audit(query: str, screenshot: str, manifest: str, facts: dict[str, Any], cards: list[dict[str, Any]]) -> dict[str, Any]:
    """Record both accepted and unresolved recognition without inventing elements."""
    fields: list[dict[str, str]] = []
    for card in cards:
        card_id, bounds = card["cardId"], card["coord"]
        for kind in ("text", "photos"):
            for item in facts["candidates"].get(kind, []):
                if not overlap(item["coord"], bounds):
                    continue
                raw = str(item.get("text", "图片"))
                fields.append({"cardId": card_id, "elementId": item.get("id", ""), "field": "visible_text" if kind == "text" else "photo",
                    "visibleText": raw, "status": status(item), "source": "full_image",
                    "reason": "accepted local candidate" if status(item) == "confirmed" else "kept as unresolved local candidate; not emitted as a confirmed Phase3 element"})
                if kind == "text" and isinstance(item.get("visualHint"), dict):
                    fields.append({"cardId": card_id, "elementId": item.get("id", ""), "field": "color_role",
                        "visibleText": str(item["visualHint"].get("colorRole", "unknown")), "status": status(item), "source": "full_image",
                        "reason": "local foreground-pixel colour estimate; requires local review before any stronger visual conclusion"})
    review = facts.get("routing", {}).get("visualReview", {})
    local_reads = int(review.get("localReviewReadCount", 0)) if isinstance(review, dict) else 0
    return {"query": query, "screenshot": screenshot, "manifest": manifest, "fullImageReadCount": 1,
        "localReviewReadCount": local_reads, "totalImageReadCount": 1 + local_reads,
        "localReviewEvidence": review if local_reads else [], "fields": fields}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a Phase3-ready element manifest from Phase2 candidate JSON")
    parser.add_argument("--query", required=True); parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--result-candidates", type=Path, required=True); parser.add_argument("--card-semantics", type=Path, required=True)
    parser.add_argument("--text-semantics", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--recognition-gate", type=Path, help="Embed the whole-page recognition gate in the canonical manifest")
    parser.add_argument("--recognition-audit", type=Path, help="Write the corresponding Phase2 recognition audit")
    args = parser.parse_args()
    gate = json.loads(args.recognition_gate.read_text(encoding="utf-8")) if args.recognition_gate else None
    payload = build(args.query, *(json.loads(path.read_text(encoding="utf-8")) for path in (args.facts, args.result_candidates, args.card_semantics, args.text_semantics)), gate)
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.recognition_audit:
        args.recognition_audit.parent.mkdir(parents=True, exist_ok=True)
        audit = recognition_audit(args.query, payload["screenshot"], str(args.output), json.loads(args.facts.read_text(encoding="utf-8")), payload["cards"])
        args.recognition_audit.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "cards": len(payload["cards"]), "phase3Ready": payload["recognition"]["phase3Ready"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
