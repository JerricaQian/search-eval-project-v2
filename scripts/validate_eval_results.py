#!/usr/bin/env python3
"""Validate deterministic overview accounting in phase3 evaluation results."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from skill_frontmatter import load_weight


COMPONENT_ROW_REQUIREMENTS: dict[str, set[str]] = {
    "eval-1-supply-completeness": {"componentId", "visibleBounds", "applicableFields", "checkResults", "rating"},
    "eval-2-visual-order-alignment": {"comparisonGroupKey", "members", "layoutSignatures", "readingOrderChecks", "evidenceSource", "rating"},
    "eval-3-color-logic": {
        "componentId", "scannedElementIds", "excludedElementIds", "sourceColorValues",
        "colorFamilies", "colorFamilyCount", "evidenceSource", "rating",
    },
    "eval-4-element-complexity": {
        "componentId", "expectedRegions", "scannedRegions", "unscannedRegions", "scannedElementIds",
        "candidateLedger", "phase2ReviewCandidates", "coverageStatus", "includedTagStyles",
        "includedIconStyles", "excludedEntities", "tagStyleCount", "iconStyleCount", "evidenceSource", "rating",
    },
    "eval-5-info-hierarchy": {
        "componentId", "sourceElements", "weightSequence", "tierTrace", "levelCount", "rating",
    },
    "eval-6-info-partitioning": {"componentId", "partitions", "adjacentBoundaryChecks", "excludedPairs", "evidenceSource", "issueCount", "rating"},
    "eval-7-info-authenticity": {
        "componentId", "candidatePairs", "pairJudgements", "inapplicableChecks",
        "scanCoverage", "conflicts", "conflictCount", "evidenceSource", "rating",
    },
    "eval-8-info-redundancy": {
        "componentId", "scannedRegions", "examinedElements", "candidatePairs",
        "selfRepeatCandidates", "duplicates", "duplicateCount", "scanCoverage",
        "evidenceSource", "rating",
    },
}

COMPONENT_FULL_COVERAGE_SKILLS = {
    "eval-2-visual-order-alignment",
    "eval-3-color-logic",
    "eval-4-element-complexity",
    "eval-5-info-hierarchy",
    "eval-7-info-authenticity",
    "eval-8-info-redundancy",
}

COMPONENT_PROBLEM_ONLY_SKILLS = {
    "eval-1-supply-completeness",
    "eval-6-info-partitioning",
}

SINGLE_ELEMENT_COLOR_ROW_REQUIREMENTS = {
    "elementId", "componentId", "phase2Boundary", "sampleMask", "rawColorGrid",
    "colorCount", "rating",
}

COMPONENT_REDUNDANCY_CROSS_CHECKS = {
    "title/subtitle ↔ basic information",
    "title/subtitle ↔ tags/price/promotion",
    "tag ↔ price/promotion",
    "title internal repeated quantified fragments",
}

FORBIDDEN_COPY_TERMS_PATH = Path(__file__).with_name("forbidden_copy_terms.json")
FORBIDDEN_ID_PATTERN_EXEMPTIONS = {"P0", "P1", "P2"}
PROJECT_DIR = Path(__file__).resolve().parents[1]
PHASE3_DIR = PROJECT_DIR / "phase3-evaluation"
_PHASE2_TAXONOMY = json.loads(
    (PROJECT_DIR / "phase2-card-annotation" / "references" / "search_card_taxonomy.v1.json").read_text(encoding="utf-8")
)
FULFILLMENT_COMPLEXITY_EXCLUSIONS = {
    re.sub(r"[\s·•|]+", "", str(value))
    for value in _PHASE2_TAXONOMY.get("commonElementVocabulary", {}).get("fulfillment", [])
}
PROMOTION_PREFIX_PATTERN = re.compile(
    r"^(?:原文:)?(?:【\s*)?(?:神抢手|神枪手|特价团|神券|限时秒杀|秒杀价|到手价|券后价|直播特惠|会员价|新客价)(?:\s*】)?"
)


def complexity_rating(tag_count: int, icon_count: int) -> str:
    """Return the fixed eval-4 rating from independently counted instances."""
    if tag_count >= 7 or icon_count >= 4:
        return "不达标"
    if tag_count <= 4 and icon_count <= 1:
        return "优秀"
    return "达标"


def _load_skill_directories() -> dict[str, Path]:
    payload = json.loads((PHASE3_DIR / "catalog.json").read_text(encoding="utf-8"))
    return {
        item["id"]: PHASE3_DIR / item["skillsDir"]
        for item in payload["dimensions"]
    }


SKILL_DIRECTORIES = _load_skill_directories()


def _load_forbidden_copy_terms() -> dict[str, Any]:
    return json.loads(FORBIDDEN_COPY_TERMS_PATH.read_text(encoding="utf-8"))


def load_skill_weight(dimension: str, skill: str) -> dict[str, float] | None:
    """Read the legacy frontmatter map whose keys define the legal ratings."""
    directory = SKILL_DIRECTORIES.get(dimension)
    path = directory / skill / "SKILL.md" if directory else None
    if path is None or not path.is_file():
        return None
    return load_weight(path)


def require_supported_rating(errors: list[str], prefix: str, dimension: str, skill: str, unit: dict[str, Any]) -> None:
    """Use the legacy weight keys only as the authoritative two/three-tier rating enum."""
    weights = load_skill_weight(dimension, skill)
    if weights is None:
        errors.append(f"{prefix}:skill_weight_unavailable")
        return
    rating = unit.get("rating")
    if rating not in weights:
        errors.append(f"{prefix}:rating_not_defined_in_skill_weight:{rating}")


def require_no_forbidden_terms(errors: list[str], prefix: str, text: str) -> None:
    """Block internal IDs/field names/script filenames/English enums leaking into reader-facing copy."""
    if not isinstance(text, str) or not text:
        return
    terms = _load_forbidden_copy_terms()
    for pattern in terms.get("internal_id_patterns", []):
        for match in re.finditer(pattern, text):
            if match.group(0) in FORBIDDEN_ID_PATTERN_EXEMPTIONS:
                continue
            errors.append(f"{prefix}:copy_contains_internal_id:{match.group(0)}")
    for field_name in terms.get("internal_field_names", []):
        if re.search(rf"\b{re.escape(field_name)}\b", text):
            errors.append(f"{prefix}:copy_contains_internal_field_name:{field_name}")
    script_pattern = terms.get("script_filename_pattern")
    if script_pattern and re.search(script_pattern, text):
        errors.append(f"{prefix}:copy_contains_script_filename")
    enum_pattern = terms.get("english_enum_pattern")
    if enum_pattern and re.search(enum_pattern, text, re.IGNORECASE):
        errors.append(f"{prefix}:copy_contains_english_enum_value")


def require_actionable_recommendation(errors: list[str], prefix: str, issue: dict[str, Any]) -> None:
    """Require an issue-scoped action and a verifiable acceptance result."""
    recommendation = str(issue.get("recommendation") or "")
    require_non_empty_string(errors, prefix, issue, "recommendation")
    if not recommendation.strip():
        return
    if not re.search(r"调整|改写|补齐|合并|删除|统一|收敛|恢复|归回|减少|保留|替换|修复", recommendation):
        errors.append(f"{prefix}:recommendation_requires_concrete_action")
    if not re.search(r"验收|复测|确认|确保|满足|不超过|不少于|无冲突|无重复|可直接", recommendation):
        errors.append(f"{prefix}:recommendation_requires_acceptance_result")


READABLE_COMPONENT_LOCATION_RE = re.compile(
    r"(?:商卡\s*[0-9一二三四五六七八九十]+|图筛|快筛|筛选(?:条|组件)?|品牌直达|"
    r"直播(?:模块|横滑商品流)?|广告卡|运营(?:聚合)?卡)"
)


def require_readable_component_location(errors: list[str], prefix: str, issue: dict[str, Any]) -> None:
    """Require issue copy to identify a user-visible card or component."""
    description = str(issue.get("description") or "")
    if not READABLE_COMPONENT_LOCATION_RE.search(description):
        errors.append(f"{prefix}:description_requires_readable_card_or_component_location")


PAGE_EVIDENCE_REQUIREMENTS: dict[str, set[str]] = {
    "eval-1-supply-module-completeness": {"modules", "expectedModules", "layoutChecks", "rating"},
    "eval-2-visual-order-alignment": {"pageRegions", "sameTypeComparisons", "rating"},
    "eval-3-page-color-logic": {
        "colorLogicContractVersion", "componentColorArtifact", "componentColorSummaries",
        "colorFamilies", "colorFamilyCount", "evidenceSource", "rating",
    },
    "eval-4-static-component-complexity": {"firstScreenBounds", "functionalModules", "moduleCount", "rating"},
    "eval-5-browsing-flow-smoothness": {"listPositions", "visibleListPositionCount", "coverageStatus", "heterogeneousCount", "rating"},
    "eval-6-info-comparability": {
        "cardGroups", "comparableFields", "comparisons", "inconsistencyCount", "evidenceSource", "rating",
    },
    "eval-7-info-redundancy": {"pageRegions", "candidatePairs", "redundancyCount", "rating"},
}


def require_row_fields(errors: list[str], prefix: str, row: Any, required: set[str]) -> bool:
    if not isinstance(row, dict):
        errors.append(f"{prefix}:assessmentRow_must_be_object")
        return False
    missing = required - row.keys()
    if missing:
        errors.append(f"{prefix}:assessmentRow_missing_fields:{','.join(sorted(missing))}")
        return False
    return True


def require_non_empty_string(errors: list[str], prefix: str, payload: dict[str, Any], field: str) -> None:
    if not isinstance(payload.get(field), str) or not payload[field].strip():
        errors.append(f"{prefix}:{field}_must_be_non_empty_string")


def require_measurement(errors: list[str], prefix: str, row: dict[str, Any]) -> None:
    """Require a reproducible measurement record when a Skill relies on deterministic metrics."""
    measurement = row.get("measurement")
    if not isinstance(measurement, dict):
        errors.append(f"{prefix}:measurement_must_be_object")
        return
    tool = measurement.get("tool")
    artifact_path = measurement.get("artifactPath")
    parameters = measurement.get("parameters")
    if not isinstance(tool, str) or not tool.strip() or not Path(tool).is_file():
        errors.append(f"{prefix}:measurement_tool_missing")
    if not isinstance(artifact_path, str) or not artifact_path or not Path(artifact_path).is_file():
        errors.append(f"{prefix}:measurement_artifact_missing")
    if not isinstance(parameters, dict) or not parameters:
        errors.append(f"{prefix}:measurement_parameters_must_be_non_empty_object")


def require_evidence_source(
    errors: list[str],
    prefix: str,
    row: dict[str, Any],
    expected_source: str,
) -> None:
    """Require the declared provenance and reject obsolete row-level measurements."""
    if row.get("evidenceSource") != expected_source:
        errors.append(f"{prefix}:evidenceSource_must_be_{expected_source}")
    if "measurement" in row:
        errors.append(f"{prefix}:row_level_measurement_forbidden")


def require_component_color_pixel_evidence(
    errors: list[str],
    prefix: str,
    row: dict[str, Any],
    active_by_id: dict[str, dict[str, Any]],
) -> None:
    """Validate a component-colour row produced from bound screenshot pixels."""
    require_evidence_source(errors, prefix, row, "original_screenshot_pixels")
    scanned = row.get("scannedElementIds")
    excluded = row.get("excludedElementIds")
    source_values = row.get("sourceColorValues")
    families = row.get("colorFamilies")
    count = row.get("colorFamilyCount")
    if not isinstance(scanned, list) or any(item not in active_by_id for item in scanned):
        errors.append(f"{prefix}:scannedElementIds_invalid")
    if not isinstance(excluded, list) or any(item not in active_by_id for item in excluded):
        errors.append(f"{prefix}:excludedElementIds_invalid")
    if not isinstance(source_values, list) or any(
        not isinstance(item, dict)
        or not {"elementId", "field", "value", "colorFamily"}.issubset(item)
        or item.get("elementId") not in active_by_id
        for item in source_values
    ):
        errors.append(f"{prefix}:sourceColorValues_invalid")
    if not isinstance(families, list) or any(not isinstance(item, str) or not item for item in families):
        errors.append(f"{prefix}:colorFamilies_invalid")
    elif len(families) != len(set(families)):
        errors.append(f"{prefix}:colorFamilies_must_be_unique")
    if not isinstance(count, int) or count < 0:
        errors.append(f"{prefix}:colorFamilyCount_invalid")
        return
    if isinstance(families, list) and count != len(families):
        errors.append(f"{prefix}:colorFamilyCount_must_match_colorFamilies")
    expected_rating = "优秀" if count <= 4 else "达标" if count == 5 else "不达标"
    if row.get("rating") != expected_rating:
        errors.append(f"{prefix}:rating_must_be_{expected_rating}")


def require_page_color_component_aggregation(errors: list[str], prefix: str, row: dict[str, Any]) -> None:
    """Validate the V4 page-colour union of component pixel-colour families."""
    if row.get("colorLogicContractVersion") != "4.0":
        errors.append(f"{prefix}:colorLogicContractVersion_must_be_4.0")
    require_evidence_source(errors, prefix, row, "component_pixel_color_aggregation")
    artifact = row.get("componentColorArtifact")
    if not isinstance(artifact, str) or not artifact or not Path(artifact).is_file():
        errors.append(f"{prefix}:componentColorArtifact_missing")
    summaries = row.get("componentColorSummaries")
    if not isinstance(summaries, list):
        errors.append(f"{prefix}:componentColorSummaries_must_be_array")
        return
    expected_families: set[str] = set()
    component_ids: set[str] = set()
    allowed_families = {"红", "橙", "黄", "绿", "青", "蓝", "紫"}
    for index, summary in enumerate(summaries, start=1):
        item_prefix = f"{prefix}:componentColorSummaries_{index}"
        if not isinstance(summary, dict):
            errors.append(f"{item_prefix}_must_be_object")
            continue
        component_id = summary.get("componentId")
        families = summary.get("colorFamilies")
        count = summary.get("colorFamilyCount")
        if not isinstance(component_id, str) or not component_id or component_id in component_ids:
            errors.append(f"{item_prefix}_componentId_invalid")
        else:
            component_ids.add(component_id)
        if not isinstance(families, list) or any(family not in allowed_families for family in families):
            errors.append(f"{item_prefix}_colorFamilies_invalid")
            continue
        if len(families) != len(set(families)):
            errors.append(f"{item_prefix}_colorFamilies_must_be_unique")
        if not isinstance(count, int) or count != len(families):
            errors.append(f"{item_prefix}_colorFamilyCount_must_match_colorFamilies")
        expected_families.update(families)
    families = row.get("colorFamilies")
    count = row.get("colorFamilyCount")
    if not isinstance(families, list) or any(family not in allowed_families for family in families):
        errors.append(f"{prefix}:colorFamilies_invalid")
        return
    if len(families) != len(set(families)):
        errors.append(f"{prefix}:colorFamilies_must_be_unique")
    if set(families) != expected_families:
        errors.append(f"{prefix}:colorFamilies_must_equal_component_union")
    if not isinstance(count, int) or count != len(families):
        errors.append(f"{prefix}:colorFamilyCount_must_match_colorFamilies")
        return
    expected_rating = "优秀" if count <= 5 else "达标" if count == 6 else "不达标"
    if row.get("rating") != expected_rating:
        errors.append(f"{prefix}:rating_must_be_{expected_rating}")


def require_single_element_color_pixel_evidence(
    errors: list[str],
    prefix: str,
    row: dict[str, Any],
    active_by_id: dict[str, dict[str, Any]],
) -> None:
    """Validate one JSON-prefiltered element's reproducible pixel result."""
    element_id = row.get("elementId")
    if element_id not in active_by_id:
        errors.append(f"{prefix}:elementId_not_in_manifest")
    if not isinstance(row.get("componentId"), str) or not row["componentId"].strip():
        errors.append(f"{prefix}:componentId_invalid")
    boundary = row.get("phase2Boundary")
    if not isinstance(boundary, list) or len(boundary) != 4 or any(
        not isinstance(value, int) for value in boundary
    ):
        errors.append(f"{prefix}:phase2Boundary_invalid")
    elif element_id in active_by_id:
        manifest_boundary = active_by_id[element_id].get("coord") or active_by_id[element_id].get("坐标")
        if isinstance(manifest_boundary, list) and boundary != manifest_boundary:
            errors.append(f"{prefix}:phase2Boundary_must_match_manifest")
    sample_mask = row.get("sampleMask")
    if not isinstance(sample_mask, str) or not sample_mask or not Path(sample_mask).is_file():
        errors.append(f"{prefix}:sampleMask_missing")
    raw_grid = row.get("rawColorGrid")
    if not isinstance(raw_grid, (list, dict)):
        errors.append(f"{prefix}:rawColorGrid_invalid")
    count = row.get("colorCount")
    if not isinstance(count, int) or count < 0:
        errors.append(f"{prefix}:colorCount_invalid")
        return
    expected_rating = "优秀" if count <= 2 else "达标" if count == 3 else "不达标"
    if row.get("rating") != expected_rating:
        errors.append(f"{prefix}:rating_must_be_{expected_rating}")


