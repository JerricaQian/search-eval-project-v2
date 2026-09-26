#!/usr/bin/env python3
"""Convert a failed Phase2 attempt into bounded, executable retry work."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"not_object:{path}")
    return payload


def card_ids(errors: list[str], gate: dict[str, Any], manifest: dict[str, Any] | None = None) -> list[str]:
    ids = {
        error.split(":", 1)[0]
        for error in errors
        if isinstance(error, str) and error.startswith("C") and ":" in error
    }
    for target in gate.get("reprocessTargets", []):
        if isinstance(target, dict) and str(target.get("cardId", "")):
            ids.add(str(target["cardId"]))
    for error in errors:
        if not error.startswith("semantic_ownership:"):
            continue
        parts = error.split(":")
        for part in parts[2:]:
            if re.fullmatch(r"C\d+", part):
                ids.add(part)
    # Manifest validation reports human-readable, one-based card positions
    # (``cards[1]`` is the first card).  Convert that position to the
    # zero-based Python list index before resolving the stable card ID.
    # Keeping this conversion here prevents a failed middle card from being
    # retried as the next (often naturally cropped) tail card.
    cards = manifest.get("cards", []) if isinstance(manifest, dict) else []
    for error in errors:
        match = re.search(r"(?:manifest_audit:)?cards\[(\d+)\]", error)
        if not match or not isinstance(cards, list):
            continue
        index = int(match.group(1)) - 1
        if 0 <= index < len(cards) and isinstance(cards[index], dict):
            card_id = str(cards[index].get("cardId", ""))
            if card_id:
                ids.add(card_id)
    return sorted(ids)


def build(gate: dict[str, Any], manifest_audit: dict[str, Any] | None, attempt: int, max_attempts: int,
          manifest: dict[str, Any] | None = None,
          ownership_audit: dict[str, Any] | None = None) -> dict[str, Any]:
    errors = [str(value) for value in gate.get("errors", [])]
    if manifest_audit and manifest_audit.get("valid") is not True:
        errors.extend(f"manifest_audit:{value}" for value in manifest_audit.get("errors", []))
    if ownership_audit and ownership_audit.get("valid") is not True:
        errors.extend(f"semantic_ownership:{value}" for value in ownership_audit.get("errors", []))
    targets = []
    for card_id in card_ids(errors, gate, manifest):
        card_errors = [error for error in errors if error.startswith(f"{card_id}:") or
                       (error.startswith("semantic_ownership:") and card_id in error.split(":")[2:])]
        if not card_errors and isinstance(manifest, dict):
            cards = manifest.get("cards", [])
            index = next((i for i, card in enumerate(cards) if isinstance(card, dict) and card.get("cardId") == card_id), None)
            if index is not None:
                validator_position = index + 1
                card_errors = [error for error in errors if f"cards[{validator_position}]" in error]
        action = "redo_card_current_pixel_review"
        required = ["cardTypeCandidate", "topology.regions", "topology.attachedItems", "atomic fields with separate coords"]
        if any("graphic" in error or "attached_goods" in error for error in card_errors):
            action = "redo_card_topology_using_cv_photo_candidates"
            required.append("do not declare graphic downhang without a CV photo anchor")
        if any("topology_selected_card_type_conflict" in error for error in card_errors):
            required.append("use the canonical merchant state machine; no-downhang is not heterogeneous")
        targets.append({"cardId": card_id, "errors": card_errors, "action": action, "required": required})
    page_module_targets = []
    for error in errors:
        if not error.startswith("semantic_ownership:"):
            continue
        parts = error.split(":")
        reason = parts[1] if len(parts) > 1 else ""
        if reason not in {"page_module_owned_by_result_card", "pre_results_module_inside_result_flow",
                          "reviewed_page_module_not_published", "published_page_module_not_in_review",
                          "rejected_page_module_still_published",
                          "result_list_does_not_own_card",
                          "duplicate_singleton_page_module", "result_flow_positions_not_contiguous",
                          "result_flow_positions_not_visual_order", "result_flow_position_invalid"}:
            continue
        module_type = "result_list" if reason == "result_list_does_not_own_card" else parts[2] if len(parts) > 2 else "result_flow"
        page_module_targets.append({
            "moduleType": module_type, "error": error,
            "action": "review_page_module_owner_and_reject_or_correct_cv_candidate",
        })
    if errors and attempt < max_attempts:
        next_action = "rerun_cv_candidate_then_targeted_current_pixel_review_then_publish"
    elif errors:
        next_action = "finalize_blocked_receipt_with_all_attempt_artifacts"
    else:
        next_action = "advance_to_phase3"
    return {
        "contract": "phase2.retry-plan",
        "retryRequired": bool(errors) and attempt < max_attempts,
        "attempt": attempt,
        "maxAttempts": max_attempts,
        "nextAttempt": attempt + 1 if errors and attempt < max_attempts else None,
        "errors": errors,
        "targets": targets,
        "pageModuleTargets": page_module_targets,
        "nextAction": next_action,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recognition-gate", required=True, type=Path)
    parser.add_argument("--manifest-audit", type=Path)
    parser.add_argument("--manifest", type=Path,
                        help="Published attempt manifest; resolves audit card indexes to stable card IDs.")
    parser.add_argument("--ownership-audit", type=Path,
                        help="Pre-publication module/card/item ownership conflicts and candidate decisions.")
    parser.add_argument("--attempt", required=True, type=int)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.attempt < 1 or args.max_attempts < args.attempt:
        parser.error("attempt_must_be_between_1_and_max_attempts")
    gate = load(args.recognition_gate)
    audit = load(args.manifest_audit) if args.manifest_audit else None
    manifest = load(args.manifest) if args.manifest else None
    ownership_audit = load(args.ownership_audit) if args.ownership_audit else None
    result = build(gate, audit, args.attempt, args.max_attempts, manifest, ownership_audit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not result["retryRequired"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
