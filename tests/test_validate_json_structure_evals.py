from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_DIR / "scripts" / "validate_eval_results.py"


def load_module():
    sys.path.insert(0, str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("validate_json_structure_evals_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


class ValidateJsonStructureEvalsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()

    def test_partition_visual_review_can_be_clear_even_when_geometry_touches(self) -> None:
        row = {
            "evidenceSource": "original_screenshot_visual_review",
            "partitions": [
                {"region": "location", "elementIds": ["L1"], "contentBounds": [10, 10, 100, 20]},
                {"region": "tags", "elementIds": ["T1"], "contentBounds": [10, 30, 80, 20]},
            ],
            "adjacentBoundaryChecks": [{
                "firstRegion": "location",
                "secondRegion": "tags",
                "axis": "vertical",
                "gapPx": 0,
                "clear": True,
                "evidenceSource": "original_screenshot_visual_review",
            }],
            "excludedPairs": [],
            "issueCount": 0,
            "rating": "优秀",
        }
        errors: list[str] = []
        self.module.require_partition_visual_evidence(errors, "eval-6/C1", row)
        self.assertEqual(errors, [])

    def test_partition_rejects_invalid_source_and_issue_count(self) -> None:
        row = {
            "evidenceSource": "phase2_json_coordinates",
            "partitions": [
                {"region": "location", "elementIds": ["L1"], "contentBounds": [10, 10, 100, 20]},
                {"region": "tags", "elementIds": ["T1"], "contentBounds": [10, 40, 80, 20]},
            ],
            "adjacentBoundaryChecks": [{
                "firstRegion": "location", "secondRegion": "tags", "axis": "vertical",
                "gapPx": 15, "clear": False, "evidenceSource": "phase2_json_coordinates",
            }],
            "excludedPairs": [],
            "issueCount": 0,
            "rating": "不达标",
            "measurement": {"tool": "forbidden"},
        }
        errors: list[str] = []
        self.module.require_partition_visual_evidence(errors, "eval-6/C1", row)
        self.assertTrue(any("evidenceSource_must_be_original_screenshot_visual_review" in error for error in errors))
        self.assertTrue(any("issueCount_must_equal_1" in error for error in errors))
        self.assertFalse(any("gapPx_must_equal" in error for error in errors))

    def test_partition_overlapping_unions_are_excluded_not_failed(self) -> None:
        row = {
            "evidenceSource": "original_screenshot_visual_review",
            "partitions": [
                {"region": "head_media", "elementIds": ["PHOTO"], "contentBounds": [10, 10, 100, 100]},
                {"region": "title", "elementIds": ["BADGE_TITLE"], "contentBounds": [90, 10, 100, 30]},
            ],
            "adjacentBoundaryChecks": [],
            "excludedPairs": [{
                "firstRegion": "head_media", "secondRegion": "title",
                "gapX": -20, "gapY": -30,
                "reason": "图片角标属于合法父子覆盖关系",
            }],
            "issueCount": 0,
            "rating": "优秀",
        }
        errors: list[str] = []
        self.module.require_partition_visual_evidence(errors, "eval-6/C1", row)
        self.assertEqual(errors, [])

    def test_alignment_uses_visual_attention_status_not_coordinate_recomputation(self) -> None:
        def signature(card: str) -> dict:
            return {
                "componentId": card,
                "layoutMode": "左图右文",
                "layoutSignature": "expected:title→decision→support;observed:title→decision→support",
                "regions": ["title", "decision", "support"],
                "relations": ["title_before_decision", "decision_before_support"],
            }

        row = {
            "evidenceSource": "original_screenshot_visual_review",
            "members": ["C1", "C2"],
            "layoutSignatures": [signature("C1"), signature("C2")],
            "readingOrderChecks": [
                {"componentId": "C1", "regionOrder": ["head_media", "title", "price"], "status": "consistent"},
                {"componentId": "C2", "regionOrder": ["head_media", "title", "price"], "status": "consistent"},
            ],
            "rating": "优秀",
        }
        errors: list[str] = []
        self.module.require_alignment_visual_evidence(errors, "eval-2/group", row)
        self.assertEqual(errors, [])

    def test_alignment_inversion_requires_fail_rating(self) -> None:
        row = {
            "evidenceSource": "original_screenshot_visual_review",
            "members": ["C1"],
            "layoutSignatures": [{
                "componentId": "C1",
                "layoutMode": "左图右文",
                "layoutSignature": "auxiliary badge overrides identity",
                "regions": ["identity", "decision", "support"],
                "relations": ["badge_before_identity"],
            }],
            "readingOrderChecks": [{
                "componentId": "C1",
                "regionOrder": ["badge", "title", "price"],
                "status": "inversion",
            }],
            "rating": "不达标",
        }
        errors: list[str] = []
        self.module.require_alignment_visual_evidence(errors, "eval-2/group", row)
        self.assertEqual(errors, [])

    def test_hierarchy_level_count_is_descriptive_not_a_rating_formula(self) -> None:
        row = {
            "componentId": "C1",
            "sourceElements": [{"elementId": "E1", "visualRole": "identity"}],
            "weightSequence": ["E1"],
            "tierTrace": ["身份层", "决策层"],
            "levelCount": 2,
            "rating": "优秀",
        }
        errors: list[str] = []
        self.module.require_hierarchy_visual_evidence(errors, "eval-5/C1", row)
        self.assertEqual(errors, [])

    def test_component_colour_is_validated_from_pixel_evidence(self) -> None:
        active = {"E1": {"coord": [0, 0, 20, 20]}, "E2": {"coord": [20, 0, 20, 20]}}
        row = {
            "evidenceSource": "original_screenshot_pixels",
            "scannedElementIds": ["E1"],
            "excludedElementIds": ["E2"],
            "sourceColorValues": [
                {"elementId": "E1", "field": "textColor", "value": "#FF6600", "colorFamily": "橙"}
            ],
            "colorFamilies": ["橙"],
            "colorFamilyCount": 1,
            "rating": "优秀",
        }
        errors: list[str] = []
        self.module.require_component_color_pixel_evidence(errors, "eval-3/C1", row, active)
        self.assertEqual(errors, [])

    def test_component_colour_four_families_is_excellent(self) -> None:
        active = {f"E{index}": {"coord": [index * 20, 0, 20, 20]} for index in range(1, 5)}
        families = ["红", "黄", "绿", "蓝"]
        row = {
            "evidenceSource": "original_screenshot_pixels",
            "scannedElementIds": list(active),
            "excludedElementIds": [],
            "sourceColorValues": [
                {"elementId": f"E{index}", "field": "textColor", "value": value, "colorFamily": family}
                for index, (family, value) in enumerate(zip(families, ("#FF0000", "#FFFF00", "#00FF00", "#0000FF")), start=1)
            ],
            "colorFamilies": families,
            "colorFamilyCount": 4,
            "rating": "优秀",
        }
        errors: list[str] = []
        self.module.require_component_color_pixel_evidence(errors, "eval-3/C4", row, active)
        self.assertEqual(errors, [])
        row["rating"] = "达标"
        self.module.require_component_color_pixel_evidence(errors, "eval-3/C4", row, active)
        self.assertTrue(any("rating_must_be_优秀" in error for error in errors))

    def test_issue_description_requires_a_readable_card_or_component_location(self) -> None:
        errors: list[str] = []
        self.module.require_readable_component_location(
            errors,
            "eval-3/issue",
            {"description": "商卡2 · 川味小馆的促销标签使用 5 个色系，命中达标档。"},
        )
        self.assertEqual(errors, [])
        self.module.require_readable_component_location(
            errors,
            "eval-3/issue",
            {"description": "图筛中的彩色标签实例过多，命中不达标档。"},
        )
        self.assertEqual(errors, [])
        self.module.require_readable_component_location(
            errors,
            "eval-3/issue",
            {"description": "C1 的标签实例过多，命中不达标档。"},
        )
        self.assertTrue(any("description_requires_readable_card_or_component_location" in error for error in errors))

    def test_page_colour_uses_the_union_of_component_families(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "component-color-families.json"
            artifact.write_text("{}", encoding="utf-8")
            row = {
                "colorLogicContractVersion": "4.0",
                "componentColorArtifact": str(artifact),
                "componentColorSummaries": [
                    {"componentId": "C1", "colorFamilies": ["红", "蓝", "黄"], "colorFamilyCount": 3},
                    {"componentId": "C2", "colorFamilies": ["蓝", "橙", "绿"], "colorFamilyCount": 3},
                ],
                "colorFamilies": ["红", "蓝", "黄", "橙", "绿"],
                "colorFamilyCount": 5,
                "evidenceSource": "component_pixel_color_aggregation",
                "rating": "优秀",
            }
            errors: list[str] = []
            self.module.require_page_color_component_aggregation(errors, "eval-3/page", row)
        self.assertEqual(errors, [])

    def test_page_colour_thresholds_are_five_six_and_seven(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "component-color-families.json"
            artifact.write_text("{}", encoding="utf-8")
            families = ["红", "橙", "黄", "绿", "青", "蓝", "紫"]
            row = {
                "colorLogicContractVersion": "4.0",
                "componentColorArtifact": str(artifact),
                "componentColorSummaries": [
                    {"componentId": "C1", "colorFamilies": families, "colorFamilyCount": 7},
                ],
                "colorFamilies": families,
                "colorFamilyCount": 7,
                "evidenceSource": "component_pixel_color_aggregation",
                "rating": "不达标",
            }
            errors: list[str] = []
            self.module.require_page_color_component_aggregation(errors, "eval-3/page", row)
            self.assertEqual(errors, [])
            row["colorFamilyCount"] = 6
            row["colorFamilies"] = families[:6]
            row["componentColorSummaries"][0]["colorFamilies"] = families[:6]
            row["componentColorSummaries"][0]["colorFamilyCount"] = 6
            row["rating"] = "达标"
            errors = []
            self.module.require_page_color_component_aggregation(errors, "eval-3/page", row)
        self.assertEqual(errors, [])

    def test_direct_json_skill_rejects_obsolete_measurement(self) -> None:
        row = {
            "evidenceSource": "phase2_json_cross_card_comparison",
            "measurement": {"tool": "obsolete"},
        }
        errors: list[str] = []
        self.module.require_evidence_source(
            errors, "eval-6/page", row, "phase2_json_cross_card_comparison"
        )
        self.assertTrue(any("measurement_forbidden" in error for error in errors))

    def test_single_element_colour_uses_pixel_result_after_json_prefilter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mask = Path(tmp) / "mask.png"
            mask.write_bytes(b"debug")
            row = {
                "elementId": "E1",
                "componentId": "C1",
                "phase2Boundary": [1, 2, 30, 20],
                "sampleMask": str(mask),
                "rawColorGrid": [{"key": "orange", "ratio": 25.0}],
                "colorCount": 1,
                "rating": "优秀",
            }
            errors: list[str] = []
            self.module.require_single_element_color_pixel_evidence(
                errors, "eval-2/E1", row, {"E1": {"coord": [1, 2, 30, 20]}}
            )
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