def require_hierarchy_visual_evidence(errors: list[str], prefix: str, row: dict[str, Any]) -> None:
    """Validate coverage of a qualitative original-screenshot hierarchy review."""
    source_elements = row.get("sourceElements")
    weight_sequence = row.get("weightSequence")
    tier_trace = row.get("tierTrace")
    level_count = row.get("levelCount")
    if not isinstance(source_elements, list) or not source_elements or any(
        not isinstance(item, dict) for item in source_elements
    ):
        errors.append(f"{prefix}:sourceElements_must_be_non_empty_object_array")
    if not isinstance(weight_sequence, list) or not weight_sequence:
        errors.append(f"{prefix}:weightSequence_must_be_non_empty_array")
    if not isinstance(tier_trace, list) or not tier_trace:
        errors.append(f"{prefix}:tierTrace_must_be_non_empty_array")
    if not isinstance(level_count, int) or level_count < 1:
        errors.append(f"{prefix}:levelCount_invalid")
    elif isinstance(tier_trace, list) and level_count != len(tier_trace):
        errors.append(f"{prefix}:levelCount_must_match_tierTrace")
    if "measurement" in row:
        errors.append(f"{prefix}:hierarchy_visual_review_must_not_require_measurement")


def require_complexity_coverage(
    errors: list[str],
    prefix: str,
    row: dict[str, Any],
    active_by_id: dict[str, dict[str, Any]] | None = None,
) -> None:
    """Require eval-4 to expose a complete, directly auditable JSON inventory."""
    expected_regions = row.get("expectedRegions")
    scanned_regions = row.get("scannedRegions")
    unscanned_regions = row.get("unscannedRegions")
    scanned_element_ids = row.get("scannedElementIds")
    ledger = row.get("candidateLedger")
    review_candidates = row.get("phase2ReviewCandidates")

    if not isinstance(expected_regions, list) or not expected_regions or not all(
        isinstance(region, str) and region for region in expected_regions
    ):
        errors.append(f"{prefix}:expectedRegions_invalid")
        return
    if not isinstance(scanned_regions, list) or set(scanned_regions) != set(expected_regions):
        errors.append(f"{prefix}:scannedRegions_must_cover_expectedRegions")
    if not isinstance(unscanned_regions, list) or unscanned_regions:
        errors.append(f"{prefix}:unscannedRegions_must_be_empty")
    if row.get("coverageStatus") != "completed":
        errors.append(f"{prefix}:coverageStatus_must_be_completed")
    if not isinstance(scanned_element_ids, list) or not all(
        isinstance(element_id, str) and element_id for element_id in scanned_element_ids
    ):
        errors.append(f"{prefix}:scannedElementIds_invalid")
        scanned_element_ids = []
    elif active_by_id is not None and any(element_id not in active_by_id for element_id in scanned_element_ids):
        errors.append(f"{prefix}:scannedElementIds_not_in_manifest")
    if not isinstance(ledger, list):
        errors.append(f"{prefix}:candidateLedger_must_be_array")
        ledger = []

    allowed_decisions = {"included_tag", "included_icon", "excluded", "phase2_review_required"}
    ledger_by_id: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(ledger, start=1):
        if not isinstance(entry, dict):
            errors.append(f"{prefix}:candidateLedger_{index}_must_be_object")
            continue
        element_id = entry.get("elementId")
        decision = entry.get("decision")
        if not isinstance(element_id, str) or not element_id or element_id in ledger_by_id:
            errors.append(f"{prefix}:candidateLedger_{index}_elementId_missing_or_duplicate")
            continue
        ledger_by_id[element_id] = entry
        if decision not in allowed_decisions:
            errors.append(f"{prefix}:candidateLedger_{index}_decision_invalid")
        if not isinstance(entry.get("reason"), str) or not entry["reason"].strip():
            errors.append(f"{prefix}:candidateLedger_{index}_reason_required")
        elif any(value in entry["reason"] for value in ("内容文字或图片", "不是独立异形异色标签")):
            errors.append(f"{prefix}:candidateLedger_{index}_generic_exclusion_reason_forbidden")
        if decision == "included_tag":
            style_key = entry.get("styleKey")
            if not isinstance(style_key, str) or len([part for part in style_key.split("|") if part.strip()]) != 5:
                errors.append(f"{prefix}:candidateLedger_{index}_included_tag_requires_five_part_styleKey")
        if active_by_id is not None and element_id in active_by_id:
            source = active_by_id[element_id]
            content = str(source.get("content") or "").removeprefix("原文:").strip()
            compact = re.sub(r"[\s·•|]+", "", content)
            semantic_role = str(source.get("semanticRole") or "")
            color_role = str(source.get("colorRole") or "unknown")
            promotion_prefix = str(source.get("promotionPrefix") or "").strip()
            is_fulfillment = (
                semantic_role in {"fulfillment", "fulfillment_tag", "delivery_time", "delivery_time_tag"}
                or compact in FULFILLMENT_COMPLEXITY_EXCLUSIONS
            )
            if is_fulfillment and decision != "excluded":
                errors.append(f"{prefix}:candidateLedger_{index}_fulfillment_must_be_excluded")
            elif source.get("isPhoto") and decision != "excluded":
                errors.append(f"{prefix}:candidateLedger_{index}_photo_material_must_be_excluded")
            elif semantic_role in {"title", "price", "rating"} and not promotion_prefix and decision in {"included_tag", "included_icon"}:
                errors.append(f"{prefix}:candidateLedger_{index}_core_field_must_not_be_counted")
            elif promotion_prefix and decision != "included_tag":
                errors.append(f"{prefix}:candidateLedger_{index}_promotion_prefix_must_be_included_tag")
            elif (
                semantic_role == "promotion"
                or PROMOTION_PREFIX_PATTERN.search(content)
            ) and color_role not in {"neutral", "unknown", ""} and decision != "included_tag":
                errors.append(f"{prefix}:candidateLedger_{index}_colored_promotion_must_be_included_tag")

    if set(ledger_by_id) != set(scanned_element_ids):
        errors.append(f"{prefix}:candidateLedger_must_cover_scannedElementIds")
    if not isinstance(review_candidates, list):
        errors.append(f"{prefix}:phase2ReviewCandidates_must_be_array")
        review_candidates = []
    if review_candidates or any(
        isinstance(entry, dict) and entry.get("decision") == "phase2_review_required" for entry in ledger
    ):
        errors.append(f"{prefix}:phase2_review_required_blocks_formal_rating")

    included_styles = row.get("includedTagStyles")
    if isinstance(included_styles, list):
        included_tag_ids: list[str] = []
        for index, style in enumerate(included_styles, start=1):
            if not isinstance(style, dict):
                continue
            style_key = style.get("styleKey")
            element_ids = style.get("elementIds")
            if not isinstance(element_ids, list) or not element_ids or not all(
                isinstance(element_id, str) and element_id for element_id in element_ids
            ):
                errors.append(f"{prefix}:includedTagStyles_{index}_elementIds_required")
                continue
            if len(element_ids) > 1 and not isinstance(style.get("groupingDecision"), str):
                errors.append(f"{prefix}:includedTagStyles_{index}_multi_atom_instance_requires_groupingDecision")
            for element_id in element_ids:
                included_tag_ids.append(element_id)
                ledger_entry = ledger_by_id.get(element_id)
                if not isinstance(ledger_entry, dict) or ledger_entry.get("decision") != "included_tag":
                    errors.append(f"{prefix}:includedTagStyles_{index}_elementId_must_reference_included_tag")
                elif style_key != ledger_entry.get("styleKey"):
                    errors.append(f"{prefix}:includedTagStyles_{index}_styleKey_must_match_candidateLedger")
                elif active_by_id is not None:
                    promotion_prefix = str(active_by_id.get(element_id, {}).get("promotionPrefix") or "").strip()
                    if promotion_prefix and str(style.get("content") or "").strip() != promotion_prefix:
                        errors.append(f"{prefix}:includedTagStyles_{index}_content_must_equal_promotionPrefix")
        if len(included_tag_ids) != len(set(included_tag_ids)):
            errors.append(f"{prefix}:includedTagStyles_elementIds_must_be_unique")
        ledger_tag_ids = {
            element_id
            for element_id, entry in ledger_by_id.items()
            if entry.get("decision") == "included_tag"
        }
        if set(included_tag_ids) != ledger_tag_ids:
            errors.append(f"{prefix}:includedTagStyles_must_cover_candidateLedger_included_tags")

