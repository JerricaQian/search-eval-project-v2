from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_DIR / "phase3-evaluation" / "dimensions" / "card-component" / "scripts" / "extract_phase3_relation_candidates.py"


def load_module():
    sys.path.insert(0, str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("extract_phase3_relation_candidates_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def item(element_id: str, text: str, role: str, element_type: str = "文本") -> dict:
    return {
        "id": element_id, "元素类型": element_type, "内容简述": f"原文:{text}", "坐标": [0, 0, 10, 10],
        "isExcluded": False, "render": {"visibleStatus": "confirmed"},
        "visual": {"visualStatus": "confirmed"}, "textFacts": {"rawText": text, "semanticRole": role},
    }


class ExtractPhase3RelationCandidatesTest(unittest.TestCase):
    def test_phase3_enumerates_pairs_without_phase2_relation_results(self) -> None:
        module = load_module()
        manifest = {"query": "q", "relations": [], "cards": [{
            "cardId": "C1", "regions": [
                {"name": "标题区", "elements": [item("T", "门店A", "title"), item("A", "可退", "benefit")]},
                {"name": "下挂商品区", "elements": [item("I", "", "image", "图片"), item("B", "可退", "benefit")]},
            ],
        }]}
        result = module.derive_relation_candidates(manifest)
        self.assertEqual(len(result["authenticityCandidates"][0]["candidatePairs"]), 2)
        pairs = result["redundancyCandidates"][0]["candidatePairs"]
        self.assertTrue(any({pair["left"]["elementId"], pair["right"]["elementId"]} == {"A", "B"} for pair in pairs))
        self.assertTrue(all(pair["phase3JudgementRequired"] for pair in pairs))

    def test_title_size_is_an_authenticity_candidate(self) -> None:
        module = load_module()
        manifest = {"query": "安睡裤", "cards": [{
            "cardId": "C3", "regions": [
                {"name": "标题区", "elements": [item("T", "安睡裤M-L码", "title")]},
                {"name": "基础信息区", "elements": [item("S", "M", "size")]},
            ],
        }]}
        result = module.derive_relation_candidates(manifest)
        pairs = result["authenticityCandidates"][0]["candidatePairs"]
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["relationType"], "title_to_size")
        self.assertEqual(pairs[0]["target"]["elementId"], "S")

    def test_range_cap_and_mixed_price_semantics_are_authenticity_candidates(self) -> None:
        module = load_module()
        manifest = {"query": "榴莲", "cards": [{
            "cardId": "C2", "regions": [
                {"name": "标题区", "elements": [item("T", "金枕榴莲3-6斤", "title")]},
                {"name": "基础信息区", "elements": [item("B", "约2kg以下", "other")]},
                {"name": "价格区", "elements": [item("P", "¥24.9起 到手价/每瓶¥4.15", "price")]},
            ],
        }]}
        result = module.derive_relation_candidates(manifest)
        authenticity = result["authenticityCandidates"][0]
        self.assertTrue(any(pair["target"]["elementId"] == "B" for pair in authenticity["candidatePairs"]))
        cues = {candidate["lexicalCue"] for candidate in authenticity["internalCandidates"]}
        self.assertIn("quantity_range_exceeds_card_cap", cues)
        self.assertIn("start_price_and_to_hand_price_in_same_claim", cues)

    def test_title_self_repeat_is_retained_for_redundancy_review(self) -> None:
        module = load_module()
        manifest = {"query": "榴莲", "cards": [{
            "cardId": "C3", "regions": [
                {"name": "标题区", "elements": [item("T", "榴莲3-4斤 金枕榴莲3-4斤", "title")]},
            ],
        }]}
        result = module.derive_relation_candidates(manifest)
        repeats = result["redundancyCandidates"][0]["selfRepeatCandidates"]
        self.assertEqual(repeats[0]["repeatedFragment"], "3-4斤")
        self.assertEqual(repeats[0]["occurrences"], 2)

    def test_semantic_aliases_create_candidates_across_fields_and_inside_title(self) -> None:
        module = load_module()
        manifest = {"query": "酸奶", "cards": [{
            "cardId": "C4", "regions": [
                {"name": "标题区", "elements": [item("T", "无蔗糖 0添加蔗糖酸奶", "title")]},
                {"name": "标签区", "elements": [item("B", "零添加蔗糖", "benefit")]},
            ],
        }]}
        result = module.derive_relation_candidates(manifest)
        redundancy = result["redundancyCandidates"][0]
        self.assertTrue(any(pair["lexicalCue"] == "semantic_alias_overlap" for pair in redundancy["candidatePairs"]))
        self.assertTrue(any(item["lexicalCue"] == "title_internal_semantic_alias_repeat" for item in redundancy["selfRepeatCandidates"]))
        self.assertEqual(result["contractVersion"], "phase3.relation-candidates.v4")

    def test_requested_semantic_cues_receive_deterministic_verdicts(self) -> None:
        module = load_module()
        manifest = {"query": "啤酒", "cards": [{
            "cardId": "C1", "regions": [
                {"name": "标题区", "elements": [item("T", "泰山原浆啤酒10度7天新鲜", "title")]},
                {"name": "基础信息区", "elements": [item("B", "麦汁浓度:10P", "product_attribute")]},
                {"name": "价格区", "elements": [item("P", "￥24.9起到手价", "price")]},
            ],
        }]}
        result = module.derive_relation_candidates(manifest)
        duplicate = next(
            module.adjudicate_redundancy_candidate(candidate)
            for candidate in result["redundancyCandidates"][0]["candidatePairs"]
            if candidate["lexicalCue"] == "same_numeric_attribute"
        )
        conflict = module.adjudicate_authenticity_candidate(
            result["authenticityCandidates"][0]["internalCandidates"][0]
        )
        self.assertEqual(duplicate["verdict"], "duplicate")
        self.assertEqual(duplicate["normalizedFact"], "麦汁浓度=10P")
        self.assertEqual(conflict["verdict"], "conflict")

    def test_generic_containment_never_becomes_automatic_redundancy(self) -> None:
        module = load_module()
        candidate = {
            "left": {"elementId": "A", "text": "可退", "semanticRole": "benefit"},
            "right": {"elementId": "B", "text": "随时可退", "semanticRole": "benefit"},
            "lexicalCue": "containment",
        }
        self.assertIsNone(module.adjudicate_redundancy_candidate(candidate))

    def test_range_conflict_and_title_self_repeat_receive_verdicts(self) -> None:
        module = load_module()
        range_candidate = {
            "left": {"elementId": "T", "text": "榴莲3-6斤", "semanticRole": "title"},
            "right": {"elementId": "B", "text": "约2kg以下", "semanticRole": "product_attribute"},
            "lexicalCue": "quantity_range_exceeds_card_cap",
            "normalizedTitleRangeKg": [1.5, 3.0], "normalizedCapKg": 2.0,
        }
        repeat_candidate = {
            "element": {"elementId": "T", "text": "榴莲3-4斤 金枕榴莲3-4斤"},
            "lexicalCue": "title_internal_repeated_quantified_fragment",
            "repeatedFragment": "3-4斤", "occurrences": 2,
        }
        self.assertEqual(module.adjudicate_authenticity_candidate(range_candidate)["verdict"], "conflict")
        self.assertEqual(module.adjudicate_self_repeat_candidate(repeat_candidate)["verdict"], "duplicate")

    def test_same_visible_merchant_identity_with_conflicting_facts_is_detected(self) -> None:
        module = load_module()
        manifest = {"query": "盒马", "cards": [
            {"cardId": "C1", "卡片类型": "商家卡片-图文下挂", "regions": [
                {"name": "title", "elements": [item("C1-T", "盒马鲜生代购（望京广顺北大街）", "title")]},
                {"name": "merchant_info", "elements": [
                    item("C1-R", "4.6分", "rating"), item("C1-S", "月售900+起送¥0", "fulfillment"), item("C1-D", "2.2km", "fulfillment"),
                ]},
            ]},
            {"cardId": "C3", "卡片类型": "商家卡片-图文下挂", "regions": [
                {"name": "title", "elements": [item("C3-T", "盒马鲜生代购（望京广顺北大街）", "title")]},
                {"name": "merchant_info", "elements": [
                    item("C3-R", "4.8分", "rating"), item("C3-S", "月售70+", "sales"), item("C3-D", "2.3km", "fulfillment"),
                ]},
            ]},
        ]}
        result = module.derive_relation_candidates(manifest)
        candidate = result["crossCardAuthenticityCandidates"][0]
        verdict = module.adjudicate_authenticity_candidate(candidate)
        self.assertEqual(verdict["verdict"], "conflict")
        self.assertEqual({fact["factName"] for fact in verdict["conflictingFacts"]}, {"评分", "月售", "距离"})


if __name__ == "__main__":
    unittest.main()
