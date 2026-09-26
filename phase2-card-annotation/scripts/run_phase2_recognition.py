#!/usr/bin/env python3
"""Local Phase2 candidate pass: screenshot -> manifest, artifacts and local audit.

The individual CV/OCR artifacts are retained for current-image calibration.
Production callers must still perform the visual review and exhaustive audit
defined by references/current_image_calibration.v1.md before Phase3 consumes it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

from apply_visual_review import load_review, _normalise_topology
from card_type_registry import display_names, known_result_types
from phase2_contract import merchant_variant, reviewed_card_type, topology_errors, topology_parts


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
GRAPHIC_DOWNHANG_EVIDENCE = {
    "right_side_attached_product_image_group",
    "summary_and_product_rail_owned_together",
}


def _review_card_is_naturally_cropped(review: dict, card: dict, topology: dict) -> bool:
    if any(
        item.get("visibleStatus") == "naturally_cropped"
        for item in topology.get("regions", []) + topology.get("attachedItems", [])
        if isinstance(item, dict)
    ):
        return True
    coord = card.get("coord")
    screenshot = Path(str(review.get("screenshot", ""))).expanduser()
    if not isinstance(coord, list) or len(coord) != 4 or not screenshot.is_file():
        return False
    try:
        with Image.open(screenshot) as image:
            viewport_height = int(image.height)
    except OSError:
        return False
    return coord[1] + coord[3] >= viewport_height - max(20, round(viewport_height * 0.02))


def invoke(arguments: list[str], check: bool = True, env: dict[str, str] | None = None) -> int:
    return subprocess.run(arguments, cwd=ROOT, check=check, env=env).returncode


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_candidate(screenshot: Path, artifacts: Path, output: Path) -> int:
    """Create an explicitly non-publishable local-CV candidate bundle.

    This is deliberately separate from manifest publication: no textual fact,
    topology, or Phase3-ready claim can be made without the later current-pixel
    review.  The bundle binds the retained CV facts to the exact screenshot.
    """
    artifacts.mkdir(parents=True, exist_ok=True)
    facts = artifacts / "cv-facts.candidate.json"
    cv_env = os.environ.copy()
    cv_env["SEARCH_EVAL_PYTHON"] = sys.executable
    cv_env["PHASE2_DISABLE_LOCAL_OCR"] = "1"
    invoke(["bash", str(SCRIPT_DIR / "run_cv_facts.sh"), str(screenshot), "--output", str(facts)], env=cv_env)
    output.write_text(json.dumps({
        "contractVersion": "phase2.candidate-bundle.v2",
        "status": "awaiting_current_pixel_review",
        "screenshot": str(screenshot.resolve()),
        "screenshotSha256": sha256_file(screenshot),
        "factsPath": str(facts.resolve()),
        "phase3Ready": False,
        "wholePageGate": False,
        "visualReviewRequired": True,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


def validate_candidate_bundle(bundle_path: Path, screenshot: Path) -> Path:
    """Return the retained CV facts only when they belong to this screenshot."""
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    if not isinstance(bundle, dict) or bundle.get("contractVersion") != "phase2.candidate-bundle.v2":
        raise ValueError("phase2_candidate_bundle_invalid")
    if bundle.get("status") != "awaiting_current_pixel_review" or bundle.get("phase3Ready") is not False:
        raise ValueError("phase2_candidate_bundle_must_not_be_publishable")
    if Path(str(bundle.get("screenshot", ""))).resolve() != screenshot.resolve():
        raise ValueError("phase2_candidate_bundle_screenshot_mismatch")
    if bundle.get("screenshotSha256") != sha256_file(screenshot):
        raise ValueError("phase2_candidate_bundle_screenshot_hash_mismatch")
    facts = Path(str(bundle.get("factsPath", ""))).resolve()
    if not facts.is_file() or facts.stat().st_size == 0:
        raise ValueError("phase2_candidate_bundle_facts_missing")
    return facts


def write_structure_gate(candidates: Path, semantics: Path, output: Path) -> bool:
    """Stage A: publish only bounded, known page components to Phase2 facts."""
    cards = json.loads(candidates.read_text(encoding="utf-8")).get("resultCards", [])
    mapped = {item.get("cardId"): item for item in json.loads(semantics.read_text(encoding="utf-8")).get("cards", [])}
    errors = []
    if not cards:
        errors.append("no_result_cards")
    for card in cards:
        coord = card.get("coord", [])
        selected = mapped.get(card.get("id"), {}).get("selectedCardType", {})
        if not isinstance(coord, list) or len(coord) != 4 or coord[2] <= 0 or coord[3] <= 0:
            errors.append(f"{card.get('id')}:invalid_component_boundary")
        # ``异构卡`` is the taxonomy's explicit, stable fallback for a real
        # result unit.  It remains fully fact-gated later; rejecting it here
        # contradicts the card contract and makes valid new layouts unable to
        # reach bounded OCR/current-pixel calibration.
        if selected.get("status") != "confirmed":
            errors.append(f"{card.get('id')}:page_or_component_type_unresolved")
    output.write_text(json.dumps({"contractVersion": "phase2.structure-gate.v1", "valid": not errors, "errors": errors}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return not errors


def _overlap(left: list[int], right: list[int]) -> bool:
    return left[0] < right[0] + right[2] and left[0] + left[2] > right[0] and left[1] < right[1] + right[3] and left[1] + left[3] > right[1]


def validate_cv_llm_visual_review(review_path: Path, cv_facts: dict | None = None) -> None:
    """Reject an incomplete review before it can be mistaken for CV+LLM facts."""
    review = load_review(review_path)
    if review.get("completeCurrentPixelReview") is not True:
        raise ValueError("cv_llm visual review must declare completeCurrentPixelReview=true")
    cards = review.get("cards")
    if not isinstance(cards, list) or not cards:
        raise ValueError("cv_llm visual review must enumerate visible result cards")
    registry = set(display_names())
    seen: set[str] = set()
    rejected_modules = review.get("rejectedModules", [])
    if not isinstance(rejected_modules, list):
        raise ValueError("cv_llm rejectedModules must be a list")
    review_modules = review.get("modules")
    reviewed_result_starts: list[float] = []
    if review_modules is not None:
        if not isinstance(review_modules, list):
            raise ValueError("cv_llm modules must be a list")
        for module in review_modules:
            coord = module.get("coord") if isinstance(module, dict) else None
            if (not isinstance(module, dict) or not isinstance(module.get("moduleType"), str)
                    or not isinstance(coord, list) or len(coord) != 4
                    or any(not isinstance(value, (int, float)) for value in coord)
                    or coord[2] <= 0 or coord[3] <= 0):
                raise ValueError("cv_llm module requires moduleType and positive coord")
            if module["moduleType"] == "result_list" and module.get("visibleStatus") == "confirmed":
                reviewed_result_starts.append(coord[1])
    for rejected in rejected_modules:
        if not isinstance(rejected, dict) or not isinstance(rejected.get("moduleType"), str) or not isinstance(rejected.get("coord"), list) or len(rejected["coord"]) != 4 or not str(rejected.get("reason", "")).strip():
            raise ValueError("cv_llm rejectedModule requires moduleType, coord and reason")
    for card in cards:
        if not isinstance(card, dict):
            raise ValueError("cv_llm visual review card must be an object")
        card_id, card_type = str(card.get("cardId", "")), str(card.get("cardTypeCandidate", ""))
        if not card_id or card_id in seen:
            raise ValueError("cv_llm visual review cardId must be non-empty and unique")
        seen.add(card_id)
        if card_type not in registry:
            raise ValueError(f"{card_id}:cardTypeCandidate is not registered")
        coord = card.get("coord")
        if (reviewed_result_starts and isinstance(coord, list) and len(coord) == 4
                and all(isinstance(value, (int, float)) for value in coord)
                and coord[1] + coord[3] / 2 < min(reviewed_result_starts)):
            raise ValueError(f"{card_id}:reviewed_result_card_before_confirmed_result_list")
        topology = _normalise_topology(card)
        if not topology["regions"]:
            raise ValueError(f"{card_id}:visual review must declare card topology regions")
        slots = {item["slot"] for item in topology["regions"]}
        naturally_cropped = _review_card_is_naturally_cropped(review, card, topology)
        errors = topology_errors(card_type, topology)
        if errors and not naturally_cropped:
            raise ValueError(f"{card_id}:{errors[0]}")
        # A visual reviewer may describe text and ownership, but it may not
        # invent a product-image rail. Graphic downhang requires a current CV
        # photo candidate inside a declared attached item.
        if card_type == "商家卡片_图文下挂" and not naturally_cropped:
            _, items = topology_parts(topology)
            photos = (cv_facts or {}).get("candidates", {}).get("photos", [])
            has_cv_anchor = any(
                isinstance(photo, dict)
                and photo.get("route") == "accepted"
                and isinstance(photo.get("coord"), list)
                and any(_overlap(photo["coord"], item["coord"]) for item in items)
                for photo in photos
            )
            if not has_cv_anchor:
                raise ValueError(f"{card_id}:merchant_graphic_hang_requires_cv_attached_photo_anchor")
        expected = reviewed_card_type(card_type, topology)
        if expected and expected != card_type and not naturally_cropped:
            raise ValueError(f"{card_id}:merchant_variant_does_not_match_topology:{expected}")


def merge_reviewed_card_boundaries(candidates_path: Path, review_path: Path, facts_path: Path) -> None:
    """Preserve current-pixel card boundaries that CV did not seed.

    This is used only by the explicit ``cv_llm`` experiment.  The review is
    already required, screenshot-bound evidence; it can therefore retain a
    bottom naturally cropped card whose thumbnail is too small for the CV
    candidate detector.  Card type and regions still go through the ordinary
    taxonomy, semantic mapper and gates.
    """
    payload = json.loads(candidates_path.read_text(encoding="utf-8"))
    facts = json.loads(facts_path.read_text(encoding="utf-8"))
    accepted_photos = [item for item in facts.get("candidates", {}).get("photos", []) if item.get("route") == "accepted"]
    existing = {str(item.get("id", "")): item for item in payload.get("resultCards", [])}
    reviewed_cards: list[dict] = []
    for reviewed in load_review(review_path).get("cards", []):
        card_id = str(reviewed.get("cardId", ""))
        coord = reviewed.get("coord")
        if not card_id or not isinstance(coord, list) or len(coord) != 4 or any(not isinstance(value, int) for value in coord):
            continue
        candidate = existing.get(card_id)
        if candidate is None:
            candidate = {
                "id": card_id, "coord": coord, "seedBlockId": "", "memberBlockIds": [],
                "confidence": 0.92, "status": "confirmed",
                "evidence": ["main_session_local_visual_read_card_boundary"],
            }
            payload.setdefault("resultCards", []).append(candidate)
            existing[card_id] = candidate
        else:
            candidate["coord"] = coord
            candidate["confidence"] = max(float(candidate.get("confidence", 0)), 0.92)
            candidate.setdefault("evidence", []).append("main_session_local_visual_read_card_boundary")
        topology = _normalise_topology(reviewed)
        candidate["reviewedTopology"] = topology
        candidate.setdefault("evidence", []).append("main_session_local_visual_read_card_topology")
        type_candidate = str(reviewed.get("cardTypeCandidate", ""))
        if type_candidate in known_result_types():
            candidate["classificationHint"] = {"cardType": type_candidate, "confidence": 0.96}
        candidate["reviewedMerchantVariant"] = merchant_variant(topology)
        candidate["reviewedCardType"] = type_candidate
        topology_slots = {str(item.get("slot", "")) for item in topology.get("regions", [])}
        if "attached_goods" not in topology_slots:
            # Current-pixel review is authoritative for this card.  Candidate
            # geometry remains in the retained process artifact, but stale
            # graphic ownership cannot stay active after the review confirms
            # text/no visible down-hang topology.
            candidate.pop("attachedProductPhotoIds", None)
            candidate["evidence"] = [
                item for item in candidate.get("evidence", [])
                if item not in GRAPHIC_DOWNHANG_EVIDENCE
            ]
        reviewed_photos = [item for item in accepted_photos if item.get("visualReview", {}).get("cardId") == card_id]
        head_ids = [item["id"] for item in reviewed_photos if item.get("visualReview", {}).get("topologySlot") in {"merchant_head", "head_media"}]
        attached_ids = [item["id"] for item in reviewed_photos if item.get("visualReview", {}).get("topologySlot") == "attached_goods"]
        if head_ids:
            candidate["headPhotoId"] = head_ids[0]
        if "attached_goods" in topology_slots:
            candidate["attachedProductPhotoIds"] = attached_ids
        candidate["evidence"] = list(dict.fromkeys(candidate.get("evidence", [])))
        reviewed_cards.append({"cardId": card_id, "coord": coord, "topology": topology})

    # Current-pixel review is stronger evidence than a low-confidence CV
    # block. Reconcile only empty boundary tails and candidates that the review
    # fully subsumes; retain every reconciliation decision in a sidecar audit.
    reviewed_cards.sort(key=lambda item: (item["coord"][1], item["cardId"]))
    reviewed_ids = {item["cardId"] for item in reviewed_cards}
    reconciliation: list[dict] = []
    for index, reviewed_card in enumerate(reviewed_cards[:-1]):
        candidate = existing.get(reviewed_card["cardId"])
        if candidate is None:
            continue
        next_card = reviewed_cards[index + 1]
        current = candidate["coord"]
        next_top = next_card["coord"][1]
        current_bottom = current[1] + current[3]
        topology_bounds = [
            item.get("coord") for item in (
                reviewed_card["topology"].get("regions", [])
                + reviewed_card["topology"].get("attachedItems", [])
            )
            if isinstance(item.get("coord"), list) and len(item["coord"]) == 4
        ]
        topology_bottom = max((box[1] + box[3] for box in topology_bounds), default=current_bottom)
        if current[1] < next_top < current_bottom and topology_bottom <= next_top:
            previous = list(current)
            candidate["coord"] = [current[0], current[1], current[2], next_top - current[1]]
            candidate.setdefault("evidence", []).append("reviewed_topology_clipped_to_next_card")
            reconciliation.append({
                "action": "clip_reviewed_card_tail",
                "cardId": reviewed_card["cardId"],
                "previousCoord": previous,
                "nextReviewedCardId": next_card["cardId"],
                "topologyBottom": topology_bottom,
                "finalCoord": candidate["coord"],
            })

    def intersection_area(left: list[int], right: list[int]) -> int:
        width = max(0, min(left[0] + left[2], right[0] + right[2]) - max(left[0], right[0]))
        height = max(0, min(left[1] + left[3], right[1] + right[3]) - max(left[1], right[1]))
        return width * height

    published_cards: list[dict] = []
    for candidate in payload.get("resultCards", []):
        candidate_id = str(candidate.get("id", ""))
        candidate_coord = candidate.get("coord")
        if candidate_id in reviewed_ids or not isinstance(candidate_coord, list) or len(candidate_coord) != 4:
            published_cards.append(candidate)
            continue
        candidate_area = candidate_coord[2] * candidate_coord[3]
        owner = next((
            reviewed for reviewed in reviewed_cards
            if candidate_area > 0
            and intersection_area(candidate_coord, existing[reviewed["cardId"]]["coord"]) / candidate_area >= 0.80
        ), None)
        if owner is None:
            published_cards.append(candidate)
            continue
        reconciliation.append({
            "action": "suppress_unreviewed_contained_candidate",
            "cardId": candidate_id,
            "coord": candidate_coord,
            "ownerCardId": owner["cardId"],
            "ownerCoord": existing[owner["cardId"]]["coord"],
            "overlapRatioOfSuppressedCandidate": round(
                intersection_area(candidate_coord, existing[owner["cardId"]]["coord"]) / candidate_area, 4
            ),
        })
    payload["resultCards"] = published_cards

    if reconciliation:
        audit_path = candidates_path.with_name(f"{candidates_path.stem}.review-reconciliation.json")
        suffix = 2
        while audit_path.exists():
            audit_path = candidates_path.with_name(f"{candidates_path.stem}.review-reconciliation-{suffix}.json")
            suffix += 1
        audit_path.write_text(json.dumps({
            "contractVersion": "phase2.reviewed-card-reconciliation.v1",
            "sourceCandidates": str(candidates_path),
            "review": str(review_path),
            "actions": reconciliation,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    payload["resultCards"].sort(key=lambda item: (int(item["coord"][1]), str(item.get("id", ""))))
    candidates_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def add_publication_error(gate_path: Path, error: str) -> None:
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    gate["valid"] = False
    gate.setdefault("errors", []).append(error)
    gate_path.write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mark_manifest_blocked(output: Path, error: str) -> None:
    payload = json.loads(output.read_text(encoding="utf-8"))
    recognition = payload.setdefault("recognition", {})
    recognition.update({"status": "blocked", "phase3Ready": False, "wholePageGate": False})
    recognition.setdefault("errors", []).append(error)
    payload.setdefault("pageFactInventory", {})["complete"] = False
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(query: str, screenshot: Path, output: Path, audit: Path | None, artifacts: Path,
        visual_review: Path | None = None,
        recognition_mode: str = "cv_llm", candidate_bundle: Path | None = None) -> int:
    if recognition_mode != "cv_llm":
        raise ValueError("Phase2 production recognition is cv_llm only; legacy local OCR modes are not available")
    artifacts.mkdir(parents=True, exist_ok=True)
    facts_initial = artifacts / "cv-facts.initial.json"
    structure_initial = artifacts / "page-structure.initial.json"
    candidates_initial = artifacts / "result-candidates.initial.json"
    card_semantics_initial = artifacts / "card-semantics.initial.json"
    text_semantics_initial = artifacts / "text-semantics.initial.json"
    gate_initial = artifacts / "recognition-gate.initial.json"
    facts = artifacts / "cv-facts.json"
    structure = artifacts / "page-structure.json"
    candidates = artifacts / "result-candidates.json"
    card_semantics = artifacts / "card-semantics.json"
    text_semantics = artifacts / "text-semantics.json"
    gate_report = artifacts / "recognition-gate.json"
    structure_gate = artifacts / "structure-gate.json"

    cv_env = os.environ.copy()
    cv_env["SEARCH_EVAL_PYTHON"] = sys.executable
    # The LLM's recorded current-pixel read is the sole text observation
    # source.  Do not silently retain any local OCR fallback.
    cv_env["PHASE2_DISABLE_LOCAL_OCR"] = "1"
    if candidate_bundle is None:
        invoke(["bash", str(SCRIPT_DIR / "run_cv_facts.sh"), str(screenshot), "--output", str(facts_initial)], env=cv_env)
        facts_source = facts_initial
    else:
        facts_source = validate_candidate_bundle(candidate_bundle, screenshot)
    if visual_review is None:
        raise ValueError("cv_llm mode requires --visual-review with completeCurrentPixelReview=true")
    validate_cv_llm_visual_review(visual_review, json.loads(facts_source.read_text(encoding="utf-8")))
    facts_reviewed = artifacts / "cv-facts.visual-reviewed.before-structure.json"
    invoke([sys.executable, str(SCRIPT_DIR / "apply_visual_review.py"), "--facts", str(facts_source), "--review", str(visual_review), "--output", str(facts_reviewed)])
    facts_source = facts_reviewed
    invoke([sys.executable, str(SCRIPT_DIR / "build_search_page_structure.py"), str(facts_source), "--output", str(structure_initial)])
    invoke([sys.executable, str(SCRIPT_DIR / "build_search_result_candidates.py"), str(facts_source), str(structure_initial), "--output", str(candidates_initial)])
    merge_reviewed_card_boundaries(candidates_initial, visual_review, facts_source)
    invoke([sys.executable, str(SCRIPT_DIR / "map_result_card_semantics.py"), str(facts_source), str(candidates_initial), "--output", str(card_semantics_initial)])
    invoke([sys.executable, str(SCRIPT_DIR / "map_search_page_semantics.py"), str(facts_source), str(structure_initial), "--output", str(text_semantics_initial)])
    structure_ok = write_structure_gate(candidates_initial, card_semantics_initial, structure_gate)
    initial_gate_code = invoke([sys.executable, str(SCRIPT_DIR / "validate_phase2_recognition.py"), "--facts", str(facts_source), "--result-candidates", str(candidates_initial), "--card-semantics", str(card_semantics_initial), "--text-semantics", str(text_semantics_initial), "--output", str(gate_initial)], check=False)

    for source, destination in (
        (facts_source, facts), (structure_initial, structure), (candidates_initial, candidates),
        (card_semantics_initial, card_semantics), (text_semantics_initial, text_semantics), (gate_initial, gate_report),
    ):
        shutil.copyfile(source, destination)
    gate_code = initial_gate_code
    if not structure_ok:
        add_publication_error(gate_report, "structure_gate_failed_after_cv_llm_topology_review")
        gate_code = 1
    build_args = [sys.executable, str(SCRIPT_DIR / "build_phase2_manifest.py"), "--query", query, "--facts", str(facts), "--result-candidates", str(candidates), "--card-semantics", str(card_semantics), "--text-semantics", str(text_semantics), "--recognition-gate", str(gate_report), "--output", str(output)]
    invoke(build_args)
    if audit:
        # The audit is derived only after the final manifest exists.  The old
        # path wrote a preliminary recognition audit, then immediately used
        # it as a required calibration audit, making every normal run fail.
        audit_args = [sys.executable, str(SCRIPT_DIR / "build_current_image_calibration_audit.py"), "--manifest", str(output), "--output", str(audit)]
        if visual_review:
            audit_args.extend(["--visual-review", str(visual_review)])
        invoke(audit_args)
    ownership_audit = artifacts / "semantic-ownership-audit.json"
    ownership_code = invoke([
        sys.executable, str(SCRIPT_DIR / "semantic_ownership.py"),
        "--manifest", str(output), "--visual-review", str(visual_review),
        "--result-candidates", str(candidates), "--output", str(ownership_audit),
    ], check=False)
    if ownership_code != 0:
        mark_manifest_blocked(output, "semantic_ownership_validation_failed")
    validation_args = [sys.executable, str(ROOT / "phase2-card-annotation" / "scripts" / "validate_element_manifest.py"), str(output), "--audit", str(output.with_suffix(".audit.json"))]
    if audit:
        # A syntactically valid manifest is not enough for publication.  The
        # supplied audit is the only place that can prove every non-excluded
        # atom was checked against this screenshot's pixels.
        validation_args.extend(["--recognition-audit", str(audit), "--require-current-image-calibration"])
    validation_code = invoke(validation_args, check=False)
    if validation_code != 0:
        mark_manifest_blocked(output, "element_manifest_or_item_groups_validation_failed")
    elif gate_code != 0:
        mark_manifest_blocked(output, "phase2_gate_failed")
    return 0 if gate_code == 0 and ownership_code == 0 and validation_code == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Recognize a screenshot directly into the Phase3 manifest contract")
    parser.add_argument("--query", required=True)
    parser.add_argument("--screenshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--recognition-audit", type=Path, help="Optional separate debug audit; the canonical gate is embedded in --output")
    parser.add_argument("--artifacts-dir", type=Path, help="Optional retained CV/OCR process artifacts directory")
    parser.add_argument("--visual-review", type=Path, help="Current-screenshot main-session local visual-review JSON")
    parser.add_argument("--candidate-bundle", type=Path, help="Retained local-CV candidate bundle bound to --screenshot")
    parser.add_argument("--stage", choices=("candidate", "publish"), default="publish",
                        help="Run candidate before visual review, then publish the reviewed result.")
    parser.add_argument("--recognition-mode", choices=("cv_llm",), default="cv_llm",
                        help="Production CV+LLM mode: local CV geometry plus mandatory current-pixel visual review; no local OCR backend")
    args = parser.parse_args()
    if args.stage == "candidate":
        if args.visual_review or args.candidate_bundle or args.recognition_audit:
            parser.error("candidate stage accepts only screenshot, output, and artifacts-dir")
        if args.artifacts_dir:
            return run_candidate(args.screenshot, args.artifacts_dir, args.output)
        with tempfile.TemporaryDirectory(prefix="phase2-candidate-") as temp:
            return run_candidate(args.screenshot, Path(temp), args.output)
    if args.artifacts_dir:
        return run(args.query, args.screenshot, args.output, args.recognition_audit, args.artifacts_dir,
                   args.visual_review, args.recognition_mode, args.candidate_bundle)
    else:
        with tempfile.TemporaryDirectory(prefix="phase2-recognition-") as temp:
            return run(args.query, args.screenshot, args.output, args.recognition_audit, Path(temp),
                       args.visual_review, args.recognition_mode, args.candidate_bundle)


if __name__ == "__main__":
    raise SystemExit(main())