def require_alignment_visual_evidence(
    errors: list[str],
    prefix: str,
    row: dict[str, Any],
) -> None:
    """Validate coverage and rating consistency of a visual-order review."""
    if row.get("evidenceSource") != "original_screenshot_visual_review":
        errors.append(f"{prefix}:evidenceSource_must_be_original_screenshot_visual_review")
    if "measurement" in row:
        errors.append(f"{prefix}:visual_review_must_not_be_measurement")
    members = row.get("members")
    signatures = row.get("layoutSignatures")
    checks = row.get("readingOrderChecks")
    if not isinstance(members, list) or not members or not all(isinstance(member, str) and member for member in members):
        errors.append(f"{prefix}:members_invalid")
        return
    if not isinstance(signatures, list) or len(signatures) != len(members):
        errors.append(f"{prefix}:layoutSignatures_must_match_members")
        return

    signature_members: set[str] = set()
    for index, signature in enumerate(signatures, start=1):
        if not isinstance(signature, dict):
            errors.append(f"{prefix}:layoutSignature_{index}_must_be_object")
            continue
        component_id = signature.get("componentId")
        if component_id not in members or component_id in signature_members:
            errors.append(f"{prefix}:layoutSignature_{index}_componentId_invalid")
            continue
        signature_members.add(component_id)
        if not isinstance(signature.get("layoutMode"), str) or not signature["layoutMode"].strip():
            errors.append(f"{prefix}:layoutSignature_{index}_layoutMode_required")
        if not isinstance(signature.get("layoutSignature"), str) or not signature["layoutSignature"].strip():
            errors.append(f"{prefix}:layoutSignature_{index}_layoutSignature_required")
        regions = signature.get("regions")
        if not isinstance(regions, list):
            errors.append(f"{prefix}:layoutSignature_{index}_regions_must_be_array")
        relations = signature.get("relations")
        if not isinstance(relations, list):
            errors.append(f"{prefix}:layoutSignature_{index}_relations_must_be_array")

    if signature_members != set(members):
        errors.append(f"{prefix}:layoutSignatures_must_cover_members")
    if not isinstance(checks, list) or len(checks) != len(members):
        errors.append(f"{prefix}:readingOrderChecks_must_match_members")
        return
    statuses: list[str] = []
    check_members: set[str] = set()
    for index, check in enumerate(checks, start=1):
        if not isinstance(check, dict):
            errors.append(f"{prefix}:readingOrderCheck_{index}_must_be_object")
            continue
        component_id = check.get("componentId")
        status = check.get("status")
        order = check.get("regionOrder")
        if component_id not in members or component_id in check_members:
            errors.append(f"{prefix}:readingOrderCheck_{index}_componentId_invalid")
        else:
            check_members.add(component_id)
        if status not in {"consistent", "local_adjustment", "inversion", "not_assessable"}:
            errors.append(f"{prefix}:readingOrderCheck_{index}_status_invalid")
        else:
            statuses.append(status)
        if not isinstance(order, list) or not order or not all(isinstance(region, str) and region for region in order):
            errors.append(f"{prefix}:readingOrderCheck_{index}_regionOrder_invalid")
    if check_members != set(members):
        errors.append(f"{prefix}:readingOrderChecks_must_cover_members")
    if "not_assessable" in statuses:
        errors.append(f"{prefix}:not_assessable_requires_phase2_review")
    expected_rating = "不达标" if "inversion" in statuses else "达标" if "local_adjustment" in statuses else "优秀"
    if row.get("rating") != expected_rating:
        errors.append(f"{prefix}:rating_must_be_{expected_rating}")


