#!/usr/bin/env python3
"""Audit one screenshot's module/card/item/atom ownership before publication.

The audit does not infer new screenshot facts. It compares the current-pixel
review, CV candidates and the assembled manifest, and rejects incompatible
claims for the same rendered supply or atom.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from apply_visual_review import load_review


CONTRACT_PATH = Path(__file__).resolve().parents[1] / "references" / "semantic_ownership_contract.v2.json"


def load_contract() -> dict[str, Any]:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if contract.get("contractVersion") != "phase2.semantic-ownership.v2":
        raise ValueError("semantic_ownership_contract_version_invalid")
    return contract


def canonical_module_type(value: Any, contract: dict[str, Any] | None = None) -> str:
    contract = contract or load_contract()
    raw = str(value or "other")
    return str(contract["moduleAliases"].get(raw, raw))


def valid_box(value: Any) -> bool:
    return (
        isinstance(value, list) and len(value) == 4
        and all(isinstance(part, (int, float)) for part in value)
        and value[2] > 0 and value[3] > 0
    )


def intersection_area(left: list[int], right: list[int]) -> float:
    width = max(0, min(left[0] + left[2], right[0] + right[2]) - max(left[0], right[0]))
    height = max(0, min(left[1] + left[3], right[1] + right[3]) - max(left[1], right[1]))
    return width * height


def area(box: list[int]) -> float:
    return box[2] * box[3]


def same_supply_instance(left: Any, right: Any) -> bool:
    """Compare independent supply boxes, not a wrapper with its contents."""
    return valid_box(left) and valid_box(right) and intersection_area(left, right) / min(area(left), area(right)) >= 0.8


def _card_elements(card: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    elements: list[dict[str, Any]] = []
    owners: dict[str, int] = {}
    for region in card.get("regions", []):
        if not isinstance(region, dict):
            continue
        elements.extend(item for item in region.get("elements", []) if isinstance(item, dict))
        for group in region.get("itemGroups", []):
            if isinstance(group, dict):
                for element_id in group.get("elementIds", []):
                    owners[str(element_id)] = group.get("itemIndex")
    return elements, owners


def _reviewed_item_index(box: list[int], topology: dict[str, Any], contract: dict[str, Any]) -> tuple[int | None, str | None]:
    rails = [region.get("coord") for region in topology.get("regions", [])
             if isinstance(region, dict) and region.get("slot") in contract["attachedTopologySlots"]
             and valid_box(region.get("coord"))]
    # A merchant head image can graze the attached rail by a few pixels. Only
    # atoms substantially inside the rail can be required to own an item.
    if not any(intersection_area(box, rail) / area(box) >= 0.6 for rail in rails):
        return None, None
    matches = [item.get("itemIndex") for item in topology.get("attachedItems", [])
               if isinstance(item, dict) and valid_box(item.get("coord"))
               and intersection_area(box, item["coord"]) / area(box) >= 0.6]
    if len(matches) != 1 or not isinstance(matches[0], int):
        return None, "reviewed_attached_atom_has_no_unique_item"
    return matches[0], None


def _matching_element(atom: dict[str, Any], elements: list[dict[str, Any]], *, photo: bool) -> dict[str, Any] | None:
    box = atom.get("coord")
    if not valid_box(box):
        return None
    matches = []
    for element in elements:
        element_box = element.get("坐标")
        if not valid_box(element_box) or intersection_area(box, element_box) / area(box) < 0.75:
            continue
        if (element.get("元素类型") == "图片") != photo:
            continue
        if not photo and str(element.get("textFacts", {}).get("rawText", "")) != str(atom.get("text", "")):
            continue
        matches.append(element)
    return matches[0] if len(matches) == 1 else None


def audit_semantic_ownership(manifest: dict[str, Any], review: dict[str, Any],
                             candidates: dict[str, Any] | None = None) -> dict[str, Any]:
    contract = load_contract()
    errors: list[str] = []
    warnings: list[str] = []
    decisions: list[dict[str, str]] = []
    if Path(str(review.get("screenshot", ""))).resolve() != Path(str(manifest.get("screenshot", ""))).resolve():
        errors.append("review_screenshot_mismatch")
    if review.get("completeCurrentPixelReview") is not True:
        errors.append("current_pixel_review_incomplete")
    if not isinstance(review.get("modules"), list):
        warnings.append("module_inventory_not_declared_legacy_cv_fallback")

    cards = [card for card in manifest.get("cards", []) if isinstance(card, dict) and valid_box(card.get("coord"))]
    cards_by_id = {str(card.get("cardId", "")): card for card in cards}
    modules = [module for module in manifest.get("pageFacts", {}).get("modules", [])
               if isinstance(module, dict) and valid_box(module.get("coord"))]
    module_types = [canonical_module_type(module.get("moduleType"), contract) for module in modules]
    if cards and contract["resultListWrapper"] not in module_types:
        errors.append("result_list_missing_for_result_cards")
    for module_type in contract["singletonPageModules"]:
        if module_types.count(module_type) > 1:
            errors.append(f"duplicate_singleton_page_module:{module_type}")

    for module, module_type in zip(modules, module_types):
        box = module["coord"]
        decisions.append({"claim": str(module.get("id", module_type)), "owner": f"page/module/{module_type}", "decision": "accepted"})
        if module_type == contract["resultListWrapper"]:
            for card in cards:
                if card.get("structure", {}).get("isResultListItem") is True and intersection_area(box, card["coord"]) / area(card["coord"]) < 0.6:
                    errors.append(f"result_list_does_not_own_card:{card.get('cardId', '')}")
            continue
        if module_type in contract["cardExclusivePageModules"]:
            for card in cards:
                if same_supply_instance(box, card["coord"]):
                    errors.append(f"page_module_owned_by_result_card:{module_type}:{card.get('cardId', '')}")
        if module_type in contract["preResultsSupplyModules"] and cards:
            first_result_top = min(card["coord"][1] for card in cards)
            if box[1] >= first_result_top:
                errors.append(f"pre_results_module_inside_result_flow:{module_type}")

    list_claims: list[tuple[int, float, float, str]] = []
    for card in cards:
        if card.get("structure", {}).get("isResultListItem") is True:
            list_claims.append((card.get("structure", {}).get("listPosition"), card["coord"][1],
                                card["coord"][1] + card["coord"][3], str(card.get("cardId", ""))))
    for module, module_type in zip(modules, module_types):
        if module.get("isListItem") is True:
            list_claims.append((module.get("listPosition"), module["coord"][1],
                                module["coord"][1] + module["coord"][3], str(module.get("id", module_type))))
    positions = [position for position, _, _, _ in list_claims]
    if any(not isinstance(position, int) or position < 1 for position in positions):
        errors.append("result_flow_position_invalid")
    elif sorted(positions) != list(range(1, len(positions) + 1)):
        errors.append("result_flow_positions_not_contiguous")
    elif any(left[2] <= right[1] and left[0] >= right[0] for left in list_claims for right in list_claims
             if left is not right):
        # The manifest array need not be ordered. Only distinct vertical rows
        # impose order; overlapping two-column cells may start at different y.
        errors.append("result_flow_positions_not_visual_order")

    for reviewed_module in review.get("modules", []):
        if not isinstance(reviewed_module, dict) or not valid_box(reviewed_module.get("coord")):
            continue
        module_type = canonical_module_type(reviewed_module.get("moduleType"), contract)
        if not any(module_type == published_type and same_supply_instance(module["coord"], reviewed_module["coord"])
                   for module, published_type in zip(modules, module_types)):
            errors.append(f"reviewed_page_module_not_published:{module_type}")
    if isinstance(review.get("modules"), list):
        for module, module_type in zip(modules, module_types):
            if module_type == contract["resultListWrapper"]:
                continue  # The result-list wrapper may be derived from reviewed cards.
            if not any(
                isinstance(reviewed, dict)
                and canonical_module_type(reviewed.get("moduleType"), contract) == module_type
                and same_supply_instance(module["coord"], reviewed.get("coord"))
                for reviewed in review["modules"]
            ):
                errors.append(f"published_page_module_not_in_review:{module_type}")
    for rejected_module in review.get("rejectedModules", []):
        if not isinstance(rejected_module, dict) or not valid_box(rejected_module.get("coord")):
            continue
        module_type = canonical_module_type(rejected_module.get("moduleType"), contract)
        if any(module_type == published_type and same_supply_instance(module["coord"], rejected_module["coord"])
               for module, published_type in zip(modules, module_types)):
            errors.append(f"rejected_page_module_still_published:{module_type}")

    for reviewed_card in review.get("cards", []):
        if not isinstance(reviewed_card, dict):
            continue
        card_id = str(reviewed_card.get("cardId", ""))
        card = cards_by_id.get(card_id)
        if card is None:
            errors.append(f"reviewed_card_not_published:{card_id}")
            continue
        if card.get("cardTypeCode") == "异构卡" or card.get("卡片类型") == "异构卡":
            if reviewed_card.get("cardTypeCandidate") != "异构卡":
                errors.append(f"heterogeneous_fallback_conflicts_with_reviewed_known_type:{card_id}")
            hetero_evidence = reviewed_card.get("heterogeneousEvidence")
            structure_field, exclusions_field = contract["heterogeneousPositiveReviewFields"]
            if not (
                isinstance(hetero_evidence, dict)
                and isinstance(hetero_evidence.get(structure_field), str)
                and hetero_evidence[structure_field].strip()
                and isinstance(hetero_evidence.get(exclusions_field), list)
                and any(isinstance(reason, str) and reason.strip() for reason in hetero_evidence[exclusions_field])
            ):
                errors.append(f"heterogeneous_positive_structure_evidence_missing:{card_id}")
        topology = reviewed_card.get("topology", {})
        if not isinstance(topology, dict):
            continue
        declared = [item.get("itemIndex") for item in topology.get("attachedItems", []) if isinstance(item, dict)]
        if declared and (any(not isinstance(index, int) or index < 1 for index in declared)
                         or sorted(declared) != list(range(1, len(declared) + 1))):
            errors.append(f"reviewed_item_indices_invalid:{card_id}")
        elements, owners = _card_elements(card)
        if str(card.get("cardTypeCode", "")).startswith("商家卡片_") or str(card.get("卡片类型", "")).startswith("商家卡片-"):
            attached_elements = [
                element for region in card.get("regions", [])
                if isinstance(region, dict) and region.get("name") in contract["attachedRegions"]
                for element in region.get("elements", []) if isinstance(element, dict)
            ]
            published_item_indices = {owners.get(str(element.get("id", ""))) for element in attached_elements}
            if declared and published_item_indices != set(declared):
                errors.append(f"reviewed_and_published_item_inventory_differs:{card_id}")
            for element in attached_elements:
                element_id = str(element.get("id", ""))
                element_box = element.get("坐标")
                if not valid_box(element_box):
                    continue
                item_index, error = _reviewed_item_index(element_box, topology, contract)
                if error or item_index is None:
                    errors.append(f"published_attached_atom_lacks_review_item:{card_id}:{element_id}")
                elif owners.get(element_id) != item_index:
                    errors.append(f"published_attached_atom_owner_mismatch:{card_id}:{element_id}:{item_index}")
        for kind, photo in (("fields", False), ("photos", True)):
            for atom in reviewed_card.get(kind, []):
                if not isinstance(atom, dict) or not valid_box(atom.get("coord")):
                    continue
                item_index, error = _reviewed_item_index(atom["coord"], topology, contract)
                if error:
                    errors.append(f"{error}:{card_id}")
                    continue
                if item_index is None:
                    continue
                element = _matching_element(atom, elements, photo=photo)
                if element is None:
                    errors.append(f"reviewed_attached_atom_not_published:{card_id}:{item_index}")
                    continue
                if owners.get(str(element.get("id"))) != item_index:
                    errors.append(f"reviewed_item_owner_mismatch:{card_id}:{element.get('id')}:{item_index}")
                decisions.append({"claim": str(element.get("id")), "owner": f"card/{card_id}/item/{item_index}", "decision": "accepted"})

    if candidates:
        for candidate in candidates.get("pageModules", []):
            if not isinstance(candidate, dict) or not valid_box(candidate.get("coord")):
                continue
            module_type = canonical_module_type(candidate.get("module"), contract)
            accepted = any(module_type == published_type and same_supply_instance(candidate["coord"], module["coord"])
                           for module, published_type in zip(modules, module_types))
            if accepted:
                decision = "accepted"
            elif any(
                isinstance(item, dict)
                and canonical_module_type(item.get("moduleType"), contract) == module_type
                and same_supply_instance(item.get("coord"), candidate["coord"])
                for item in review.get("rejectedModules", [])
            ):
                decision = "rejected_by_current_pixel_review"
            elif any(canonical_module_type(item.get("moduleType"), contract) == module_type
                     for item in review.get("modules", []) if isinstance(item, dict)):
                decision = "rejected_by_current_pixel_review"
            elif module_type == contract["resultListWrapper"] and contract["resultListWrapper"] in module_types:
                decision = "rejected_by_card_derived_result_list"
            elif module_type in contract["preResultsSupplyModules"] and any(same_supply_instance(candidate["coord"], card["coord"]) for card in cards):
                decision = "rejected_as_result_card_supply"
            else:
                # CV is a proposal, not a second authority over a completed
                # current-pixel module inventory. An unselected proposal is
                # retained for audit, but cannot veto an otherwise consistent
                # manifest or silently become a published page module.
                decision = "not_selected_by_current_pixel_review" if isinstance(review.get("modules"), list) else "unresolved_cv_candidate"
                warnings.append(f"cv_page_module_not_published:{module_type}")
            decisions.append({"claim": str(candidate.get("id", module_type)), "owner": f"page/module/{module_type}", "decision": decision})

    return {"contractVersion": contract["contractVersion"], "valid": not errors,
            "errors": sorted(set(errors)), "warnings": sorted(set(warnings)), "claimDecisions": decisions}


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit semantic ownership before immutable Phase2 publication")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--visual-review", required=True, type=Path)
    parser.add_argument("--result-candidates", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    review = load_review(args.visual_review)
    candidates = json.loads(args.result_candidates.read_text(encoding="utf-8")) if args.result_candidates else None
    result = audit_semantic_ownership(manifest, review, candidates)
    result["screenshot"] = str(Path(str(manifest.get("screenshot", ""))).resolve())
    result["screenshotSha256"] = hashlib.sha256(Path(result["screenshot"]).read_bytes()).hexdigest()
    result["manifestSha256"] = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
    result["reviewSha256"] = hashlib.sha256(args.visual_review.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"valid": result["valid"], "errors": result["errors"], "warnings": result["warnings"],
                      "output": str(args.output)}, ensure_ascii=False))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
