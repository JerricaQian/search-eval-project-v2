from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw


PROJECT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_DIR / "phase2-card-annotation/scripts/extract_cv_facts.py"
PHOTO_SCRIPT = PROJECT_DIR / "phase2-card-annotation/scripts/detect_photo_region.py"
STRUCTURE_SCRIPT = PROJECT_DIR / "phase2-card-annotation/scripts/build_search_page_structure.py"
SEMANTIC_SCRIPT = PROJECT_DIR / "phase2-card-annotation/scripts/map_search_page_semantics.py"
RESULT_CANDIDATES_SCRIPT = PROJECT_DIR / "phase2-card-annotation/scripts/build_search_result_candidates.py"
RESULT_SEMANTICS_SCRIPT = PROJECT_DIR / "phase2-card-annotation/scripts/map_result_card_semantics.py"
MANIFEST_SCRIPT = PROJECT_DIR / "phase2-card-annotation/scripts/build_phase2_manifest.py"
VISUAL_REVIEW_SCRIPT = PROJECT_DIR / "phase2-card-annotation/scripts/apply_visual_review.py"
MANIFEST_VALIDATOR = PROJECT_DIR / "phase2-card-annotation/scripts/validate_element_manifest.py"
CALIBRATION_AUDIT_SCRIPT = PROJECT_DIR / "phase2-card-annotation/scripts/build_current_image_calibration_audit.py"
RECOGNITION_GATE = PROJECT_DIR / "phase2-card-annotation/scripts/validate_phase2_recognition.py"
REPROCESS_SCRIPT = PROJECT_DIR / "phase2-card-annotation/scripts/reprocess_bounded_cards.py"
GATE_HOOKS_SCRIPT = PROJECT_DIR / "phase2-card-annotation/scripts/recognition_gate_hooks.py"
GOLDEN_PAGE_STRUCTURE = PROJECT_DIR / "phase2-card-annotation/references/golden_page_structure.v1.json"
GOLDEN_PRODUCT_PAGE_STRUCTURE = PROJECT_DIR / "phase2-card-annotation/references/golden_product_page_structure.v1.json"
RECOGNITION_CONTRACTS = PROJECT_DIR / "phase2-card-annotation/references/card_recognition_contracts.v1.json"


