#!/usr/bin/env python3
"""Apply an explicitly recorded main-session local visual review to CV facts.

This is deliberately an input-driven evidence step, not a language-correction
model. A review must identify the current screenshot, local crop and each
observed string. Superseded OCR inside that reviewed card is retained as
rejected audit evidence and can never leak into the manifest.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any

from extract_cv_facts import Box, _direct_text_phase3_facts
from phase2_contract import fulfillment_semantic_kind


TOPOLOGY_SLOTS = {
    "head_media", "merchant_head", "merchant_info", "rights", "attached_goods", "text_attachment", "price", "primary_info",
    "title", "subtitle", "tag", "package_summary", "performance_info", "entity_title", "entity_info", "media", "secondary_info", "action", "attachment",
}


def _normalise_topology(card: dict[str, Any]) -> dict[str, Any]:
    """Keep reviewer-declared card topology as structured current-pixel fact.

    Geometry may corroborate a relation, but it must not manufacture one.  A
    graphic merchant card therefore declares its head, merchant summary and
    attached-goods rail explicitly, plus one visible item record per rail
    item.  This is deliberately compact enough for a visual-review JSON.
    """
    raw = card.get("topology", {})
    if not isinstance(raw, dict):
        return {"regions": [], "attachedItems": []}
    regions = []
    for region in raw.get("regions", []):
        if not isinstance(region, dict):
            continue
        slot, coord = str(region.get("slot", "")), region.get("coord")
        if slot in TOPOLOGY_SLOTS and isinstance(coord, list) and len(coord) == 4 and all(isinstance(value, int) for value in coord):
            regions.append({"slot": slot, "coord": coord, "visibleStatus": region.get("visibleStatus", "confirmed")})
    items = []
    for index, item in enumerate(raw.get("attachedItems", []), 1):
        if not isinstance(item, dict):
            continue
        coord = item.get("coord")
        if not isinstance(coord, list) or len(coord) != 4 or not all(isinstance(value, int) for value in coord):
            continue
        items.append({"itemIndex": int(item.get("itemIndex", index)), "coord": coord,
                      "visibleStatus": item.get("visibleStatus", "confirmed")})
    return {"regions": regions, "attachedItems": items}


def _topology_slot(topology: dict[str, Any], coord: list[int]) -> tuple[str, int | None]:
    for item in topology.get("attachedItems", []):
        if overlap(coord, item["coord"]):
            # Item membership and its rail type are separate facts.  The old
            # implementation returned ``attached_goods`` for every item,
            # silently turning text downhang atoms into graphic ones in later
            # manifest assembly.  Resolve the declared enclosing rail first.
            rail = next(
                (str(region.get("slot", "")) for region in topology.get("regions", [])
                 if str(region.get("slot", "")) in {"attached_goods", "text_attachment"}
                 and overlap(coord, region.get("coord", []))),
                "attached_goods",
            )
            return rail, int(item["itemIndex"])
    for region in topology.get("regions", []):
        if overlap(coord, region["coord"]):
            return str(region["slot"]), None
    return "", None


def load_review(path: Path) -> dict[str, Any]:
    """Load a current-pixel review, optionally layering a small local patch.

    A patch can use ``extends`` to reference an immutable earlier review and
    override only newly reviewed fields such as page modules.  It never
    modifies the source review and keeps the same screenshot identity.
    """
    review = json.loads(path.read_text(encoding="utf-8"))
    extends = review.pop("extends", "")
    if not extends:
        return review
    base_path = Path(str(extends)).expanduser()
    if not base_path.is_absolute():
        base_path = (path.parent / base_path).resolve()
    base = load_review(base_path)
    if review.get("screenshot") and base.get("screenshot") and Path(str(review["screenshot"])).resolve() != Path(str(base["screenshot"])).resolve():
        raise ValueError("visual review patch screenshot does not match its base review")
    merged = {**base, **review}
    for key in ("cards", "modules", "rejectedModules", "localReviewPaths"):
        if key not in review:
            merged[key] = base.get(key, [])
    # A Phase2 retry normally corrects one rejected card.  Requiring a full
    # replacement list makes that retry silently discard previously reviewed
    # cards, contrary to the bounded-rework rule. ``cardOverrides`` is a
    # narrow, screenshot-bound overlay: every override must name an existing
    # card and replaces only the explicitly supplied card keys.
    overrides = review.get("cardOverrides", [])
    if overrides:
        if not isinstance(overrides, list):
            raise ValueError("visual review cardOverrides must be a list")
        cards = merged.get("cards", [])
        if not isinstance(cards, list):
            raise ValueError("visual review base cards must be a list")
        by_id = {str(card.get("cardId", "")): dict(card) for card in cards if isinstance(card, dict)}
        for override in overrides:
            if not isinstance(override, dict):
                raise ValueError("visual review cardOverride must be an object")
            card_id = str(override.get("cardId", ""))
            if not card_id or card_id not in by_id:
                raise ValueError(f"visual review cardOverride unknown cardId: {card_id}")
            by_id[card_id] = {**by_id[card_id], **{key: value for key, value in override.items() if key != "cardId"}}
        merged["cards"] = [by_id.get(str(card.get("cardId", "")), card) if isinstance(card, dict) else card for card in cards]
    merged.pop("cardOverrides", None)
    return merged

def overlap(a: list[int], b: list[int]) -> bool:
    return a[0] < b[0]+b[2] and a[0]+a[2] > b[0] and a[1] < b[1]+b[3] and a[1]+a[3] > b[1]


def _fulfillment_field_owns_photo_candidate(field: dict[str, Any], photo: dict[str, Any]) -> bool:
    """Return true when a CV photo is actually the reviewed fulfillment UI."""
    if field.get("role") != "fulfillment" and not fulfillment_semantic_kind(str(field.get("text", ""))):
        return False
    label = field.get("coord", [])
    image = photo.get("coord", [])
    if not all(isinstance(box, list) and len(box) == 4 for box in (label, image)):
        return False
    x0, y0 = max(label[0], image[0]), max(label[1], image[1])
    x1, y1 = min(label[0] + label[2], image[0] + image[2]), min(label[1] + label[3], image[1] + image[3])
    shared = max(0, x1 - x0) * max(0, y1 - y0)
    label_area = max(1, label[2] * label[3])
    image_area = max(1, image[2] * image[3])
    return shared / label_area >= 0.70 and image_area / label_area <= 12

def apply(facts: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
    if Path(str(review.get("screenshot", ""))).resolve() != Path(str(facts["screenshot"])).resolve():
        raise ValueError("visual review screenshot does not match CV facts")
    observed = review.get("cards", [])
    # A local review normally confirms only selected fields (for example the
    # merchant header).  It is not evidence that every other line in the card
    # is wrong.  Replacing the whole card silently discarded valid Paddle
    # reads of promotions and attached products, leaving a schema-valid but
    # materially incomplete manifest.  Only an explicit full-card replacement
    # may invalidate the rest of that card's OCR observations.
    replacement_boxes = [
        field["coord"]
        for card in observed
        for field in card.get("fields", [])
        if isinstance(field, dict) and isinstance(field.get("coord"), list) and len(field["coord"]) == 4
    ]
    full_card_replacements = [card["coord"] for card in observed if card.get("replaceAllCardText") is True]
    for item in facts.get("candidates", {}).get("text", []):
        if any(overlap(item["coord"], box) for box in replacement_boxes + full_card_replacements):
            item["route"] = "rejected"
            item.setdefault("rejectionReasons", []).append("superseded_by_main_session_local_visual_review")
    # A directly reviewed photo is the current-pixel replacement for a CV
    # detection in the same box. Keep an explicit ``replacePhotoBoxes`` escape
    # hatch for a reviewer that wants to suppress a photo without recording a
    # replacement, but never publish both atoms for one visible image.
    replacement_photo_boxes = [
        box for card in observed for box in card.get("replacePhotoBoxes", [])
        if isinstance(box, list) and len(box) == 4
    ] + [
        photo.get("coord") for card in observed for photo in card.get("photos", [])
        if isinstance(photo, dict) and isinstance(photo.get("coord"), list) and len(photo["coord"]) == 4
    ]
    for item in facts.get("candidates", {}).get("photos", []):
        if any(overlap(item["coord"], box) for box in replacement_photo_boxes):
            item["route"] = "rejected"
            item.setdefault("rejectionReasons", []).append("superseded_by_main_session_local_visual_review")
    next_id = 1
    text = facts.setdefault("candidates", {}).setdefault("text", [])
    for card in observed:
        topology = _normalise_topology(card)
        for field in card.get("fields", []):
            coord = [int(v) for v in field["coord"]]
            label = str(field["text"]).strip()
            if not label:
                continue
            box = Box(*coord)
            visible_status = field.get("visibleStatus", "confirmed")
            if visible_status not in {"confirmed", "naturally_cropped", "uncertain"}:
                raise ValueError(f"invalid visual review visibleStatus: {visible_status}")
            phase3_facts = _direct_text_phase3_facts(label, box, {"colorRole": field.get("colorRole", "unknown"), "evidence": "main_session_local_visual_read"}, True)
            # Typography is a current-pixel fact required by the hierarchy
            # gate. Preserve the geometry-derived size when the reviewer did
            # not explicitly record a bucket, but never leave a reviewed text
            # atom with an unusable unknown weight or colour role.
            text_facts = phase3_facts["textFacts"]
            text_facts["fontSizeBucket"] = field.get("fontSizeBucket", text_facts["fontSizeBucket"])
            text_facts["fontWeightBucket"] = field.get("fontWeightBucket", "regular")
            text_facts["textColorRole"] = field.get("colorRole", "neutral")
            # A visual review may additionally record the typographic buckets it
            # confirmed from the current pixels.  Do not manufacture these
            # fields: preserve the extractor's values unless the review has an
            # explicit, enum-valid observation.  This keeps hierarchy facts
            # attributable to the current-image review instead of an OCR guess.
            text_facts = phase3_facts.get("textFacts", {})
            for key in ("fontSizeBucket", "fontWeightBucket", "textColorRole", "emphasisLevel"):
                value = field.get(key)
                if isinstance(value, str) and value.strip() and value != "unknown":
                    text_facts[key] = value
            phase3_facts["textFacts"] = text_facts
            if visible_status != "confirmed":
                phase3_facts["render"].update({"visibleStatus": visible_status, "renderState": "partial" if visible_status == "naturally_cropped" else "uncertain"})
                phase3_facts["textFacts"]["textStatus"] = visible_status
                # Visual facts use the existing binary confidence enum;
                # render/text preserve the more precise natural-crop state.
                phase3_facts["visual"]["visualStatus"] = "uncertain"
            topology_slot, item_index = _topology_slot(topology, coord)
            # In a text downhang, the reviewer has already established that
            # this line belongs to an independently purchasable/service item.
            # OCR's generic ``subtitle`` label is not enough to erase that
            # ownership: retain the explicit current-pixel attachment role so
            # every confirmed item can be audited with its title and price.
            if topology_slot == "text_attachment" and field.get("role") in {"attachment", "subtitle"}:
                phase3_facts["textFacts"]["semanticRole"] = "attachment"
            text.append({"id": f"VR{next_id}", "kind": "text", "text": label, "coord": coord,
                "ocrConsensus": {"status": "confirmed", "primaryText": label, "secondaryText": "",
                                 "method": "main_session_local_visual_read"},
                "geometry": {"rowAlignment": "main_session_local_review"},
                "visualHint": {"colorRole": field.get("colorRole", "unknown"), "evidence": "main_session_local_visual_read"},
                "phase3Facts": phase3_facts,
                "route": "accepted", "rejectionReasons": [],
                "visualReview": {"cardId": card.get("cardId", ""), "crop": card["coord"], "readId": field.get("readId", "main_session_local_read"), "role": field.get("role", "other"), "topologySlot": topology_slot, "itemIndex": item_index, "visibleStatus": visible_status}})
            next_id += 1
    # Resolve reviewed fulfillment labels before later card topology consumes
    # generic CV media.  The rejected box remains in the audit with the exact
    # semantic reason; this is a classification correction, not a new gate.
    fulfillment_fields = [
        field for card in observed for field in card.get("fields", [])
        if isinstance(field, dict)
        and (field.get("role") == "fulfillment" or fulfillment_semantic_kind(str(field.get("text", ""))))
    ]
    for photo in facts.get("candidates", {}).get("photos", []):
        if photo.get("route") == "accepted" and any(
            _fulfillment_field_owns_photo_candidate(field, photo) for field in fulfillment_fields
        ):
            photo["route"] = "rejected"
            photo.setdefault("rejectionReasons", []).append("reviewed_fulfillment_ui_not_photo")
    next_photo_id = 1
    photos = facts.setdefault("candidates", {}).setdefault("photos", [])
    for card in observed:
        topology = _normalise_topology(card)
        for photo in card.get("photos", []):
            coord = [int(v) for v in photo["coord"]]
            visible_status = photo.get("visibleStatus", "confirmed")
            if visible_status not in {"confirmed", "naturally_cropped", "uncertain"}:
                raise ValueError(f"invalid visual review photo visibleStatus: {visible_status}")
            visual_status = "confirmed" if visible_status == "confirmed" else "uncertain"
            topology_slot, item_index = _topology_slot(topology, coord)
            photos.append({
                "id": f"VP{next_photo_id}", "kind": "photo_candidate", "coord": coord,
                "detectorRule": "main_session_local_visual_read", "confidence": 1.0,
                "confidenceParts": {"detector": 1.0, "rowGeometry": 1.0},
                "phase3Facts": {
                    "render": {"visibleStatus": visible_status, "renderState": "normal" if visible_status == "confirmed" else "partial" if visible_status == "naturally_cropped" else "uncertain", "isPhoto": True, "isSystemUi": False},
                    "visual": {"entityKind": "image", "visualStatus": visual_status, "isColored": False, "isShaped": False, "colorRole": "unknown", "backgroundColor": "", "textColor": "", "borderColor": "", "hasGraphicAssist": False, "graphicType": "无", "styleKey": "image|unknown|photo|无容器|无", "colorEvidence": "main_session_local_visual_read"},
                },
                "route": "accepted", "rejectionReasons": [],
                "visualReview": {"cardId": card.get("cardId", ""), "crop": card["coord"], "readId": photo.get("readId", "main_session_local_read"), "topologySlot": topology_slot, "itemIndex": item_index, "visibleStatus": visible_status},
            })
            next_photo_id += 1
    # Page-level modules can be directly confirmed in the current screenshot
    # (for example a conditional safety notice or an intent graphical filter).
    # Keep those facts alongside card reads so the manifest does not lose a
    # visible page module merely because the CV module detector did not name it.
    review_modules = review.get("modules", [])
    if not isinstance(review_modules, list):
        raise ValueError("visual review modules must be a list")
    rejected_modules = review.get("rejectedModules", [])
    if not isinstance(rejected_modules, list):
        raise ValueError("visual review rejectedModules must be a list")
    facts.setdefault("routing", {})["visualReview"] = {
        "source": "main_session_local_read", "cards": observed,
        "modules": review_modules, "rejectedModules": rejected_modules,
        "moduleInventoryComplete": "modules" in review,
        "localReviewReadCount": len(observed),
    }
    facts["routing"]["unresolvedCandidateIds"] = [item["id"] for kind in ("text", "photos") for item in facts["candidates"].get(kind, []) if item.get("route") != "accepted"]
    return facts

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--facts", type=Path, required=True); parser.add_argument("--review", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = apply(json.loads(args.facts.read_text(encoding="utf-8")), load_review(args.review))
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return 0
if __name__ == "__main__": raise SystemExit(main())