def require_partition_visual_evidence(
    errors: list[str],
    prefix: str,
    row: dict[str, Any],
) -> None:
    """Validate coverage and counting of a qualitative partition review."""
    if row.get("evidenceSource") != "original_screenshot_visual_review":
        errors.append(f"{prefix}:evidenceSource_must_be_original_screenshot_visual_review")
    if "measurement" in row:
        errors.append(f"{prefix}:visual_review_must_not_be_measurement")
    partitions = row.get("partitions")
    if not isinstance(partitions, list):
        errors.append(f"{prefix}:partitions_must_be_array")
        partitions = []
    region_names = {
        str(item.get("region")) for item in partitions
        if isinstance(item, dict) and isinstance(item.get("region"), str) and item.get("region")
    }
    checks = row.get("adjacentBoundaryChecks")
    excluded_pairs = row.get("excludedPairs")
    if not isinstance(excluded_pairs, list):
        errors.append(f"{prefix}:excludedPairs_must_be_array")
        excluded_pairs = []
    if not isinstance(checks, list):
        errors.append(f"{prefix}:adjacentBoundaryChecks_must_be_array")
        return
    issue_count = 0
    for index, check in enumerate(checks, start=1):
        if not isinstance(check, dict):
            errors.append(f"{prefix}:boundaryCheck_{index}_must_be_object")
            continue
        first_name = check.get("firstRegion")
        second_name = check.get("secondRegion")
        if first_name not in region_names or second_name not in region_names:
            errors.append(f"{prefix}:boundaryCheck_{index}_unknown_region")
            continue
        if not isinstance(check.get("clear"), bool):
            errors.append(f"{prefix}:boundaryCheck_{index}_clear_must_be_boolean")
            continue
        if check.get("evidenceSource") != "original_screenshot_visual_review":
            errors.append(f"{prefix}:boundaryCheck_{index}_evidenceSource_invalid")
        if check.get("clear") is False:
            issue_count += 1
    for index, pair in enumerate(excluded_pairs, start=1):
        if not isinstance(pair, dict):
            errors.append(f"{prefix}:excludedPair_{index}_must_be_object")
            continue
        first_name = pair.get("firstRegion")
        second_name = pair.get("secondRegion")
        if first_name not in region_names or second_name not in region_names:
            errors.append(f"{prefix}:excludedPair_{index}_unknown_region")
        if not isinstance(pair.get("reason"), str) or not pair["reason"].strip():
            errors.append(f"{prefix}:excludedPair_{index}_reason_required")
    if row.get("issueCount") != issue_count:
        errors.append(f"{prefix}:issueCount_must_equal_{issue_count}")
    expected_rating = "优秀" if issue_count == 0 else "不达标"
    if row.get("rating") != expected_rating:
        errors.append(f"{prefix}:rating_must_be_{expected_rating}")


def require_zero_redundancy_scan(errors: list[str], prefix: str, row: dict[str, Any], scope: str) -> None:
    """Validate full redundancy evidence for both zero and positive results."""
    count_field = "duplicateCount" if scope == "component" else "redundancyCount"
    count = row.get(count_field)
    if not isinstance(count, int) or count < 0:
        errors.append(f"{prefix}:{count_field}_must_be_non_negative_integer")
        return
    coverage = row.get("scanCoverage")
    if not isinstance(coverage, dict) or coverage.get("status") != "completed":
        suffix = "excellent_zero_redundancy_requires_completed_scanCoverage" if row.get("rating") == "优秀" and count == 0 else "requires_completed_scanCoverage"
        errors.append(f"{prefix}:{suffix}")
        return

    if scope == "component":
        atom_count = coverage.get("textAtomCount")
        element_ids = coverage.get("scannedElementIds")
        regions = coverage.get("scannedRegions")
        cross_checks = coverage.get("crossChecks")
        if not isinstance(atom_count, int) or atom_count < 0:
            errors.append(f"{prefix}:scanCoverage_textAtomCount_invalid")
        if not isinstance(element_ids, list) or len(element_ids) != atom_count:
            errors.append(f"{prefix}:scanCoverage_scannedElementIds_must_match_textAtomCount")
        if not isinstance(regions, list):
            errors.append(f"{prefix}:scanCoverage_scannedRegions_must_be_array")
        if not isinstance(cross_checks, list) or not COMPONENT_REDUNDANCY_CROSS_CHECKS.issubset(cross_checks):
            errors.append(f"{prefix}:scanCoverage_missing_component_crossChecks")
        examined = row.get("examinedElements")
        if not isinstance(examined, list) or examined != element_ids:
            errors.append(f"{prefix}:examinedElements_must_match_scanCoverage")
        if not isinstance(row.get("scannedRegions"), list) or row.get("scannedRegions") != regions:
            errors.append(f"{prefix}:scannedRegions_must_match_scanCoverage")
        if not isinstance(row.get("candidatePairs"), list):
            errors.append(f"{prefix}:candidatePairs_must_be_array")
        if not isinstance(row.get("selfRepeatCandidates"), list):
            errors.append(f"{prefix}:selfRepeatCandidates_must_be_array")
        duplicates = row.get("duplicates")
        if not isinstance(duplicates, list):
            errors.append(f"{prefix}:duplicates_must_be_array")
            duplicates = []
        if count != len(duplicates):
            errors.append(f"{prefix}:duplicateCount_must_match_duplicates")
        scanned_set = set(element_ids) if isinstance(element_ids, list) else set()
        for index, duplicate in enumerate(duplicates, start=1):
            if not isinstance(duplicate, dict):
                errors.append(f"{prefix}:duplicate_{index}_must_be_object")
                continue
            if duplicate.get("verdict") != "duplicate":
                errors.append(f"{prefix}:duplicate_{index}_verdict_invalid")
            for field in ("lexicalCue", "normalizedFact", "noLossReason"):
                if not isinstance(duplicate.get(field), str) or not duplicate[field].strip():
                    errors.append(f"{prefix}:duplicate_{index}_{field}_must_be_non_empty_string")
            duplicate_ids = [
                duplicate.get("elementId"), duplicate.get("leftElementId"), duplicate.get("rightElementId")
            ]
            duplicate_ids = [value for value in duplicate_ids if isinstance(value, str) and value]
            if not duplicate_ids or any(value not in scanned_set for value in duplicate_ids):
                errors.append(f"{prefix}:duplicate_{index}_elementIds_must_be_scanned")
        expected_rating = "优秀" if count == 0 else "不达标"
        if row.get("rating") != expected_rating:
            errors.append(f"{prefix}:rating_must_be_{expected_rating}")
        return

    if row.get("rating") == "优秀" and count != 0:
        errors.append(f"{prefix}:excellent_redundancy_count_must_equal_0")
        return

    page_regions = row.get("pageRegions")
    scanned_region_ids = coverage.get("scannedRegionIds")
    cross_checks = coverage.get("crossChecks")
    if not isinstance(page_regions, list) or not page_regions or not all(isinstance(region, str) and region for region in page_regions):
        errors.append(f"{prefix}:pageRegions_must_be_non_empty_strings")
        return
    if not isinstance(scanned_region_ids, list) or not set(page_regions).issubset(scanned_region_ids):
        errors.append(f"{prefix}:scanCoverage_scannedRegionIds_must_cover_pageRegions")
    expected_pair_checks = len(page_regions) * (len(page_regions) - 1) // 2
    if not isinstance(cross_checks, list) or len(cross_checks) < expected_pair_checks or any(
        not isinstance(check, str) or not check.strip() for check in cross_checks
    ):
        errors.append(f"{prefix}:scanCoverage_crossChecks_must_cover_page_region_pairs")


