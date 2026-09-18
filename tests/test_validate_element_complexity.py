from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_DIR / "scripts" / "validate_eval_results.py"


def load_module():
    sys.path.insert(0, str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("validate_eval_results_complexity_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


class ValidateElementComplexityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()
        self.ledger = [
            {
                "elementId": "E1",
                "region": "rating_and_reason",
                "content": "服务很好非常喜欢",
                "decision": "included_tag",
                "reason": "无容器彩色辅助文字",
                "styleKey": "tag|orange|recommendation|none|none",
            },
            {
                "elementId": "E2",
                "region": "price",
                "content": "¥375起",
                "decision": "excluded",
                "reason": "主价格不是标签",
            },
        ]
    def valid_row(self) -> dict:
        return {
            "componentId": "C1",
            "expectedRegions": ["rating_and_reason", "price"],
            "scannedRegions": ["rating_and_reason", "price"],
            "unscannedRegions": [],
            "scannedElementIds": ["E1", "E2"],
            "candidateLedger": self.ledger,
            "phase2ReviewCandidates": [],
            "coverageStatus": "completed",
            "evidenceSource": "phase2_json_visual_inventory",
            "includedTagStyles": [{
                "elementIds": ["E1"],
                "content": "服务很好非常喜欢",
                "styleKey": "tag|orange|recommendation|none|none",
                "countDecision": "计入",
                "dedupDecision": "逐实例计入（不去重）",
            }],
        }

    @staticmethod
    def active_elements() -> dict[str, dict]:
        return {
            "E1": {
                "id": "E1", "content": "原文:服务很好非常喜欢",
                "semanticRole": "recommendation", "promotionPrefix": "",
                "colorRole": "orange", "entityKind": "text", "isPhoto": False,
            },
            "E2": {
                "id": "E2", "content": "原文:¥375起",
                "semanticRole": "price", "promotionPrefix": "",
                "colorRole": "red", "entityKind": "text", "isPhoto": False,
            },
        }

    def test_complete_whole_card_coverage_is_directly_auditable(self) -> None:
        errors: list[str] = []
        self.module.require_complexity_coverage(errors, "eval-4/C1", self.valid_row())
        self.assertEqual(errors, [])

    def test_json_derived_complexity_rejects_measurement(self) -> None:
        row = self.valid_row()
        row["measurement"] = {"tool": "obsolete"}
        errors: list[str] = []
        self.module.require_evidence_source(
            errors, "eval-4/C1", row, "phase2_json_visual_inventory"
        )
        self.assertTrue(any("measurement_forbidden" in error for error in errors))

    def test_missing_region_is_rejected(self) -> None:
        row = self.valid_row()
        row["scannedRegions"] = ["price"]
        errors: list[str] = []
        self.module.require_complexity_coverage(errors, "eval-4/C1", row)
        self.assertTrue(any("scannedRegions_must_cover_expectedRegions" in error for error in errors))

    def test_phase2_review_candidate_blocks_formal_rating(self) -> None:
        row = self.valid_row()
        row["phase2ReviewCandidates"] = [{"coord": [0, 0, 20, 20]}]
        errors: list[str] = []
        self.module.require_complexity_coverage(errors, "eval-4/C1", row)
        self.assertTrue(any("phase2_review_required_blocks_formal_rating" in error for error in errors))

    def test_repeated_style_keys_are_counted_as_separate_tag_instances(self) -> None:
        row = self.valid_row()
        repeated = {
            "elementId": "E3",
            "region": "rating_and_reason",
            "content": "服务很好非常喜欢",
            "decision": "included_tag",
            "reason": "无容器彩色辅助文字",
            "styleKey": "tag|orange|recommendation|none|none",
        }
        row["candidateLedger"].append(repeated)
        row["scannedElementIds"].append("E3")
        row["includedTagStyles"].append({
            "elementIds": ["E3"],
            "content": "服务很好非常喜欢",
            "styleKey": "tag|orange|recommendation|none|none",
            "countDecision": "计入",
            "dedupDecision": "逐实例计入（不去重）",
        })
        errors: list[str] = []
        self.module.require_complexity_coverage(errors, "eval-4/C1", row)
        self.assertEqual(errors, [])

    def test_one_tag_instance_may_group_multiple_atoms(self) -> None:
        row = self.valid_row()
        grouped_atom = {
            "elementId": "E3",
            "region": "rating_and_reason",
            "content": "满38可用",
            "decision": "included_tag",
            "reason": "组合优惠标签的组成原子",
            "styleKey": "tag|orange|recommendation|none|none",
        }
        row["candidateLedger"].append(grouped_atom)
        row["scannedElementIds"].append("E3")
        row["includedTagStyles"][0]["elementIds"] = ["E1", "E3"]
        row["includedTagStyles"][0]["groupingDecision"] = "同一组合优惠标签，计 1 个实例"
        errors: list[str] = []
        self.module.require_complexity_coverage(errors, "eval-4/C1", row)
        self.assertEqual(errors, [])

    def test_colored_special_offer_cannot_use_generic_text_exclusion(self) -> None:
        row = self.valid_row()
        row["candidateLedger"][0].update({
            "content": "特价团", "decision": "excluded", "reason": "当前原子为内容文字或图片",
        })
        row["includedTagStyles"] = []
        active = self.active_elements()
        active["E1"].update({"content": "原文:特价团", "semanticRole": "promotion", "colorRole": "red"})
        errors: list[str] = []

        self.module.require_complexity_coverage(errors, "eval-4/C1", row, active)

        self.assertTrue(any("generic_exclusion_reason_forbidden" in error for error in errors))
        self.assertTrue(any("colored_promotion_must_be_included_tag" in error for error in errors))

    def test_embedded_shenqiangshou_counts_prefix_only(self) -> None:
        row = self.valid_row()
        row["candidateLedger"][0].update({
            "content": "【神抢手】精选双人餐",
            "styleKey": "tag|red|promotion|none|none",
        })
        row["includedTagStyles"][0].update({
            "content": "【神抢手】精选双人餐",
            "styleKey": "tag|red|promotion|none|none",
        })
        active = self.active_elements()
        active["E1"].update({
            "content": "原文:【神抢手】精选双人餐", "semanticRole": "attachment",
            "promotionPrefix": "【神抢手】", "colorRole": "neutral",
        })
        errors: list[str] = []

        self.module.require_complexity_coverage(errors, "eval-4/C1", row, active)

        self.assertTrue(any("content_must_equal_promotionPrefix" in error for error in errors))

        row["includedTagStyles"][0]["content"] = "【神抢手】"
        errors = []
        self.module.require_complexity_coverage(errors, "eval-4/C1", row, active)
        self.assertEqual(errors, [])

    def test_fulfillment_semantics_outrank_colored_tag_style(self) -> None:
        row = self.valid_row()
        active = self.active_elements()
        active["E1"].update({"content": "原文:闪购", "semanticRole": "fulfillment", "colorRole": "yellow"})
        errors: list[str] = []

        self.module.require_complexity_coverage(errors, "eval-4/C1", row, active)

        self.assertTrue(any("fulfillment_must_be_excluded" in error for error in errors))

    def test_revised_complexity_thresholds(self) -> None:
        self.assertEqual(self.module.complexity_rating(4, 1), "优秀")
        self.assertEqual(self.module.complexity_rating(5, 0), "达标")
        self.assertEqual(self.module.complexity_rating(6, 1), "达标")
        self.assertEqual(self.module.complexity_rating(4, 2), "达标")
        self.assertEqual(self.module.complexity_rating(7, 0), "不达标")
        self.assertEqual(self.module.complexity_rating(0, 4), "不达标")



if __name__ == "__main__":
    unittest.main()
