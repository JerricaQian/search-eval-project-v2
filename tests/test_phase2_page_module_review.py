import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = str(ROOT / "phase2-card-annotation" / "scripts")
sys.path.insert(0, SCRIPTS)
from build_phase2_manifest import merge_page_modules, reconcile_interstitial_list_modules  # noqa: E402
sys.path.remove(SCRIPTS)


class PageModuleReviewTests(unittest.TestCase):
    def test_explicit_review_inventory_replaces_cv_instances(self):
        cv_modules = [
            {"module": "tab", "coord": [10, 350, 380, 40], "status": "confirmed", "evidence": ["text_row"]},
            {"module": "banner", "coord": [0, 280, 400, 50], "status": "confirmed", "evidence": ["promo"]},
        ]
        review_modules = [
            {"moduleType": "tab", "coord": [0, 80, 400, 55], "visibleStatus": "confirmed",
             "contentRole": "心智Tab", "isListPrefix": True},
        ]
        modules = merge_page_modules(cv_modules, review_modules)
        self.assertEqual([(item["moduleType"], item["coord"]) for item in modules], [
            ("tab", [0, 80, 400, 55]),
        ])
        self.assertEqual([item["id"] for item in modules], ["M1"])
        self.assertEqual(modules[0]["contentRole"], "心智Tab")

    def test_same_bounds_uses_review_metadata_once(self):
        cv_modules = [{"module": "tab", "coord": [0, 80, 400, 55], "status": "uncertain"}]
        review_modules = [{"moduleType": "tab", "coord": [0, 80, 400, 55],
                           "visibleStatus": "confirmed", "contentRole": "心智Tab"}]
        modules = merge_page_modules(cv_modules, review_modules)
        self.assertEqual(len(modules), 1)
        self.assertEqual(modules[0]["visibleStatus"], "confirmed")
        self.assertEqual(modules[0]["contentRole"], "心智Tab")

    def test_explicit_empty_review_excludes_cv_only_modules(self):
        cv_modules = [{"module": "tab", "coord": [0, 80, 400, 55], "status": "confirmed",
                       "evidence": ["text_row"]}]
        self.assertEqual(merge_page_modules(cv_modules, []), [])
        self.assertEqual([(item["moduleType"], item["coord"]) for item in merge_page_modules(cv_modules, None)],
                         [("tab", [0, 80, 400, 55])])

    def test_reviewed_list_owns_alias_and_suppresses_derived_list(self):
        cv_modules = [{"module": "results_list", "coord": [0, 300, 400, 400], "status": "confirmed"}]
        review_modules = [{"moduleType": "result_list", "coord": [0, 260, 400, 440],
                           "visibleStatus": "confirmed", "contentRole": "复核结果列表"}]
        derived = {"moduleType": "result_list", "coord": [0, 320, 400, 380],
                   "visibleStatus": "confirmed", "contentRole": "结果供给",
                   "isListPrefix": False, "isListItem": False}
        modules = merge_page_modules(cv_modules, review_modules, derived)
        self.assertEqual(len(modules), 1)
        self.assertEqual(modules[0]["moduleType"], "result_list")
        self.assertEqual(modules[0]["coord"], [0, 260, 400, 440])
        self.assertEqual(modules[0]["contentRole"], "复核结果列表")
        self.assertFalse(modules[0]["isListPrefix"])

    def test_derived_list_owns_cv_alias_when_cards_exist(self):
        cv_modules = [{"module": "results_list", "coord": [0, 300, 400, 400], "status": "confirmed"}]
        derived = {"moduleType": "result_list", "coord": [0, 320, 400, 380],
                   "visibleStatus": "confirmed", "contentRole": "结果供给",
                   "isListPrefix": False, "isListItem": False}
        modules = merge_page_modules(cv_modules, [], derived)
        self.assertEqual(len(modules), 1)
        self.assertEqual(modules[0]["coord"], [0, 320, 400, 380])
        self.assertEqual(merge_page_modules(cv_modules, None)[0]["coord"], [0, 300, 400, 400])

    def test_review_aliases_replace_cv_core_modules(self):
        cv_modules = [
            {"module": "search_bar", "coord": [0, 50, 400, 50], "status": "confirmed"},
            {"module": "tab", "coord": [0, 110, 400, 50], "status": "confirmed"},
            {"module": "sort_filter", "coord": [0, 170, 400, 50], "status": "confirmed"},
        ]
        review = [
            {"moduleType": "search_box", "coord": [10, 50, 380, 50], "visibleStatus": "confirmed"},
            {"moduleType": "tab_bar", "coord": [0, 110, 400, 50], "visibleStatus": "confirmed"},
            {"moduleType": "filter_sort", "coord": [0, 170, 400, 50], "visibleStatus": "confirmed"},
        ]
        modules = merge_page_modules(cv_modules, review)
        self.assertEqual([item["moduleType"] for item in modules], ["search_bar", "tab", "sort_filter"])
        self.assertEqual(modules[0]["coord"], [10, 50, 380, 50])

    def test_cv_main_poi_same_as_result_below_filter_is_suppressed(self):
        cv_modules = [{"module": "main_poi_card", "coord": [0, 230, 400, 180], "status": "confirmed"}]
        review = [{"moduleType": "sort_filter", "coord": [0, 170, 400, 50], "visibleStatus": "confirmed"}]
        cards = [{"coord": [0, 225, 400, 180], "卡片类型": "酒店卡片",
                  "structure": {"isResultListItem": True}}]
        modules = merge_page_modules(cv_modules, review, result_cards=cards)
        self.assertEqual([item["moduleType"] for item in modules], ["sort_filter"])
        above = [{**cv_modules[0], "coord": [0, 10, 400, 150]}]
        self.assertNotIn("main_poi_card", [item["moduleType"] for item in merge_page_modules(above, review, result_cards=cards)])
        confirmed_review = review + [{"moduleType": "main_poi_card", "coord": above[0]["coord"],
                                      "visibleStatus": "confirmed"}]
        self.assertIn("main_poi_card", [item["moduleType"] for item in merge_page_modules(above, confirmed_review, result_cards=cards)])

    def test_related_search_between_results_gets_one_list_position(self):
        cards = [
            {"coord": [0, 230, 400, 180], "structure": {"isResultListItem": True, "listPosition": 1}},
            {"coord": [0, 610, 400, 180], "structure": {"isResultListItem": True, "listPosition": 2}},
        ]
        modules = [
            {"moduleType": "sort_filter", "coord": [0, 170, 400, 50], "visibleStatus": "confirmed"},
            {"moduleType": "related_search", "coord": [0, 430, 400, 150], "visibleStatus": "confirmed", "isListItem": False},
            {"moduleType": "related_search", "coord": [0, 810, 400, 100], "visibleStatus": "confirmed", "isListItem": False},
        ]
        reconcile_interstitial_list_modules(modules, cards)
        self.assertEqual(modules[1]["listPosition"], 2)
        self.assertTrue(modules[1]["isListItem"])
        self.assertFalse(modules[2]["isListItem"])
        self.assertEqual([card["structure"]["listPosition"] for card in cards], [1, 3])

    def test_explicitly_rejected_cv_module_is_not_published(self):
        cv_modules = [{"module": "tab", "coord": [20, 300, 360, 35], "status": "confirmed"}]
        rejected = [{"moduleType": "tab_bar", "coord": [20, 300, 360, 35],
                     "reason": "card-owned metric row"}]
        self.assertEqual(merge_page_modules(cv_modules, [], rejected_modules=rejected), [])


if __name__ == "__main__":
    unittest.main()
