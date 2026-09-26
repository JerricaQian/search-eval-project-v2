import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "phase2-card-annotation" / "scripts"))
from semantic_ownership import audit_semantic_ownership  # noqa: E402
sys.path.pop(0)


def fixture():
    card = {
        "cardId": "C1", "卡片类型": "酒店卡片", "coord": [0, 250, 400, 220],
        "structure": {"isResultListItem": True, "listPosition": 1}, "regions": [],
    }
    modules = [
        {"id": "M1", "moduleType": "search_bar", "coord": [0, 0, 400, 50]},
        {"id": "M2", "moduleType": "tab", "coord": [0, 60, 400, 50]},
        {"id": "M3", "moduleType": "sort_filter", "coord": [0, 120, 400, 50]},
        {"id": "M4", "moduleType": "result_list", "coord": [0, 250, 400, 220]},
    ]
    manifest = {"screenshot": "/tmp/ownership-example.png", "cards": [card], "pageFacts": {"modules": modules}}
    review = {"screenshot": manifest["screenshot"], "completeCurrentPixelReview": True,
              "cards": [{"cardId": "C1", "topology": {"regions": [], "attachedItems": []}}],
              "modules": [{"moduleType": "search_bar", "coord": [0, 0, 400, 50]},
                          {"moduleType": "tab_bar", "coord": [0, 60, 400, 50]},
                          {"moduleType": "sort_filter", "coord": [0, 120, 400, 50]}]}
    return manifest, review


