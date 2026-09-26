import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = str(ROOT / "phase2-card-annotation" / "scripts")
sys.path.insert(0, SCRIPTS)

from apply_visual_review import apply  # noqa: E402
from build_phase2_manifest import append_item_groups, card_local_semantics  # noqa: E402
from build_search_result_candidates import _module_candidates, _repeated_merchant_head_cards, build_candidates  # noqa: E402
from card_contract_engine import extract_features, title_semantic_family  # noqa: E402
from card_type_registry import load_registry, validate_phase2_taxonomy  # noqa: E402
from map_result_card_semantics import map_cards  # noqa: E402
from run_phase2_recognition import merge_reviewed_card_boundaries, run, sha256_file, validate_candidate_bundle, validate_cv_llm_visual_review  # noqa: E402
from validate_phase2_recognition import gate  # noqa: E402
from validate_element_manifest import text_downhang_has_inline_price  # noqa: E402
from phase2_contract import STRUCTURE_BLUEPRINTS, card_contract, golden_structure_examples, merchant_variant, registered_card_types, review_topology_slots, structure_blueprint, topology_errors  # noqa: E402
from build_phase2_retry_plan import build as build_retry_plan  # noqa: E402

sys.path.remove(SCRIPTS)


class CvLlmTopologyTests(unittest.TestCase):
    def test_reviewed_list_boundary_excludes_pre_results_card_seed(self):
        facts = {
            "contractVersion": "phase2.cv-facts.v1", "screenshot": "/tmp/page.png",
            "viewport": {"width": 400, "height": 800},
            "candidates": {"text": [], "photos": []},
            "routing": {"visualReview": {"modules": [
                {"moduleType": "sort_filter", "coord": [0, 260, 400, 40], "visibleStatus": "confirmed"},
                {"moduleType": "result_list", "coord": [0, 320, 400, 480], "visibleStatus": "confirmed"},
            ]}},
        }
        structure = {"contractVersion": "phase2.search-page-structure.v1", "blocks": [
            {"id": "B1", "coord": [0, 100, 400, 150], "layoutCandidate": "left_image_right_text", "confidence": 0.9},
            {"id": "B2", "coord": [0, 350, 400, 170], "layoutCandidate": "left_image_right_text", "confidence": 0.9},
        ]}
        result = build_candidates(facts, structure)
        self.assertEqual([card["seedBlockId"] for card in result["resultCards"]], ["B2"])

    def test_review_cannot_reinsert_a_pre_results_module_as_result_card(self):
        with tempfile.TemporaryDirectory() as temp:
            review_path = Path(temp) / "review.json"
            review_path.write_text(json.dumps({
                "completeCurrentPixelReview": True,
                "modules": [{"moduleType": "result_list", "coord": [0, 320, 400, 300], "visibleStatus": "confirmed"}],
                "cards": [{
                    "cardId": "C1", "coord": [0, 100, 400, 160], "cardTypeCandidate": "商品卡片",
                    "topology": {"regions": [
                        {"slot": "head_media", "coord": [0, 100, 100, 100]},
                        {"slot": "title", "coord": [110, 100, 200, 30]},
                        {"slot": "price", "coord": [110, 170, 100, 30]},
                    ], "attachedItems": []},
                }],
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "reviewed_result_card_before_confirmed_result_list"):
                validate_cv_llm_visual_review(review_path)

    def test_pre_results_main_point_uses_title_before_block_content(self):
        facts = {"viewport": {"width": 400, "height": 600}, "candidates": {
            "text": [
                {"id": "T1", "text": "北京大学", "coord": [145, 155, 190, 30], "route": "accepted"},
                {"id": "T2", "text": "校园地址与简介", "coord": [145, 275, 190, 25], "route": "accepted"},
                {"id": "T3", "text": "综合排序", "coord": [40, 405, 110, 30], "route": "accepted"},
            ], "photos": [{"id": "P1", "coord": [20, 175, 100, 100], "route": "accepted"}],
        }}
        structure = {"blocks": [
            {"id": "B1", "coord": [0, 140, 400, 180], "layoutCandidate": "left_image_right_text"},
            {"id": "B2", "coord": [0, 390, 400, 50], "layoutCandidate": "text_only"},
        ]}
        modules = _module_candidates(facts, structure)
        self.assertIn("main_poi_card", [module["module"] for module in modules])

    def test_title_semantics_uses_owned_title_not_promotions_or_query(self):
        card = {"id": "C2", "coord": [0, 100, 400, 230]}
        facts = {"candidates": {"text": [
            {"id": "T1", "text": "季枫国际酒店(古城地铁站店)", "coord": [120, 110, 260, 35], "route": "accepted",
             "visualReview": {"cardId": "C2", "role": "title", "topologySlot": "title"}},
            {"id": "T2", "text": "30天低价｜立减186", "coord": [120, 270, 200, 25], "route": "accepted",
             "visualReview": {"cardId": "C2", "role": "promotion", "topologySlot": "tag"}},
            {"id": "T3", "text": "电影《错位》", "coord": [120, 110, 200, 25], "route": "accepted",
             "visualReview": {"cardId": "C1", "role": "title", "topologySlot": "title"}},
        ]}}
        self.assertEqual(title_semantic_family(card, facts)["family"], "酒店卡片")
        self.assertEqual(title_semantic_family(card, facts)["sourceId"], "T1")
        facts["candidates"]["text"][0]["text"] = "酒店用品收纳盒"
        self.assertEqual(title_semantic_family(card, facts)["family"], "")

    def test_hotel_title_outweighs_promotion_duration_and_product_shape(self):
        references = ROOT / "phase2-card-annotation" / "references"
        load = lambda name: json.loads((references / name).read_text(encoding="utf-8"))
        facts = {"contractVersion": "phase2.cv-facts.v1", "screenshot": "/tmp/hotel.png", "viewport": {"width": 400, "height": 600}, "candidates": {
            "photos": [{"id": "P1", "coord": [10, 110, 90, 140], "route": "accepted"}],
            "text": [
                {"id": "T1", "text": "季枫国际酒店(古城地铁站店)", "coord": [120, 110, 260, 34], "route": "accepted",
                 "visualReview": {"cardId": "C1", "role": "title", "topologySlot": "title"}},
                {"id": "T2", "text": "¥219起", "coord": [270, 200, 100, 25], "route": "accepted",
                 "visualReview": {"cardId": "C1", "role": "price", "topologySlot": "price"}},
                {"id": "T3", "text": "30天低价｜立减186", "coord": [120, 260, 200, 25], "route": "accepted",
                 "visualReview": {"cardId": "C1", "role": "promotion", "topologySlot": "tag"}},
            ],
        }}
        candidates = {"structureBlocks": [], "resultCards": [{
            "id": "C1", "coord": [0, 100, 400, 220], "status": "confirmed",
            "evidence": ["repeated_left_image_right_text_seed"], "reviewedCardType": "商品卡片",
            "reviewedTopology": {"regions": [
                {"slot": "head_media"}, {"slot": "title"}, {"slot": "price"},
            ], "attachedItems": []},
        }]}
        with patch("map_result_card_semantics.classify_card_types", side_effect=AssertionError("content fallback called")):
            result = map_cards(facts, candidates, load("search_card_taxonomy.v1.json"),
                               load("card_recognition_contracts.v1.json"), load("learned_card_geometry_profiles.v1.json"))
        mapped = result["cards"][0]
        self.assertEqual(mapped["selectedCardType"]["cardType"], "酒店卡片")
        self.assertEqual(mapped["selectedCardType"]["classificationMode"], "title_semantics_with_structure_v1")
        self.assertFalse(mapped["recognitionFeatures"]["package_summary"])
        self.assertTrue(mapped["contractValidation"]["minimumSatisfied"])

    def test_title_family_does_not_override_incompatible_attachment_topology(self):
        references = ROOT / "phase2-card-annotation" / "references"
        load = lambda name: json.loads((references / name).read_text(encoding="utf-8"))
        card = {"id": "C1", "coord": [0, 100, 400, 220], "reviewedTopology": {"regions": [
            {"slot": "merchant_head"}, {"slot": "merchant_info"}, {"slot": "attached_goods"},
        ], "attachedItems": [{"itemIndex": 1, "coord": [120, 210, 100, 70]}]}}
        facts = {"contractVersion": "phase2.cv-facts.v1", "viewport": {"width": 400, "height": 600}, "candidates": {"text": [
            {"id": "T1", "text": "好利来生日蛋糕", "coord": [120, 110, 200, 30], "route": "accepted",
             "visualReview": {"cardId": "C1", "role": "title", "topologySlot": "title"}},
        ], "photos": [
            {"id": "P-head", "coord": [10, 110, 90, 90], "route": "accepted",
             "visualReview": {"cardId": "C1", "topologySlot": "merchant_head"}},
            {"id": "P-item", "coord": [125, 215, 90, 55], "route": "accepted",
             "visualReview": {"cardId": "C1", "topologySlot": "attached_goods"}},
        ]}}
        self.assertEqual(title_semantic_family(card, facts)["family"], "商品卡片")
        self.assertTrue(topology_errors("商品卡片", card["reviewedTopology"]))
        mapped = map_cards(facts, {"structureBlocks": [], "resultCards": [card]},
                           load("search_card_taxonomy.v1.json"), load("card_recognition_contracts.v1.json"),
                           load("learned_card_geometry_profiles.v1.json"))["cards"][0]
        self.assertEqual(mapped["selectedCardType"]["cardType"], "商家卡片_图文下挂")

    def test_text_downhang_requires_attached_items_and_plain_is_known_variant(self):
        topology = {
            "regions": [
                {"slot": "merchant_head", "coord": [10, 10, 90, 90]},
                {"slot": "merchant_info", "coord": [110, 10, 260, 90]},
                {"slot": "text_attachment", "coord": [110, 110, 260, 50]},
            ], "attachedItems": [],
        }
        self.assertEqual(merchant_variant(topology), "")
        plain = {"regions": topology["regions"][:2], "attachedItems": []}
        self.assertEqual(merchant_variant(plain), "商家卡片_无下挂")
        topology["attachedItems"] = [{"itemIndex": 1, "coord": [110, 110, 260, 50]}]
        self.assertEqual(merchant_variant(topology), "商家卡片_文字下挂")

    def test_contract_covers_every_registry_type(self):
        merchant = {"商家卡片_图文下挂", "商家卡片_文字下挂", "商家卡片_无下挂"}
        self.assertEqual(registered_card_types(), set(STRUCTURE_BLUEPRINTS))
        for card_type in registered_card_types():
            complete = card_contract(card_type)
            self.assertTrue(complete["taxonomyRegions"], card_type)
            self.assertTrue(complete["minimumEvidenceGroups"], card_type)
            self.assertTrue(complete["boundaryStrategy"], card_type)
            self.assertTrue(complete["reviewTopologySlots"], card_type)
            self.assertEqual(complete["structureBlueprint"], structure_blueprint(card_type))
        for card_type in registered_card_types() - merchant:
            slots = review_topology_slots(card_type)
            if card_type == "演出电影卡片":
                slots |= {"head_media", "performance_info"}
            topology = {"regions": [{"slot": slot, "coord": [0, index * 10, 10, 10]} for index, slot in enumerate(sorted(slots))], "attachedItems": []}
            self.assertEqual(topology_errors(card_type, topology), [], card_type)

    def test_non_merchant_topology_has_type_specific_rejections(self):
        self.assertIn("product_card_forbidden:attached_goods", topology_errors("商品卡片", {"regions": [{"slot": slot} for slot in ("head_media", "title", "price", "attached_goods")], "attachedItems": []}))
        self.assertIn("hotel_card_forbidden:package_summary", topology_errors("酒店卡片", {"regions": [{"slot": slot} for slot in ("head_media", "title", "price", "package_summary")], "attachedItems": []}))
        self.assertIn("hotel_package_card_missing:package_summary", topology_errors("度假酒店套餐卡片", {"regions": [{"slot": slot} for slot in ("head_media", "title", "price")], "attachedItems": []}))
        self.assertIn("performance_movie_card_requires_performance_poster_info_or_cinema_info", topology_errors("演出电影卡片", {"regions": [{"slot": slot} for slot in ("title", "price")], "attachedItems": []}))
        self.assertIn("heterogeneous_card_must_not_bypass_merchant_variant", topology_errors("异构卡", {"regions": [{"slot": slot} for slot in ("primary_info", "merchant_head", "merchant_info")], "attachedItems": []}))

    def test_uses_atomic_golden_structures_without_fabricating_missing_types(self):
        for card_type in ("商品卡片", "商家卡片_文字下挂", "商家卡片_图文下挂", "酒店卡片", "演出电影卡片", "主点卡片"):
            self.assertTrue(golden_structure_examples(card_type), card_type)
        for card_type in ("商家卡片_无下挂", "度假酒店套餐卡片", "广告卡", "异构卡"):
            self.assertEqual(golden_structure_examples(card_type), [], card_type)

    def test_visual_review_rejects_text_without_items_and_graphic_without_cv_anchor(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            screenshot = base / "screen.png"
            Image.new("RGB", (400, 300), "white").save(screenshot)
            text_review = base / "text.json"
            text_review.write_text(json.dumps({"screenshot": str(screenshot), "completeCurrentPixelReview": True, "cards": [{
                "cardId": "C1", "coord": [0, 0, 400, 220], "cardTypeCandidate": "商家卡片_文字下挂",
                "topology": {"regions": [{"slot": "merchant_head", "coord": [10, 10, 90, 90]}, {"slot": "merchant_info", "coord": [110, 10, 260, 90]}, {"slot": "text_attachment", "coord": [110, 110, 260, 50]}], "attachedItems": []},
            }]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "requires_head_info_text_attachment_and_attached_items"):
                validate_cv_llm_visual_review(text_review, {"candidates": {"photos": []}})
            graphic_review = base / "graphic.json"
            graphic_review.write_text(json.dumps({"screenshot": str(screenshot), "completeCurrentPixelReview": True, "cards": [{
                "cardId": "C1", "coord": [0, 0, 400, 220], "cardTypeCandidate": "商家卡片_图文下挂",
                "topology": {"regions": [{"slot": "merchant_head", "coord": [10, 10, 90, 90]}, {"slot": "merchant_info", "coord": [110, 10, 260, 90]}, {"slot": "attached_goods", "coord": [110, 110, 260, 80]}], "attachedItems": [{"itemIndex": 1, "coord": [110, 110, 120, 80]}]},
            }]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "requires_cv_attached_photo_anchor"):
                validate_cv_llm_visual_review(graphic_review, {"candidates": {"photos": []}})

    def test_gate_failure_becomes_bounded_retry_plan(self):
        plan = build_retry_plan({"errors": ["C4:reviewed_topology_selected_card_type_conflict"], "reprocessTargets": []}, None, 1, 3)
        self.assertTrue(plan["retryRequired"])
        self.assertEqual(plan["nextAttempt"], 2)
        self.assertEqual(plan["targets"][0]["cardId"], "C4")
        exhausted = build_retry_plan({"errors": ["C4:reviewed_topology_selected_card_type_conflict"]}, None, 3, 3)
        self.assertFalse(exhausted["retryRequired"])

    def test_retry_maps_manifest_audit_index_to_card_id(self):
        manifest = {"cards": [{"cardId": "C1"}, {"cardId": "C4"}]}
        plan = build_retry_plan({"errors": []}, {"valid": False, "errors": ["cards[1].regions[2]:bad_item"]}, 1, 3, manifest)
        self.assertEqual(plan["targets"][0]["cardId"], "C1")
        self.assertEqual(plan["targets"][0]["errors"], ["manifest_audit:cards[1].regions[2]:bad_item"])

    def test_retry_keeps_a_middle_card_error_off_the_cropped_tail_card(self):
        manifest = {"cards": [{"cardId": "C1"}, {"cardId": "C2"}, {"cardId": "C3"}]}
        plan = build_retry_plan(
            {"errors": []},
            {"valid": False, "errors": ["cards[2].regions[3].itemGroups[2]:appended_item_requires_text_and_price"]},
            1,
            3,
            manifest,
        )
        self.assertEqual([target["cardId"] for target in plan["targets"]], ["C2"])
        self.assertIn("cards[2].regions[3].itemGroups[2]", plan["targets"][0]["errors"][0])

    def test_semantic_ownership_retry_targets_card_and_page_module(self):
        ownership = {"valid": False, "errors": [
            "page_module_owned_by_result_card:tab:C1",
            "reviewed_item_owner_mismatch:C2:C2-T3:1",
        ]}
        plan = build_retry_plan({"errors": []}, {"valid": True, "errors": []}, 1, 3,
                                {"cards": [{"cardId": "C1"}, {"cardId": "C2"}]}, ownership)
        self.assertEqual([target["cardId"] for target in plan["targets"]], ["C1", "C2"])
        self.assertEqual(plan["pageModuleTargets"][0]["moduleType"], "tab")
        self.assertTrue(plan["retryRequired"])

    def test_cropped_graphic_item_does_not_require_offscreen_text_or_price(self):
        groups = append_item_groups("下挂商品区", [{
            "id": "P1", "元素类型": "图片", "坐标": [0, 0, 80, 60],
            "render": {"visibleStatus": "naturally_cropped"},
        }], "商家卡片_图文下挂")
        self.assertEqual(groups[0]["visibleStatus"], "naturally_cropped")
        self.assertEqual(groups[0]["textElementIds"], [])
        self.assertEqual(groups[0]["priceElementIds"], [])

    def test_text_attachment_item_preserves_text_attachment_slot(self):
        facts = {"screenshot": "/tmp/current.png", "candidates": {"text": [], "photos": []}, "routing": {}}
        review = {"screenshot": "/tmp/current.png", "cards": [{
            "cardId": "C1", "coord": [0, 0, 400, 220], "cardTypeCandidate": "商家卡片_文字下挂",
            "topology": {"regions": [
                {"slot": "merchant_head", "coord": [10, 10, 80, 80]},
                {"slot": "merchant_info", "coord": [100, 10, 280, 80]},
                {"slot": "text_attachment", "coord": [100, 100, 280, 50]},
            ], "attachedItems": [{"itemIndex": 1, "coord": [100, 100, 280, 50]}]},
            "fields": [{"text": "服务套餐", "coord": [150, 105, 120, 30], "role": "subtitle", "colorRole": "neutral"}],
        }], "modules": []}
        result = apply(facts, review)
        self.assertEqual(result["candidates"]["text"][0]["visualReview"]["topologySlot"], "text_attachment")
        self.assertTrue(result["routing"]["visualReview"]["moduleInventoryComplete"])

    def test_reviewed_photo_replaces_overlapping_cv_photo(self):
        """A reviewed head image must not be published twice with its CV candidate."""
        with tempfile.TemporaryDirectory() as temp:
            screenshot = Path(temp) / "current.png"
            Image.new("RGB", (400, 300), "white").save(screenshot)
            facts = {
                "screenshot": str(screenshot),
                "candidates": {"text": [], "photos": [
                    {"id": "P1", "coord": [10, 10, 90, 90], "route": "accepted"},
                ]},
                "routing": {},
            }
            review = {"screenshot": str(screenshot), "cards": [{
                "cardId": "C1", "coord": [0, 0, 400, 220],
                "topology": {"regions": [{"slot": "merchant_head", "coord": [10, 10, 90, 90]}], "attachedItems": []},
                "photos": [{"coord": [10, 10, 90, 90]}],
            }], "modules": []}

            result = apply(facts, review)

        self.assertEqual(result["candidates"]["photos"][0]["route"], "rejected")
        self.assertEqual(result["candidates"]["photos"][-1]["id"], "VP1")

    def test_reviewed_merchant_text_items_override_product_lexicon(self):
        """A service label outside the old keyword list remains text-downhang."""
        references = ROOT / "phase2-card-annotation" / "references"
        taxonomy = json.loads((references / "search_card_taxonomy.v1.json").read_text(encoding="utf-8"))
        contracts = json.loads((references / "card_recognition_contracts.v1.json").read_text(encoding="utf-8"))
        profiles = json.loads((references / "learned_card_geometry_profiles.v1.json").read_text(encoding="utf-8"))
        facts = {
            "contractVersion": "phase2.cv-facts.v1",
            "screenshot": "/tmp/ktv.png",
            "viewport": {"width": 400, "height": 600},
            "candidates": {
                "photos": [
                    {"id": "H1", "coord": [10, 100, 90, 90], "route": "accepted"},
                    # A CV false positive that overlaps the service row cannot
                    # promote a text downhang to graphic without review.
                    {"id": "P-badge", "coord": [120, 220, 40, 24], "route": "accepted"},
                ],
                "text": [
                    {"id": "T1", "text": "夜场KTV", "coord": [120, 110, 130, 24], "route": "accepted"},
                    {"id": "T2", "text": "¥99", "coord": [120, 150, 60, 24], "route": "accepted"},
                    {"id": "T3", "text": "小包3小时", "coord": [120, 220, 130, 24], "route": "accepted",
                     "visualReview": {"cardId": "C1", "topologySlot": "text_attachment", "itemIndex": 1}},
                ],
            },
        }
        candidates = {"structureBlocks": [], "resultCards": [{
            "id": "C1", "coord": [0, 90, 400, 220], "status": "confirmed",
            "reviewedCardType": "商家卡片_文字下挂",
            "reviewedTopology": {"regions": [
                {"slot": "merchant_head", "coord": [10, 100, 90, 90]},
                {"slot": "merchant_info", "coord": [120, 100, 260, 90]},
                {"slot": "text_attachment", "coord": [120, 210, 260, 60]},
            ], "attachedItems": [{"itemIndex": 1, "coord": [120, 210, 260, 60]}]},
        }]}
        result = map_cards(facts, candidates, taxonomy, contracts, profiles)
        selected = result["cards"][0]["selectedCardType"]
        self.assertEqual(selected["cardType"], "商家卡片_文字下挂")
        self.assertEqual(selected["classificationMode"], "reviewed_merchant_attachment_state_machine_v3")
        self.assertTrue(result["cards"][0]["contractValidation"]["minimumSatisfied"])

    def test_merchant_summary_never_enters_text_downhang_item_groups(self):
        """An explicit merchant-info price is summary information, not a service item."""
        card = {"id": "C1", "coord": [0, 0, 400, 260]}
        average_spend = {
            "id": "T-average", "text": "人均¥128", "coord": [120, 64, 96, 24],
            "visualReview": {"role": "price", "topologySlot": "merchant_info"},
        }
        service = {
            "id": "T-service", "text": "75分钟精油SPA", "coord": [120, 180, 170, 24],
            "visualReview": {"role": "attachment", "topologySlot": "text_attachment", "itemIndex": 1},
        }
        output = card_local_semantics(card, "商家卡片_文字下挂", [average_spend, service], {})

        self.assertEqual(output["T-average"]["regionCandidate"], "基础信息区")
        self.assertEqual(output["T-service"]["regionCandidate"], "文字下挂区")

    def test_text_downhang_can_prove_price_inside_service_text(self):
        group = {"textElementIds": ["T-service"], "priceElementIds": []}
        elements = [{
            "id": "T-service",
            "textFacts": {"rawText": "轻奢小包2小时38元起"},
        }]
        self.assertTrue(text_downhang_has_inline_price(group, elements))
        self.assertFalse(text_downhang_has_inline_price(group, [{
            "id": "T-service",
            "textFacts": {"rawText": "轻奢小包2小时"},
        }]))

    def test_candidate_bundle_is_non_publishable_and_bound_to_its_screenshot(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            screenshot = temp_path / "screen.png"
            facts = temp_path / "cv-facts.candidate.json"
            bundle = temp_path / "candidate.json"
            Image.new("RGB", (20, 20), "white").save(screenshot)
            facts.write_text('{"candidates": {}}', encoding="utf-8")
            bundle.write_text(json.dumps({
                "contractVersion": "phase2.candidate-bundle.v2",
                "status": "awaiting_current_pixel_review",
                "screenshot": str(screenshot),
                "screenshotSha256": sha256_file(screenshot),
                "factsPath": str(facts),
                "phase3Ready": False,
            }), encoding="utf-8")
            self.assertEqual(validate_candidate_bundle(bundle, screenshot), facts.resolve())
            payload = json.loads(bundle.read_text(encoding="utf-8"))
            payload["phase3Ready"] = True
            bundle.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must_not_be_publishable"):
                validate_candidate_bundle(bundle, screenshot)

    def test_merchant_candidate_does_not_claim_graphic_downhang_without_attached_photo(self):
        facts = {
            "viewport": {"width": 400, "height": 600},
            "candidates": {"photos": [
                {"id": "H1", "coord": [10, 100, 100, 100], "route": "accepted"},
                {"id": "H2", "coord": [10, 350, 100, 100], "route": "accepted"},
            ]},
        }
        cards = _repeated_merchant_head_cards(facts, [], 50)
        self.assertEqual(len(cards), 2)
        self.assertTrue(all(not card["attachedProductPhotoIds"] for card in cards))
        self.assertTrue(all("right_side_attached_product_image_group" not in card["evidence"] for card in cards))
        self.assertTrue(all("summary_and_product_rail_owned_together" not in card["evidence"] for card in cards))

    def test_phase2_taxonomy_uses_the_shared_card_type_registry(self):
        taxonomy = json.loads((ROOT / "phase2-card-annotation" / "references" / "search_card_taxonomy.v1.json").read_text(encoding="utf-8"))
        validate_phase2_taxonomy(taxonomy)
        registry_ids = {item["id"] for item in load_registry()["resultCardTypes"]}
        self.assertEqual(registry_ids, {item["id"] for item in taxonomy["cardTypes"]})

    def test_visual_review_publishes_declared_topology_not_geometry_guess(self):
        screenshot = ROOT / "screenshots" / "药店_全部_1_副本.png"
        facts = {"screenshot": str(screenshot), "candidates": {"text": [], "photos": []}, "routing": {}}
        review = {
            "screenshot": str(screenshot),
            "cards": [{
                "cardId": "C1", "coord": [0, 500, 1224, 600], "cardTypeCandidate": "商家卡片_图文下挂",
                "topology": {
                    "regions": [
                        {"slot": "merchant_head", "coord": [24, 520, 180, 180]},
                        {"slot": "merchant_info", "coord": [220, 520, 700, 180]},
                        {"slot": "attached_goods", "coord": [220, 720, 900, 240]},
                    ],
                    "attachedItems": [{"itemIndex": 1, "coord": [220, 720, 180, 240], "visibleStatus": "confirmed"}],
                },
                "fields": [{"text": "示例商家", "coord": [220, 530, 220, 36], "role": "title", "colorRole": "neutral"}],
                "photos": [
                    {"coord": [24, 520, 180, 180]},
                    {"coord": [220, 720, 180, 180]},
                ],
            }],
            "modules": [],
        }
        result = apply(facts, review)
        slots = [item["visualReview"]["topologySlot"] for item in result["candidates"]["photos"]]
        self.assertEqual(slots, ["merchant_head", "attached_goods"])
        self.assertEqual(result["candidates"]["text"][0]["visualReview"]["topologySlot"], "merchant_info")

    def test_declared_graphic_merchant_topology_is_a_contract_feature(self):
        facts = {
            "viewport": {"width": 1224, "height": 2700},
            "candidates": {
                "text": [{"coord": [220, 520, 230, 30], "text": "示例商家", "route": "accepted"}],
                "photos": [
                    {"coord": [24, 520, 180, 180], "route": "accepted"},
                    {"coord": [220, 720, 180, 200], "route": "accepted"},
                ],
            },
        }
        card = {
            "coord": [0, 500, 1224, 600], "status": "confirmed", "evidence": [],
            "reviewedTopology": {"regions": [
                {"slot": "merchant_head", "coord": [24, 520, 180, 180]},
                {"slot": "merchant_info", "coord": [220, 520, 700, 180]},
                {"slot": "attached_goods", "coord": [220, 720, 900, 240]},
            ], "attachedItems": [{"itemIndex": 1, "coord": [220, 720, 180, 240], "visibleStatus": "confirmed"}]},
        }
        features = extract_features(card, facts, {})
        self.assertTrue(features["merchant_graphic_boundary"])
        self.assertTrue(features["graphic_downhang"])

    def test_reviewed_text_downhang_overrides_stale_graphic_hint(self):
        facts = {
            "viewport": {"width": 1206, "height": 2622},
            "candidates": {
                "text": [{"coord": [286, 1080, 700, 40], "text": "第一防护·专业运动拉伸馆", "route": "accepted"}],
                "photos": [{"coord": [30, 1080, 228, 228], "route": "accepted"}],
            },
        }
        card = {
            "coord": [0, 1040, 1206, 380],
            "status": "confirmed",
            "evidence": ["repeated_left_image_right_text_seed", "right_side_attached_product_image_group"],
            "reviewedTopology": {
                "regions": [
                    {"slot": "merchant_head", "coord": [30, 1080, 228, 228]},
                    {"slot": "merchant_info", "coord": [286, 1080, 890, 120]},
                    {"slot": "text_attachment", "coord": [286, 1210, 890, 120]},
                ],
                "attachedItems": [
                    {"itemIndex": 1, "coord": [286, 1210, 890, 44], "visibleStatus": "confirmed"},
                    {"itemIndex": 2, "coord": [286, 1270, 890, 44], "visibleStatus": "confirmed"},
                ],
            },
        }
        features = extract_features(card, facts, {})
        self.assertTrue(features["text_downhang"])
        self.assertTrue(features["merchant_text_boundary"])
        self.assertFalse(features["graphic_downhang"])
        self.assertFalse(features["merchant_graphic_boundary"])

    def test_review_merge_removes_stale_graphic_ownership_for_text_downhang(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            candidates_path = temp_path / "candidates.json"
            facts_path = temp_path / "facts.json"
            review_path = temp_path / "review.json"
            candidates_path.write_text(json.dumps({"resultCards": [{
                "id": "C1", "coord": [0, 100, 400, 300], "status": "confirmed",
                "attachedProductPhotoIds": ["OLD"],
                "evidence": ["left_square_merchant_head", "right_side_attached_product_image_group", "summary_and_product_rail_owned_together"],
            }]}), encoding="utf-8")
            facts_path.write_text(json.dumps({"candidates": {"photos": []}}), encoding="utf-8")
            review_path.write_text(json.dumps({"cards": [{
                "cardId": "C1", "coord": [0, 100, 400, 300], "cardTypeCandidate": "商家卡片_文字下挂",
                "topology": {"regions": [
                    {"slot": "merchant_head", "coord": [10, 110, 100, 100]},
                    {"slot": "merchant_info", "coord": [130, 110, 250, 80]},
                    {"slot": "text_attachment", "coord": [130, 210, 250, 120]},
                ], "attachedItems": [{"itemIndex": 1, "coord": [130, 210, 250, 50]}]},
            }]}), encoding="utf-8")
            merge_reviewed_card_boundaries(candidates_path, review_path, facts_path)
            card = json.loads(candidates_path.read_text(encoding="utf-8"))["resultCards"][0]
        self.assertNotIn("attachedProductPhotoIds", card)
        self.assertNotIn("right_side_attached_product_image_group", card["evidence"])
        self.assertNotIn("summary_and_product_rail_owned_together", card["evidence"])
        self.assertEqual(card["classificationHint"]["cardType"], "商家卡片_文字下挂")

    def test_review_merge_reconciles_duplicate_cv_candidate_and_adjacent_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            candidates_path = temp_path / "candidates.json"
            facts_path = temp_path / "facts.json"
            review_path = temp_path / "review.json"
            candidates_path.write_text(json.dumps({"resultCards": [
                {"id": "C1", "coord": [0, 100, 400, 430], "status": "confirmed"},
                {"id": "C2", "coord": [0, 115, 400, 385], "status": "confirmed", "confidence": 0.49},
                {"id": "C3", "coord": [0, 500, 400, 300], "status": "confirmed"},
            ]}), encoding="utf-8")
            facts_path.write_text(json.dumps({"candidates": {"photos": []}}), encoding="utf-8")
            review_path.write_text(json.dumps({"cards": [
                {"cardId": "C1", "coord": [0, 100, 400, 430], "cardTypeCandidate": "商品卡片",
                 "topology": {"regions": [{"slot": "head_media", "coord": [20, 100, 100, 100]}, {"slot": "price", "coord": [140, 400, 180, 100]}], "attachedItems": []}},
                {"cardId": "C3", "coord": [0, 500, 400, 300], "cardTypeCandidate": "商品卡片",
                 "topology": {"regions": [{"slot": "head_media", "coord": [20, 500, 100, 100]}, {"slot": "price", "coord": [140, 650, 180, 80]}], "attachedItems": []}},
            ]}), encoding="utf-8")

            merge_reviewed_card_boundaries(candidates_path, review_path, facts_path)
            cards = json.loads(candidates_path.read_text(encoding="utf-8"))["resultCards"]
            reconciliation = json.loads((temp_path / "candidates.review-reconciliation.json").read_text(encoding="utf-8"))

        self.assertEqual([card["id"] for card in cards], ["C1", "C3"])
        self.assertEqual(cards[0]["coord"], [0, 100, 400, 400])
        self.assertIn("clip_reviewed_card_tail", [item["action"] for item in reconciliation["actions"]])
        self.assertIn("suppress_unreviewed_contained_candidate", [item["action"] for item in reconciliation["actions"]])

    def test_bottom_cropped_graphic_card_review_can_omit_unseen_downhang(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            screenshot = temp_path / "screen.png"
            Image.new("RGB", (400, 600), "white").save(screenshot)
            review_path = temp_path / "review.json"
            review_path.write_text(json.dumps({
                "screenshot": str(screenshot), "completeCurrentPixelReview": True,
                "cards": [{
                    "cardId": "C2", "coord": [0, 510, 400, 90], "cardTypeCandidate": "商家卡片_图文下挂",
                    "topology": {"regions": [{"slot": "merchant_head", "coord": [10, 520, 70, 70]}], "attachedItems": []},
                }],
            }), encoding="utf-8")
            validate_cv_llm_visual_review(review_path)

    def test_reviewed_topology_conflict_blocks_only_complete_card(self):
        facts = {"candidates": {"text": [
            {"id": "T1", "text": "测试商家", "coord": [130, 110, 160, 24], "route": "accepted"},
            {"id": "T2", "text": "4.5分", "coord": [130, 145, 80, 24], "route": "accepted"},
        ]}}
        candidate = {
            "id": "C1", "coord": [0, 100, 400, 300], "status": "confirmed",
            "reviewedCardType": "商家卡片_文字下挂",
            "reviewedTopology": {"regions": [
                {"slot": "merchant_head", "coord": [10, 110, 100, 100]},
                {"slot": "merchant_info", "coord": [130, 110, 250, 80]},
                {"slot": "text_attachment", "coord": [130, 210, 250, 120]},
            ], "attachedItems": [{"itemIndex": 1, "coord": [130, 210, 250, 50]}]},
        }
        semantics = {"cardId": "C1", "selectedCardType": {"cardType": "异构卡", "status": "confirmed"},
                     "contractValidation": {"minimumSatisfied": True}, "regions": []}
        text_semantics = {"candidates": [
            {"sourceId": "T1", "semanticRoleCandidate": "title", "status": "confirmed"},
            {"sourceId": "T2", "semanticRoleCandidate": "rating", "status": "confirmed"},
        ]}
        complete = gate(facts, {"resultCards": [candidate]}, {"cards": [semantics]}, text_semantics)
        self.assertIn("C1:reviewed_topology_selected_card_type_conflict", complete["errors"])
        partial_semantics = {**semantics, "partialCardPolicy": {"applied": True}}
        partial = gate(facts, {"resultCards": [candidate]}, {"cards": [partial_semantics]}, text_semantics)
        self.assertNotIn("C1:reviewed_topology_selected_card_type_conflict", partial["errors"])

    def test_naturally_cropped_downhang_item_does_not_become_uncertain(self):
        elements = [
            {"id": "P1", "元素类型": "图片", "坐标": [100, 200, 120, 120], "render": {"visibleStatus": "naturally_cropped"}},
            {"id": "T1", "元素类型": "文本", "坐标": [100, 330, 120, 30], "render": {"visibleStatus": "naturally_cropped"}, "textFacts": {"semanticRole": "title"}},
            {"id": "T2", "元素类型": "文本", "坐标": [100, 365, 100, 30], "render": {"visibleStatus": "naturally_cropped"}, "textFacts": {"semanticRole": "price"}},
        ]
        groups = append_item_groups("下挂商品区", elements, "商家卡片_图文下挂")
        self.assertEqual(groups[0]["visibleStatus"], "naturally_cropped")

    def test_declared_item_ownership_wins_over_nearest_image_geometry(self):
        elements = [
            {"id": "P1", "元素类型": "图片", "坐标": [100, 200, 120, 120], "render": {"visibleStatus": "confirmed"}, "_reviewItemIndex": 1},
            {"id": "P2", "元素类型": "图片", "坐标": [300, 200, 120, 120], "render": {"visibleStatus": "confirmed"}, "_reviewItemIndex": 2},
            # This label sits nearer to P1 but the current-pixel review saw it
            # as the title of item 2; grouping must preserve that ownership.
            {"id": "T2", "元素类型": "文本", "坐标": [205, 330, 90, 30], "render": {"visibleStatus": "confirmed"}, "textFacts": {"semanticRole": "title"}, "_reviewItemIndex": 2},
        ]
        groups = append_item_groups("下挂商品区", elements, "商家卡片_图文下挂")
        self.assertIn("T2", groups[1]["elementIds"])

    def test_text_attachment_declared_item_spans_multiple_vertical_rows(self):
        elements = [
            {"id": "T1", "元素类型": "文本", "坐标": [100, 200, 140, 30], "render": {"visibleStatus": "confirmed"}, "textFacts": {"semanticRole": "attachment"}, "_reviewItemIndex": 1},
            {"id": "T2", "元素类型": "文本", "坐标": [100, 300, 100, 30], "render": {"visibleStatus": "confirmed"}, "textFacts": {"semanticRole": "price"}, "_reviewItemIndex": 1},
            {"id": "T3", "元素类型": "文本", "坐标": [100, 400, 140, 30], "render": {"visibleStatus": "confirmed"}, "textFacts": {"semanticRole": "attachment"}, "_reviewItemIndex": 1},
        ]
        groups = append_item_groups("文字下挂区", elements, "商家卡片_文字下挂")
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["textElementIds"], ["T1", "T3"])
        self.assertEqual(groups[0]["priceElementIds"], ["T2"])
        self.assertEqual(groups[0]["visibleStatus"], "confirmed")

        for element in elements:
            element.pop("_reviewItemIndex")
        self.assertEqual(len(append_item_groups("文字下挂区", elements, "商家卡片_文字下挂")), 3)

    def test_paddle_mode_cannot_be_reenabled_through_the_python_api(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "cv_llm only"):
                run("x", Path(temp) / "screen.png", Path(temp) / "elements.json", None, Path(temp) / "artifacts", recognition_mode="paddle_assisted")

    def test_complete_review_requires_registered_type_and_topology(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "review.json"
            path.write_text(json.dumps({"completeCurrentPixelReview": True, "cards": [{"cardId": "C1", "cardTypeCandidate": "商家卡片_图文下挂", "topology": {"regions": []}}]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "topology regions"):
                validate_cv_llm_visual_review(path)

    def test_declared_module_inventory_rejects_invalid_box(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "review.json"
            path.write_text(json.dumps({
                "completeCurrentPixelReview": True,
                "modules": [{"moduleType": "tab", "coord": [0, 80, 400, 0]}],
                "cards": [{"cardId": "C1", "cardTypeCandidate": "商品卡片", "topology": {
                    "regions": [{"slot": "head_media", "coord": [0, 100, 100, 100]},
                                {"slot": "title", "coord": [110, 100, 250, 40]},
                                {"slot": "price", "coord": [110, 160, 100, 40]}],
                    "attachedItems": [],
                }}],
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "module requires moduleType and positive coord"):
                validate_cv_llm_visual_review(path)
