#!/usr/bin/env python3
"""Separate page modules from repeatable result-card candidates.

The input structure is deliberately non-semantic. This script adds only
conservative candidates: a repeated image-left/text-right block seeds a result
card, and intervening text-only blocks are attached until the next seed. It
does not decide that omitted optional modules are absent or defective.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from card_contract_engine import title_semantic_family


VERSION = "phase2.search-result-candidates.v1"


def _overlap_y(a: list[int], b: list[int]) -> bool:
    return a[1] < b[1] + b[3] and a[1] + a[3] > b[1]


def _texts_in(box: list[int], texts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in texts if _overlap_y(box, item["coord"])]


def _union(boxes: list[list[int]]) -> list[int]:
    x0, y0 = min(box[0] for box in boxes), min(box[1] for box in boxes)
    x1 = max(box[0] + box[2] for box in boxes)
    y1 = max(box[1] + box[3] for box in boxes)
    return [x0, y0, x1 - x0, y1 - y0]


def _repeated_merchant_head_cards(facts: dict[str, Any], blocks: list[dict[str, Any]], results_start_y: int) -> list[dict[str, Any]]:
    """Recover merchant-card boundaries from repeated left square heads.

    A merchant card owns both its summary and the horizontal product rail.
    Treating the rail's next image as a new card seed split every merchant
    into two cards. Repeated head-photo geometry is stronger current-screen
    evidence for the card start, so it owns the interval until the next head.
    """
    width, height = int(facts["viewport"]["width"]), int(facts["viewport"]["height"])
    heads = []
    for photo in facts.get("candidates", {}).get("photos", []):
        x, y, w, h = photo.get("coord", [0, 0, 0, 0])
        ratio = w / h if h else 0
        if photo.get("route") == "accepted" and y >= results_start_y and x <= width * 0.10 and 90 <= w <= 240 and 90 <= h <= 240 and 0.72 <= ratio <= 1.30:
            heads.append(photo)
    heads.sort(key=lambda item: item["coord"][1])
    # De-duplicate any detector variants on the same head image.
    unique = [head for head in heads if not any(abs(head["coord"][1] - earlier["coord"][1]) < 45 for earlier in heads[:heads.index(head)])]
    if len(unique) < 2:
        return []
    cards = []
    for index, head in enumerate(unique):
        top = head["coord"][1]
        bottom = unique[index + 1]["coord"][1] if index + 1 < len(unique) else height
        if bottom - top < 180:
            continue
        coord = [0, top, width, bottom - top]
        members = [block["id"] for block in blocks if _overlap_y(block["coord"], coord)]
        attached_product_ids = [photo["id"] for photo in facts.get("candidates", {}).get("photos", [])
                                if photo.get("route") == "accepted" and photo.get("id") != head["id"]
                                and photo["coord"][1] >= top + head["coord"][3] and _overlap_y(photo["coord"], coord)]
        evidence = ["repeated_left_square_merchant_head", "left_square_merchant_head", "next_repeated_head_boundary"]
        if attached_product_ids:
            evidence.extend(["right_side_attached_product_image_group", "summary_and_product_rail_owned_together"])
        cards.append({"id": f"merchant-head-{index + 1}", "coord": coord, "seedBlockId": "", "memberBlockIds": members,
                      "headPhotoId": head["id"], "attachedProductPhotoIds": attached_product_ids, "confidence": 0.91, "status": "confirmed",
                      "evidence": evidence})
    return cards


def _module_candidates(facts: dict[str, Any], structure: dict[str, Any]) -> list[dict[str, Any]]:
    texts = [item for item in facts.get("candidates", {}).get("text", []) if item.get("route") != "rejected"]
    photos = [item for item in facts.get("candidates", {}).get("photos", []) if item.get("route") == "accepted"]
    blocks = sorted(structure.get("blocks", []), key=lambda item: item["coord"][1])
    viewport = facts["viewport"]
    width, height = int(viewport["width"]), int(viewport["height"])

    def block_for(item: dict[str, Any]) -> dict[str, Any] | None:
        middle = item["coord"][1] + item["coord"][3] / 2
        return next((block for block in blocks if block["coord"][1] <= middle <= block["coord"][1] + block["coord"][3]), None)

    modules: list[dict[str, Any]] = []

    # Search and tab are local top-of-page structures. Never union every
    # matching word across the long screenshot: that produced page-sized
    # pseudo modules and confused bottom filters with the top tab row.
    top_cjk = [item for item in texts if item["coord"][1] < height * 0.15 and re.search(r"[\u4e00-\u9fff]{2,}", str(item.get("text", "")))]
    if top_cjk:
        query = min(top_cjk, key=lambda item: abs((item["coord"][1] + item["coord"][3] / 2) - height * 0.075))
        qy = max(0, query["coord"][1] - max(24, query["coord"][3]))
        modules.append({"module": "search_bar", "coord": [round(width * 0.09), qy, round(width * 0.79), max(80, query["coord"][3] * 3)], "confidence": 0.82, "status": "confirmed", "evidence": ["top_query_text_in_search_geometry"]})
    top_row_texts = [item for item in texts if height * 0.09 <= item["coord"][1] <= height * 0.22 and item["coord"][2] >= 20]
    row_clusters: list[list[dict[str, Any]]] = []
    for item in sorted(top_row_texts, key=lambda value: value["coord"][1]):
        cluster = next((row for row in row_clusters if abs(row[0]["coord"][1] - item["coord"][1]) <= 28), None)
        if cluster is None:
            row_clusters.append([item])
        else:
            cluster.append(item)
    tab_row = max(row_clusters, key=lambda row: len(row), default=[])
    if len(tab_row) >= 3:
        box = _union([item["coord"] for item in tab_row])
        if box[2] >= width * 0.55:
            modules.append({"module": "tab", "coord": [max(0, box[0] - 24), max(0, box[1] - 16), min(width, box[2] + 48), box[3] + 32], "confidence": 0.80, "status": "confirmed", "evidence": ["top_horizontal_text_row_geometry"]})

    sort_matches = [item for item in texts if re.search(r"综合排序|排序|筛选", str(item.get("text", "")))]
    sort_item = max(sort_matches, key=lambda item: item["coord"][1], default=None)
    sort_block = block_for(sort_item) if sort_item else None
    sort_top = sort_block["coord"][1] if sort_block else height
    if sort_block:
        modules.append({"module": "sort_filter", "coord": sort_block["coord"], "confidence": 0.90, "status": "confirmed", "evidence": ["localized_sort_filter_row"]})

    watcher = [item for item in texts if re.search(r"直播|观看", str(item.get("text", "")))]
    live_block = next((block for block in blocks if block["coord"][1] < height * 0.18 and block["coord"][3] >= height * 0.28 and (any(_overlap_y(item["coord"], block["coord"]) for item in watcher) or any(module["module"] == "tab" and _overlap_y(module["coord"], block["coord"]) for module in modules))), None)
    if live_block:
        modules.append({"module": "live_card", "cardType": "异构卡-直播卡", "coord": live_block["coord"], "confidence": 0.84, "status": "confirmed", "evidence": ["large_top_media_block", "live_or_top_tab_evidence"]})

    live_bottom = live_block["coord"][1] + live_block["coord"][3] if live_block else 0
    poi_pattern = re.compile(r"地铁站|大学|医院|商场|景点|度假区|迪士尼|游客量|门票")
    poi_blocks = []
    for block in blocks:
        by, bottom = block["coord"][1], block["coord"][1] + block["coord"][3]
        local_text = "\n".join(str(item.get("text", "")) for item in texts if _overlap_y(item["coord"], block["coord"]))
        local_photos = [item for item in photos if _overlap_y(item["coord"], block["coord"])]
        title_family = title_semantic_family({"id": "pre-results-candidate", "coord": block["coord"]}, facts)["family"]
        # A decisive title establishes the page-module family. Only ambiguous
        # titles fall back to the old within-block POI content combination.
        poi_identity = title_family == "主点卡片" if title_family else bool(poi_pattern.search(local_text))
        if by >= live_bottom and bottom <= sort_top and local_photos and poi_identity:
            poi_blocks.append(block)
    main_poi = poi_blocks[0] if poi_blocks else None
    main_poi_bottom = 0
    if main_poi:
        main_boxes = [main_poi["coord"]]
        main_bottom = main_poi["coord"][1] + main_poi["coord"][3]
        for block in blocks:
            if block["coord"][1] == main_bottom and block.get("layoutCandidate") == "text_only":
                main_boxes.append(block["coord"])
                main_bottom = block["coord"][1] + block["coord"][3]
        modules.append({"module": "main_poi_card", "coord": _union(main_boxes), "confidence": 0.84, "status": "confirmed", "evidence": ["poi_identity_with_local_media_before_filters"]})
        main_poi_bottom = main_bottom

    module_floor = main_poi_bottom or (live_bottom if live_block else 0)
    filter_blocks = [block for block in blocks if block["coord"][1] >= module_floor and block["coord"][1] < sort_top]
    if sort_block and module_floor > 0 and filter_blocks:
        filter_photos = [item for item in photos if any(_overlap_y(item["coord"], block["coord"]) for block in filter_blocks)]
        filter_text = "\n".join(str(item.get("text", "")) for item in texts if any(_overlap_y(item["coord"], block["coord"]) for block in filter_blocks))
        if len(filter_photos) >= 2 or re.search(r"推荐|景点|酒店|美食|飞机票|火车票|品类|套餐", filter_text):
            modules.append({"module": "business_image_filter", "coord": _union([block["coord"] for block in filter_blocks]), "confidence": 0.80, "status": "confirmed", "evidence": ["localized_media_or_category_filter_before_sort"]})

    modules.sort(key=lambda module: (module["coord"][1], module["module"]))
    return modules


def _merchant_graphic_hang_cards(facts: dict[str, Any], results_start_y: int) -> list[dict[str, Any]]:
    """Find the merchant-image/text-downhang topology from local photo geometry.

    A merchant head image is a near-square photo in the left image column. A
    graphic downhang needs a separate, sufficiently large photo group to its
    right below that head. Tall left-column coupon artwork is deliberately not
    counted as a product group.
    """
    viewport_width = int(facts["viewport"]["width"])
    photos = sorted(facts.get("candidates", {}).get("photos", []), key=lambda item: item["coord"][1])
    texts = [item for item in facts.get("candidates", {}).get("text", []) if item.get("route") != "rejected"]
    heads = []
    for item in photos:
        x, y, w, h = item["coord"]
        ratio = w / h if h else 0
        # Merchant heads use the narrow left column; product strips begin
        # around x=227 on a 1224px reference canvas, so 16% keeps them apart.
        if y < results_start_y or x > viewport_width * 0.16 or w < 88 or h < 88 or not 0.65 <= ratio <= 1.35:
            continue
        # Coupon artwork and a product tile can be square in the same left
        # column.  A merchant head additionally needs a local merchant-metric
        # line beside it; this keeps internal down-hang media from becoming a
        # new card boundary.
        local = [
            text for text in texts
            if y - 100 <= text["coord"][1] <= y + h * 0.52
            and text["coord"][0] >= x + w * 0.72
        ]
        local_text = "\n".join(str(text.get("text", "")) for text in local)
        has_merchant_metric = bool(re.search(r"(?:\d(?:\.\d)?\s*分|暂无评分|新店|人均|\d+\s*条|\d+(?:\.\d+)?\s*km|到店)", local_text, re.I))
        has_nearby_right_group = any(
            photo["coord"][0] >= viewport_width * 0.18
            and y + h * 0.35 <= photo["coord"][1] < y + h * 1.60
            and photo["coord"][2] >= 96 and photo["coord"][3] >= 96
            for photo in photos
        )
        if not (has_merchant_metric or has_nearby_right_group):
            continue
        heads.append({**item, "anchorY": min([y] + [text["coord"][1] for text in local])})
    cards: list[dict[str, Any]] = []
    for index, head in enumerate(heads):
        x, y, w, h = head["coord"]
        anchor_y = int(head["anchorY"])
        next_y = int(heads[index + 1]["anchorY"]) if index + 1 < len(heads) else int(facts["viewport"]["height"])
        product_groups = []
        for photo in photos:
            px, py, pw, ph = photo["coord"]
            if py < y + h * 0.35 or py >= next_y or px < viewport_width * 0.18 or pw < 96 or ph < 96:
                continue
            product_groups.append(photo)
        # The down-hang can be one detector region containing a whole product
        # strip. It is already separated from the left head by x/y topology,
        # so requiring two detector boxes incorrectly rejects merged strips.
        # A lone right-edge image is normally a floating service/control, not
        # a merchant product down-hang. Genuine strips have at least one item
        # anchored before 70% of the viewport (often x≈227/311 on 1224px).
        if not product_groups or not any(photo["coord"][0] < viewport_width * 0.70 for photo in product_groups):
            continue
        bottom = next_y if index + 1 < len(heads) else min(next_y, max(photo["coord"][1] + photo["coord"][3] for photo in product_groups) + 150)
        cards.append({
            "id": f"G{len(cards) + 1}", "coord": [0, anchor_y, viewport_width, bottom - anchor_y],
            "seedBlockId": "", "memberBlockIds": [], "confidence": 0.90, "status": "confirmed",
            "classificationHint": {"cardType": "商家卡片_图文下挂", "confidence": 0.90},
            "evidence": ["left_square_merchant_head", "right_side_attached_product_image_group", "left_coupon_art_excluded"],
            "headPhotoId": head["id"], "attachedProductPhotoIds": [photo["id"] for photo in product_groups],
        })
    return cards


def _split_cards_on_left_media_anchors(cards: list[dict[str, Any]], facts: dict[str, Any], blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Recover a bottom card whose photo shares one oversized structure block.

    Long-page row segmentation can merge two adjacent product cards when the
    final card is clipped by the viewport.  Two vertically separated, large
    left-column media anchors are stronger physical boundaries than that merged
    block.  Merchant graphic cards are handled later by their specialised
    detector, so its product strip cannot become the final owner.
    """
    viewport_width = int(facts["viewport"]["width"])
    photos = [
        item for item in facts.get("candidates", {}).get("photos", [])
        if item.get("route") == "accepted" and item["coord"][0] < viewport_width * 0.18
        and item["coord"][2] >= 96 and item["coord"][3] >= 96
    ]
    output: list[dict[str, Any]] = []
    for card in cards:
        x, y, width, height = card["coord"]
        anchors = sorted(
            (item for item in photos if y <= item["coord"][1] < y + height),
            key=lambda item: item["coord"][1],
        )
        deduped: list[dict[str, Any]] = []
        for anchor in anchors:
            if not deduped or anchor["coord"][1] - deduped[-1]["coord"][1] >= 96:
                deduped.append(anchor)
        split_starts = [anchor["coord"][1] for anchor in deduped[1:] if anchor["coord"][1] >= y + max(120, round(height * 0.35))]
        if not split_starts:
            output.append(card)
            continue
        starts = [y] + split_starts
        ends = split_starts + [y + height]
        for part_index, (start, end) in enumerate(zip(starts, ends), 1):
            if end - start < 96:
                continue
            coord = [x, start, width, end - start]
            members = [block for block in blocks if _overlap_y(block["coord"], coord)]
            output.append({
                **card,
                "id": f"{card['id']}S{part_index}", "coord": coord,
                "memberBlockIds": [member["id"] for member in members],
                "evidence": sorted(set(card.get("evidence", [])) | {"left_media_anchor_split"}),
            })
    return output