class SemanticOwnershipTests(unittest.TestCase):
    def test_independent_page_tab_and_result_card_pass(self):
        manifest, review = fixture()
        self.assertTrue(audit_semantic_ownership(manifest, review)["valid"])

    def test_card_internal_row_cannot_be_page_tab(self):
        manifest, review = fixture()
        manifest["pageFacts"]["modules"][1]["coord"] = [20, 300, 360, 35]
        review["modules"][1]["coord"] = [20, 300, 360, 35]
        errors = audit_semantic_ownership(manifest, review)["errors"]
        self.assertIn("page_module_owned_by_result_card:tab:C1", errors)

    def test_result_list_must_substantially_cover_each_list_card(self):
        manifest, review = fixture()
        manifest["pageFacts"]["modules"][3]["coord"] = [0, 410, 400, 60]
        self.assertIn("result_list_does_not_own_card:C1",
                      audit_semantic_ownership(manifest, review)["errors"])

    def test_small_result_list_boundary_difference_does_not_block(self):
        manifest, review = fixture()
        manifest["pageFacts"]["modules"][3]["coord"] = [0, 300, 400, 170]
        self.assertTrue(audit_semantic_ownership(manifest, review)["valid"])

    def test_reviewed_module_boundary_shift_is_same_instance(self):
        manifest, review = fixture()
        review["modules"][1]["coord"] = [8, 62, 384, 48]
        self.assertTrue(audit_semantic_ownership(manifest, review)["valid"])

    def test_published_cv_module_cannot_bypass_complete_review(self):
        manifest, review = fixture()
        manifest["pageFacts"]["modules"].append({
            "id": "M5", "moduleType": "tip_strip", "coord": [0, 185, 400, 50],
        })
        self.assertIn("published_page_module_not_in_review:tip_strip",
                      audit_semantic_ownership(manifest, review)["errors"])

    def test_two_column_rows_need_no_false_vertical_order(self):
        manifest, review = fixture()
        second = copy.deepcopy(manifest["cards"][0])
        manifest["cards"][0]["coord"] = [0, 250, 190, 220]
        second["cardId"] = "C2"
        second["coord"] = [210, 255, 190, 220]
        second["structure"]["listPosition"] = 2
        manifest["cards"].append(second)
        review["cards"].append({"cardId": "C2", "topology": {"regions": [], "attachedItems": []}})
        self.assertTrue(audit_semantic_ownership(manifest, review)["valid"])

    def test_hotel_result_cannot_also_be_pre_results_main_point(self):
        manifest, review = fixture()
        manifest["pageFacts"]["modules"].append({
            "id": "M5", "moduleType": "main_poi_card", "coord": [0, 250, 400, 220],
        })
        errors = audit_semantic_ownership(manifest, review)["errors"]
        self.assertIn("page_module_owned_by_result_card:main_poi_card:C1", errors)
        self.assertIn("pre_results_module_inside_result_flow:main_poi_card", errors)

    def test_genuine_pre_results_main_point_passes(self):
        manifest, review = fixture()
        manifest["pageFacts"]["modules"].append({
            "id": "M5", "moduleType": "main_poi_card", "coord": [0, 175, 400, 60],
        })
        review["modules"].append({"moduleType": "main_poi_card", "coord": [0, 175, 400, 60]})
        self.assertTrue(audit_semantic_ownership(manifest, review)["valid"])

    def test_vertical_coupon_rows_keep_one_reviewed_item_owner(self):
        manifest, review = fixture()
        manifest["cards"][0]["卡片类型"] = "商家卡片-文字下挂"
        manifest["cards"][0]["coord"] = [0, 250, 400, 300]
        manifest["pageFacts"]["modules"][3]["coord"] = [0, 250, 400, 300]
        atoms = [
            {"id": "C1-T1", "坐标": [60, 320, 140, 30], "元素类型": "文本", "textFacts": {"rawText": "代金券"}},
            {"id": "C1-T2", "坐标": [60, 380, 80, 30], "元素类型": "文本", "textFacts": {"rawText": "¥100"}},
            {"id": "C1-T3", "坐标": [60, 440, 140, 30], "元素类型": "文本", "textFacts": {"rawText": "满120可用"}},
        ]
        manifest["cards"][0]["regions"] = [{
            "name": "文字下挂区", "elements": atoms,
            "itemGroups": [{"itemIndex": 1, "elementIds": [atom["id"] for atom in atoms]}],
        }]
        review["cards"][0]["topology"] = {
            "regions": [{"slot": "text_attachment", "coord": [0, 300, 400, 200]}],
            "attachedItems": [{"itemIndex": 1, "coord": [40, 310, 340, 180]}],
        }
        review["cards"][0]["fields"] = [
            {"coord": atom["坐标"], "text": atom["textFacts"]["rawText"]} for atom in atoms
        ]
        self.assertTrue(audit_semantic_ownership(manifest, review)["valid"])
        split = copy.deepcopy(manifest)
        split["cards"][0]["regions"][0]["itemGroups"] = [
            {"itemIndex": index, "elementIds": [atom["id"]]}
            for index, atom in enumerate(atoms, 1)
        ]
        errors = audit_semantic_ownership(split, review)["errors"]
        self.assertTrue(any(error.startswith("reviewed_item_owner_mismatch") for error in errors))

    def test_unselected_cv_module_is_advisory_not_a_veto(self):
        manifest, review = fixture()
        candidates = {"pageModules": [{"id": "cv-extra", "module": "tip_strip", "coord": [0, 180, 400, 50]}]}
        result = audit_semantic_ownership(manifest, review, candidates)
        self.assertTrue(result["valid"])
        self.assertIn("cv_page_module_not_published:tip_strip", result["warnings"])
        self.assertEqual(result["claimDecisions"][-1]["decision"], "not_selected_by_current_pixel_review")
        review["rejectedModules"] = [{"moduleType": "tip_strip", "coord": [0, 180, 400, 50],
                                      "reason": "current pixels show a card-internal row"}]
        result = audit_semantic_ownership(manifest, review, candidates)
        self.assertTrue(result["valid"])
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["claimDecisions"][-1]["decision"], "rejected_by_current_pixel_review")

    def test_heterogeneous_fallback_requires_positive_current_pixel_evidence(self):
        manifest, review = fixture()
        manifest["cards"][0]["卡片类型"] = "异构卡"
        manifest["cards"][0]["cardTypeCode"] = "异构卡"
        review["cards"][0]["cardTypeCandidate"] = "酒店卡片"
        self.assertIn("heterogeneous_fallback_conflicts_with_reviewed_known_type:C1",
                      audit_semantic_ownership(manifest, review)["errors"])
        review["cards"][0]["cardTypeCandidate"] = "异构卡"
        self.assertIn("heterogeneous_positive_structure_evidence_missing:C1",
                      audit_semantic_ownership(manifest, review)["errors"])
        review["cards"][0]["heterogeneousEvidence"] = {
            "distinctStructure": "independent media, action, and primary-information layout",
            "whyKnownCardTypesFail": ["no hotel title or room/price relation"],
        }
        self.assertTrue(audit_semantic_ownership(manifest, review)["valid"])


if __name__ == "__main__":
    unittest.main()