class ExtractCvFactsTest(unittest.TestCase):
    def test_title_prefix_fulfillment_label_uses_geometry_not_label_text_alone(self) -> None:
        script_dir = MANIFEST_SCRIPT.parent
        sys.path.insert(0, str(script_dir))
        try:
            spec = importlib.util.spec_from_file_location("phase2_manifest_title_prefix_test", MANIFEST_SCRIPT)
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
        finally:
            sys.path.pop(0)

        card = {"id": "C1", "coord": [0, 0, 400, 200]}
        title = {"id": "T-title", "text": "商品标题", "coord": [100, 20, 180, 30]}
        prefix = {"id": "T-prefix", "text": "外卖", "coord": [40, 24, 48, 24]}
        base_line = {"id": "T-base", "text": "外卖", "coord": [40, 80, 48, 24]}
        semantics = {
            "T-title": {"semanticRoleCandidate": "title", "regionCandidate": "标题区", "status": "confirmed"},
            "T-prefix": {"semanticRoleCandidate": "fulfillment", "regionCandidate": "基础信息区", "status": "confirmed"},
            "T-base": {"semanticRoleCandidate": "fulfillment", "regionCandidate": "基础信息区", "status": "confirmed"},
        }
        output = module.card_local_semantics(card, "商品卡片", [title, prefix, base_line], semantics)

        self.assertEqual(output["T-prefix"]["regionCandidate"], "标题区")
        self.assertEqual(output["T-prefix"]["elementTypeCandidate"], "标签")
        self.assertEqual(output["T-prefix"]["semanticRoleCandidate"], "fulfillment")
        self.assertEqual(output["T-base"]["regionCandidate"], "基础信息区")
        self.assertNotIn("elementTypeCandidate", output["T-base"])

    def test_graphic_downhang_review_keeps_text_and_price_with_attached_goods(self) -> None:
        script_dir = MANIFEST_SCRIPT.parent
        sys.path.insert(0, str(script_dir))
        try:
            spec = importlib.util.spec_from_file_location("phase2_manifest_graphic_downhang_test", MANIFEST_SCRIPT)
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
        finally:
            sys.path.pop(0)

        card = {"id": "C1", "coord": [0, 0, 400, 260]}
        title = {
            "id": "T-title", "text": "商品名称", "coord": [120, 150, 120, 24],
            "visualReview": {"role": "attachment", "topologySlot": "attached_goods"},
        }
        price = {
            "id": "T-price", "text": "¥9.9", "coord": [120, 190, 80, 24],
            "visualReview": {"role": "price", "topologySlot": "attached_goods"},
        }
        output = module.card_local_semantics(card, "商家卡片_图文下挂", [title, price], {})

        self.assertEqual(output["T-title"]["regionCandidate"], "下挂商品区")
        self.assertEqual(output["T-title"]["semanticRoleCandidate"], "attachment")
        self.assertEqual(output["T-price"]["regionCandidate"], "下挂商品区")
        self.assertEqual(output["T-price"]["semanticRoleCandidate"], "price")

    def test_colored_downhang_promotion_is_classified_as_tag_without_losing_embedded_title(self) -> None:
        script_dir = MANIFEST_SCRIPT.parent
        sys.path.insert(0, str(script_dir))
        try:
            spec = importlib.util.spec_from_file_location("phase2_manifest_promotion_test", MANIFEST_SCRIPT)
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
        finally:
            sys.path.pop(0)

        card = {"id": "C1", "coord": [0, 0, 500, 300]}
        standalone = {
            "id": "T-sale", "text": "特价团", "coord": [120, 160, 80, 24],
            "visualHint": {"colorRole": "red"},
            "visualReview": {"role": "attachment", "topologySlot": "attached_goods"},
        }
        embedded = {
            "id": "T-prefix", "text": "【神抢手】精选双人餐", "coord": [220, 160, 180, 24],
            # A mixed prefix + neutral title box can collapse to a neutral
            # aggregate colour; the explicit prefix must still survive.
            "visualHint": {"colorRole": "neutral"},
            "visualReview": {"role": "attachment", "topologySlot": "attached_goods"},
        }
        output = module.card_local_semantics(card, "商家卡片_图文下挂", [standalone, embedded], {})

        self.assertEqual(output["T-sale"]["semanticRoleCandidate"], "promotion")
        self.assertEqual(output["T-sale"]["elementTypeCandidate"], "标签")
        self.assertEqual(output["T-prefix"]["semanticRoleCandidate"], "attachment")
        self.assertEqual(output["T-prefix"]["promotionPrefix"], "【神抢手】")
        self.assertNotIn("elementTypeCandidate", output["T-prefix"])

    def test_reviewed_fulfillment_badge_owns_compact_photo_candidate_only(self) -> None:
        script_dir = VISUAL_REVIEW_SCRIPT.parent
        sys.path.insert(0, str(script_dir))
        try:
            spec = importlib.util.spec_from_file_location("phase2_visual_review_fulfillment_test", VISUAL_REVIEW_SCRIPT)
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
        finally:
            sys.path.pop(0)

        field = {"text": "闪购", "role": "fulfillment", "coord": [100, 100, 80, 36]}
        badge_candidate = {"coord": [94, 94, 94, 48]}
        product_photo = {"coord": [20, 20, 320, 320]}

        self.assertTrue(module._fulfillment_field_owns_photo_candidate(field, badge_candidate))
        self.assertFalse(module._fulfillment_field_owns_photo_candidate(field, product_photo))

    def test_rating_schema_requires_a_complete_rating_field(self) -> None:
        script_dir = GATE_HOOKS_SCRIPT.parent
        sys.path.insert(0, str(script_dir))
        try:
            spec = importlib.util.spec_from_file_location("phase2_gate_hooks_rating_test", GATE_HOOKS_SCRIPT)
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        finally:
            sys.path.pop(0)
        context = {"semanticItems": [
            {"sourceId": "R1", "role": "rating", "text": "4.6"},
            {"sourceId": "R2", "role": "rating", "text": "21分钟"},
        ]}
        findings = module.field_schema_hook(context)
        self.assertEqual(findings, [{
            "hook": "field_schema", "sourceId": "R2",
            "reason": "rating_text_does_not_match_field_grammar:21分钟",
        }])

    def test_paddle_empty_or_serialized_v3_result_is_a_valid_backend_response(self) -> None:
        script_dir = SCRIPT.parent
        sys.path.insert(0, str(script_dir))
        try:
            spec = importlib.util.spec_from_file_location("phase2_extract_cv_facts_paddle_test", SCRIPT)
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
        finally:
            sys.path.pop(0)

        empty_entries, empty_supported = module._parse_paddle_output([])
        self.assertEqual(empty_entries, [])
        self.assertTrue(empty_supported)

        class SerializedResult:
            def json(self) -> str:
                return json.dumps({
                    "rec_texts": ["锦州烧烤（望京店）"],
                    "rec_scores": [0.99],
                    "rec_boxes": [[12, 8, 164, 36]],
                }, ensure_ascii=False)

        entries, supported = module._parse_paddle_output([SerializedResult()])
        self.assertTrue(supported)
        self.assertEqual(entries, [{"text": "锦州烧烤（望京店）", "coord": [12, 8, 152, 28], "ocrConfidence": 0.99}])

    def test_empty_paddle_crop_does_not_fall_back_to_tesseract(self) -> None:
        script_dir = SCRIPT.parent
        sys.path.insert(0, str(script_dir))
        try:
            spec = importlib.util.spec_from_file_location("phase2_extract_cv_facts_empty_crop_test", SCRIPT)
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
        finally:
            sys.path.pop(0)
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "empty.png"
            Image.new("RGB", (40, 20), "white").save(image)
            original_paddle, original_tesseract = module._ocr_with_paddle, module._run_tesseract
            try:
                module._ocr_with_paddle = lambda _path: ([], None)
                module._run_tesseract = lambda *_args: self.fail("empty Paddle response must not trigger Tesseract")
                entries, backend, error = module.ocr_region(image, [0, 0, 40, 20], tesseract_psm=6)
            finally:
                module._ocr_with_paddle, module._run_tesseract = original_paddle, original_tesseract
        self.assertEqual(entries, [])
        self.assertEqual(backend, "paddleocr")
        self.assertIsNone(error)

    def test_low_hue_textured_product_photo_is_not_discarded_as_ui(self) -> None:
        script_dir = PHOTO_SCRIPT.parent
        sys.path.insert(0, str(script_dir))
        try:
            spec = importlib.util.spec_from_file_location("phase2_detect_photo_region_test", PHOTO_SCRIPT)
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        finally:
            sys.path.pop(0)
        stats = {"active_bins": 2, "rgb_std": 79.0, "chrom_ratio": 0.61, "hue_std": 3.0}
        self.assertEqual(module._classify(58, 1166, 278, 222, 42534, stats), ("photo", "low_hue_textured"))
        flat = {"active_bins": 2, "rgb_std": 20.0, "chrom_ratio": 0.9, "hue_std": 2.0}
        self.assertNotEqual(module._classify(58, 1166, 278, 222, 42534, flat)[0], "photo")

    def test_bounded_price_refinement_requires_numeric_anchor(self) -> None:
        script_dir = SCRIPT.parent
        sys.path.insert(0, str(script_dir))
        try:
            spec = importlib.util.spec_from_file_location("phase2_extract_cv_facts_test", SCRIPT)
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
        finally:
            sys.path.pop(0)
        self.assertEqual(
            module._select_bounded_price_refinement("em 10.9神价 每片2.18", [{"text": "¥10.9 神价/每片Y2.18"}]),
            "¥10.9 神价/每片Y2.18",
        )
        self.assertEqual(module._select_bounded_price_refinement("起送#35免配送费", [{"text": "¥20"}]), "")
        entries = [{"text": "Lee¥21.7言方ih", "ocrConsensus": {"status": "disagreed", "secondaryText": "¥21.7官方补贴已售5000+"}}]
        self.assertEqual(module._prefer_independent_structured_text(entries), 1)
        self.assertEqual(entries[0]["text"], "¥21.7官方补贴已售5000+")
        mismatch = [{"text": "Y¥97.5起", "ocrConsensus": {"status": "disagreed", "secondaryText": "¥37.5起"}}]
        self.assertEqual(module._prefer_independent_structured_text(mismatch), 0)

    def test_golden_page_contract_lists_complete_ordered_components(self) -> None:
        """Gold annotations, not sparse CV candidates, define page component presence."""
        contract = json.loads(GOLDEN_PAGE_STRUCTURE.read_text(encoding="utf-8"))
        pages = contract["pages"]

        for page_name, components in pages.items():
            types = [item[0] for item in components]
            self.assertEqual(types[0:2], ["search_bar", "tab"], page_name)
            self.assertIn("results_list", types, page_name)
            self.assertGreater(types.count("result_card"), 0, page_name)

        birthday_types = [item[0] for item in pages["商家卡片-图文下挂-搜索词为生日蛋糕"]]
        self.assertEqual(
            birthday_types,
            ["search_bar", "tab", "business_operation_card", "image_filter", "sort_filter", "results_list", "result_card", "result_card"],
        )
        mixue_types = [item[0] for item in pages["商家卡片-图文下挂-搜索词为蜜雪冰城"]]
        self.assertIn("live_card", mixue_types)

        birthday_annotations = contract["componentElementAnnotations"]["商家卡片-图文下挂-搜索词为生日蛋糕"]
        self.assertEqual(birthday_annotations["search_bar"]["searchKeyword"], "生日蛋糕")
        self.assertEqual([item["text"] for item in birthday_annotations["image_filter"]["tabs"]], ["款式", "用途"])
        self.assertEqual([item["text"] for item in birthday_annotations["image_filter"]["items"]], ["动物奶油", "提拉米苏", "慕斯蛋糕", "草莓蛋糕", "榴莲千层", "水果蛋糕"])
        medicine_annotations = contract["componentElementAnnotations"]["商家卡片-图文下挂-搜索词为药店"]
        self.assertEqual([item["text"] for item in medicine_annotations["business_image_filter"]["items"]], ["肠胃用药", "男科用药", "儿童用药", "五官用药", "抗菌消炎", "止痛用药"])

    def test_product_card_golden_contract_preserves_component_ownership(self) -> None:
        contract = json.loads(GOLDEN_PRODUCT_PAGE_STRUCTURE.read_text(encoding="utf-8"))
        self.assertEqual(len(contract["pages"]), 7)
        for page_name, components in contract["pages"].items():
            kinds = [item[0] for item in components]
            self.assertEqual(kinds[:2], ["search_bar", "tab"], page_name)
            self.assertIn("results_list", kinds, page_name)
            self.assertIn("result_card", kinds, page_name)
            self.assertEqual(contract["componentElementAnnotations"][page_name]["searchKeyword"], page_name.removeprefix("商品卡片-搜索词为"))
        ibuprofen = [item[0] for item in contract["pages"]["商品卡片-搜索词为布洛芬"]]
        self.assertIn("heterogeneous_card", ibuprofen)
        self.assertIn("floating_service", ibuprofen)

    def test_golden_outputs_use_page_order_and_result_list_positions(self) -> None:
        for directory in ("merchant-graphic-hang", "product-card"):
            output_dir = PROJECT_DIR / "phase2-card-annotation/golden-sample-results" / directory
            for output_path in output_dir.glob("*.elements.json"):
                result = json.loads(output_path.read_text(encoding="utf-8"))
                components = result["pageStructure"]["components"]
                self.assertEqual([component["order"] for component in components], list(range(1, len(components) + 1)), output_path)
                result_list = next(component for component in components if component["componentType"] == "results_list")
                self.assertEqual([item["listPosition"] for item in result_list["components"]], list(range(1, len(result_list["components"]) + 1)), output_path)

    def test_records_geometry_and_missing_ocr_without_claiming_absence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            image_path = tmp_path / "screen.png"
            output_path = tmp_path / "facts.json"
            image = Image.new("RGB", (240, 360), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((12, 80, 228, 170), fill=(30, 30, 30))
            draw.rectangle((12, 210, 228, 290), fill=(80, 120, 190))
            image.save(image_path)

            subprocess.run(
                [sys.executable, str(SCRIPT), str(image_path), "--output", str(output_path)],
                check=True,
                cwd=PROJECT_DIR,
                capture_output=True,
                text=True,
            )
            facts = json.loads(output_path.read_text(encoding="utf-8"))
            structure_path = tmp_path / "structure.json"
            subprocess.run(
                [sys.executable, str(STRUCTURE_SCRIPT), str(output_path), "--output", str(structure_path)],
                check=True,
                cwd=PROJECT_DIR,
                capture_output=True,
                text=True,
            )
            structure = json.loads(structure_path.read_text(encoding="utf-8"))

        self.assertEqual(facts["contractVersion"], "phase2.cv-facts.v1")
        self.assertEqual(facts["viewport"], {"width": 240, "height": 360})
        self.assertGreaterEqual(len(facts["contentRows"]), 2)
        self.assertIn(facts["backends"]["ocr"], {"tesseract", "paddleocr", "unavailable"})
        if facts["backends"]["ocr"] == "unavailable":
            self.assertIn("local_chinese_ocr", facts["routing"]["missingCapabilities"])
        self.assertIn("absence, defects, or excellence", facts["routing"]["rule"])
        self.assertEqual(structure["contractVersion"], "phase2.search-page-structure.v1")
        self.assertGreaterEqual(len(structure["blocks"]), 2)
        self.assertTrue(all(block["route"] == "local_vision" for block in structure["blocks"]))

    def test_maps_colored_live_status_to_a_confirmed_tag_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            facts_path = tmp_path / "facts.json"
            structure_path = tmp_path / "structure.json"
            output_path = tmp_path / "semantic.json"
            facts_path.write_text(json.dumps({
                "contractVersion": "phase2.cv-facts.v1", "screenshot": "/tmp/screen.png",
                "viewport": {"width": 400, "height": 600}, "candidates": {"photos": [], "text": [{
                    "id": "T1", "text": "直播中", "coord": [220, 100, 72, 28], "confidence": 0.97,
                    "visualHint": {"colorRole": "red"},
                }]}, "routing": {"missingCapabilities": []},
            }, ensure_ascii=False), encoding="utf-8")
            structure_path.write_text(json.dumps({
                "contractVersion": "phase2.search-page-structure.v1", "blocks": [{
                    "id": "B1", "coord": [0, 80, 400, 240], "layoutCandidate": "left_image_right_text",
                }],
            }), encoding="utf-8")
            subprocess.run(
                [sys.executable, str(SEMANTIC_SCRIPT), str(facts_path), str(structure_path), "--output", str(output_path)],
                check=True, cwd=PROJECT_DIR, capture_output=True, text=True,
            )
            result = json.loads(output_path.read_text(encoding="utf-8"))

        candidate = result["candidates"][0]
        self.assertEqual(candidate["semanticRoleCandidate"], "tag")
        self.assertEqual(candidate["regionCandidate"], "标签区")
        self.assertEqual(candidate["status"], "confirmed")

    def test_product_quantity_and_price_confirm_product_card_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            facts_path = tmp_path / "facts.json"
            output_path = tmp_path / "classification.json"
            facts_path.write_text(json.dumps({
                "contractVersion": "phase2.cv-facts.v1", "screenshot": "/tmp/screen.png",
                "candidates": {"text": [
                    {"id": "T1", "text": "布洛芬咀嚼片 0.2g*10片", "coord": [220, 300, 280, 36]},
                    {"id": "T2", "text": "¥22.4", "coord": [220, 390, 90, 36]},
                ]},
            }, ensure_ascii=False), encoding="utf-8")
            subprocess.run(
                [sys.executable, str(PROJECT_DIR / "phase2-card-annotation/scripts/classify_search_card_types.py"),
                 str(facts_path), "--taxonomy", str(PROJECT_DIR / "phase2-card-annotation/references/search_card_taxonomy.v1.json"),
                 "--coord", "0,200,600,400", "--output", str(output_path)],
                check=True, cwd=PROJECT_DIR, capture_output=True, text=True,
            )
            result = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(result["selected"]["cardType"], "商品卡片")
        self.assertEqual(result["selected"]["status"], "confirmed")

    def test_contract_state_machine_uses_known_then_ad_then_heterogeneous(self) -> None:
        cases = [
            ("known", [{"id": "P1", "coord": [20, 100, 100, 100], "route": "accepted"}], [
                {"id": "T1", "text": "布洛芬咀嚼片", "coord": [150, 100, 150, 28], "route": "accepted"},
                {"id": "T2", "text": "¥20", "coord": [150, 150, 70, 28], "route": "accepted"},
            ], "商品卡片"),
            ("advertising", [], [{"id": "T1", "text": "广告 品牌活动", "coord": [40, 100, 180, 30], "route": "accepted"}], "广告卡"),
            ("heterogeneous", [], [{"id": "T1", "text": "直播专题入口", "coord": [40, 100, 180, 30], "route": "accepted"}], "异构卡"),
        ]
        for name, photos, texts, expected in cases:
            with self.subTest(case=name), tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                facts_path, candidates_path, output_path = tmp_path / "facts.json", tmp_path / "candidates.json", tmp_path / "semantics.json"
                facts_path.write_text(json.dumps({
                    "contractVersion": "phase2.cv-facts.v1", "screenshot": "/tmp/screen.png", "viewport": {"width": 320, "height": 320},
                    "candidates": {"photos": photos, "text": texts}, "routing": {"missingCapabilities": []},
                }, ensure_ascii=False), encoding="utf-8")
                candidates_path.write_text(json.dumps({
                    "contractVersion": "phase2.search-result-candidates.v1", "resultCards": [{"id": "C1", "coord": [0, 80, 320, 200], "status": "confirmed", "memberBlockIds": [], "evidence": ["repeated_left_image_right_text_seed"]}], "structureBlocks": []
                }, ensure_ascii=False), encoding="utf-8")
                subprocess.run([sys.executable, str(RESULT_SEMANTICS_SCRIPT), str(facts_path), str(candidates_path), "--output", str(output_path)], check=True, cwd=PROJECT_DIR, capture_output=True, text=True)
                result = json.loads(output_path.read_text(encoding="utf-8"))["cards"][0]

            self.assertEqual(result["selectedCardType"]["cardType"], expected)
            self.assertEqual(result["selectedCardType"]["status"], "confirmed")
            self.assertTrue(result["contractValidation"]["minimumSatisfied"])
            self.assertNotEqual(result["selectedCardType"]["cardType"], "unknown")

    def test_merchant_card_without_downhang_is_not_heterogeneous(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            facts_path, candidates_path, output_path = tmp_path / "facts.json", tmp_path / "candidates.json", tmp_path / "semantics.json"
            facts_path.write_text(json.dumps({
                "contractVersion": "phase2.cv-facts.v1", "screenshot": "/tmp/screen.png", "viewport": {"width": 400, "height": 500},
                "candidates": {
                    "photos": [{"id": "P1", "coord": [20, 100, 120, 120], "route": "accepted"}],
                    "text": [
                        {"id": "T1", "text": "花果山漂流", "coord": [160, 100, 180, 30], "route": "accepted"},
                        {"id": "T2", "text": "4.0 23条评论", "coord": [160, 145, 150, 28], "route": "accepted"},
                        {"id": "T3", "text": "水上项目/水上体验 紫竹桥", "coord": [160, 185, 180, 28], "route": "accepted"},
                    ],
                }, "routing": {"missingCapabilities": []},
            }, ensure_ascii=False), encoding="utf-8")
            candidates_path.write_text(json.dumps({
                "contractVersion": "phase2.search-result-candidates.v1",
                "resultCards": [{"id": "C1", "coord": [0, 80, 400, 180], "status": "confirmed", "memberBlockIds": [], "evidence": ["repeated_left_image_right_text_seed"]}],
                "structureBlocks": [],
            }, ensure_ascii=False), encoding="utf-8")
            subprocess.run([sys.executable, str(RESULT_SEMANTICS_SCRIPT), str(facts_path), str(candidates_path), "--output", str(output_path)], check=True, cwd=PROJECT_DIR, capture_output=True, text=True)
            result = json.loads(output_path.read_text(encoding="utf-8"))["cards"][0]

        self.assertEqual(result["selectedCardType"]["cardType"], "商家卡片_无下挂")
        self.assertFalse(result["recognitionFeatures"]["text_downhang"])

    def test_reviewed_product_topology_outweighs_merchant_fulfillment_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            facts_path, candidates_path, output_path = tmp_path / "facts.json", tmp_path / "candidates.json", tmp_path / "semantics.json"
            facts_path.write_text(json.dumps({
                "contractVersion": "phase2.cv-facts.v1", "screenshot": "/tmp/water.png", "viewport": {"width": 1224, "height": 2600},
                "candidates": {
                    "photos": [{"id": "P1", "coord": [56, 902, 318, 318], "route": "accepted"}],
                    "text": [
                        {"id": "T1", "text": "天然水550ml*12瓶", "coord": [405, 908, 500, 56], "route": "accepted"},
                        {"id": "T2", "text": "¥9.9", "coord": [405, 1068, 104, 51], "route": "accepted", "visualHint": {"colorRole": "red"}},
                        {"id": "T3", "text": "月售800+", "coord": [518, 1074, 151, 42], "route": "accepted"},
                        {"id": "T4", "text": "闪购", "coord": [980, 1135, 100, 45], "route": "accepted"},
                    ],
                }, "routing": {"missingCapabilities": []},
            }, ensure_ascii=False), encoding="utf-8")
            candidates_path.write_text(json.dumps({
                "contractVersion": "phase2.search-result-candidates.v1",
                "resultCards": [{
                    "id": "C1", "coord": [24, 882, 1088, 366], "status": "confirmed",
                    "memberBlockIds": [], "evidence": ["repeated_left_image_right_text_seed"],
                    "reviewedCardType": "商品卡片",
                    "reviewedTopology": {
                        "regions": [
                            {"slot": "head_media", "coord": [56, 902, 318, 318]},
                            {"slot": "title", "coord": [405, 908, 500, 56]},
                            {"slot": "price", "coord": [405, 1068, 104, 51]},
                        ],
                        "attachedItems": [],
                    },
                }],
                "structureBlocks": [],
            }, ensure_ascii=False), encoding="utf-8")
            subprocess.run([sys.executable, str(RESULT_SEMANTICS_SCRIPT), str(facts_path), str(candidates_path), "--output", str(output_path)], check=True, cwd=PROJECT_DIR, capture_output=True, text=True)
            result = json.loads(output_path.read_text(encoding="utf-8"))["cards"][0]

        self.assertEqual(result["selectedCardType"]["cardType"], "商品卡片")
        self.assertEqual(result["selectedCardType"]["classificationMode"], "title_semantics_with_structure_v1")
        self.assertTrue(result["contractValidation"]["minimumSatisfied"])

    def test_learned_geometry_is_a_soft_known_type_signal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            facts_path, candidates_path, output_path = tmp_path / "facts.json", tmp_path / "candidates.json", tmp_path / "semantics.json"
            facts_path.write_text(json.dumps({
                "contractVersion": "phase2.cv-facts.v1", "screenshot": "/tmp/screen.png", "viewport": {"width": 400, "height": 900},
                "candidates": {
                    "photos": [{"id": "P1", "coord": [20, 200, 120, 120], "route": "accepted"}],
                    "text": [
                        {"id": "T1", "text": "布洛芬咀嚼片", "coord": [160, 200, 170, 28], "route": "accepted"},
                        {"id": "T2", "text": "¥20", "coord": [160, 280, 70, 28], "route": "accepted"},
                    ],
                }, "routing": {"missingCapabilities": []},
            }, ensure_ascii=False), encoding="utf-8")
            candidates_path.write_text(json.dumps({
                "contractVersion": "phase2.search-result-candidates.v1",
                "resultCards": [{"id": "C1", "coord": [0, 180, 400, 180], "status": "confirmed", "memberBlockIds": [], "evidence": ["repeated_left_image_right_text_seed"]}],
                "structureBlocks": [],
            }, ensure_ascii=False), encoding="utf-8")
            subprocess.run([sys.executable, str(RESULT_SEMANTICS_SCRIPT), str(facts_path), str(candidates_path), "--output", str(output_path)], check=True, cwd=PROJECT_DIR, capture_output=True, text=True)
            card = json.loads(output_path.read_text(encoding="utf-8"))["cards"][0]

        self.assertEqual(card["selectedCardType"]["cardType"], "商品卡片")
        geometry = card["contractValidation"]["geometryValidation"]
        self.assertTrue(geometry["available"])
        self.assertTrue(geometry["withinLearnedRange"])
        self.assertEqual(geometry["source"], "approved_golden_aggregate_geometry")

    def test_two_column_hotel_rows_split_into_independent_cells_and_classify_per_card(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            facts_path, structure_path = tmp_path / "facts.json", tmp_path / "structure.json"
            candidates_path, semantics_path = tmp_path / "candidates.json", tmp_path / "semantics.json"
            photos = []
            texts = [{"id": "Sort", "text": "综合排序", "coord": [180, 120, 100, 24], "route": "accepted"}]
            for row, y in enumerate((220, 600), 1):
                for column, x in (("L", 16), ("R", 306)):
                    photos.append({"id": f"P{row}{column}", "coord": [x, y, 278, 180], "route": "accepted"})
                    texts.extend([
                        {"id": f"T{row}{column}1", "text": "特惠双人电竞房", "coord": [x + 8, y + 190, 220, 28], "route": "accepted"},
                        {"id": f"T{row}{column}2", "text": "20m² 2人 双床 2台 240Hz", "coord": [x + 8, y + 228, 250, 26], "route": "accepted"},
                        {"id": f"T{row}{column}3", "text": "¥354起 已售500+", "coord": [x + 8, y + 270, 190, 30], "route": "accepted", "visualHint": {"colorRole": "red"}},
                    ])
            facts_path.write_text(json.dumps({
                "contractVersion": "phase2.cv-facts.v1", "screenshot": "/tmp/grid.png",
                "viewport": {"width": 600, "height": 1000}, "routing": {"missingCapabilities": []},
                "candidates": {"photos": photos, "text": texts},
            }, ensure_ascii=False), encoding="utf-8")
            structure_path.write_text(json.dumps({
                "contractVersion": "phase2.search-page-structure.v1", "blocks": [
                    {"id": "Sort", "coord": [0, 100, 600, 80], "layoutCandidate": "text_only", "confidence": 0.9},
                    {"id": "R1", "coord": [0, 200, 600, 380], "layoutCandidate": "other", "confidence": 0.82},
                    {"id": "R2", "coord": [0, 580, 600, 380], "layoutCandidate": "other", "confidence": 0.82},
                ],
            }), encoding="utf-8")
            subprocess.run([sys.executable, str(RESULT_CANDIDATES_SCRIPT), str(facts_path), str(structure_path), "--output", str(candidates_path)], check=True, cwd=PROJECT_DIR, capture_output=True, text=True)
            subprocess.run([sys.executable, str(RESULT_SEMANTICS_SCRIPT), str(facts_path), str(candidates_path), "--output", str(semantics_path)], check=True, cwd=PROJECT_DIR, capture_output=True, text=True)
            candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
            semantics = json.loads(semantics_path.read_text(encoding="utf-8"))

        self.assertEqual(len(candidates["resultCards"]), 4)
        self.assertEqual([card["gridColumn"] for card in candidates["resultCards"]], ["left", "right", "left", "right"])
        self.assertTrue(all(card["coord"][2] < 600 * 0.55 for card in candidates["resultCards"]))
        self.assertEqual([card["selectedCardType"]["cardType"] for card in semantics["cards"]], ["酒店卡片"] * 4)

    def test_hotel_time_text_does_not_satisfy_performance_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            facts_path, candidates_path, output_path = tmp_path / "facts.json", tmp_path / "candidates.json", tmp_path / "cards.json"
            facts_path.write_text(json.dumps({
                "contractVersion": "phase2.cv-facts.v1", "screenshot": "/tmp/hotel.png", "viewport": {"width": 400, "height": 600},
                "candidates": {
                    "photos": [{"id": "P1", "coord": [20, 100, 120, 180], "route": "accepted"}],
                    "text": [
                        {"id": "T1", "text": "全季酒店 高档型", "coord": [160, 100, 180, 28], "route": "accepted"},
                        {"id": "T2", "text": "2026-07-10 18:30 可预订", "coord": [160, 180, 210, 28], "route": "accepted"},
                        {"id": "T3", "text": "¥519起", "coord": [160, 240, 100, 30], "route": "accepted", "visualHint": {"colorRole": "red"}},
                    ],
                }, "routing": {"missingCapabilities": []},
            }, ensure_ascii=False), encoding="utf-8")
            candidates_path.write_text(json.dumps({
                "contractVersion": "phase2.search-result-candidates.v1", "structureBlocks": [],
                "resultCards": [{"id": "C1", "coord": [0, 80, 400, 240], "status": "confirmed", "memberBlockIds": [], "evidence": ["repeated_left_image_right_text_seed"]}],
            }), encoding="utf-8")
            subprocess.run([sys.executable, str(RESULT_SEMANTICS_SCRIPT), str(facts_path), str(candidates_path), "--output", str(output_path)], check=True, cwd=PROJECT_DIR, capture_output=True, text=True)
            card = json.loads(output_path.read_text(encoding="utf-8"))["cards"][0]

        self.assertEqual(card["selectedCardType"]["cardType"], "酒店卡片")
        performance = next(item for item in card["contractEvaluations"] if item["cardType"] == "演出电影卡片")
        self.assertTrue(performance["minimumSatisfied"])
        self.assertNotIn("performance_identity", card["selectedCardType"]["evidence"])

    def test_hotel_contract_beats_wrong_product_review_and_excludes_room_urgency_from_price(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            facts_path, candidates_path, output_path = tmp_path / "facts.json", tmp_path / "candidates.json", tmp_path / "cards.json"
            facts_path.write_text(json.dumps({
                "contractVersion": "phase2.cv-facts.v1", "screenshot": "/tmp/hotel.png", "viewport": {"width": 400, "height": 600},
                "candidates": {
                    "photos": [{"id": "P1", "coord": [20, 100, 120, 180], "route": "accepted"}],
                    "text": [
                        {"id": "T1", "text": "全季酒店 高档型", "coord": [160, 100, 180, 28], "route": "accepted"},
                        {"id": "T2", "text": "低价房仅剩1间", "coord": [160, 150, 160, 28], "route": "accepted", "visualHint": {"colorRole": "red"}},
                        {"id": "T3", "text": "立减83", "coord": [160, 185, 90, 28], "route": "accepted", "visualHint": {"colorRole": "red"}},
                        {"id": "T4", "text": "¥519起", "coord": [160, 230, 100, 30], "route": "accepted", "visualHint": {"colorRole": "red"}},
                    ],
                }, "routing": {"missingCapabilities": []},
            }, ensure_ascii=False), encoding="utf-8")
            candidates_path.write_text(json.dumps({
                "contractVersion": "phase2.search-result-candidates.v1", "structureBlocks": [],
                "resultCards": [{
                    "id": "C1", "coord": [0, 80, 400, 240], "status": "confirmed", "memberBlockIds": [],
                    "classificationHint": {"cardType": "商品卡片", "confidence": 0.96},
                    "reviewedTopology": {"regions": [
                        {"slot": "head_media", "coord": [20, 100, 120, 180]},
                        {"slot": "title", "coord": [160, 100, 180, 28]},
                        {"slot": "price", "coord": [160, 230, 100, 30]},
                    ], "attachedItems": []},
                    "evidence": ["repeated_left_image_right_text_seed"],
                }],
            }, ensure_ascii=False), encoding="utf-8")
            subprocess.run([sys.executable, str(RESULT_SEMANTICS_SCRIPT), str(facts_path), str(candidates_path), "--output", str(output_path)], check=True, cwd=PROJECT_DIR, capture_output=True, text=True)
            card = json.loads(output_path.read_text(encoding="utf-8"))["cards"][0]

        self.assertEqual(card["selectedCardType"]["cardType"], "酒店卡片")
        self.assertEqual(card["selectedCardType"]["classificationMode"], "known_minimum_contract_priority")
        price_region = next(region for region in card["regions"] if region["region"] == "价格区")
        self.assertEqual(price_region["evidenceSourceIds"], ["T4"])

    def test_bottom_partial_card_inherits_previous_repeated_type_and_waives_missing_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            facts_path, candidates_path, cards_path, text_path, gate_path = (
                tmp_path / "facts.json", tmp_path / "candidates.json", tmp_path / "cards.json", tmp_path / "text.json", tmp_path / "gate.json"
            )
            facts_path.write_text(json.dumps({
                "contractVersion": "phase2.cv-facts.v1", "screenshot": "/tmp/screen.png", "viewport": {"width": 400, "height": 600},
                "candidates": {
                    "photos": [
                        {"id": "H1", "coord": [20, 110, 110, 110], "route": "accepted"},
                        {"id": "G1", "coord": [160, 230, 120, 100], "route": "accepted"},
                        {"id": "H2", "coord": [20, 520, 80, 80], "route": "accepted"},
                    ],
                    "text": [
                        {"id": "T1", "text": "测试商家", "coord": [150, 120, 120, 24], "route": "accepted", "ocrConsensus": {"status": "confirmed", "primaryText": "测试商家", "secondaryText": "测试商家"}},
                        {"id": "T2", "text": "¥20", "coord": [160, 280, 60, 24], "route": "accepted", "ocrConsensus": {"status": "confirmed", "primaryText": "¥20", "secondaryText": "¥20"}},
                    ],
                }, "routing": {"missingCapabilities": []},
            }, ensure_ascii=False), encoding="utf-8")
            candidates_path.write_text(json.dumps({
                "contractVersion": "phase2.search-result-candidates.v1", "structureBlocks": [],
                "resultCards": [
                    {"id": "C1", "coord": [0, 100, 400, 300], "status": "confirmed", "memberBlockIds": [], "classificationHint": {"cardType": "商家卡片_图文下挂", "confidence": 0.9}, "attachedProductPhotoIds": ["G1"], "evidence": ["left_square_merchant_head", "right_side_attached_product_image_group"]},
                    {"id": "C2", "coord": [0, 500, 400, 100], "status": "confirmed", "memberBlockIds": [],
                     "classificationHint": {"cardType": "商家卡片_图文下挂", "confidence": 0.96},
                     "reviewedTopology": {"regions": [{"slot": "merchant_head", "coord": [20, 520, 80, 80], "visibleStatus": "naturally_cropped"}], "attachedItems": []},
                     "evidence": ["repeated_left_image_right_text_seed", "screen_bottom_natural_crop"]},
                ],
            }, ensure_ascii=False), encoding="utf-8")
            subprocess.run([sys.executable, str(RESULT_SEMANTICS_SCRIPT), str(facts_path), str(candidates_path), "--output", str(cards_path)], check=True, cwd=PROJECT_DIR, capture_output=True, text=True)
            cards = json.loads(cards_path.read_text(encoding="utf-8"))
            text_path.write_text(json.dumps({"candidates": [
                {"sourceId": "T1", "semanticRoleCandidate": "title", "status": "confirmed"},
                {"sourceId": "T2", "semanticRoleCandidate": "price", "status": "confirmed"},
            ]}, ensure_ascii=False), encoding="utf-8")
            completed = subprocess.run([sys.executable, str(RECOGNITION_GATE), "--facts", str(facts_path), "--result-candidates", str(candidates_path), "--card-semantics", str(cards_path), "--text-semantics", str(text_path), "--output", str(gate_path)], check=True, cwd=PROJECT_DIR, capture_output=True, text=True)

        partial = cards["cards"][1]
        self.assertEqual(partial["selectedCardType"]["cardType"], "商家卡片_图文下挂")
        self.assertEqual(partial["selectedCardType"]["classificationMode"], "bottom_partial_inherit_previous_repeated_type")
        self.assertTrue(partial["partialCardPolicy"]["applied"])
        self.assertTrue(json.loads(completed.stdout)["valid"])

    def test_bounded_retry_is_card_local_and_caps_crops(self) -> None:
        script_dir = REPROCESS_SCRIPT.parent
        sys.path.insert(0, str(script_dir))
        try:
            spec = importlib.util.spec_from_file_location("phase2_bounded_retry_test", REPROCESS_SCRIPT)
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
        finally:
            sys.path.pop(0)
        facts = {"candidates": {"photos": [{"id": "P1", "coord": [20, 100, 110, 110], "route": "accepted"}], "text": [{"id": "T1", "text": "测试商品", "coord": [150, 110, 120, 24]}]}}
        candidates = {"resultCards": [{"id": "C1", "coord": [0, 80, 400, 240]}]}
        semantics = {"cards": [{"cardId": "C1", "selectedCardType": {"status": "uncertain"}, "contractValidation": {"missingEvidenceGroups": [["title_like_text"], ["price_text"], ["performance_schedule"]]}}]}
        gate = {"errors": ["C1:card_type_unconfirmed"], "reprocessTargets": [{"sourceId": "T1", "hook": "ocr_consensus"}]}
        targets = module.plan_targets(facts, candidates, semantics, gate)
        self.assertLessEqual(len(targets), 3)
        self.assertTrue(all(item["cardId"] == "C1" for item in targets))
        self.assertIn("price", {item["region"] for item in targets})

    def test_bounded_retry_rejects_head_photo_source_instead_of_one_pixel_crop(self) -> None:
        script_dir = REPROCESS_SCRIPT.parent
        sys.path.insert(0, str(script_dir))
        try:
            spec = importlib.util.spec_from_file_location("phase2_bounded_retry_head_photo_test", REPROCESS_SCRIPT)
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
        finally:
            sys.path.pop(0)
        facts = {"routing": {}, "candidates": {"photos": [{"id": "P1", "coord": [50, 1500, 256, 150], "route": "accepted"}], "text": [{"id": "T38", "text": "图片内文字", "coord": [124, 1582, 76, 25], "route": "accepted"}]}}
        candidates = {"resultCards": [{"id": "C4", "coord": [0, 1500, 1200, 400]}]}
        semantics = {"cards": [{"cardId": "C4", "selectedCardType": {"status": "uncertain"}, "contractValidation": {"missingEvidenceGroups": []}}]}
        targets = module.plan_targets(facts, candidates, semantics, {"errors": [], "reprocessTargets": [{"sourceId": "T38", "hook": "ocr_consensus", "role": "title"}]})
        self.assertEqual(module._text_column(candidates["resultCards"][0], facts), 322)
        self.assertEqual(facts["candidates"]["text"][0]["route"], "rejected")
        self.assertIn("T38", facts["routing"]["nonBodyEvidenceIds"])
        self.assertNotIn("source_line", {item["region"] for item in targets})
        self.assertTrue(all(item["coord"][2] >= 32 and item["coord"][3] >= 20 for item in targets))
        self.assertTrue(module.compatible_text("近30天318人复购", "HBT近30天318人复购"))
        self.assertEqual(module.corroborated_title_span("oem|he)锦州烧烤(悠乐汇店)", "钊州烧烤(您乐汇店)"), "锦州烧烤(悠乐汇店)")
        grouped = module.group_bounded_title_entries([
            {"text": "北京", "coord": [100, 10, 60, 30]},
            {"text": "咂摸相声专场(南锣鼓巷观乐", "coord": [180, 10, 420, 32]},
            {"text": "演出", "coord": [20, 12, 60, 28]},
            {"text": "专场）", "coord": [20, 54, 90, 30]},
        ])
        self.assertEqual(grouped[0]["text"], "咂摸相声专场(南锣鼓巷观乐专场）")
        self.assertEqual({item.get("_boundedRegion") for item in grouped[1:]}, {"tag", "location"})
        self.assertTrue(module.suspicious_short_mixed_text("ae本四"))
        self.assertFalse(module.suspicious_short_mixed_text("AI智能"))
        self.assertFalse(module.suspicious_short_mixed_text("KTV团购"))

    def test_bounded_retry_is_idempotent_for_shifted_duplicate_text(self) -> None:
        script_dir = REPROCESS_SCRIPT.parent
        sys.path.insert(0, str(script_dir))
        try:
            spec = importlib.util.spec_from_file_location("phase2_bounded_retry_dedupe_test", REPROCESS_SCRIPT)
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
        finally:
            sys.path.pop(0)
        facts = {
            "candidates": {
                "photos": [],
                "text": [
                    {"id": "T14", "kind": "text", "text": "测试商品", "coord": [0, 10, 100, 24], "route": "accepted", "rejectionReasons": []},
                    {"id": "T15", "kind": "text", "text": "测试商品", "coord": [92, 10, 100, 24], "route": "accepted", "rejectionReasons": []},
                ],
            },
            "routing": {},
        }
        observation = {
            "id": "",
            "kind": "text",
            "text": "测试商品",
            "coord": [184, 10, 100, 24],
            "route": "accepted",
            "rejectionReasons": [],
            "ocrConsensus": {"status": "bounded_single_observation"},
            "boundedReprocess": {"cardId": "C2", "region": "title", "semanticRegion": "title", "backend": "paddleocr", "crop": [0, 0, 300, 80]},
            "phase3Facts": {"textFacts": {"rawText": "测试商品"}},
        }
        added, corroborated = module.merge_observations(facts, [observation], set())
        active = [item for item in facts["candidates"]["text"] if item.get("route") != "rejected"]
        self.assertEqual(added, 0)
        self.assertEqual(corroborated, 1)
        self.assertEqual(len(active), 1)
        self.assertEqual(facts["routing"]["boundedCardReprocessDeduplicated"], 1)

    def test_component_ocr_separates_product_artwork_from_product_metadata(self) -> None:
        """A merchant carousel must not be OCRed as one image/text soup."""
        script_dir = REPROCESS_SCRIPT.parent
        sys.path.insert(0, str(script_dir))
        try:
            spec = importlib.util.spec_from_file_location("phase2_component_band_test", REPROCESS_SCRIPT)
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
        finally:
            sys.path.pop(0)
        facts = {"candidates": {"photos": [
            {"id": "P1", "coord": [58, 547, 163, 163], "route": "accepted"},
            {"id": "P2", "coord": [58, 845, 274, 395], "route": "accepted"},
        ]}}
        candidates = {"resultCards": [{"id": "C1", "coord": [0, 547, 1224, 770], "headPhotoId": "P1", "attachedProductPhotoIds": ["P2"]}]}
        targets = module._component_targets(facts, candidates)
        self.assertEqual([item["region"] for item in targets], ["main_info", "downhang_overlay", "product_meta"])
        self.assertEqual(targets[0]["coord"], [252, 547, 972, 298])
        self.assertEqual(targets[1]["coord"], [252, 845, 972, 274])
        self.assertEqual(targets[2]["coord"], [252, 1119, 972, 198])

        facts["candidates"]["text"] = [
            {"id": "T1", "text": "包装内文字", "coord": [256, 933, 60, 20], "route": "accepted"},
            {"id": "T2", "text": "点评推荐", "coord": [838, 1082, 100, 24], "route": "accepted"},
            {"id": "T3", "text": "刚刚有用户看过“下次还点(oo)”", "coord": [436, 1451, 478, 59], "route": "accepted"},
        ]
        self.assertEqual(module._exclude_photo_inner_ocr(facts, candidates), 1)
        self.assertEqual(facts["candidates"]["text"][0]["route"], "rejected")
        self.assertEqual(facts["candidates"]["text"][1]["route"], "accepted")
        self.assertEqual(module._reject_unsplittable_container_lines(facts), 1)
        self.assertEqual(facts["candidates"]["text"][2]["route"], "rejected")

    def test_gate_hook_accepts_minute_fulfillment_and_rejects_conflicting_price(self) -> None:
        spec = importlib.util.spec_from_file_location("phase2_gate_hooks_test", GATE_HOOKS_SCRIPT)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        context = {"semanticItems": [{"sourceId": "T1", "role": "fulfillment", "text": "33分钟"}]}
        self.assertEqual(module.field_schema_hook(context), [])
        visual_forms = {
            "semanticItems": [
                {"sourceId": "T-rating", "role": "rating", "text": "4.6"},
                {"sourceId": "T-start", "role": "fulfillment", "text": "起送¥20"},
                {"sourceId": "T-hours", "role": "fulfillment", "text": "17:00营业"},
                {"sourceId": "T-conditional-fee", "role": "fulfillment", "text": "满20配送¥1"},
            ]
        }
        self.assertEqual(module.field_schema_hook(visual_forms), [])
        self.assertNotEqual(module.field_schema_hook({"semanticItems": [
            {"sourceId": "T-intent", "role": "sales", "text": "1人想买"},
        ]}), [])
        self.assertEqual(module.field_schema_hook({"semanticItems": [{"sourceId": "T-hotel-sales", "role": "sales", "text": "100+消费"}]}), [])
        self.assertTrue(module._layout_texts_compatible("fulfillment", "33分钟", "33分钟|钟"))
        self.assertFalse(module._layout_texts_compatible("price", "¥37.5起", "¥97.5起"))

        merged = {
            "semanticItems": [{"sourceId": "T2", "role": "promotion", "region": "标签区", "text": "全程保神券立减5公益商家"}],
            "factsById": {"T2": {"visualHint": {"horizontalForegroundSegments": []}}},
        }
        findings = module.semantic_atomicity_hook(merged)
        self.assertTrue(any("multiple_independent_tags_merged" in item["reason"] for item in findings))

        one_ranking = {
            "semanticItems": [{"sourceId": "T3", "role": "promotion", "region": "标签区", "text": "望京美发回头客榜第2名"}],
            "factsById": {"T3": {"visualHint": {"horizontalForegroundSegments": []}}},
        }
        self.assertEqual(module.semantic_atomicity_hook(one_ranking), [])

        visually_split = {
            "semanticItems": [{"sourceId": "T4", "role": "promotion", "region": "标签区", "text": "北京男性体检销量榜第2名体检"}],
            "factsById": {"T4": {"visualHint": {"horizontalForegroundSegments": [
                {"xOffset": 0, "width": 220, "colorRole": "orange"},
                {"xOffset": 240, "width": 50, "colorRole": "neutral"},
            ]}}},
        }
        self.assertTrue(module.semantic_atomicity_hook(visually_split))

        dense = {
            "semanticItems": [
                {"sourceId": "T5", "role": "other", "text": "4.5分4.8万条"},
                {"sourceId": "T6", "role": "location", "text": "图6.0km"},
                {"sourceId": "T7", "role": "price", "text": "¥30.6¥10.9¥17¥18.04"},
                {"sourceId": "T8", "role": "promotion", "text": "神券52减1862减20"},
                {"sourceId": "T9", "role": "other", "text": "17:555"},
            ],
        }
        dense_reasons = {item["reason"] for item in module.dense_numeric_atomicity_hook(dense)}
        self.assertIn("rating_token_must_be_a_standalone_rating_field", dense_reasons)
        self.assertIn("distance_has_non_distance_prefix", dense_reasons)
        self.assertIn("multiple_product_prices_are_merged_in_one_element", dense_reasons)
        self.assertIn("adjacent_coupon_thresholds_are_merged", dense_reasons)
        self.assertIn("session_time_has_extra_trailing_digit", dense_reasons)
        self.assertEqual(module.dense_numeric_atomicity_hook({"semanticItems": [{"sourceId": "T-hotel-distance", "role": "location", "text": "距您直线17.7km"}]}), [])
        self.assertTrue(module.dense_numeric_atomicity_hook({"semanticItems": [{"sourceId": "T-misplaced-distance", "role": "tag", "text": "距您直线17.7km"}]}))
        self.assertEqual(
            module.dense_numeric_atomicity_hook({"semanticItems": [{"sourceId": "T10", "role": "fulfillment", "text": "33分钟"}]}),
            [],
        )
        # Current-pixel topology wins over the ambiguous glyph ``分``: these
        # are service durations in an attached item, not 0--5 rating fields.
        service_duration = {
            "semanticItems": [
                {"sourceId": "T11", "role": "price", "text": "¥555 恢复SPA·品质调理｜80分… 年售60+"},
                {"sourceId": "T12", "role": "price", "text": "特价团 肩颈放松60分… 年售200+"},
                {"sourceId": "T13", "role": "price", "text": "短时体验4分…"},
            ],
            "factsById": {
                source_id: {"visualReview": {"role": "attached_item", "topologySlot": "text_attachment"}}
                for source_id in ("T11", "T12", "T13")
            },
        }
        self.assertEqual(module.dense_numeric_atomicity_hook(service_duration), [])
        self.assertEqual(
            module.dense_numeric_atomicity_hook({"semanticItems": [{"sourceId": "T14", "role": "price", "text": "4.8分"}]}),
            [{"hook": "dense_numeric_atomicity", "sourceId": "T14", "reason": "rating_token_must_be_a_standalone_rating_field"}],
        )

    def test_price_evidence_recovers_currency_glyph_damage_without_using_delivery_fee(self) -> None:
        cases = [("YQ97.5起", "red", "商品卡片"), ("起送#35免配送费", "red", "异构卡")]
        for price_text, color, expected in cases:
            with self.subTest(text=price_text), tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                facts_path, candidates_path, output_path = tmp_path / "facts.json", tmp_path / "candidates.json", tmp_path / "cards.json"
                facts_path.write_text(json.dumps({
                    "contractVersion": "phase2.cv-facts.v1", "screenshot": "/tmp/screen.png", "viewport": {"width": 400, "height": 600},
                    "candidates": {
                        "photos": [{"id": "P1", "coord": [20, 120, 110, 110], "route": "accepted"}],
                        "text": [
                            {"id": "T1", "text": "测试商品", "coord": [150, 120, 120, 24], "route": "accepted", "visualHint": {"colorRole": "neutral"}},
                            {"id": "T2", "text": price_text, "coord": [155, 220, 130, 32], "route": "accepted", "visualHint": {"colorRole": color}},
                        ],
                    }, "routing": {"missingCapabilities": []},
                }, ensure_ascii=False), encoding="utf-8")
                candidates_path.write_text(json.dumps({
                    "contractVersion": "phase2.search-result-candidates.v1", "structureBlocks": [],
                    "resultCards": [{"id": "C1", "coord": [0, 100, 400, 220], "status": "confirmed", "memberBlockIds": [], "evidence": ["repeated_left_image_right_text_seed"]}],
                }, ensure_ascii=False), encoding="utf-8")
                subprocess.run([sys.executable, str(RESULT_SEMANTICS_SCRIPT), str(facts_path), str(candidates_path), "--output", str(output_path)], check=True, cwd=PROJECT_DIR, capture_output=True, text=True)
                card = json.loads(output_path.read_text(encoding="utf-8"))["cards"][0]

            self.assertEqual(card["selectedCardType"]["cardType"], expected)

    def test_groups_only_post_sort_cards_and_uses_text_attachment_topology(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            facts_path = tmp_path / "facts.json"
            structure_path = tmp_path / "structure.json"
            candidates_path = tmp_path / "candidates.json"
            semantics_path = tmp_path / "semantics.json"
            facts_path.write_text(json.dumps({
                "contractVersion": "phase2.cv-facts.v1", "screenshot": "/tmp/screen.png",
                "viewport": {"width": 400, "height": 1000}, "routing": {"missingCapabilities": []},
                "candidates": {"photos": [
                    {"id": "Pfilter", "coord": [20, 120, 100, 100]}, {"id": "P1", "coord": [20, 360, 120, 120]}, {"id": "P2", "coord": [20, 680, 120, 120]},
                ], "text": [
                    {"id": "Tsort", "text": "综合排序", "coord": [180, 280, 80, 22]},
                    {"id": "T1", "text": "商家标题 4.8分", "coord": [160, 370, 160, 22]}, {"id": "T1a", "text": "可预约服务", "coord": [160, 510, 100, 22]},
                    {"id": "T2", "text": "商家标题 人均¥30", "coord": [160, 690, 180, 22]}, {"id": "T2a", "text": "可预约服务", "coord": [160, 830, 100, 22]},
                ]},
            }, ensure_ascii=False), encoding="utf-8")
            structure_path.write_text(json.dumps({
                "contractVersion": "phase2.search-page-structure.v1", "blocks": [
                    {"id": "Bfilter", "coord": [0, 100, 400, 160], "layoutCandidate": "top_image_bottom_text", "confidence": 0.8},
                    {"id": "Bsort", "coord": [0, 260, 400, 80], "layoutCandidate": "text_only", "confidence": 0.8},
                    {"id": "B1", "coord": [0, 340, 400, 140], "layoutCandidate": "left_image_right_text", "confidence": 0.9},
                    {"id": "B1a", "coord": [0, 480, 400, 120], "layoutCandidate": "text_only", "confidence": 0.8},
                    {"id": "B2", "coord": [0, 660, 400, 140], "layoutCandidate": "left_image_right_text", "confidence": 0.9},
                    {"id": "B2a", "coord": [0, 800, 400, 120], "layoutCandidate": "text_only", "confidence": 0.8},
                ],
            }), encoding="utf-8")
            subprocess.run([sys.executable, str(RESULT_CANDIDATES_SCRIPT), str(facts_path), str(structure_path), "--output", str(candidates_path)], check=True, cwd=PROJECT_DIR, capture_output=True, text=True)
            subprocess.run([sys.executable, str(RESULT_SEMANTICS_SCRIPT), str(facts_path), str(candidates_path), "--output", str(semantics_path)], check=True, cwd=PROJECT_DIR, capture_output=True, text=True)
            candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
            semantics = json.loads(semantics_path.read_text(encoding="utf-8"))

        self.assertEqual([card["id"] for card in candidates["resultCards"]], ["C1", "C2"])
        self.assertEqual([card["selectedCardType"]["cardType"] for card in semantics["cards"]], ["商家卡片_文字下挂", "商家卡片_文字下挂"])

    def test_confirms_graphic_hang_from_head_and_right_product_group(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            facts_path = tmp_path / "facts.json"
            structure_path = tmp_path / "structure.json"
            candidates_path = tmp_path / "candidates.json"
            semantics_path = tmp_path / "semantics.json"
            facts_path.write_text(json.dumps({
                "contractVersion": "phase2.cv-facts.v1", "screenshot": "/tmp/screen.png", "viewport": {"width": 400, "height": 900}, "routing": {"missingCapabilities": []},
                "candidates": {"photos": [
                    {"id": "H1", "coord": [20, 340, 120, 120]}, {"id": "Coupon", "coord": [20, 470, 120, 230]}, {"id": "Goods1", "coord": [150, 480, 110, 160]}, {"id": "Goods2", "coord": [270, 480, 110, 160]}, {"id": "H2", "coord": [20, 700, 120, 120]},
                ], "text": [
                    {"id": "Sort", "text": "综合排序", "coord": [180, 280, 80, 20]}, {"id": "Title", "text": "商家标题 4.8分", "coord": [160, 350, 160, 20]}, {"id": "Price", "text": "¥20", "coord": [160, 650, 60, 20]},
                ]},
            }, ensure_ascii=False), encoding="utf-8")
            structure_path.write_text(json.dumps({"contractVersion": "phase2.search-page-structure.v1", "blocks": [
                {"id": "Sort", "coord": [0, 260, 400, 60], "layoutCandidate": "text_only", "confidence": 0.8},
                {"id": "Body", "coord": [0, 320, 400, 150], "layoutCandidate": "left_image_right_text", "confidence": 0.9},
                {"id": "Attach", "coord": [0, 470, 400, 220], "layoutCandidate": "other", "confidence": 0.8},
            ]}), encoding="utf-8")
            subprocess.run([sys.executable, str(RESULT_CANDIDATES_SCRIPT), str(facts_path), str(structure_path), "--output", str(candidates_path)], check=True, cwd=PROJECT_DIR, capture_output=True, text=True)
            subprocess.run([sys.executable, str(RESULT_SEMANTICS_SCRIPT), str(facts_path), str(candidates_path), "--output", str(semantics_path)], check=True, cwd=PROJECT_DIR, capture_output=True, text=True)
            semantics = json.loads(semantics_path.read_text(encoding="utf-8"))

        self.assertEqual(semantics["cards"][0]["selectedCardType"]["cardType"], "商家卡片_图文下挂")
        self.assertEqual(semantics["cards"][0]["selectedCardType"]["status"], "confirmed")

    def test_builds_phase3_manifest_with_cv_colour_evidence_and_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            facts = {
                "screenshot": "/tmp/screen.png", "viewport": {"width": 400, "height": 600},
                "candidates": {"photos": [{"id": "P1", "coord": [20, 120, 120, 120], "route": "accepted"}], "text": [
                    {"id": "T0", "text": "外卖", "coord": [160, 130, 48, 28], "route": "accepted", "visualHint": {"colorRole": "yellow"}},
                    {"id": "T1", "text": "布洛芬咀嚼片", "coord": [214, 130, 180, 28], "route": "accepted",
                     "visualHint": {"colorRole": "red", "medianRgb": [216, 56, 56], "evidence": "foreground_pixel_median"}},
                ]}, "routing": {"unresolvedCandidateIds": []},
            }
            candidates = {"pageModules": [{"module": "results_list", "coord": [0, 100, 400, 200], "status": "confirmed", "evidence": ["result_cards"]}], "resultCards": [{"id": "C1", "coord": [0, 100, 400, 200]}]}
            card_semantics = {"cards": [{"cardId": "C1", "selectedCardType": {"cardType": "商品卡片", "status": "confirmed", "evidence": ["quantity_and_price"]}, "regions": []}]}
            text_semantics = {"candidates": [
                {"sourceId": "T0", "semanticRoleCandidate": "fulfillment", "regionCandidate": "基础信息区", "status": "confirmed"},
                {"sourceId": "T1", "semanticRoleCandidate": "title", "regionCandidate": "标题区", "status": "confirmed"},
            ]}
            paths = {name: tmp_path / f"{name}.json" for name in ("facts", "candidates", "cards", "text", "elements", "recognition")}
            for name, payload in (("facts", facts), ("candidates", candidates), ("cards", card_semantics), ("text", text_semantics)):
                paths[name].write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            subprocess.run([sys.executable, str(MANIFEST_SCRIPT), "--query", "布洛芬", "--facts", str(paths["facts"]), "--result-candidates", str(paths["candidates"]), "--card-semantics", str(paths["cards"]), "--text-semantics", str(paths["text"]), "--output", str(paths["elements"]), "--recognition-audit", str(paths["recognition"])], check=True, cwd=PROJECT_DIR, capture_output=True, text=True)
            validation = subprocess.run([sys.executable, str(MANIFEST_VALIDATOR), str(paths["elements"]), "--recognition-audit", str(paths["recognition"])], check=True, cwd=PROJECT_DIR, capture_output=True, text=True)
            manifest = json.loads(paths["elements"].read_text(encoding="utf-8"))
            subprocess.run([sys.executable, str(CALIBRATION_AUDIT_SCRIPT), str(paths["elements"]), "--output", str(paths["recognition"])], check=True, cwd=PROJECT_DIR, capture_output=True, text=True)
            calibration = json.loads(paths["recognition"].read_text(encoding="utf-8"))
            self.assertFalse(calibration["reviewedAgainstCurrentPixels"])
            self.assertTrue(all(field["status"] == "uncertain" for field in calibration["fields"]))
            review = tmp_path / "visual-review.json"
            review.write_text(json.dumps({
                "screenshot": "/tmp/screen.png",
                "completeCurrentPixelReview": True,
                "localReviewPaths": [],
                "cards": [],
            }, ensure_ascii=False), encoding="utf-8")
            subprocess.run([
                sys.executable, str(CALIBRATION_AUDIT_SCRIPT), str(paths["elements"]),
                "--output", str(paths["recognition"]), "--visual-review", str(review),
            ], check=True, cwd=PROJECT_DIR, capture_output=True, text=True)
            calibration = json.loads(paths["recognition"].read_text(encoding="utf-8"))
            calibrated_validation = subprocess.run(
                [sys.executable, str(MANIFEST_VALIDATOR), str(paths["elements"]), "--recognition-audit", str(paths["recognition"]), "--require-current-image-calibration"],
                check=True, cwd=PROJECT_DIR, capture_output=True, text=True,
            )

            original_visible_text = calibration["fields"][0]["visibleText"]
            calibration["fields"][0]["visibleText"] = "mismatched review text"
            paths["recognition"].write_text(json.dumps(calibration, ensure_ascii=False), encoding="utf-8")
            mismatched = subprocess.run(
                [sys.executable, str(MANIFEST_VALIDATOR), str(paths["elements"]), "--recognition-audit", str(paths["recognition"]), "--require-current-image-calibration"],
                check=False, cwd=PROJECT_DIR, capture_output=True, text=True,
            )

            calibration["fields"][0]["visibleText"] = original_visible_text
            calibration["goldenValueInjection"] = True
            paths["recognition"].write_text(json.dumps(calibration, ensure_ascii=False), encoding="utf-8")
            rejected = subprocess.run(
                [sys.executable, str(MANIFEST_VALIDATOR), str(paths["elements"]), "--recognition-audit", str(paths["recognition"]), "--require-current-image-calibration"],
                check=False, cwd=PROJECT_DIR, capture_output=True, text=True,
            )

        title_region = next(region for region in manifest["cards"][0]["regions"] if region["name"] == "标题区")
        prefix, element = title_region["elements"]
        self.assertEqual(prefix["元素类型"], "标签")
        self.assertEqual(prefix["textFacts"]["semanticRole"], "fulfillment")
        self.assertEqual(prefix["textFacts"]["rawText"], "外卖")
        self.assertEqual(prefix["visual"]["styleKey"].split("|")[2], "履约标")
        self.assertNotIn("semanticRole", prefix["visual"])
        self.assertEqual(element["visual"]["colorRole"], "red")
        self.assertNotIn("textColor", element["visual"])
        self.assertNotIn("colorEvidence", element["visual"])
        self.assertNotIn("sourceRegion", element["visual"])
        self.assertNotIn("sourceRegion", element["render"])
        all_elements = [
            item
            for card in manifest["cards"]
            for region in card["regions"]
            for item in region["elements"]
        ]
        self.assertTrue(all("内容简述" not in item and "excludeReason" not in item for item in all_elements))
        self.assertEqual(element["textFacts"]["rawText"], "布洛芬咀嚼片")
        self.assertTrue(any(item["元素类型"] == "图片" and "textFacts" not in item for item in all_elements))
        self.assertTrue(json.loads(validation.stdout)["valid"])
        self.assertTrue(json.loads(calibrated_validation.stdout)["valid"])
        self.assertIn(
            f"current_image_calibration_visible_text_mismatch:{calibration['fields'][0]['elementId']}",
            json.loads(mismatched.stdout)["errors"],
        )
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("current_image_calibration_golden_value_injection_forbidden", json.loads(rejected.stdout)["errors"])

    def test_recognition_gate_blocks_by_batch_quality_not_ocr_confidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            payloads = {
                "facts": {"candidates": {"text": [{"id": "T1", "text": "布洛芬", "coord": [160, 120, 80, 24], "route": "accepted", "ocrConsensus": {"status": "confirmed", "primaryText": "布洛芬", "secondaryText": "布洛芬"}}, {"id": "T2", "text": "¥20", "coord": [160, 160, 60, 24], "route": "accepted", "ocrConsensus": {"status": "confirmed", "primaryText": "¥20", "secondaryText": "¥20"}}], "photos": [{"id": "P1", "coord": [20, 100, 100, 100], "route": "accepted"}]}},
                "candidates": {"resultCards": [{"id": "C1", "coord": [0, 80, 320, 200]}]},
                "cards": {"cards": [{"cardId": "C1", "selectedCardType": {"cardType": "商品卡片", "status": "confirmed"}}]},
                "text": {"candidates": [
                    {"sourceId": "T1", "text": "布洛芬", "semanticRoleCandidate": "title", "status": "confirmed"},
                    {"sourceId": "T2", "text": "¥20", "semanticRoleCandidate": "price", "status": "confirmed"},
                ]},
            }
            paths = {name: tmp_path / f"{name}.json" for name in payloads}
            for name, content in payloads.items():
                paths[name].write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
            report = tmp_path / "gate.json"
            completed = subprocess.run([sys.executable, str(RECOGNITION_GATE), "--facts", str(paths["facts"]), "--result-candidates", str(paths["candidates"]), "--card-semantics", str(paths["cards"]), "--text-semantics", str(paths["text"]), "--output", str(report)], check=True, cwd=PROJECT_DIR, capture_output=True, text=True)

        self.assertTrue(json.loads(completed.stdout)["valid"])

    def test_recognition_gate_blocks_fluent_looking_text_when_ocr_layouts_disagree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            payloads = {
                "facts": {"candidates": {"text": [
                    {"id": "T1", "text": "仁辣共去", "coord": [160, 120, 100, 24], "route": "accepted", "ocrConsensus": {"status": "disagreed", "primaryText": "仁辣共去", "secondaryText": "人来公园"}},
                    {"id": "T2", "text": "¥20", "coord": [160, 160, 60, 24], "route": "accepted", "ocrConsensus": {"status": "confirmed", "primaryText": "¥20", "secondaryText": "¥20"}},
                ], "photos": [{"id": "P1", "coord": [20, 100, 100, 100], "route": "accepted"}]}},
                "candidates": {"resultCards": [{"id": "C1", "coord": [0, 80, 320, 200]}]},
                "cards": {"cards": [{"cardId": "C1", "selectedCardType": {"cardType": "商品卡片", "status": "confirmed"}}]},
                "text": {"candidates": [
                    {"sourceId": "T1", "text": "仁辣共去", "semanticRoleCandidate": "title", "status": "confirmed"},
                    {"sourceId": "T2", "text": "¥20", "semanticRoleCandidate": "price", "status": "confirmed"},
                ]},
            }
            paths = {name: tmp_path / f"{name}.json" for name in payloads}
            for name, content in payloads.items():
                paths[name].write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
            report = tmp_path / "gate.json"
            completed = subprocess.run([sys.executable, str(RECOGNITION_GATE), "--facts", str(paths["facts"]), "--result-candidates", str(paths["candidates"]), "--card-semantics", str(paths["cards"]), "--text-semantics", str(paths["text"]), "--output", str(report)], check=False, cwd=PROJECT_DIR, capture_output=True, text=True)

        result = json.loads(completed.stdout)
        self.assertNotEqual(completed.returncode, 0)
        self.assertFalse(result["valid"])
        self.assertTrue(any(item["hook"] == "ocr_consensus" and item["sourceId"] == "T1" for item in result["semanticHookFindings"]))

    def test_recognition_gate_reuses_confirmed_card_region_roles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            payloads = {
                "facts": {"candidates": {"text": [
                    {"id": "T1", "text": "布洛芬咀嚼片", "coord": [160, 120, 120, 24], "route": "accepted", "ocrConsensus": {"status": "confirmed", "primaryText": "布洛芬咀嚼片", "secondaryText": "布洛芬咀嚼片"}},
                    {"id": "T2", "text": "¥20", "coord": [160, 160, 60, 24], "route": "accepted", "ocrConsensus": {"status": "confirmed", "primaryText": "¥20", "secondaryText": "¥20"}},
                ], "photos": [{"id": "P1", "coord": [20, 100, 100, 100], "route": "accepted"}]}},
                "candidates": {"resultCards": [{"id": "C1", "coord": [0, 80, 320, 200]}]},
                "cards": {"cards": [{
                    "cardId": "C1", "selectedCardType": {"cardType": "商品卡片", "status": "confirmed"},
                    "contractValidation": {"minimumSatisfied": True},
                    "regions": [
                        {"region": "标题区", "status": "confirmed", "evidenceSourceIds": ["T1"]},
                        {"region": "价格区", "status": "confirmed", "evidenceSourceIds": ["T2"]},
                    ],
                }]},
                "text": {"candidates": []},
            }
            paths = {name: tmp_path / f"{name}.json" for name in payloads}
            for name, content in payloads.items():
                paths[name].write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
            report = tmp_path / "gate.json"
            completed = subprocess.run([sys.executable, str(RECOGNITION_GATE), "--facts", str(paths["facts"]), "--result-candidates", str(paths["candidates"]), "--card-semantics", str(paths["cards"]), "--text-semantics", str(paths["text"]), "--output", str(report)], check=True, cwd=PROJECT_DIR, capture_output=True, text=True)

        self.assertTrue(json.loads(completed.stdout)["valid"])

    def test_consensus_hook_accepts_compatible_title_crop_but_not_rewritten_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            payloads = {
                "facts": {"candidates": {"text": [
                    {"id": "T1", "text": "锦州烧烤望京店", "coord": [160, 120, 130, 24], "route": "accepted", "ocrConsensus": {"status": "disagreed", "primaryText": "锦州烧烤望京店", "secondaryText": "锦州烧烤望京"}},
                    {"id": "T2", "text": "¥20", "coord": [160, 160, 60, 24], "route": "accepted", "ocrConsensus": {"status": "confirmed", "primaryText": "¥20", "secondaryText": "¥20"}},
                ], "photos": [{"id": "P1", "coord": [20, 100, 100, 100], "route": "accepted"}]}},
                "candidates": {"resultCards": [{"id": "C1", "coord": [0, 80, 320, 200]}]},
                "cards": {"cards": [{"cardId": "C1", "selectedCardType": {"cardType": "商品卡片", "status": "confirmed"}, "contractValidation": {"minimumSatisfied": True}}]},
                "text": {"candidates": [
                    {"sourceId": "T1", "semanticRoleCandidate": "title", "status": "confirmed"},
                    {"sourceId": "T2", "semanticRoleCandidate": "price", "status": "confirmed"},
                ]},
            }
            paths = {name: tmp_path / f"{name}.json" for name in payloads}
            for name, content in payloads.items():
                paths[name].write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
            report = tmp_path / "gate.json"
            completed = subprocess.run([sys.executable, str(RECOGNITION_GATE), "--facts", str(paths["facts"]), "--result-candidates", str(paths["candidates"]), "--card-semantics", str(paths["cards"]), "--text-semantics", str(paths["text"]), "--output", str(report)], check=True, cwd=PROJECT_DIR, capture_output=True, text=True)

        result = json.loads(completed.stdout)
        self.assertTrue(result["valid"])
        self.assertEqual(payloads["facts"]["candidates"]["text"][0]["text"], "锦州烧烤望京店")

    def test_blocked_gate_is_embedded_in_single_manifest_and_blocks_phase3(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            payloads = {
                "facts": {"screenshot": "/tmp/screen.png", "viewport": {"width": 320, "height": 320}, "backends": {"ocr": "tesseract"}, "routing": {"unresolvedCandidateIds": ["T1"]}, "candidates": {"text": [{"id": "T1", "text": "仁辣共去", "coord": [150, 100, 100, 28], "route": "accepted"}], "photos": [{"id": "P1", "coord": [20, 100, 100, 100], "route": "accepted"}]}},
                "candidates": {"pageModules": [], "resultCards": [{"id": "C1", "coord": [0, 80, 320, 200]}]},
                "cards": {"cards": [{"cardId": "C1", "selectedCardType": {"cardType": "商品卡片", "status": "confirmed", "evidence": ["test"]}, "regions": []}]},
                "text": {"candidates": [{"sourceId": "T1", "semanticRoleCandidate": "title", "regionCandidate": "标题区", "status": "confirmed"}]},
                "gate": {"valid": False, "errors": ["C1:semantic_text_invalid"], "semanticHookFindings": [{"hook": "ocr_consensus", "sourceId": "T1", "reason": "disagreed"}], "reprocessTargets": [{"sourceId": "T1", "hook": "ocr_consensus", "reason": "disagreed", "action": "rerun_bounded_local_ocr_or_rebuild_card_boundary"}], "reprocess": ["rerun C1"]},
            }
            paths = {name: tmp_path / f"{name}.json" for name in payloads}
            for name, payload in payloads.items():
                paths[name].write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            output = tmp_path / "elements.json"
            subprocess.run([sys.executable, str(MANIFEST_SCRIPT), "--query", "测试", "--facts", str(paths["facts"]), "--result-candidates", str(paths["candidates"]), "--card-semantics", str(paths["cards"]), "--text-semantics", str(paths["text"]), "--recognition-gate", str(paths["gate"]), "--output", str(output)], check=True, cwd=PROJECT_DIR, capture_output=True, text=True)
            manifest = json.loads(output.read_text(encoding="utf-8"))
            validated = subprocess.run([sys.executable, str(MANIFEST_VALIDATOR), str(output)], check=False, cwd=PROJECT_DIR, capture_output=True, text=True)
            validation = json.loads(validated.stdout)

        self.assertEqual(manifest["recognition"]["status"], "blocked")
        self.assertFalse(manifest["recognition"]["phase3Ready"])
        self.assertEqual(manifest["recognition"]["blockingCardIds"], ["C1"])
        self.assertNotEqual(validated.returncode, 0)
        self.assertIn("whole_page_recognition_blocked", validation["errors"])


if __name__ == "__main__":
    unittest.main()