def _split_two_column_grid_cards(cards: list[dict[str, Any]], facts: dict[str, Any], blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Split repeated full-width rows into independent two-column cells.

    The trigger is screenshot-local: at least two rows contain paired
    near-half-width photo slots.  Card cells are then emitted row-major, so a
    text-only heterogeneous tile in one cell cannot absorb its hotel neighbour.
    Image height is intentionally not part of the contract.
    """
    viewport_width = int(facts["viewport"]["width"])
    photos = [item for item in facts.get("candidates", {}).get("photos", []) if item.get("route") == "accepted"]

    def paired_media(card: dict[str, Any]) -> bool:
        y0, y1 = card["coord"][1], card["coord"][1] + card["coord"][3]
        local = [item for item in photos if y0 <= item["coord"][1] < y1 and viewport_width * 0.38 <= item["coord"][2] <= viewport_width * 0.52]
        return any(item["coord"][0] < viewport_width * 0.10 for item in local) and any(item["coord"][0] >= viewport_width * 0.50 for item in local)

    full_rows = [card for card in cards if card["coord"][2] >= viewport_width * 0.90]
    if sum(paired_media(card) for card in full_rows) < 2:
        return cards

    margin = max(0, round(viewport_width * 0.014))
    midpoint = viewport_width // 2
    cell_width = midpoint - margin
    output: list[dict[str, Any]] = []
    for card in cards:
        if card not in full_rows:
            output.append(card)
            continue
        y, height = card["coord"][1], card["coord"][3]
        for column, x in (("left", margin), ("right", midpoint)):
            coord = [x, y, cell_width, height]
            local_text = [
                item for item in facts.get("candidates", {}).get("text", [])
                if item.get("route") != "rejected"
                and item["coord"][0] < x + cell_width and item["coord"][0] + item["coord"][2] > x
                and _overlap_y(item["coord"], coord)
            ]
            local_media = [
                item for item in photos
                if item["coord"][0] < x + cell_width and item["coord"][0] + item["coord"][2] > x
                and _overlap_y(item["coord"], coord)
            ]
            if not local_text and not local_media:
                continue
            members = [block for block in blocks if _overlap_y(block["coord"], coord)]
            output.append({
                **card,
                "id": f"{card['id']}-{column}",
                "coord": coord,
                "memberBlockIds": [member["id"] for member in members],
                "evidence": sorted(set(card.get("evidence", [])) | {"two_column_grid_cell_boundary", f"grid_column:{column}"}),
                "gridColumn": column,
            })
    return output


def build_candidates(facts: dict[str, Any], structure: dict[str, Any]) -> dict[str, Any]:
    if facts.get("contractVersion") != "phase2.cv-facts.v1":
        raise ValueError("cv facts version is not supported")
    if structure.get("contractVersion") != "phase2.search-page-structure.v1":
        raise ValueError("structure version is not supported")
    blocks = sorted(structure.get("blocks", []), key=lambda block: block["coord"][1])
    modules = _module_candidates(facts, structure)
    sort_modules = [module for module in modules if module["module"] == "sort_filter" and module["status"] == "confirmed"]
    cv_results_start_y = max((module["coord"][1] + module["coord"][3] for module in sort_modules), default=0)
    # The current-pixel review can establish the list boundary when CV has no
    # usable text (and therefore cannot detect the sort row). A confirmed
    # result-list start is stronger than a sort-row estimate; otherwise the
    # reviewed sort row supplies the same boundary as its CV counterpart.
    reviewed_modules = facts.get("routing", {}).get("visualReview", {}).get("modules", [])
    reviewed_modules = reviewed_modules if isinstance(reviewed_modules, list) else []
    reviewed_list_starts = [
        module["coord"][1] for module in reviewed_modules
        if isinstance(module, dict) and module.get("moduleType") == "result_list"
        and module.get("visibleStatus") == "confirmed"
        and isinstance(module.get("coord"), list) and len(module["coord"]) == 4
    ]
    reviewed_sort_bottoms = [
        module["coord"][1] + module["coord"][3] for module in reviewed_modules
        if isinstance(module, dict) and module.get("moduleType") == "sort_filter"
        and module.get("visibleStatus") == "confirmed"
        and isinstance(module.get("coord"), list) and len(module["coord"]) == 4
    ]
    results_start_y = max(
        cv_results_start_y,
        max(reviewed_list_starts, default=0),
        max(reviewed_sort_bottoms, default=0),
    )
    seeds = {index for index, block in enumerate(blocks) if block.get("layoutCandidate") == "left_image_right_text" and block.get("confidence", 0) >= 0.75}
    # Photo detection is a useful second seed source: OCR can occasionally
    # cause a valid image-left/text-right block to be labelled "other".
    for photo in facts.get("candidates", {}).get("photos", []):
        px, py, pw, ph = photo["coord"]
        if px > facts["viewport"]["width"] * 0.40 or pw < 96 or ph < 96:
            continue
        for index, block in enumerate(blocks):
            if _overlap_y(block["coord"], photo["coord"]) and block["coord"][3] >= 160:
                seeds.add(index)
                break
    seeds = sorted(seeds)
    seeds = [index for index in seeds if blocks[index]["coord"][1] >= results_start_y]
    # A horizontal category/image filter can look like an image-left/text-right
    # block after OCR has been rerun, especially when its labels are sparse.
    # It is not a result card: several similarly sized images share the same
    # row and span most of the viewport.  Reject it at candidate discovery so
    # Phase5 never has to silently discard a spurious ``unknown`` card.
    def is_horizontal_image_filter(block: dict[str, Any]) -> bool:
        bx, by, bw, bh = block["coord"]
        local_photos = [
            photo for photo in facts.get("candidates", {}).get("photos", [])
            if photo.get("route") == "accepted" and _overlap_y(photo["coord"], block["coord"])
        ]
        centers = sorted({photo["coord"][0] + photo["coord"][2] / 2 for photo in local_photos})
        return len(centers) >= 3 and centers[-1] - centers[0] >= bw * 0.45

    seeds = [index for index in seeds if not is_horizontal_image_filter(blocks[index])]
    trusted_non_result_modules = [
        module["coord"] for module in modules
        if module.get("status") == "confirmed" and module.get("module") in {"business_image_filter"}
    ]
    seeds = [index for index in seeds if not any(_overlap_y(blocks[index]["coord"], module_coord) for module_coord in trusted_non_result_modules)]
    cards: list[dict[str, Any]] = []
    for card_index, start_index in enumerate(seeds):
        end_index = seeds[card_index + 1] if card_index + 1 < len(seeds) else len(blocks)
        members = blocks[start_index:end_index]
        # Do not absorb a very distant next page/module. The next card seed
        # already provides the normal stopping boundary.
        while len(members) > 1 and members[-1]["coord"][1] - members[0]["coord"][1] > max(720, members[0]["coord"][3] * 3):
            members.pop()
        coord = _union([member["coord"] for member in members])
        cards.append({
            "id": f"C{card_index + 1}", "coord": coord,
            "seedBlockId": blocks[start_index]["id"], "memberBlockIds": [member["id"] for member in members],
            "confidence": round(min(0.95, blocks[start_index]["confidence"]), 4),
            "status": "confirmed", "evidence": ["repeated_left_image_right_text_seed", "attached_until_next_card_seed"],
        })
    # If two consecutive full-width cards establish a stable repeat interval,
    # recover at most one immediately preceding card whose image seed was
    # missed. This uses only the current screenshot and aggregate geometry;
    # it never imports a golden coordinate or expected card count.
    if len(cards) >= 2:
        first_start, second_start = cards[0]["coord"][1], cards[1]["coord"][1]
        interval = second_start - first_start
        predicted_start = first_start - interval
        confirmed_top_floor = max(
            (module["coord"][1] + module["coord"][3] for module in modules
             if module.get("status") == "confirmed" and module.get("module") in {"tab", "sort_filter", "business_image_filter"}),
            default=results_start_y,
        )
        proposed = [0, predicted_start, int(facts["viewport"]["width"]), interval]
        interval_ratio = interval / int(facts["viewport"]["height"])
        local_text = [item for item in facts.get("candidates", {}).get("text", []) if item.get("route") != "rejected" and _overlap_y(item["coord"], proposed)]
        local_photos = [item for item in facts.get("candidates", {}).get("photos", []) if item.get("route") == "accepted" and _overlap_y(item["coord"], proposed)]
        overlaps_module = any(_overlap_y(proposed, coord) for coord in trusted_non_result_modules)
        if predicted_start >= max(results_start_y, confirmed_top_floor) and 0.05 <= interval_ratio <= 0.35 and not overlaps_module and not is_horizontal_image_filter({"coord": proposed}) and (len(local_text) >= 2 or local_photos):
            members = [block for block in blocks if _overlap_y(block["coord"], proposed)]
            cards.insert(0, {
                "id": "C0", "coord": proposed, "seedBlockId": "", "memberBlockIds": [member["id"] for member in members],
                "confidence": 0.78, "status": "confirmed",
                "evidence": ["learned_repeat_interval_backfill", "current_screenshot_two_card_periodicity"],
            })
    cards = _split_cards_on_left_media_anchors(cards, facts, blocks)
    cards = _split_two_column_grid_cards(cards, facts, blocks)
    merchant_head_cards = _repeated_merchant_head_cards(facts, blocks, results_start_y)
    if merchant_head_cards:
        cards = merchant_head_cards
    graphic_cards = _merchant_graphic_hang_cards(facts, results_start_y)
    if graphic_cards and not merchant_head_cards:
        # The specialised detector owns intervals it can explain. Keep generic
        # cards only for non-overlapping list sections, avoiding duplicates.
        def overlaps_special(card: dict[str, Any]) -> bool:
            cy0, cy1 = card["coord"][1], card["coord"][1] + card["coord"][3]
            return any(cy0 < special["coord"][1] + special["coord"][3] and cy1 > special["coord"][1] for special in graphic_cards)
        cards = graphic_cards + [card for card in cards if not overlaps_special(card)]
        # Preserve a final naturally cropped repetition even when it has no
        # visible right-side product group. The preceding complete specialised
        # cards establish the topology; semantic mapping still applies the
        # normal bottom-partial inheritance and gate policy.
        viewport_height = int(facts["viewport"]["height"])
        for photo in facts.get("candidates", {}).get("photos", []):
            px, py, pw, ph = photo["coord"]
            ratio = pw / ph if ph else 0
            if photo.get("route") != "accepted" or px > int(facts["viewport"]["width"]) * 0.18 or not 0.65 <= ratio <= 1.35:
                continue
            if py + ph < viewport_height - max(20, round(viewport_height * 0.02)):
                continue
            proposed = [0, py, int(facts["viewport"]["width"]), viewport_height - py]
            if any(_overlap_y(proposed, card["coord"]) for card in cards):
                continue
            cards.append({
                "id": "partial", "coord": proposed, "seedBlockId": "", "memberBlockIds": [],
                "confidence": 0.78, "status": "confirmed",
                "evidence": ["left_media_anchor_split", "screen_bottom_natural_crop", "repeated_graphic_card_partial_head"],
                "headPhotoId": photo["id"],
            })
    cards.sort(key=lambda card: card["coord"][1])
    for index, card in enumerate(cards, start=1):
        card["id"] = f"C{index}"
    return {
        "contractVersion": VERSION, "sourceCvFacts": facts.get("screenshot", ""),
        "pageModules": modules, "resultCards": cards, "structureBlocks": blocks,
        "routing": {"rule": "Only repeated list-layout seeds become result-card candidates. Missing optional modules, ungrouped blocks, or uncertain candidates cannot establish absence, defects, failing results, excellence, or a human-review task."}
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build search-page module and result-card candidates")
    parser.add_argument("cv_facts", type=Path)
    parser.add_argument("structure", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_candidates(json.loads(args.cv_facts.read_text(encoding="utf-8")), json.loads(args.structure.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "modules": len(result["pageModules"]), "resultCards": len(result["resultCards"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