def _payload_contains(payload: Any, target: str) -> bool:
    if not target:
        return False
    if isinstance(payload, dict):
        return any(_payload_contains(value, target) for value in payload.values())
    if isinstance(payload, list):
        return any(_payload_contains(value, target) for value in payload)
    return str(payload) == target


def require_problem_rows_match_issues(
    errors: list[str],
    prefix: str,
    assessment_rows: Any,
    issues: list[Any],
    *,
    page_level: bool = False,
) -> None:
    """Require each actionable assessment row to project to exactly one report issue."""
    if not isinstance(assessment_rows, list):
        if issues:
            errors.append(f"{prefix}:problem_issues_require_assessmentRows")
        return
    problem_rows = [
        row for row in assessment_rows
        if isinstance(row, dict) and row.get("rating") in {"达标", "不达标", "🟡", "🔴"}
    ]
    if len(problem_rows) != len(issues):
        errors.append(f"{prefix}:problem_assessmentRows_{len(problem_rows)}_must_equal_issues_{len(issues)}")
        return
    if page_level:
        return
    unmatched = list(problem_rows)
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        targets = [str(issue.get("elementId") or ""), str(issue.get("component") or "")]
        match = next(
            (row for row in unmatched if any(_payload_contains(row, target) for target in targets if target)),
            None,
        )
        if match is None:
            errors.append(f"{prefix}:issue_not_derived_from_assessmentRow:{issue.get('elementId') or issue.get('component')}")
        else:
            unmatched.remove(match)


def require_component_copy_consistency(
    errors: list[str],
    prefix: str,
    skill: str,
    issue: dict[str, Any],
    assessment_rows: Any,
) -> None:
    """Block issue copy that contradicts its component assessment row."""
    if not isinstance(assessment_rows, list):
        return
    component_id = str(issue.get("component") or "")
    row = next((item for item in assessment_rows if isinstance(item, dict) and str(item.get("componentId") or "") == component_id), None)
    if not isinstance(row, dict):
        return
    description = str(issue.get("description") or "")
    combined = description
    rating = str(issue.get("rating") or "")
    if skill == "eval-3-color-logic":
        count = row.get("colorFamilyCount")
        families = row.get("colorFamilies")
        if not isinstance(count, int) or count < 0:
            return
        if str(count) not in description:
            errors.append(f"{prefix}:color_copy_must_include_measured_colorFamilyCount")
        if not isinstance(families, list) or not families:
            errors.append(f"{prefix}:color_copy_requires_colorFamilies")
        if re.search(r"\b(?:red|orange|yellow|green|blue|cyan|magenta|purple)\b", combined, re.IGNORECASE):
            errors.append(f"{prefix}:color_copy_must_use_chinese_family_names")
        expected_rating = "优秀" if count <= 4 else "达标" if count == 5 else "不达标"
        if rating != expected_rating:
            errors.append(f"{prefix}:color_copy_rating_must_match_measured_count")
    elif skill == "eval-4-element-complexity":
        tag_count = row.get("tagStyleCount")
        icon_count = row.get("iconStyleCount")
        if not isinstance(tag_count, int) or not isinstance(icon_count, int):
            return
        if str(tag_count) not in description or str(icon_count) not in description:
            errors.append(f"{prefix}:complexity_copy_must_include_tag_and_icon_counts")
        expected_rating = complexity_rating(tag_count, icon_count)
        if rating != expected_rating:
            errors.append(f"{prefix}:complexity_copy_rating_must_match_measured_counts")
    elif skill == "eval-5-info-hierarchy":
        tier_trace = row.get("tierTrace")
        if not isinstance(tier_trace, list) or not tier_trace:
            errors.append(f"{prefix}:hierarchy_copy_requires_tierTrace")
        if rating != row.get("rating"):
            errors.append(f"{prefix}:hierarchy_copy_rating_must_match_visual_review")
    elif skill == "eval-7-info-authenticity":
        statuses = row.get("pairJudgements")
        conflict_count = row.get("conflictCount")
        if not isinstance(conflict_count, int) or conflict_count < 0:
            return
        if str(conflict_count) not in description:
            errors.append(f"{prefix}:authenticity_copy_must_include_measured_conflictCount")
        if not isinstance(statuses, list) or not statuses:
            errors.append(f"{prefix}:authenticity_copy_requires_pairJudgements")
        expected_rating = "优秀" if conflict_count == 0 else "不达标"
        if rating != expected_rating:
            errors.append(f"{prefix}:authenticity_copy_rating_must_match_measured_conflictCount")


