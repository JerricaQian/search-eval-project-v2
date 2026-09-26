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

    def test_alignment_reviews_eligible_card_by_information_line_count(self) -> None:
        row = {
            "componentId": "商品卡1",
            "cardVariant": "商品卡片",
            "visibleInformationLineCount": 5,
            "excellentRange": [3, 5],
            "passLineCounts": [6],
            "failRule": "≤2 或 ≥7",
            "evidenceSource": "original_screenshot_visual_review",
            "rating": "优秀",
        }
        errors: list[str] = []
        self.module.require_alignment_line_count_evidence(errors, "eval-2/商品卡1", row)
        self.assertEqual(errors, [])

    def test_alignment_rejects_primary_point_and_heterogeneous_cards(self) -> None:
        row = {
            "componentId": "主点卡1",
            "cardVariant": "主点卡片",
            "visibleInformationLineCount": 4,
            "excellentRange": [3, 5],
            "passLineCounts": [6],
            "failRule": "≤2 或 ≥7",
            "evidenceSource": "original_screenshot_visual_review",
            "rating": "优秀",
        }
        errors: list[str] = []
        self.module.require_alignment_line_count_evidence(errors, "eval-2/主点卡1", row)
        self.assertIn("eval-2/主点卡1:cardVariant_must_be_an_eligible_line_count_card_type", errors)

    def test_alignment_product_and_hotel_two_lines_are_failures(self) -> None:
        row = {
            "componentId": "酒店卡1",
            "cardVariant": "酒店卡片",
            "visibleInformationLineCount": 2,
            "excellentRange": [3, 5],
            "passLineCounts": [6],
            "failRule": "≤2 或 ≥7",
            "evidenceSource": "original_screenshot_visual_review",
            "rating": "不达标",
        }
        errors: list[str] = []
        self.module.require_alignment_line_count_evidence(errors, "eval-2/酒店卡1", row)
        self.assertEqual(errors, [])

    def test_page_alignment_one_result_card_style_is_excellent(self) -> None:
        row = {
            "sourceCardIds": ["C1", "C2"],
            "cardTypeInventory": [{
                "cardTypeCode": "商家卡片_文字下挂",
                "cardTypeName": "商家卡片-文字下挂",
                "cardIds": ["C1", "C2"],
            }],
            "distinctCardTypeCodes": ["商家卡片_文字下挂"],
            "distinctCardStyleCount": 1,
            "countRule": "1=优秀; 2=达标; >2=不达标",
            "evidenceSource": "phase2_json_card_type_inventory",
            "rating": "优秀",
        }
        errors: list[str] = []
        self.module.require_page_card_style_count_evidence(errors, "page-eval-2", row)
        self.assertEqual(errors, [])

    def test_page_alignment_two_result_card_styles_is_pass(self) -> None:
        row = {
            "sourceCardIds": ["C1", "C2", "C3"],
            "cardTypeInventory": [
                {"cardTypeCode": "商家卡片_文字下挂", "cardTypeName": "商家卡片-文字下挂", "cardIds": ["C1", "C2"]},
                {"cardTypeCode": "商家卡片_图文下挂", "cardTypeName": "商家卡片-图文下挂", "cardIds": ["C3"]},
            ],
            "distinctCardTypeCodes": ["商家卡片_文字下挂", "商家卡片_图文下挂"],
            "distinctCardStyleCount": 2,
            "countRule": "1=优秀; 2=达标; >2=不达标",
            "evidenceSource": "phase2_json_card_type_inventory",
            "rating": "达标",
        }
        errors: list[str] = []
        self.module.require_page_card_style_count_evidence(errors, "page-eval-2", row)
        self.assertEqual(errors, [])

    def test_page_alignment_more_than_two_styles_is_fail(self) -> None:
        row = {
            "sourceCardIds": ["C1", "C2", "C3"],
            "cardTypeInventory": [
                {"cardTypeCode": "A", "cardTypeName": "样式A", "cardIds": ["C1"]},
                {"cardTypeCode": "B", "cardTypeName": "样式B", "cardIds": ["C2"]},
                {"cardTypeCode": "C", "cardTypeName": "样式C", "cardIds": ["C3"]},
            ],
            "distinctCardTypeCodes": ["A", "B", "C"],
            "distinctCardStyleCount": 3,
            "countRule": "1=优秀; 2=达标; >2=不达标",
            "evidenceSource": "phase2_json_card_type_inventory",
            "rating": "不达标",
        }
        errors: list[str] = []
        self.module.require_page_card_style_count_evidence(errors, "page-eval-2", row)
        self.assertEqual(errors, [])

    def test_page_alignment_inventory_must_cover_source_cards(self) -> None:
        row = {
            "sourceCardIds": ["C1", "C2"],
            "cardTypeInventory": [
                {"cardTypeCode": "A", "cardTypeName": "样式A", "cardIds": ["C1"]},
            ],
            "distinctCardTypeCodes": ["A"],
            "distinctCardStyleCount": 1,
            "countRule": "1=优秀; 2=达标; >2=不达标",
            "evidenceSource": "phase2_json_card_type_inventory",
            "rating": "优秀",
        }
        errors: list[str] = []
        self.module.require_page_card_style_count_evidence(errors, "page-eval-2", row)
        self.assertIn("page-eval-2:cardTypeInventory_must_cover_sourceCardIds", errors)

    def test_current_page_style_counts_pre_filter_supply_modules(self) -> None:
        row = {
            "sourceCardIds": ["C1"], "sourceModuleIds": ["M1"],
            "excludedModules": [{"moduleId": "M2", "reason": "筛选区"}],
            "styleInventory": [
                {"styleCode": "main_poi_card", "styleName": "主点卡", "cardIds": [], "moduleIds": ["M1"]},
                {"styleCode": "酒店卡片", "styleName": "酒店卡", "cardIds": ["C1"], "moduleIds": []},
            ],
            "distinctStyleCodes": ["main_poi_card", "酒店卡片"],
            "distinctCardStyleCount": 2, "countRule": "1=优秀; 2=达标; >2=不达标",
            "evidenceSource": "phase2_json_page_supply_style_inventory", "rating": "达标",
        }
        errors: list[str] = []
        self.module.require_page_supply_style_inventory_v5_2(errors, "page-eval-2", row)
        self.assertEqual(errors, [])
        row["sourceModuleIds"] = []
        errors = []
        self.module.require_page_supply_style_inventory_v5_2(errors, "page-eval-2", row)
        self.assertIn("page-eval-2:styleInventory_must_partition_sourceModuleIds", errors)

    def test_current_page_color_requires_v5_1_and_six_colors_fail(self) -> None:
        families = ["红", "橙", "黄", "绿", "青", "蓝"]
        row = {
            "colorLogicContractVersion": "5.1",
            "componentColorSummaries": [{
                "componentId": "C1", "colorFamilies": families, "gradientColorValues": [],
                "colorFamilyCount": 6, "scannedElementIds": ["E1"],
                "excludedElementIds": [], "reviewItems": [],
            }],
            "reviewItems": [], "colorFamilies": families,
            "gradientColorValues": [], "gradientContributionCount": 0,
            "colorFamilyCount": 6,
            "evidenceSource": "phase2_json_component_color_aggregation", "rating": "不达标",
        }
        errors: list[str] = []
        self.module.require_page_color_component_aggregation_v5_1(errors, "page-eval-3", row)
        self.assertEqual(errors, [])
        row["rating"] = "达标"
        errors = []
        self.module.require_page_color_component_aggregation_v5_1(errors, "page-eval-3", row)
        self.assertIn("page-eval-3:rating_must_be_不达标", errors)

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

    def test_component_colour_is_validated_from_phase2_json_evidence(self) -> None:
        active = {"E1": {"coord": [0, 0, 20, 20]}, "E2": {"coord": [20, 0, 20, 20]}}
        row = {
            "evidenceSource": "phase2_json_color_inventory",
            "scannedElementIds": ["E1"],
            "excludedElementIds": ["E2"],
            "reviewItems": [],
            "sourceColorValues": [
                {"elementId": "E1", "field": "visual.colorRole", "value": "orange", "colorFamily": "橙"}
            ],
            "neutralColorValues": [],
            "colorFamilies": ["橙"],
            "colorFamilyCount": 1,
            "rating": "优秀",
        }
        errors: list[str] = []
        self.module.require_component_color_json_evidence(errors, "eval-3/C1", row, active)
        self.assertEqual(errors, [])

    def test_component_colour_four_families_is_excellent(self) -> None:
        active = {f"E{index}": {"coord": [index * 20, 0, 20, 20]} for index in range(1, 5)}
        families = ["红", "黄", "绿", "蓝"]
        row = {
            "evidenceSource": "phase2_json_color_inventory",
            "scannedElementIds": list(active),
            "excludedElementIds": [],
            "reviewItems": [],
            "sourceColorValues": [
                {"elementId": f"E{index}", "field": "visual.colorRole", "value": value, "colorFamily": family}
                for index, (family, value) in enumerate(zip(families, ("red", "yellow", "green", "blue")), start=1)
            ],
            "neutralColorValues": [],
            "colorFamilies": families,
            "colorFamilyCount": 4,
            "rating": "优秀",
        }
        errors: list[str] = []
        self.module.require_component_color_json_evidence(errors, "eval-3/C4", row, active)
        self.assertEqual(errors, [])
        row["rating"] = "达标"
        self.module.require_component_color_json_evidence(errors, "eval-3/C4", row, active)
        self.assertTrue(any("rating_must_be_优秀" in error for error in errors))

    def test_component_colour_unresolved_json_role_blocks_formal_rating(self) -> None:
        active = {"E1": {"coord": [0, 0, 20, 20]}}
        row = {
            "evidenceSource": "phase2_json_color_inventory",
            "scannedElementIds": [],
            "excludedElementIds": [],
            "reviewItems": [{"elementId": "E1", "reason": "visual.colorRole=unknown"}],
            "sourceColorValues": [],
            "neutralColorValues": [],
            "colorFamilies": [],
            "colorFamilyCount": 0,
            "rating": "优秀",
        }
        errors: list[str] = []
        self.module.require_component_color_json_evidence(errors, "eval-3/C1", row, active)
        self.assertIn("eval-3/C1:unresolved_color_roles_block_formal_rating", errors)

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
        row = {
            "colorLogicContractVersion": "5.0",
            "componentColorSummaries": [
                {"componentId": "C1", "colorFamilies": ["红", "黄", "蓝"], "colorFamilyCount": 3, "scannedElementIds": ["E1"], "excludedElementIds": [], "reviewItems": []},
                {"componentId": "C2", "colorFamilies": ["橙", "绿", "蓝"], "colorFamilyCount": 3, "scannedElementIds": ["E2"], "excludedElementIds": [], "reviewItems": []},
            ],
            "reviewItems": [],
            "colorFamilies": ["红", "橙", "黄", "绿", "蓝"],
            "colorFamilyCount": 5,
            "evidenceSource": "phase2_json_component_color_aggregation",
            "rating": "优秀",
        }
        errors: list[str] = []
        self.module.require_page_color_component_aggregation(errors, "eval-3/page", row)
        self.assertEqual(errors, [])

    def test_page_colour_thresholds_are_five_six_and_seven(self) -> None:
        families = ["红", "橙", "黄", "绿", "青", "蓝", "紫"]
        row = {
            "colorLogicContractVersion": "5.0",
            "componentColorSummaries": [
                {"componentId": "C1", "colorFamilies": families, "colorFamilyCount": 7, "scannedElementIds": ["E1"], "excludedElementIds": [], "reviewItems": []},
            ],
            "reviewItems": [],
            "colorFamilies": families,
            "colorFamilyCount": 7,
            "evidenceSource": "phase2_json_component_color_aggregation",
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
