from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "phase5-report" / "scripts" / "build_experience_dashboard.py"


def load_module():
    spec = importlib.util.spec_from_file_location("phase5_dashboard", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def card(card_type: str, semantic: tuple[str, ...] = (), fulfillment: tuple[str, ...] = ()) -> dict:
    return {
        "cardId": "C1",
        "卡片类型": card_type,
        "regions": [{
            "name": "标题区",
            "elements": [
                {"内容简述": text, "textFacts": {"semanticRole": "title"}}
                for text in semantic
            ],
        }, {
            "name": "履约区",
            "elements": [
                {"内容简述": text, "textFacts": {"semanticRole": "fulfillment"}}
                for text in fulfillment
            ],
        }],
    }


class Phase5BusinessClassificationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()

    def test_unclassified_card_count_deduplicates_manifest_and_issue_records(self) -> None:
        entries = [
            {"query": "凯米", "screenshot": "凯米_全部_1.png", "cardId": "C3", "reason": "卡片归属未知"},
            {"query": "凯米", "screenshot": "凯米_全部_1.png", "cardId": "C3", "reason": "问题归属未知"},
            {"query": "凯米", "screenshot": "凯米_全部_2.png", "cardId": "C3", "reason": "卡片归属未知"},
        ]
        self.assertEqual(self.module.count_unclassified_cards(entries), 2)

    def test_merchant_semantics_and_delivery_classify_as_food_delivery(self) -> None:
        result = self.module.classify_card(card("商家卡片-文字下挂", ("原文:火锅餐厅",), ("原文:外卖", "原文:配送费¥2")))
        self.assertEqual(result["businessCode"], "food_delivery")

    def test_governance_priority_uses_current_fixed_thresholds(self) -> None:
        priority = self.module.priority_from_vote_counts
        self.assertEqual(priority(4, 0), "P0")
        self.assertEqual(priority(0, 6), "P0")
        self.assertEqual(priority(2, 0), "P1")
        self.assertEqual(priority(0, 4), "P1")
        self.assertEqual(priority(0, 1), "P2")
        self.assertEqual(priority(0, 3), "P2")
        self.assertEqual(priority(1, 0), "P2")
        self.assertIsNone(priority(0, 0))
        self.assertIn("剩余低频问题", self.module.priority_reason_from_vote_counts(1, 0, "P2"))

    def test_product_card_with_shared_fulfillment_is_flash_delivery(self) -> None:
        result = self.module.classify_card(card("商品卡片", ("原文:矿泉水",), ("原文:外卖", "原文:配送费¥2")))
        self.assertEqual(result["businessCode"], "flash_delivery")

    def test_flash_delivery_covers_visible_daily_goods_and_fresh_product_terms(self) -> None:
        for product in ("原文:安睡裤", "原文:卫生巾", "原文:泰国金枕榴莲"):
            with self.subTest(product=product):
                result = self.module.classify_card(card("商品卡片", (product,), ("原文:外卖",)))
                self.assertEqual(result["businessCode"], "flash_delivery")

    def test_stationery_with_visible_instant_delivery_is_flash_delivery(self) -> None:
        result = self.module.classify_card(card(
            "商品卡片",
            ("原文:六格田字本 小学生文具作业本",),
            ("原文:闪购", "原文:30分钟送达", "原文:免配送费"),
        ))
        self.assertEqual(result["businessCode"], "flash_delivery")

    def test_electronics_with_visible_delivery_are_instant_retail(self) -> None:
        result = self.module.classify_card(card(
            "商品卡片", ("原文:蓝牙耳机",), ("原文:48分钟",),
        ))
        self.assertEqual(result["businessCode"], "flash_delivery")

    def test_product_flash_badge_outranks_broad_service_copy(self) -> None:
        result = self.module.classify_card(card(
            "商品卡片", ("原文:蓝牙耳机", "原文:休闲娱乐"), ("原文:闪购",),
        ))
        self.assertEqual(result["businessCode"], "flash_delivery")

    def test_food_semantics_classify_without_query_override(self) -> None:
        result = self.module.classify_card(card("商家卡片-文字下挂", ("原文:火锅餐厅",), ("原文:到店团购",)))
        self.assertEqual(result["businessCode"], "dine_in")
        self.assertFalse(hasattr(self.module, "REPORT_QUERY_BUSINESS_OVERRIDES"))

    def test_business_terms_are_case_insensitive(self) -> None:
        result = self.module.classify_card(card("商家卡片-文字下挂", ("原文:量贩式KTV",), ()))
        self.assertEqual(result["businessCode"], "service_retail")

    def test_fitness_and_diy_cards_are_service_retail(self) -> None:
        for semantic in ("原文:24小时健身房", "原文:DIY手工坊拼豆"):
            with self.subTest(semantic=semantic):
                result = self.module.classify_card(card("商家卡片-文字下挂", (semantic,), ()))
                self.assertEqual(result["businessCode"], "service_retail")

    def test_visible_home_service_roles_are_service_retail(self) -> None:
        for semantic in ("原文:小飞侠家政保洁", "原文:月嫂育儿嫂保姆"):
            with self.subTest(semantic=semantic):
                result = self.module.classify_card(card("商家卡片-文字下挂", (semantic,), ("原文:到店",)))
                self.assertEqual(result["businessCode"], "service_retail")

    def test_location_semantics_do_not_override_visible_retail_identity(self) -> None:
        input_card = card("异构卡", ("原文:好想来零食乐园",), ())
        input_card["regions"][0]["elements"].append({
            "内容简述": "原文:中山医院",
            "textFacts": {"semanticRole": "location"},
        })
        result = self.module.classify_card(input_card)
        self.assertEqual(result["businessCode"], "service_retail")

    def test_visible_flash_badge_is_sufficient_delivery_identity(self) -> None:
        result = self.module.classify_card(card("商品卡片", ("原文:充电宝",), ("原文:闪购",)))
        self.assertEqual(result["businessCode"], "flash_delivery")

    def test_breakfast_with_delivery_is_food_delivery(self) -> None:
        result = self.module.classify_card(card("商家卡片-图文下挂", ("原文:品致早餐",), ("原文:外卖",)))
        self.assertEqual(result["businessCode"], "food_delivery")

    def test_visible_legacy_food_and_service_terms_are_classified(self) -> None:
        cases = [
            (card("异构卡", ("原文:肯德基官方直播间",), ()), "dine_in"),
            (card("商家卡片-图文下挂", ("原文:滨寿司",), ()), "dine_in"),
            (card("商家卡片-图文下挂", ("原文:CONTENT U COFFEE",), ("原文:外卖",)), "food_delivery"),
            (card("商家卡片-图文下挂", ("原文:情趣成人用品",), ("原文:外卖",)), "flash_delivery"),
            (card("商家卡片-文字下挂", ("原文:专业采耳水洗头疗",), ()), "service_retail"),
            (card("商家卡片-文字下挂", ("原文:台球棋牌俱乐部",), ()), "service_retail"),
        ]
        for input_card, expected in cases:
            with self.subTest(expected=expected, card=input_card):
                self.assertEqual(self.module.classify_card(input_card)["businessCode"], expected)

    def test_visible_local_service_terms_cover_car_care_and_internet_cafes(self) -> None:
        for semantic in (
            "原文:巨会养车鸿云祥汽服 美容洗车",
            "原文:网鱼网咖 网吧",
            "原文:普瑞祥电竞 新客专享网费",
        ):
            with self.subTest(semantic=semantic):
                result = self.module.classify_card(card("商家卡片-文字下挂", (semantic,), ()))
                self.assertEqual(result["businessCode"], "service_retail")

    def test_visible_sports_photo_and_beauty_services_are_service_retail(self) -> None:
        for semantic in (
            "原文:拳击俱乐部",
            "原文:游泳馆",
            "原文:生日个性写真",
            "原文:胸部养护 美胸",
            "原文:电玩城",
            "原文:休闲公园",
            "原文:蜜蜡脱毛",
        ):
            with self.subTest(semantic=semantic):
                result = self.module.classify_card(card("商家卡片-文字下挂", (semantic,), ("原文:到店",)))
                self.assertEqual(result["businessCode"], "service_retail")

    def test_minutes_inside_service_copy_do_not_override_service_identity(self) -> None:
        result = self.module.classify_card(card(
            "商家卡片-文字下挂",
            ("原文:胸部养护 美胸",),
            ("原文:30分钟养生调理",),
        ))
        self.assertEqual(result["businessCode"], "service_retail")

    def test_visible_restaurant_terms_cover_current_unknown_cards(self) -> None:
        cases = [
            ("原文:海底捞拌饭 番茄肥牛捞饭", "原文:外卖 免配送费", "food_delivery"),
            ("原文:蓝色港湾日本料理 牛肉乌冬面", "原文:到店", "dine_in"),
            ("原文:乡野江西菜", "原文:外卖 免配送费", "food_delivery"),
            ("原文:葱花鸡蛋炒饭 热卤鸭头", "原文:外卖 免配送费", "food_delivery"),
            ("原文:鱼酷活鱼烤鱼", "原文:到店", "dine_in"),
            ("原文:探鱼烤鱼", "原文:外卖 免配送费", "food_delivery"),
            ("原文:北京烤鸭", "原文:起送¥15", "food_delivery"),
            ("原文:爷爷不泡茶", "原文:外卖 22分钟", "food_delivery"),
            ("原文:台爸鲁肉饭", "原文:到店", "dine_in"),
            ("原文:烧麦 馄饨 抄手", "原文:到店", "dine_in"),
            ("原文:春饼", "原文:到店", "dine_in"),
            ("原文:羊肉烩面 羊肉汤", "原文:到店", "dine_in"),
            ("原文:菜煎饼 鱼丸", "原文:外卖 免配送费", "food_delivery"),
            ("原文:商务茶馆", "原文:到店", "dine_in"),
            ("原文:轻食沙拉 鸡胸杂粮饭", "原文:外卖 免配送费", "food_delivery"),
            ("原文:创意菜 蟹黄面馆", "原文:到店", "dine_in"),
        ]
        for semantic, fulfillment, expected in cases:
            with self.subTest(semantic=semantic, expected=expected):
                result = self.module.classify_card(card(
                    "商家卡片-图文下挂",
                    (semantic,),
                    (fulfillment,),
                ))
                self.assertEqual(result["businessCode"], expected)

    def test_visible_current_cuisine_terms_classify_without_query_fallback(self) -> None:
        cases = [
            ("原文:川菜家常菜", "原文:到店", "dine_in"),
            ("原文:粤菜茶点", "原文:到店", "dine_in"),
            ("原文:Wagas 西式简餐", "原文:到店", "dine_in"),
            ("原文:胶东味 鲁菜", "原文:到店", "dine_in"),
            ("原文:徽菜家宴", "原文:到店", "dine_in"),
            ("原文:泰国菜 东南亚菜", "原文:到店", "dine_in"),
            ("原文:顺德菜 招牌烤鸡", "原文:到店", "dine_in"),
            ("原文:鸡公煲 砂锅鱼 猪蹄煲", "原文:外卖 20分钟", "food_delivery"),
        ]
        for semantic, fulfillment, expected in cases:
            with self.subTest(semantic=semantic):
                result = self.module.classify_card(card(
                    "商家卡片-图文下挂", (semantic,), (fulfillment,),
                ))
                self.assertEqual(result["businessCode"], expected)

    def test_visible_local_retail_terms_are_service_retail_without_delivery(self) -> None:
        for semantic in (
            "原文:美莱百货 居家日用",
            "原文:食品商行 其他食品滋补",
        ):
            with self.subTest(semantic=semantic):
                result = self.module.classify_card(card(
                    "商家卡片-无下挂", (semantic,), ("原文:到店",),
                ))
                self.assertEqual(result["businessCode"], "service_retail")

    def test_current_visible_service_and_local_retail_categories(self) -> None:
        for semantic in (
            "原文:望京8号·高端连锁轰趴馆·团建聚会",
            "原文:YONEX尤尼克斯 运动户外",
            "原文:百惠眼镜 蔡司 凯米折扣店 眼镜店",
            "原文:京准达手柄数码家电",
        ):
            with self.subTest(semantic=semantic):
                result = self.module.classify_card(card("商家卡片-无下挂", (semantic,), ("原文:到店",)))
                self.assertEqual(result["businessCode"], "service_retail")

    def test_current_visible_product_and_food_categories_require_own_card_facts(self) -> None:
        cases = (
            ("原文:无线游戏手柄", "原文:配送¥1", "flash_delivery"),
            ("原文:爆汁烤冷面", "原文:外卖", "food_delivery"),
            ("原文:鸡蛋灌饼", "原文:外卖", "food_delivery"),
            ("原文:好利来(望京中福店)", "原文:外卖", "food_delivery"),
            ("原文:咳露口服液 止咳", "原文:30分钟", "healthcare"),
        )
        for semantic, fulfillment, expected in cases:
            with self.subTest(semantic=semantic):
                result = self.module.classify_card(card("商品卡片", (semantic,), (fulfillment,)))
                self.assertEqual(result["businessCode"], expected)

    def test_generic_company_listing_stays_unknown_without_consumer_supply(self) -> None:
        result = self.module.classify_card(card(
            "商家卡片-无下挂", ("原文:北京凯米特科技发展有限公司", "原文:公司企业"),
            ("原文:到店",),
        ))
        self.assertEqual(result["businessCode"], "unknown")

    def test_confirmed_food_brand_with_delivery_classifies_as_food_delivery(self) -> None:
        result = self.module.classify_card(card(
            "商家卡片-无下挂",
            ("原文:便宜坊（望京店）",),
            ("原文:外卖", "原文:免配送费"),
        ))
        self.assertEqual(result["businessCode"], "food_delivery")

    def test_photo_only_natural_bottom_crop_does_not_create_unknown_business(self) -> None:
        input_card = {
            "cardId": "C4",
            "卡片类型": "商家卡片-图文下挂",
            "structure": {"visibleStatus": "naturally_cropped"},
            "regions": [{"name": "下挂商品区", "elements": [{"id": "P1", "元素类型": "图片"}]}],
        }
        result = self.module.classify_card(input_card)
        self.assertEqual(result["scope"], "cropped")
        self.assertNotEqual(result["businessCode"], "unknown")

    def test_named_business_semantics_take_priority_over_fulfillment(self) -> None:
        result = self.module.classify_card(card("商品卡片", ("原文:连锁药房",), ("原文:分钟达",)))
        self.assertEqual(result["businessCode"], "healthcare")

    def test_scripted_mystery_is_service_retail_even_when_copy_mentions_theater(self) -> None:
        result = self.module.classify_card(card(
            "商家卡片-文字下挂",
            ("原文:沉浸式剧本杀演绎剧场",),
            ("原文:预约到店",),
        ))
        self.assertEqual(result["businessCode"], "service_retail")

    def test_cinema_foot_massage_is_service_retail_not_maoyan(self) -> None:
        result = self.module.classify_card(card(
            "商家卡片-文字下挂",
            ("原文:沐云·影院足道·奢颜SPA", "原文:肩颈四肢按摩+观影"),
            ("原文:到店",),
        ))
        self.assertEqual(result["businessCode"], "service_retail")

    def test_bathhouse_semantics_override_hotel_style_copy(self) -> None:
        for semantic in (
            "原文:汤泉洗浴 可过夜 酒店式休息区",
            "原文:附近洗浴 汗蒸住宿",
        ):
            with self.subTest(semantic=semantic):
                result = self.module.classify_card(card(
                    "商家卡片-文字下挂",
                    (semantic,),
                    ("原文:到店",),
                ))
                self.assertEqual(result["businessCode"], "service_retail")
                self.assertEqual(result["confidence"], "specific_service_semantic")

    def test_location_labels_number_standard_cards_and_name_heterogeneous_cards(self) -> None:
        cards = [
            {**card("商家卡片-无下挂", ("原文:商户A",), ()), "cardId": "C1"},
            {**card("异构卡", ("原文:大家还在搜",), ()), "cardId": "H1", "structure": {"isHeterogeneous": True}},
            {**card("异构卡", ("原文:直播好货",), ()), "cardId": "H2", "structure": {"isHeterogeneous": True}},
            {**card("商品卡片", ("原文:商品B",), ()), "cardId": "C2"},
        ]
        self.assertEqual(self.module.card_location_labels(cards), {
            "C1": "商卡1", "H1": "异构卡-大家还在搜", "H2": "异构卡-直播大卡", "C2": "商卡2",
        })

    def test_all_supported_businesses_have_a_deterministic_card_rule(self) -> None:
        cases = [
            ("到餐", card("商家卡片-文字下挂", ("原文:火锅餐厅",), ("原文:到店团购",)), "dine_in"),
            ("餐饮外卖", card("商家卡片-文字下挂", ("原文:火锅餐厅",), ("原文:外卖配送",)), "food_delivery"),
            ("闪购", card("商品卡片", ("原文:咖啡豆",), ("原文:外卖配送",)), "flash_delivery"),
            ("小象超市", card("商家卡片-文字下挂", ("原文:小象超市",), ("原文:分钟达",)), "xiaoxiang"),
            ("医药健康", card("商品卡片", ("原文:连锁药房",), ("原文:分钟达",)), "healthcare"),
            ("酒店旅行", card("商家卡片-文字下挂", ("原文:精品酒店",), ()), "hotel_travel"),
            ("服务零售", card("商家卡片-文字下挂", ("原文:专业理发",), ("原文:预约",)), "service_retail"),
            ("猫眼", card("商家卡片-文字下挂", ("原文:电影票",), ("原文:场次",)), "maoyan"),
        ]
        for name, input_card, expected in cases:
            with self.subTest(business=name):
                self.assertEqual(self.module.classify_card(input_card)["businessCode"], expected)

    def test_flash_delivery_requires_delivery_and_a_flash_category(self) -> None:
        self.assertEqual(
            self.module.classify_card(card("商品卡片", ("原文:矿泉水",), ()))["businessCode"],
            "unknown",
        )
        self.assertEqual(
            self.module.classify_card(card("商品卡片", ("原文:矿泉水",), ("原文:外卖配送",)))["businessCode"],
            "flash_delivery",
        )
        self.assertEqual(
            self.module.classify_card(card("商品卡片", ("原文:奶茶",), ("原文:外卖配送",)))["businessCode"],
            "food_delivery",
        )

    def test_visible_minutes_are_delivery_evidence_for_flash_category(self) -> None:
        result = self.module.classify_card(card("商家卡片-图文下挂", ("原文:鲜花店",), ("原文:71分钟",)))
        self.assertEqual(result["businessCode"], "flash_delivery")

    def test_storage_goods_with_visible_minutes_are_flash_delivery(self) -> None:
        result = self.module.classify_card(card(
            "商品卡片",
            ("原文:硬款收纳盒 收纳包",),
            ("原文:64分钟",),
        ))
        self.assertEqual(result["businessCode"], "flash_delivery")

    def test_flower_shops_without_delivery_are_local_retail(self) -> None:
        result = self.module.classify_card(card(
            "商家卡片-图文下挂",
            ("原文:鲜花店 花卉绿植",),
            ("原文:到店",),
        ))
        self.assertEqual(result["businessCode"], "service_retail")

    def test_partially_visible_tail_card_without_business_facts_is_cropped(self) -> None:
        input_card = card("商品卡片", ("原文:教师节礼物",), ())
        input_card["structure"] = {"visibleStatus": "naturally_cropped"}
        result = self.module.classify_card(input_card)
        self.assertEqual(result["scope"], "cropped")

    def test_cropped_merchant_with_delivery_but_no_category_stays_cropped(self) -> None:
        input_card = card("商家卡片-图文下挂", ("原文:某商家",), ("原文:外卖 20分钟",))
        input_card["structure"] = {"visibleStatus": "naturally_cropped"}
        result = self.module.classify_card(input_card)
        self.assertEqual(result["scope"], "cropped")

    def test_unclassified_merchant_card_blocks_business_dashboard(self) -> None:
        result = self.module.classify_card(card("商家卡片-文字下挂", ("原文:某商户",), ()))
        self.assertEqual(result["businessCode"], "unknown")
        with self.assertRaisesRegex(ValueError, "无法由当前商卡语义与履约事实判定"):
            self.module.validate_dataset({
                "queryCount": 1,
                "queryDetails": {"测试": [{"rating": "未执行", "issues": []}]},
                "unknown": [{"query": "测试", "cardId": "C1", "reason": "证据不足"}],
                "businesses": [],
                "groups": [],
            }, Path("/tmp"), set())

    def test_phase2_explicit_business_ownership_cannot_override_visible_facts(self) -> None:
        input_card = card("商品卡片", ("原文:火锅餐厅",), ("原文:外卖配送",))
        input_card.update({"ownershipScope": "business", "businessCode": "healthcare"})
        result = self.module.classify_card(input_card)
        self.assertEqual(result["businessCode"], "unknown")
        self.assertIn("conflicts_visible_facts", result["confidence"])

    def test_query_or_task_tab_never_participates_in_business_attribution(self) -> None:
        input_card = card("商家卡片-文字下挂", ("原文:火锅餐厅",), ("原文:外卖配送",))
        input_card.update({"query": "医药", "tab": "医药健康", "expectedBusinessTab": "healthcare"})
        result = self.module.classify_card(input_card)
        self.assertEqual(result["businessCode"], "food_delivery")

    def test_matching_explicit_business_is_only_audit_metadata(self) -> None:
        input_card = card("商品卡片", ("原文:火锅餐厅",), ("原文:外卖配送",))
        input_card.update({"ownershipScope": "business", "businessCode": "food_delivery"})
        result = self.module.classify_card(input_card)
        self.assertEqual(result["businessCode"], "food_delivery")
        self.assertEqual(result["confidence"], "phase2_explicit+delivery+food_category")

    def test_unsupported_phase2_business_ownership_stays_unknown(self) -> None:
        input_card = card("商品卡片", ("原文:火锅餐厅",), ("原文:外卖配送",))
        input_card.update({"ownershipScope": "business", "businessCode": "made_up_business"})
        result = self.module.classify_card(input_card)
        self.assertEqual(result["businessCode"], "unknown")
        self.assertIn("unsupported_explicit_business_code", result["confidence"])

    def test_visible_business_tabs_are_derived_from_collected_cards(self) -> None:
        data = {
            "businesses": [
                {"businessCode": "food_delivery"},
                {"businessCode": "service_retail"},
            ],
        }
        self.assertEqual(self.module.visible_business_tabs(data), {"food_delivery", "service_retail"})

    def test_original_screenshot_evidence_override_keeps_dataset_layers_consistent(self) -> None:
        data = {
            "queryDetails": {
                "火锅": [{
                    "screenshot": "/tmp/firepot.png",
                    "issues": [{"evidenceImage": "/tmp/firepot_redbox.png"}],
                }],
            },
            "groups": [{
                "evidence": [{
                    "screenshot": "/tmp/firepot.png",
                    "evidenceImage": "/tmp/firepot_redbox.png",
                }],
            }],
        }
        self.module.replace_issue_evidence_with_original_screenshots(data)
        self.assertEqual(
            data["queryDetails"]["火锅"][0]["issues"][0]["evidenceImage"],
            "/tmp/firepot.png",
        )
        self.assertEqual(data["groups"][0]["evidence"][0]["evidenceImage"], "/tmp/firepot.png")

    def test_report_exclusion_parser_requires_query_and_element_id(self) -> None:
        self.assertEqual(
            self.module.parse_excluded_issue_keys(["自助餐:C1-P2"]),
            {("自助餐", "C1-P2")},
        )
        with self.assertRaisesRegex(ValueError, "搜索词"):
            self.module.parse_excluded_issue_keys(["自助餐"])

    def test_positive_redundancy_metrics_are_rendered_as_problem_names(self) -> None:
        self.assertEqual(self.module.METRICS["eval-8-info-redundancy"][0], "信息冗余")
        self.assertEqual(self.module.METRICS["eval-7-info-redundancy"][0], "功能/信息冗余")

    def test_complexity_metrics_use_short_report_names(self) -> None:
        self.assertEqual(self.module.METRICS["eval-4-element-complexity"][0], "元素复杂")
        self.assertEqual(self.module.METRICS["eval-4-static-component-complexity"][0], "组件复杂")

    def test_colour_metrics_use_dimension_specific_problem_names(self) -> None:
        self.assertEqual(self.module.METRICS["eval-2-color-logic-single-element"][0], "单一元素色彩复杂")
        self.assertEqual(self.module.METRICS["eval-3-color-logic"][0], "组件色彩复杂")
        self.assertEqual(self.module.METRICS["eval-3-page-color-logic"][0], "页面色彩复杂")

    def test_collect_uses_explicit_multi_screenshot_manifests_without_id_collision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            artifact_dir = project / ".artifacts" / "过程文件-评测结果与审计" / "batch-1"
            artifact_dir.mkdir(parents=True)
            manifests = []
            screenshots = []
            for index in (1, 2):
                screenshot = project / "screenshots" / f"咖啡_全部_{index}.png"
                screenshot.parent.mkdir(parents=True, exist_ok=True)
                screenshot.write_bytes(b"image")
                manifest = project / "screenshots-out" / f"elements_咖啡_全部_{index}_run.json"
                manifest.parent.mkdir(parents=True, exist_ok=True)
                payload = {
                    "query": "咖啡",
                    "screenshot": str(screenshot),
                    "cards": [{
                        "cardId": "C1",
                        "卡片类型": "商家卡片-文字下挂",
                        "ownershipScope": "business",
                        "businessCode": "dine_in",
                        "regions": [{
                            "name": "标题区",
                            "elements": [{"id": "E1", "内容简述": f"原文:咖啡店{index}"}],
                        }],
                    }],
                }
                manifest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                manifests.append(manifest)
                screenshots.append(screenshot)

            result_path = artifact_dir / "评测原始结果_咖啡_full19.json"
            result_path.write_text(json.dumps([{
                "dimension": "phase3-card_or_component-eval",
                "skill": "eval-8-info-redundancy",
                "units": [{
                    "tab": "全部",
                    "rating": "不达标",
                    "reason": "存在重复信息",
                    "details": {
                        "screenshot": str(screenshot),
                        "evidenceMode": "original-page",
                        "issues": [{
                            "elementId": "E1",
                            "component": "C1",
                            "rating": "不达标",
                            "description": f"第{index}屏存在重复信息。",
                            "recommendation": f"删除第{index}屏重复信息，并确保复测无重复。",
                        }],
                    },
                } for index, screenshot in enumerate(screenshots, start=1)],
            }], ensure_ascii=False), encoding="utf-8")

            data = self.module.collect(project, artifact_dir, manifests, [result_path])

            self.assertEqual(data["manifests"], 2)
            self.assertEqual(data["queryCount"], 1)
            self.assertEqual(data["unknown"], [])
            self.assertEqual(len(data["groups"]), 1)
            self.assertEqual(len(data["groups"][0]["evidence"]), 2)
            self.assertEqual(data["businesses"][0]["evaluatedCards"], 2)

    def test_collect_resolves_portable_runid_result_from_unit_screenshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            artifact_dir = project / ".artifacts" / "过程文件-评测结果与审计" / "batch-1"
            result_dir = artifact_dir / "batch-1-IMG_1" / "results"
            result_dir.mkdir(parents=True)
            screenshot = project / "screenshots" / "IMG_1.PNG"
            screenshot.parent.mkdir(parents=True)
            screenshot.write_bytes(b"image")
            manifest = project / "screenshots-out" / "elements_IMG_1_batch-1.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({
                "query": "咖啡",
                "screenshot": str(screenshot),
                "cards": [{
                    "cardId": "C1",
                    "卡片类型": "商家卡片-文字下挂",
                    "ownershipScope": "business",
                    "businessCode": "dine_in",
                    "regions": [{"name": "标题区", "elements": []}],
                }],
            }, ensure_ascii=False), encoding="utf-8")
            result_path = result_dir / "评测原始结果_batch-1-IMG_1.json"
            result_path.write_text(json.dumps([{
                "dimension": "phase3-card_or_component-eval",
                "skill": "eval-8-info-redundancy",
                "units": [{
                    "tab": "全部",
                    "rating": "优秀",
                    "reason": "无冗余",
                    "details": {"screenshot": str(screenshot), "issues": []},
                }],
            }], ensure_ascii=False), encoding="utf-8")

            data = self.module.collect(project, artifact_dir, [manifest], [result_path])

            self.assertEqual(data["queryCount"], 1)
            self.assertIn("咖啡", data["queryDetails"])