def require_complexity_description(errors: list[str], prefix: str, issue: dict[str, Any]) -> None:
    """Block opaque threshold-only wording: readers must see the actual counted objects."""
    description = issue.get("description")
    combined = str(description or "")
    prohibited = "图标样式数量为 2 至 3 种且未触发不达标条件时评级为达标"
    if not isinstance(description, str) or not description.strip():
        errors.append(f"{prefix}:complexity_description_missing")
    elif prohibited in combined:
        errors.append(f"{prefix}:complexity_description_must_not_repeat_template_rule")
    if "「" not in combined or "种" not in combined:
        errors.append(f"{prefix}:complexity_description_must_list_visible_objects_and_count")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate evaluation result accounting")
    parser.add_argument("--manifest-audit", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True, help="JSON array of EVAL_SCHEMA results")
    parser.add_argument("--audit", type=Path, help="Write audit JSON")
    parser.add_argument("--phase2-review", type=Path, help="Write pending Phase2 re-recognition requests for unsupported component findings")
    parser.add_argument("--require-evidence", action="store_true", help="Require a local evidence image for every failed element issue")
    args = parser.parse_args()

    manifest = json.loads(args.manifest_audit.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = json.loads(args.results.read_text(encoding="utf-8"))
    expected_total = manifest.get("total")
    manifest_query = manifest.get("query", "")
    if not isinstance(manifest_query, str) or not manifest_query.strip():
        match = re.match(r"^elements_(.+?)(?:_[^/]+)?\.audit\.json$", args.manifest_audit.name)
        manifest_query = match.group(1) if match else ""
    active_by_id = {item.get("id"): item for item in manifest.get("activeElements", []) if isinstance(item, dict)}
    page_framework_dimension = "phase3-page_framework-eval"
    single_element_dimension = "phase3-single_element-eval"
    component_skills = {
        "eval-1-supply-completeness",
        "eval-2-visual-order-alignment",
        "eval-3-color-logic",
        "eval-4-element-complexity",
        "eval-5-info-hierarchy",
        "eval-6-info-partitioning",
        "eval-7-info-authenticity",
        "eval-8-info-redundancy",
    }
    errors: list[str] = []
    phase2_review_items: list[dict[str, Any]] = []
    if not manifest.get("valid") or not isinstance(expected_total, int) or expected_total <= 0:
        errors.append("manifest_audit_invalid")

    for result in results:
        skill = result.get("skill", "unknown")
        dimension = str(result.get("dimension") or "")
        for unit in result.get("units", []):
            if not isinstance(unit, dict):
                errors.append(f"{skill}/unknown:unit_must_be_object")
                continue
            tab = unit.get("tab", "unknown")
            require_supported_rating(errors, f"{skill}/{tab}", dimension, str(skill), unit)
            details = unit.get("details") or {}
            if not isinstance(details, dict):
                errors.append(f"{skill}/{tab}:details_must_be_object")
                continue
            require_non_empty_string(errors, f"{skill}/{tab}", unit, "reason")
            require_no_forbidden_terms(errors, f"{skill}/{tab}:reason", str(unit.get("reason") or ""))
            screenshot = details.get("screenshot")
            if not isinstance(screenshot, str) or not screenshot or not Path(screenshot).is_file():
                errors.append(f"{skill}/{tab}:screenshot_must_reference_existing_original")
            evidence_mode = details.get("evidenceMode")
            if evidence_mode not in {"annotated-region", "original-page", "hybrid"}:
                errors.append(f"{skill}/{tab}:evidenceMode_invalid:{evidence_mode}")
            overview = details.get("overview") or {}
            values = [overview.get("total"), overview.get("excellent"), overview.get("pass"), overview.get("fail")]
            if not all(isinstance(value, int) and value >= 0 for value in values):
                errors.append(f"{skill}/{tab}:overview_requires_non_negative_integers")
                continue
            total, excellent, passed, failed = values
            evidence = (unit.get("details") or {}).get("evidence") or {}
            assessment_rows = evidence.get("assessmentRows")
            if result.get("dimension") == page_framework_dimension:
                if total != 1:
                    errors.append(f"{skill}/{tab}:page_framework_overview_total_must_equal_1")
                if evidence_mode not in {"original-page", "hybrid", "annotated-region"}:
                    errors.append(f"{skill}/{tab}:page_framework_requires_evidence_mode")
                required_page_fields = PAGE_EVIDENCE_REQUIREMENTS.get(skill)
                evidence_required = (
                    unit.get("rating") != "优秀"
                    or skill == "eval-3-page-color-logic"
                    or skill in {"eval-6-info-comparability", "eval-7-info-redundancy"}
                )
                if evidence_required:
                    if not isinstance(assessment_rows, list) or len(assessment_rows) != 1:
                        errors.append(f"{skill}/{tab}:page_framework_requires_exactly_one_assessmentRow")
                    elif required_page_fields:
                        require_row_fields(errors, f"{skill}/{tab}", assessment_rows[0], required_page_fields)
                    else:
                        errors.append(f"{skill}/{tab}:unknown_page_framework_skill_without_evidence_contract")
                if skill == "eval-7-info-redundancy" and isinstance(assessment_rows, list) and assessment_rows:
                    row = assessment_rows[0]
                    if isinstance(row, dict):
                        require_zero_redundancy_scan(errors, f"{skill}/{tab}/row_1", row, "page")
                if skill == "eval-3-page-color-logic" and isinstance(assessment_rows, list) and assessment_rows:
                    row = assessment_rows[0]
                    if isinstance(row, dict):
                        require_page_color_component_aggregation(errors, f"{skill}/{tab}/row_1", row)
                if skill == "eval-6-info-comparability" and isinstance(assessment_rows, list) and assessment_rows:
                    row = assessment_rows[0]
                    if isinstance(row, dict):
                        require_evidence_source(
                            errors,
                            f"{skill}/{tab}/row_1",
                            row,
                            "phase2_json_cross_card_comparison",
                        )
                        for field in ("cardGroups", "comparableFields", "comparisons"):
                            if not isinstance(row.get(field), list):
                                errors.append(f"{skill}/{tab}:{field}_must_be_array")
                        comparisons = row.get("comparisons")
                        if isinstance(comparisons, list):
                            for index, comparison in enumerate(comparisons, start=1):
                                if not isinstance(comparison, dict) or not {
                                    "comparisonGroupKey", "semanticRole", "observations",
                                    "detectedDifferences", "phase3Judgement",
                                }.issubset(comparison):
                                    errors.append(f"{skill}/{tab}:comparison_{index}_missing_phase3_derivation_trace")
                                    continue
                                if not isinstance(comparison.get("observations"), list) or len(comparison["observations"]) < 2:
                                    errors.append(f"{skill}/{tab}:comparison_{index}_requires_two_observations")
                                if not isinstance(comparison.get("detectedDifferences"), dict):
                                    errors.append(f"{skill}/{tab}:comparison_{index}_detectedDifferences_invalid")
                                if comparison.get("phase3Judgement") not in {"consistent", "inconsistent", "not_material", "needs_review"}:
                                    errors.append(f"{skill}/{tab}:comparison_{index}_phase3Judgement_invalid")
                page_issues = (unit.get("details") or {}).get("issues")
                if unit.get("rating") in {"达标", "不达标", "🟡", "🔴"} and (not isinstance(page_issues, list) or not page_issues):
                    errors.append(f"{skill}/{tab}:actionable_page_result_requires_non_empty_issues")
                if page_issues is not None and not isinstance(page_issues, list):
                    errors.append(f"{skill}/{tab}:page_framework_issues_must_be_array")
                    page_issues = []
                page_issue_required = {"pageArea", "description", "rating", "recommendation"}
                page_recommendations: set[str] = set()
                for issue in page_issues or []:
                    if not isinstance(issue, dict):
                        errors.append(f"{skill}/{tab}:page_framework_issue_must_be_object")
                        continue
                    missing_page_fields = page_issue_required - issue.keys()
                    if missing_page_fields:
                        errors.append(f"{skill}/{tab}:page_framework_issue_missing_fields:{','.join(sorted(missing_page_fields))}")
                    require_non_empty_string(errors, f"{skill}/{tab}:page_framework_issue", issue, "description")
                    require_no_forbidden_terms(errors, f"{skill}/{tab}:page_framework_issue:description", str(issue.get("description") or ""))
                    require_no_forbidden_terms(errors, f"{skill}/{tab}:page_framework_issue:recommendation", str(issue.get("recommendation") or ""))
                    require_actionable_recommendation(errors, f"{skill}/{tab}:page_framework_issue", issue)
                    recommendation = str(issue.get("recommendation", "")).strip()
                    if recommendation and recommendation in page_recommendations:
                        errors.append(f"{skill}/{tab}:page_framework_issue_recommendation_must_be_issue_specific")
                    page_recommendations.add(recommendation)
                    forbidden_fields = {"elementId", "coord", "component", "elementType", "content", "finding", "priority", "priorityReason", "dimension"} & issue.keys()
                    if forbidden_fields:
                        errors.append(f"{skill}/{tab}:page_framework_issue_forbidden_fields:{','.join(sorted(forbidden_fields))}")
                    if args.require_evidence and issue.get("rating") in {"达标", "不达标", "🟡", "🔴"}:
                        evidence_path = issue.get("evidenceImage")
                        if not isinstance(evidence_path, str) or not evidence_path or not Path(evidence_path).is_file():
                            errors.append(f"{skill}/{tab}:page_framework_issue_evidence_image_missing")
                require_problem_rows_match_issues(
                    errors, f"{skill}/{tab}", assessment_rows, page_issues or [], page_level=True
                )
            elif result.get("dimension") == single_element_dimension and (
                skill == "eval-2-color-logic-single-element"
                or any(key in evidence for key in ("evaluatedUnitCount", "evaluatedUnitIds", "excludedUnits"))
            ):
                evaluated_unit_count = evidence.get("evaluatedUnitCount")
                evaluated_unit_ids = evidence.get("evaluatedUnitIds")
                excluded_units = evidence.get("excludedUnits", [])
                if not isinstance(evaluated_unit_count, int) or evaluated_unit_count < 0:
                    errors.append(f"{skill}/{tab}:single_element_evaluatedUnitCount_required")
                elif total != evaluated_unit_count:
                    errors.append(f"{skill}/{tab}:overview_total_{total}_must_equal_evaluatedUnitCount_{evaluated_unit_count}")
                if not isinstance(evaluated_unit_ids, list) or len(evaluated_unit_ids) != evaluated_unit_count:
                    errors.append(f"{skill}/{tab}:single_element_evaluatedUnitIds_must_match_evaluatedUnitCount")
                elif any(not isinstance(element_id, str) or element_id not in active_by_id for element_id in evaluated_unit_ids):
                    errors.append(f"{skill}/{tab}:single_element_evaluatedUnitIds_not_in_manifest")
                if not isinstance(excluded_units, list) or any(not isinstance(item, dict) or item.get("id") not in active_by_id or not isinstance(item.get("reason"), str) or not item["reason"].strip() for item in excluded_units):
                    errors.append(f"{skill}/{tab}:single_element_excludedUnits_invalid")
                elif isinstance(evaluated_unit_ids, list):
                    excluded_ids = {item["id"] for item in excluded_units}
                    if excluded_ids & set(evaluated_unit_ids) or len(excluded_ids) + len(evaluated_unit_ids) != expected_total:
                        errors.append(f"{skill}/{tab}:single_element_inventory_must_partition_manifest")
                if evidence.get("sourceManifestTotal") != expected_total:
                    errors.append(f"{skill}/{tab}:sourceManifestTotal_must_equal_{expected_total}")
                if skill == "eval-2-color-logic-single-element":
                    assessment_rows = evidence.get("assessmentRows")
                    colored_candidate_ids = evidence.get("coloredCandidateIds")
                    neutral_excluded_ids = evidence.get("neutralExcludedIds")
                    if evidence.get("prefilterEvidenceSource") != "phase2_json_visual_colors":
                        errors.append(f"{skill}/{tab}:prefilterEvidenceSource_invalid")
                    if not isinstance(colored_candidate_ids, list) or colored_candidate_ids != evaluated_unit_ids:
                        errors.append(f"{skill}/{tab}:coloredCandidateIds_must_equal_evaluatedUnitIds")
                    if not isinstance(neutral_excluded_ids, list) or any(
                        element_id not in active_by_id for element_id in neutral_excluded_ids
                    ):
                        errors.append(f"{skill}/{tab}:neutralExcludedIds_invalid")
                    if not isinstance(assessment_rows, list) or len(assessment_rows) != evaluated_unit_count:
                        errors.append(f"{skill}/{tab}:assessmentRows_must_match_colored_candidates")
                    elif isinstance(evaluated_unit_ids, list):
                        row_ids: list[str] = []
                        for index, row in enumerate(assessment_rows, start=1):
                            row_prefix = f"{skill}/{tab}/row_{index}"
                            if not require_row_fields(errors, row_prefix, row, SINGLE_ELEMENT_COLOR_ROW_REQUIREMENTS):
                                continue
                            row_ids.append(str(row.get("elementId")))
                            require_measurement(errors, row_prefix, row)
                            require_single_element_color_pixel_evidence(
                                errors, row_prefix, row, active_by_id
                            )
                        if row_ids != evaluated_unit_ids:
                            errors.append(f"{skill}/{tab}:assessmentRows_must_follow_evaluatedUnitIds")
            elif skill in component_skills:
                evaluated_unit_count = evidence.get("evaluatedUnitCount")
                assessment_rows = evidence.get("assessmentRows")
                full_coverage_required = skill in COMPONENT_FULL_COVERAGE_SKILLS
                evidence_required = unit.get("rating") != "优秀" or full_coverage_required
                if evidence_required:
                    if not isinstance(assessment_rows, list) or not assessment_rows:
                        errors.append(f"{skill}/{tab}:component_assessmentRows_required")
                    elif full_coverage_required:
                        if not isinstance(evaluated_unit_count, int) or evaluated_unit_count < 0:
                            errors.append(f"{skill}/{tab}:component_evaluatedUnitCount_required")
                        elif total != evaluated_unit_count:
                            errors.append(f"{skill}/{tab}:overview_total_{total}_must_equal_evaluatedUnitCount_{evaluated_unit_count}")
                        if len(assessment_rows) != evaluated_unit_count:
                            errors.append(f"{skill}/{tab}:component_assessmentRows_must_match_evaluatedUnitCount")
                        if evidence.get("sourceManifestTotal") != expected_total:
                            errors.append(f"{skill}/{tab}:sourceManifestTotal_must_equal_{expected_total}")
                    elif skill in COMPONENT_PROBLEM_ONLY_SKILLS and any(
                        isinstance(row, dict) and row.get("rating") in {"优秀", "🟢"}
                        for row in assessment_rows
                    ):
                        errors.append(f"{skill}/{tab}:component_assessmentRows_must_keep_problem_rows_only")
                    required_component_fields = COMPONENT_ROW_REQUIREMENTS.get(skill)
                    if isinstance(assessment_rows, list) and required_component_fields:
                        for index, row in enumerate(assessment_rows, start=1):
                            require_row_fields(errors, f"{skill}/{tab}/row_{index}", row, required_component_fields)
                            if skill == "eval-3-color-logic" and isinstance(row, dict):
                                require_component_color_pixel_evidence(
                                    errors, f"{skill}/{tab}/row_{index}", row, active_by_id
                                )
                            if skill == "eval-4-element-complexity" and isinstance(row, dict):
                                require_evidence_source(
                                    errors,
                                    f"{skill}/{tab}/row_{index}",
                                    row,
                                    "phase2_json_visual_inventory",
                                )
                            if skill == "eval-5-info-hierarchy" and isinstance(row, dict):
                                require_hierarchy_visual_evidence(
                                    errors, f"{skill}/{tab}/row_{index}", row
                                )
                            if skill == "eval-7-info-authenticity" and isinstance(row, dict):
                                require_evidence_source(
                                    errors,
                                    f"{skill}/{tab}/row_{index}",
                                    row,
                                    "phase2_json_and_original_screenshot",
                                )
                            if skill == "eval-8-info-redundancy" and isinstance(row, dict):
                                require_evidence_source(
                                    errors,
                                    f"{skill}/{tab}/row_{index}",
                                    row,
                                    "phase2_json_full_redundancy_scan",
                                )
                                require_zero_redundancy_scan(errors, f"{skill}/{tab}/row_{index}", row, "component")
                if skill == "eval-2-visual-order-alignment" and isinstance(assessment_rows, list):
                    for index, row in enumerate(assessment_rows, start=1):
                        if not isinstance(row, dict):
                            continue
                        if not isinstance(row.get("comparisonGroupKey"), str) or not row["comparisonGroupKey"].strip():
                            errors.append(f"{skill}/{tab}:alignment_assessmentRow_{index}_comparisonGroupKey_invalid")
                        require_alignment_visual_evidence(
                            errors,
                            f"{skill}/{tab}:alignment_assessmentRow_{index}",
                            row,
                        )
                if skill == "eval-6-info-partitioning" and isinstance(assessment_rows, list):
                    for index, row in enumerate(assessment_rows, start=1):
                        if isinstance(row, dict):
                            require_partition_visual_evidence(
                                errors,
                                f"{skill}/{tab}:partition_assessmentRow_{index}",
                                row,
                            )
                if skill == "eval-7-info-authenticity" and isinstance(assessment_rows, list):
                    for index, row in enumerate(assessment_rows, start=1):
                        if not isinstance(row, dict):
                            continue
                        relations = row.get("candidatePairs")
                        statuses = row.get("pairJudgements")
                        inapplicable = row.get("inapplicableChecks")
                        if not isinstance(relations, list):
                            errors.append(f"{skill}/{tab}:authenticity_assessmentRow_{index}_candidatePairs_invalid")
                        if not isinstance(statuses, list) or len(statuses) != len(relations or []):
                            errors.append(f"{skill}/{tab}:authenticity_assessmentRow_{index}_pairJudgements_must_match_candidates")
                        elif any(status not in {"consistent", "conflict", "not_applicable"} for status in statuses):
                            errors.append(f"{skill}/{tab}:authenticity_assessmentRow_{index}_pairJudgements_invalid")
                        if not isinstance(inapplicable, list):
                            errors.append(f"{skill}/{tab}:authenticity_assessmentRow_{index}_inapplicableChecks_must_be_array")
                        coverage = row.get("scanCoverage")
                        if not isinstance(coverage, dict) or coverage.get("status") != "completed":
                            errors.append(f"{skill}/{tab}:authenticity_assessmentRow_{index}_scanCoverage_invalid")
                        elif any(
                            not isinstance(coverage.get(field), list)
                            for field in ("scannedElementIds", "scannedRegions", "crossChecks")
                        ):
                            errors.append(f"{skill}/{tab}:authenticity_assessmentRow_{index}_scanCoverage_arrays_required")
                        conflicts = row.get("conflicts")
                        conflict_count = row.get("conflictCount")
                        if not isinstance(conflicts, list):
                            errors.append(f"{skill}/{tab}:authenticity_assessmentRow_{index}_conflicts_must_be_array")
                            conflicts = []
                        if not isinstance(conflict_count, int) or conflict_count < 0:
                            errors.append(f"{skill}/{tab}:authenticity_assessmentRow_{index}_conflictCount_invalid")
                        elif conflict_count != len(conflicts):
                            errors.append(f"{skill}/{tab}:authenticity_assessmentRow_{index}_conflictCount_must_match_conflicts")
                        expected_rating = "优秀" if conflict_count == 0 else "不达标"
                        if isinstance(conflict_count, int) and row.get("rating") != expected_rating:
                            errors.append(f"{skill}/{tab}:authenticity_assessmentRow_{index}_rating_must_be_{expected_rating}")
                        for conflict_index, conflict in enumerate(conflicts, start=1):
                            if not isinstance(conflict, dict) or conflict.get("verdict") != "conflict":
                                errors.append(f"{skill}/{tab}:authenticity_assessmentRow_{index}_conflict_{conflict_index}_invalid")
                if skill in {"eval-7-info-authenticity", "eval-8-info-redundancy"} and isinstance(assessment_rows, list):
                    evaluated_unit_ids = evidence.get("evaluatedUnitIds")
                    row_component_ids = [row.get("componentId") for row in assessment_rows if isinstance(row, dict)]
                    if not isinstance(evaluated_unit_ids, list) or row_component_ids != evaluated_unit_ids:
                        errors.append(f"{skill}/{tab}:assessmentRows_must_follow_evaluatedUnitIds")
                if skill == "eval-4-element-complexity" and isinstance(assessment_rows, list):
                    for index, row in enumerate(assessment_rows, start=1):
                        if not isinstance(row, dict):
                            errors.append(f"{skill}/{tab}:complexity_assessmentRow_{index}_must_be_object")
                            continue
                        required_complexity_fields = COMPONENT_ROW_REQUIREMENTS["eval-4-element-complexity"]
                        missing_complexity_fields = required_complexity_fields - row.keys()
                        if missing_complexity_fields:
                            continue
                        for field in ("includedTagStyles", "includedIconStyles", "excludedEntities"):
                            if not isinstance(row[field], list):
                                errors.append(f"{skill}/{tab}:complexity_assessmentRow_{index}_{field}_must_be_array")
                        require_complexity_coverage(
                            errors,
                            f"{skill}/{tab}:complexity_assessmentRow_{index}",
                            row,
                            active_by_id,
                        )
                        tag_count = row.get("tagStyleCount")
                        icon_count = row.get("iconStyleCount")
                        if not isinstance(tag_count, int) or tag_count < 0:
                            errors.append(f"{skill}/{tab}:complexity_assessmentRow_{index}_tagStyleCount_invalid")
                        elif isinstance(row.get("includedTagStyles"), list) and tag_count != len(row["includedTagStyles"]):
                            errors.append(f"{skill}/{tab}:complexity_assessmentRow_{index}_tagStyleCount_mismatch")
                        if not isinstance(icon_count, int) or icon_count < 0:
                            errors.append(f"{skill}/{tab}:complexity_assessmentRow_{index}_iconStyleCount_invalid")
                        elif isinstance(row.get("includedIconStyles"), list) and icon_count != len(row["includedIconStyles"]):
                            errors.append(f"{skill}/{tab}:complexity_assessmentRow_{index}_iconStyleCount_mismatch")
                        if isinstance(tag_count, int) and isinstance(icon_count, int):
                            expected_rating = complexity_rating(tag_count, icon_count)
                            if row.get("rating") != expected_rating:
                                errors.append(f"{skill}/{tab}:complexity_assessmentRow_{index}_rating_must_be_{expected_rating}")
                        tag_entries = row.get("includedTagStyles")
                        if isinstance(tag_entries, list):
                            for entry_index, entry in enumerate(tag_entries, start=1):
                                if not isinstance(entry, dict) or not all(
                                    isinstance(entry.get(key), str) and entry[key].strip()
                                    for key in ("content", "styleKey", "countDecision", "dedupDecision")
                                ):
                                    errors.append(f"{skill}/{tab}:complexity_includedTagStyles_{entry_index}_must_include_traceable_chinese_style_facts")
                                elif len([part for part in entry["styleKey"].split("|") if part.strip()]) != 5:
                                    errors.append(f"{skill}/{tab}:complexity_includedTagStyles_{entry_index}_styleKey_must_have_five_segments")
                        icon_entries = row.get("includedIconStyles")
                        if isinstance(icon_entries, list):
                            for entry_index, entry in enumerate(icon_entries, start=1):
                                if not isinstance(entry, dict) or not all(
                                    isinstance(entry.get(key), str) and entry[key].strip()
                                    for key in ("elementId", "content", "styleKey", "countDecision", "dedupDecision")
                                ):
                                    errors.append(f"{skill}/{tab}:complexity_includedIconStyles_{entry_index}_must_include_traceable_chinese_style_facts")
                                elif len([part for part in entry["styleKey"].split("|") if part.strip()]) != 5:
                                    errors.append(f"{skill}/{tab}:complexity_includedIconStyles_{entry_index}_styleKey_must_have_five_segments")
            elif total != expected_total:
                errors.append(f"{skill}/{tab}:overview_total_{total}_must_equal_{expected_total}")
            if excellent + passed + failed != total:
                errors.append(f"{skill}/{tab}:overview_distribution_does_not_sum_to_total")
            fail_rate = overview.get("failRate")
            expected_rate = f"{(failed / total * 100):.1f}%" if total else "0%"
            if fail_rate not in (expected_rate, expected_rate.replace('.0%', '%')):
                errors.append(f"{skill}/{tab}:failRate_{fail_rate}_must_equal_{expected_rate}")
            issues = details.get("issues")
            if result.get("dimension") == page_framework_dimension:
                continue
            if unit.get("rating") in {"达标", "不达标", "🟡", "🔴"} and (not isinstance(issues, list) or not issues):
                errors.append(f"{skill}/{tab}:actionable_result_requires_non_empty_issues")
            if not isinstance(issues, list):
                errors.append(f"{skill}/{tab}:issues_must_be_array")
                continue
            issue_ids: set[str] = set()
            issue_recommendations: set[str] = set()
            issue_pass = 0
            issue_fail = 0
            required_issue_fields = {"elementId", "coord", "component", "description", "rating", "recommendation"}
            for issue in issues:
                if not isinstance(issue, dict):
                    errors.append(f"{skill}/{tab}:issue_must_be_object")
                    continue
                missing = required_issue_fields - issue.keys()
                if missing:
                    errors.append(f"{skill}/{tab}:issue_missing_fields:{','.join(sorted(missing))}")
                    continue
                require_non_empty_string(errors, f"{skill}/{tab}:issue", issue, "description")
                require_no_forbidden_terms(errors, f"{skill}/{tab}:issue:description", str(issue.get("description") or ""))
                require_no_forbidden_terms(errors, f"{skill}/{tab}:issue:recommendation", str(issue.get("recommendation") or ""))
                require_actionable_recommendation(errors, f"{skill}/{tab}:issue", issue)
                if result.get("dimension") in {single_element_dimension, "phase3-card_or_component-eval"}:
                    require_readable_component_location(errors, f"{skill}/{tab}:issue", issue)
                forbidden_issue_fields = {"finding", "priority", "priorityReason", "dimension", "elementType", "content"} & issue.keys()
                if forbidden_issue_fields:
                    errors.append(f"{skill}/{tab}:issue_forbidden_fields:{','.join(sorted(forbidden_issue_fields))}")
                if skill in {"eval-3-color-logic", "eval-4-element-complexity", "eval-5-info-hierarchy", "eval-7-info-authenticity"}:
                    require_component_copy_consistency(
                        errors, f"{skill}/{tab}:issue", skill, issue, assessment_rows
                    )
                if skill == "eval-4-element-complexity":
                    require_complexity_description(errors, f"{skill}/{tab}:issue", issue)
                recommendation = str(issue.get("recommendation", "")).strip()
                if recommendation and recommendation in issue_recommendations:
                    errors.append(f"{skill}/{tab}:issue_recommendation_must_be_issue_specific")
                issue_recommendations.add(recommendation)
                element_id = issue.get("elementId")
                if not isinstance(element_id, str) or element_id in issue_ids:
                    errors.append(f"{skill}/{tab}:issue_elementId_missing_or_duplicate:{element_id}")
                    continue
                issue_ids.add(element_id)
                element_in_manifest = element_id in active_by_id
                if not element_in_manifest:
                    errors.append(f"{skill}/{tab}:issue_elementId_not_in_manifest:{element_id}")
                elif issue.get("coord") != active_by_id[element_id].get("coord"):
                    errors.append(f"{skill}/{tab}:issue_coord_must_equal_manifest:{element_id}")
                if not element_in_manifest:
                    continue
                # Whole-page conclusions without a Phase2-confirmed local boundary
                # intentionally use original-page evidence and must not fabricate a red box.
                requires_local_evidence = evidence_mode in {"annotated-region", "hybrid"}
                if args.require_evidence and requires_local_evidence and issue.get("rating") in {"🟡", "达标", "🔴", "不达标"}:
                    evidence_path = issue.get("evidenceImage")
                    if not isinstance(evidence_path, str) or not evidence_path or not Path(evidence_path).is_file():
                        errors.append(f"{skill}/{tab}:problem_issue_evidence_image_missing:{element_id}")
                    if result.get("dimension") == "phase3-single_element-eval":
                        if issue.get("evidenceScope") not in {"component", "card"}:
                            errors.append(f"{skill}/{tab}:single_element_evidence_scope_must_be_component_or_card:{element_id}")
                        if issue.get("evidenceTargetElementId") != element_id:
                            errors.append(f"{skill}/{tab}:single_element_evidence_target_must_equal_issue_element:{element_id}")
                        if issue.get("evidenceTargetCoord") != active_by_id[element_id].get("coord"):
                            errors.append(f"{skill}/{tab}:single_element_evidence_target_coord_must_equal_manifest:{element_id}")
                rating = issue.get("rating")
                if rating in {"🔴", "不达标"}:
                    issue_fail += 1
                elif rating in {"🟡", "达标"}:
                    issue_pass += 1
                else:
                    errors.append(f"{skill}/{tab}:issue_rating_must_be_pass_or_fail:{rating}")
            if evidence_mode == "annotated-region" and (issue_pass + issue_fail) and not args.require_evidence:
                # Phase4 may run later; the mode only declares that these issues are geometrically annotatable.
                pass
            if issue_fail != failed:
                errors.append(f"{skill}/{tab}:fail_count_{failed}_must_equal_fail_issues_{issue_fail}")
            if issue_pass != passed:
                errors.append(f"{skill}/{tab}:pass_count_{passed}_must_equal_pass_issues_{issue_pass}")
            require_problem_rows_match_issues(errors, f"{skill}/{tab}", assessment_rows, issues)

    audit = {
        "valid": not errors,
        "expectedTotal": expected_total,
        "errors": errors,
        "phase2ReviewRequired": bool(phase2_review_items),
        "phase2ReviewItems": phase2_review_items,
    }
    if args.phase2_review:
        args.phase2_review.parent.mkdir(parents=True, exist_ok=True)
        args.phase2_review.write_text(json.dumps({"pending": phase2_review_items}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.audit:
        args.audit.parent.mkdir(parents=True, exist_ok=True)
        args.audit.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False))
    return 0 if audit["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
