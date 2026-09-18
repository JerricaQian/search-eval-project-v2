#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the cross-query, issue-centric search-result experience dashboard.

The dashboard keeps search terms as evidence only. Business conclusions are
aggregated from result cards that are classified by their visible content.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

PHASE5_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
for module_dir in (PHASE5_DIR,):
    if str(module_dir) not in sys.path:
        sys.path.insert(0, str(module_dir))
from dashboard_renderer import render_dashboard

BUSINESS_LINES = {
    "dine_in": "到餐", "food_delivery": "餐饮外卖", "flash_delivery": "闪购",
    "service_retail": "服务零售", "healthcare": "医药健康", "hotel_travel": "酒店旅行",
    "xiaoxiang": "小象超市", "maoyan": "猫眼",
}
# 报告业务 Tab 的唯一允许集合。每批生成前必须校验输出业务代码与名称；
# 未被治理口径认可的分类（如已废弃的 tuangou_goods）一律阻断交付。
EXPECTED_REPORT_BUSINESS_TABS = BUSINESS_LINES.copy()
PLATFORM_SCOPES = {"宏观组件", "特殊广告卡", "运营聚合卡", "相似推荐提示"}
DEDICATED_BUSINESS_TERMS = (
    ("healthcare", ("医院", "体检", "医药", "药店", "药房", "诊所", "医疗", "门诊", "口腔", "眼科", "中医", "医美", "整形", "OTC", "处方药", "保健品", "医疗器械", "生理盐水", "快药", "布洛芬", "止痛药", "退烧药")),
    ("hotel_travel", ("酒店", "民宿", "房型", "景点", "度假", "露营", "营地", "漂流", "门票", "宾馆", "公寓", "钟点房", "跟团游", "自由行", "租车")),
    ("maoyan", ("电影", "影院", "演出", "场次", "票价", "剧场")),
    ("xiaoxiang", ("小象超市", "小象")),
)
SERVICE_RETAIL_TERMS = (
    "休闲娱乐", "休闲园区", "KTV", "洗浴", "美发", "美甲", "美睫", "美容院", "美容美体",
    "皮肤管理", "祛痘", "面部清洁", "丽人", "摄影", "婚礼", "结婚", "教育", "培训", "家政",
    "亲子", "儿童乐园", "剧本杀", "沉浸式探秘", "团建拓展", "按摩", "理发", "维修",
    "健身", "健身房", "健身中心", "健身工作室", "私教", "DIY手工坊", "手作", "手工坊",
    "主机游戏", "游戏体验馆", "游戏馆", "桌游", "头疗", "采耳", "养发", "台球", "台球厅", "棋牌",
    "酒吧", "学习规划", "机器人编程", "留学考试", "雅思", "托福", "自习室",
    "洗车", "汽车美容", "美容洗车", "养车", "汽服", "网吧", "网咖", "网费",
)
# 这些服务业态的展示文案可能同时出现“剧场/演绎”“住宿/酒店式”等
# 其他业务弱提示词，但其业务身份仍由更具体的服务零售语义决定。
SERVICE_RETAIL_EXCLUSIVE_TERMS = (
    "剧本杀", "沉浸式探秘", "足道", "足浴", "按摩", "spa",
    "洗浴", "汤泉", "汗蒸",
)
FLASH_DELIVERY_TERMS = ("闪购", "分钟达", "即时零售", "小时达", "闪电仓", "歪马送酒")
FLASH_CATEGORY_TERMS = ("零食", "饮料", "日用百货", "卫生巾", "安睡裤", "纸巾", "粮油", "调味", "水果", "西瓜", "果切", "榴莲", "蔬菜", "黄瓜", "肉禽蛋", "水产", "生鲜", "鲜生", "盒马", "超市", "鲜花", "花束", "啤酒", "白酒", "红酒", "矿泉水", "咖啡豆", "便利店", "成人用品", "情趣", "避孕套", "健康用品", "计生用品")
FLASH_CATEGORY_OVERRIDE_TERMS = ("咖啡豆", "咖啡粉", "咖啡胶囊")
FOOD_TERMS = (
    "餐厅", "饭店", "火锅", "烧烤", "肉串", "猪脚饭", "烧腊", "蛋糕", "面包甜点", "早餐",
    "柠檬水", "百香果", "咖啡", "coffee", "奶茶", "茶饮", "果茶", "奶酪", "酸奶", "菜品",
    "美食", "小吃", "快餐", "汉堡", "粉面", "米粉", "米线", "盒饭", "日料", "中餐", "西餐",
    "包子", "小笼包", "黄焖鸡", "疙瘩汤", "汤粉", "炸鸡", "鸡腿", "寿司", "鳗鱼饭", "刺身",
    "烧鸟", "披萨", "比萨", "肯德基", "kfc", "必胜客", "达美乐", "星巴克", "喜茶", "1点点",
    "一点点", "老乡鸡", "烤肉", "自助餐", "自助", "茉莉奶白", "茶百道", "霸王茶姬",
    "螺蛳粉", "云饺", "饺子", "水饺", "云吞", "麻辣烫", "麻辣香锅", "鸡架", "弹弹面",
    "盖饭", "牛肉饭", "湘菜", "小炒", "肠粉", "粥", "鸡柳大人", "麦当劳",
    "拌饭", "捞饭", "鲁肉饭", "猪肘饭", "炒饭", "烧饼", "热卤", "鸭头",
    "烤鱼", "烤鸭", "江西菜", "日本料理", "乌冬面", "定食", "寿喜锅", "泡茶", "便宜坊",
)
LOCAL_RETAIL_TERMS = ("零食", "零食乐园", "品牌零食", "省钱超市")
DELIVERY_TERMS = ("外卖", "配送", "起送", "送达", "外送", "分钟")
LEVELS = {
    "phase3-single_element-eval": ("单一元素维度", "element", "#6366f1"),
    "phase3-card_or_component-eval": ("组件/卡片维度", "component", "#10b981"),
    "phase3-page_framework-eval": ("页面框架维度", "page", "#60a5fa"),
}
LEVEL_ORDER = tuple(LEVELS.items())
PASS_RATINGS = {"达标", "🟡"}
FAIL_RATINGS = {"不达标", "🔴"}


def priority_from_vote_counts(fail_count: int, pass_count: int) -> str | None:
    """Return the deterministic governance priority for one business/level/metric unit."""
    if fail_count >= 4 or pass_count >= 6:
        return "P0"
    if fail_count >= 2 or pass_count >= 4:
        return "P1"
    if 1 <= pass_count <= 3:
        return "P2"
    # The three explicit thresholds do not cover a single failing vote with no
    # passing votes. Keep that detected issue visible in the lowest priority
    # instead of silently dropping it from the dashboard.
    if fail_count == 1 and pass_count == 0:
        return "P2"
    return None


def priority_reason_from_vote_counts(fail_count: int, pass_count: int, priority: str) -> str:
    reason = (
        f"同一业务线、同一维度、同一指标本轮统计：不达标 {fail_count} 票，达标 {pass_count} 票。"
        f"按固定阈值（不达标≥4或达标≥6为P0；不达标≥2或达标≥4为P1；达标1至3为P2）判定为 {priority}。"
    )
    if fail_count == 1 and pass_count == 0:
        reason += "该组合未命中三条显式阈值，为避免已检测问题从报告消失，按剩余低频问题收纳为P2。"
    return reason


METRICS = {
    # 该名称用于“待优化项”问题卡，统一描述问题本身而不是理想状态。
    "eval-1-supply-quality-scanner": ("供给呈现问题", "supply_quality"),
    "eval-1-supply-completeness": ("供给呈现问题", "supply_completeness"),
    "eval-1-supply-module-completeness": ("供给呈现问题（页面框架）", "supply_module_completeness"),
    "eval-2-color-logic-single-element": ("单一元素色彩复杂", "color_logic"),
    "eval-2-visual-order-alignment": ("视觉秩序问题", "visual_order"),
    "eval-3-page-color-logic": ("页面色彩复杂", "page_color_logic"),
    "eval-3-color-logic": ("组件色彩复杂", "color_logic"),
    "eval-3-element-compliance-scanner": ("静态元素复杂", "element_compliance"),
    "eval-4-element-complexity": ("元素复杂", "element_complexity"),
    "eval-4-static-component-complexity": ("组件复杂", "static_component_complexity"),
    "eval-4-info-authenticity-single-element": ("信息/功能歧义", "info_authenticity"),
    "eval-5-info-hierarchy": ("信息层级不清", "information_hierarchy"),
    "eval-5-browsing-flow-smoothness": ("浏览动线问题", "browsing_flow"),
    "eval-5-info-redundancy": ("信息冗余", "information_redundancy"),
    "eval-6-info-partitioning": ("信息分区问题", "information_partitioning"),
    "eval-6-info-comparability": ("信息不可比", "information_comparability"),
    "eval-7-info-authenticity": ("信息/功能歧义", "info_authenticity"),
    "eval-7-browsing-flow-smoothness": ("浏览动线问题", "browsing_flow"),
    "eval-7-info-redundancy": ("功能/信息冗余", "page_information_redundancy"),
    "eval-8-info-redundancy": ("信息冗余", "information_redundancy"),
}


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def card_semantic_text(card: dict[str, Any]) -> str:
    """Return current merchant/product semantics, excluding fulfilment facts."""
    values: list[str] = [str(card.get("卡片类型", "")), str(card.get("cardTypeCode", ""))]
    for region in card.get("regions", []):
        for element in region.get("elements", []):
            facts = element.get("textFacts") if isinstance(element.get("textFacts"), dict) else {}
            semantic_role = str(facts.get("semanticRole") or "").strip()
            if semantic_role in {"fulfillment", "location", "distance"} or "履约" in str(region.get("name", "")):
                continue
            values.extend(str(element.get(key, "")) for key in ("内容简述", "content", "text", "visibleText"))
            values.append(str(facts.get("rawText", "")))
    return " ".join(values).lower()


def fulfillment_text(card: dict[str, Any]) -> str:
    """Return only Phase2's confirmed fulfilment table, never the search query."""
    values: list[str] = []
    for region in card.get("regions", []):
        for element in region.get("elements", []):
            facts = element.get("textFacts") if isinstance(element.get("textFacts"), dict) else {}
            if facts.get("semanticRole") == "fulfillment" or "履约" in str(region.get("name", "")):
                values.extend(str(element.get(key, "")) for key in ("内容简述", "content", "text", "visibleText"))
                values.append(str(facts.get("rawText", "")))
    return " ".join(values).lower()


def card_type_code(card_type: str) -> str:
    if "商品" in card_type:
        return "product_card"
    if "图文下挂" in card_type:
        return "merchant_image_append_card"
    if "文字下挂" in card_type:
        return "merchant_text_append_card"
    if "无下挂" in card_type:
        return "merchant_plain_card"
    if "主点" in card_type:
        return "poi_card"
    if "酒店" in card_type:
        return "hotel_card"
    return "merchant_card"


def has_any(text: str, terms: tuple[str, ...]) -> bool:
    normalized = text.casefold()
    return any(term.casefold() in normalized for term in terms)


def classified_business(code: str, kind: str, card_type: str, confidence: str) -> dict[str, str]:
    return {
        "scope": "business", "businessCode": code, "businessName": BUSINESS_LINES[code],
        "confidence": confidence, "cardTypeCode": kind, "cardTypeName": card_type,
    }


def classify_card(card: dict[str, Any]) -> dict[str, str]:
    """Classify one card by current visible facts, in this fixed precedence.

    Highly specific service-retail semantics win before weaker cross-business
    wording such as theater or hotel-style rest areas. Other dedicated business
    semantics (healthcare, travel, Maoyan, Xiaoxiang) then take precedence.
    For delivery cards, a flash label or a recognised flash product category
    distinguishes flash delivery from food delivery. A card type by itself is
    never a flash-delivery fact. Missing evidence remains ``unknown``.
    """
    card_type = str(card.get("卡片类型", ""))
    kind = card_type_code(card_type)
    # Business attribution is deliberately recomputed from the accepted
    # current-screen facts below.  A Phase2 businessCode is audit metadata,
    # not a fallback or an override: otherwise a query-level preset could be
    # smuggled into Phase5 without visible merchant semantics or fulfilment.
    explicit_code = str(card.get("businessCode") or "").strip()
    has_explicit_business = card.get("ownershipScope") == "business" and bool(explicit_code)
    if has_explicit_business and explicit_code not in BUSINESS_LINES:
        return {
            "scope": "unknown", "businessCode": "unknown", "businessName": "未知待确认",
            "confidence": f"unsupported_explicit_business_code:{explicit_code}",
            "cardTypeCode": kind, "cardTypeName": card_type,
        }
    semantic, fulfillment = card_semantic_text(card), fulfillment_text(card)
    has_visible_text = any(
        str((element.get("textFacts") or {}).get("rawText") or element.get("内容简述")
            or element.get("content") or element.get("text") or element.get("visibleText") or "").strip()
        for region in card.get("regions", [])
        for element in region.get("elements", [])
        if isinstance(element, dict)
    )
    if (not has_visible_text
            and str((card.get("structure") or {}).get("visibleStatus") or "") == "naturally_cropped"):
        return {
            "scope": "cropped", "businessCode": "", "businessName": "自然触底未形成可归属卡片",
            "confidence": "naturally_cropped_without_visible_semantics",
            "cardTypeCode": kind, "cardTypeName": card_type,
        }
    if (card_type in PLATFORM_SCOPES or card.get("cardId") == "macro-top"
            or (card_type == "异构卡" and "大家还在搜" in semantic)):
        return {"scope": "platform", "businessCode": "platform", "businessName": "平台公共组件",
                "confidence": "high", "cardTypeCode": "platform_component", "cardTypeName": card_type}
    visible_result: dict[str, str]
    if has_any(semantic, SERVICE_RETAIL_EXCLUSIVE_TERMS):
        visible_result = classified_business("service_retail", kind, card_type, "specific_service_semantic")
    else:
        visible_result = {}
    for business, terms in DEDICATED_BUSINESS_TERMS:
        if not visible_result and has_any(semantic, terms):
            visible_result = classified_business(business, kind, card_type, "semantic")

    is_service = has_any(semantic, SERVICE_RETAIL_TERMS)
    is_flash_label = has_any(semantic, FLASH_DELIVERY_TERMS) or has_any(fulfillment, FLASH_DELIVERY_TERMS)
    is_flash_category = has_any(semantic, FLASH_CATEGORY_TERMS)
    is_flash_category_override = has_any(semantic, FLASH_CATEGORY_OVERRIDE_TERMS)
    is_food = has_any(semantic, FOOD_TERMS)
    is_delivery = has_any(fulfillment, DELIVERY_TERMS)
    is_local_retail = has_any(semantic, LOCAL_RETAIL_TERMS)

    if not visible_result and is_service:
        visible_result = classified_business("service_retail", kind, card_type, "semantic")
    # “闪购/分钟达”等是当前卡片直接可见的即时零售履约身份；即使 OCR 将
    # 起送/配送字段归入价格区，也不应因此把已显示闪购标识的卡片留为 unknown。
    if not visible_result and (is_delivery or is_flash_label):
        if is_flash_label or (is_flash_category and (not is_food or is_flash_category_override)):
            visible_result = classified_business("flash_delivery", kind, card_type, "delivery+flash_category")
        elif is_food:
            visible_result = classified_business("food_delivery", kind, card_type, "delivery+food_category")
        else:
            visible_result = {
                "scope": "unknown", "businessCode": "unknown", "businessName": "未知待确认",
                "confidence": "delivery_category_not_confirmed", "cardTypeCode": kind, "cardTypeName": card_type,
            }
    if not visible_result and is_food:
        visible_result = classified_business("dine_in", kind, card_type, "food_category+non_delivery")
    if not visible_result and is_local_retail:
        visible_result = classified_business("service_retail", kind, card_type, "local_retail_semantic")
    if not visible_result and str((card.get("structure") or {}).get("visibleStatus") or "") == "naturally_cropped":
        return {
            "scope": "cropped", "businessCode": "", "businessName": "自然触底未形成可归属卡片",
            "confidence": "naturally_cropped_without_sufficient_business_facts",
            "cardTypeCode": kind, "cardTypeName": card_type,
        }
    if not visible_result:
        # A card container alone is not business evidence.  Defaulting it to
        # a permitted tab makes a dashboard look complete while silently
        # corrupting that tab's score and issue rate.
        visible_result = {
            "scope": "unknown", "businessCode": "unknown", "businessName": "未知待确认",
            "confidence": "insufficient_current_facts", "cardTypeCode": kind, "cardTypeName": card_type,
        }

    if not has_explicit_business:
        return visible_result
    if visible_result["scope"] != "business":
        return {
            "scope": "unknown", "businessCode": "unknown", "businessName": "未知待确认",
            "confidence": "explicit_business_without_visible_card_evidence",
            "cardTypeCode": kind, "cardTypeName": card_type,
        }
    if explicit_code != visible_result["businessCode"]:
        return {
            "scope": "unknown", "businessCode": "unknown", "businessName": "未知待确认",
            "confidence": f"explicit_business_conflicts_visible_facts:{explicit_code}!={visible_result['businessCode']}",
            "cardTypeCode": kind, "cardTypeName": card_type,
        }
    return {**visible_result, "confidence": f"phase2_explicit+{visible_result['confidence']}"}


def humanize_element_label(element: dict[str, Any]) -> str:
    """Turn a Phase2 element record into a concise reader-facing object label."""
    element_type = str(element.get("元素类型") or element.get("elementType") or "元素").strip()
    facts = element.get("textFacts") if isinstance(element.get("textFacts"), dict) else {}
    content = str(facts.get("rawText") or element.get("内容简述") or element.get("content") or "").strip()
    content = re.sub(r"^(?:原文|内容)\s*[:：]\s*", "", content).strip()
    if content:
        return f"{element_type}：「{content}」"
    return element_type or "页面元素"


def humanize_issue_element(issue: dict[str, Any]) -> str:
    """Prefer accepted issue copy when a historical manifest cannot resolve the element."""
    element_type = str(issue.get("elementType") or "元素").strip()
    content = str(issue.get("content") or "").strip()
    content = re.sub(r"^(?:原文|内容)\s*[:：]\s*", "", content).strip()
    return f"{element_type}：「{content}」" if content else (element_type or "页面元素")


def card_location_labels(cards: list[dict[str, Any]]) -> dict[str, str]:
    """Return reader-facing list positions without exposing card IDs or coordinates."""
    labels: dict[str, str] = {}
    standard_index = 0
    for card in cards:
        card_id = str(card.get("cardId") or "")
        structure = card.get("structure") if isinstance(card.get("structure"), dict) else {}
        card_type = str(card.get("卡片类型") or card.get("cardTypeCode") or "")
        heterogeneous = bool(structure.get("isHeterogeneous")) or card_type in {"异构卡", "heterogeneous"}
        if not heterogeneous:
            standard_index += 1
            labels[card_id] = f"商卡{standard_index}"
            continue
        semantic = card_semantic_text(card)
        if "大家还在搜" in semantic:
            subtype = "大家还在搜"
        elif "直播" in semantic:
            subtype = "直播大卡"
        else:
            subtype = str(card.get("variant") or "其他")
        labels[card_id] = f"异构卡-{subtype}"
    return labels


def issue_code(skill: str, issue: dict[str, Any]) -> str:
    desc = str(issue.get("description", "")).lower()
    if "层级" in desc or "主次" in desc:
        return "MULTIPLE_PRIMARY_EMPHASIS"
    if "颜色" in desc or "色彩" in desc:
        return "COLOR_LOGIC_CONFLICT"
    if "冗余" in desc or "重复" in desc:
        return "REDUNDANT_INFORMATION"
    if "分区" in desc or "边界" in desc:
        return "WEAK_INFORMATION_PARTITION"
    if "完整" in desc or "缺失" in desc or "截断" in desc:
        return "CONTENT_COMPLETENESS_FAILURE"
    if "真实" in desc or "歧义" in desc or "误导" in desc:
        return "AUTHENTICITY_OR_CLARITY_RISK"
    return f"{skill.upper().replace('-', '_')}_ISSUE"


def query_from_result(path: Path) -> str | None:
    # Recheck artifacts may append a suffix such as `_eval-4-recheck`; their
    # query is reliably the parent query directory, not a fragile filename slice.
    if path.parent.name in {"phase3", "phase3-recheck", "phase4", "phase4-recheck"}:
        return path.parent.parent.name
    if path.parent.name == "results" and path.parent.parent.name:
        parent_name = path.parent.parent.name
        # A few retained batch directories append `_results` to the query name.
        # Prefer the filename parser below for the canonical query in that case.
        if not parent_name.endswith("_results"):
            return parent_name
    match = re.match(r"\.eval_results_(.+?)_(?:首评-单一元素-\d+_dual|试评测(?:_[^.]*)?|single_element|card_component(?:_page_framework)?|page_framework)\.json$", path.name)
    if match:
        return match.group(1)
    match = re.match(r"评测原始结果_(.+?)(?:_[^/]*)?_(?:single_element|card_or_component|page_framework|single_element_card_or_component|card_or_component_page_framework|single_element_card_or_component_page_framework)\.json$", path.name)
    if match:
        return match.group(1)
    # 单词 Phase2-4 子任务的最终交接文件命名为 all-results_<query>... 或
    # <query>.all-results...；目录名是本批次唯一的 query 事实源。
    if "all-results" in path.name and path.parent.name == "results":
        return path.parent.parent.name
    return None


def normalize_results(raw_results: Any) -> list[dict[str, Any]]:
    """Normalize workflow lists and direct phase3 raw result documents.

    The caller resolves Phase2-4 handoff wrappers before invoking this function.
    """
    if isinstance(raw_results, list):
        return raw_results
    if not isinstance(raw_results, dict):
        return []
    dimension = str(raw_results.get("dimension", ""))
    evaluations = raw_results.get("evaluations")
    if not dimension or not isinstance(evaluations, list):
        return []
    normalized: list[dict[str, Any]] = []
    for evaluation in evaluations:
        if not isinstance(evaluation, dict):
            continue
        normalized.append({
            "dimension": dimension,
            "skill": str(evaluation.get("skill", "")),
            "units": [{
                "tab": str(evaluation.get("tab", "全部")),
                "rating": str(evaluation.get("rating", "")),
                "reason": str(evaluation.get("reason", "")),
                "details": evaluation.get("details") or {},
            }],
        })
    return normalized


def collect(
    project: Path,
    artifact_dir: Path,
    manifest_paths: list[Path] | None = None,
    result_paths: list[Path] | None = None,
    evaluation_scope: dict[str, Any] | None = None,
    excluded_issue_keys: set[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    # A query can contain multiple screenshots. Keep one accepted manifest per
    # source screenshot so repeated C1/E1 identifiers never collide across pages.
    manifests: dict[str, dict[str, tuple[Path, dict[str, Any]]]] = defaultdict(dict)

    def register_manifest(path: Path, data: dict[str, Any]) -> None:
        query = str(data.get("query") or "").strip()
        screenshot = str(data.get("screenshot") or "").strip()
        if not query or not screenshot or not isinstance(data.get("cards"), list):
            return
        current = manifests[query].get(screenshot)
        if current is None or path.stat().st_mtime > current[0].stat().st_mtime:
            manifests[query][screenshot] = (path, data)

    source_manifests = manifest_paths if manifest_paths is not None else list((project / "screenshots-out").glob("elements_*.json"))
    for path in source_manifests:
        data = read_json(path)
        # recognition-audit files share the `elements_` prefix but are not manifests.
        # Only select a document with the required Phase2 card payload, otherwise a
        # newer audit can shadow the actual screenshot declaration for a query.
        if isinstance(data, dict):
            register_manifest(path, data)

    # Golden-JSON exemption runs do not create legacy ``screenshots-out``
    # manifests.  Their read-only Atomic v3 fact packs retain the canonical
    # source manifest, whose loader verifies schema, publication status and
    # source-image hash before exposing the same Phase3 card facts.  Consume
    # those facts directly so the governance report remains tied to the
    # accepted source rather than to a reconstructed Phase2 projection.
    try:
        from phase2_bundle_loader import load_phase2_facts
    except ImportError:
        load_phase2_facts = None
    if load_phase2_facts is not None:
        fact_pack_paths = [
            *artifact_dir.rglob("atomic-facts*.json"),
            *artifact_dir.rglob("*.atomic-fact-pack.v1.json"),
            # Golden-source evaluation runs retain the loader-verified manifest
            # path in their Stage A acceptance audit.  They do not necessarily
            # materialize a second Atomic fact-pack file, so consume that audit
            # as the canonical pointer instead of silently dropping the query.
            *artifact_dir.rglob("golden-acceptance-audit.json"),
        ]
        for fact_pack_path in fact_pack_paths:
            fact_pack = read_json(fact_pack_path)
            if not isinstance(fact_pack, dict):
                continue
            if fact_pack_path.name == "golden-acceptance-audit.json":
                if fact_pack.get("valid") is not True:
                    continue
                manifest_name = fact_pack.get("manifest")
            else:
                source = fact_pack.get("source")
                manifest_name = source.get("manifest") if isinstance(source, dict) else None
            if not isinstance(manifest_name, str) or not manifest_name:
                continue
            try:
                facts = load_phase2_facts(manifest_path=Path(manifest_name))
            except (OSError, ValueError, KeyError):
                continue
            query = str(facts.get("query", ""))
            if not query:
                continue
            # A fact source retained inside the selected artifact batch is
            # stronger than any same-query legacy projection in screenshots-out.
            # Overwrite it so an older, shorter card list cannot shadow the
            # loader-verified golden manifest and orphan current issue IDs.
            register_manifest(fact_pack_path, {
                "query": query,
                "screenshot": str(facts.get("screenshot", "")),
                "annotatedImage": "",
                "cards": facts.get("cards", []),
            })

    classifications: dict[tuple[str, str], dict[str, dict[str, str]]] = {}
    element_cards: dict[tuple[str, str], dict[str, str]] = {}
    element_labels: dict[tuple[str, str], dict[str, str]] = {}
    location_labels: dict[tuple[str, str], dict[str, str]] = {}
    manifest_data: dict[tuple[str, str], dict[str, Any]] = {}
    for query, by_screenshot in manifests.items():
        for screenshot, (_, manifest) in by_screenshot.items():
            context = (query, screenshot)
            manifest_data[context] = manifest
            classifications[context] = {}
            element_cards[context] = {}
            element_labels[context] = {}
            location_labels[context] = card_location_labels(manifest.get("cards", []))
            for card in manifest.get("cards", []):
                card_id = str(card.get("cardId", ""))
                classifications[context][card_id] = classify_card(card)
                for region in card.get("regions", []):
                    for element in region.get("elements", []):
                        element_id = str(element.get("id", ""))
                        element_cards[context][element_id] = card_id
                        element_labels[context][element_id] = humanize_element_label(element)

    stats: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    query_details: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unknown: list[dict[str, str]] = []
    for (query, screenshot), cards in classifications.items():
        for card_id, classification in cards.items():
            if classification["scope"] == "unknown":
                unknown.append({
                    "query": query,
                    "screenshot": screenshot,
                    "cardId": card_id,
                    "reason": "当前商卡语义与履约事实不足以判定业务",
                })
    # Phase3 results are retained under each query's isolated phase3 directory.
    # Discover recursively, then select one combined result per query so compatibility
    # aliases or per-dimension fallback files do not double-count a query.
    candidates_by_query: dict[str, list[Path]] = defaultdict(list)

    def resolve_result_query(path: Path) -> str | None:
        query = query_from_result(path)
        if query in manifests:
            return query
        # Portable query tasks name their isolated result directories with the
        # immutable runId rather than the human query.  Resolve that runId via
        # its adjacent task contract before falling back to fragile filename
        # or unit-screenshot heuristics.  This is especially important for
        # versioned retry runs (``...-q24-r2``), whose result filenames cannot
        # safely encode a Chinese query and whose units may legitimately have
        # no issues.
        run_id = path.parent.parent.name if path.parent.name == "results" else ""
        if run_id:
            task = read_json(project / "runs" / run_id / "task.json")
            workflow_args = task.get("workflowArgs") if isinstance(task, dict) else None
            task_query = str(workflow_args.get("query") or "").strip() if isinstance(workflow_args, dict) else ""
            if task_query in manifests:
                return task_query
        filename_matches = [
            candidate for candidate in manifests
            if path.name.startswith(f"评测原始结果_{candidate}_")
            or path.name.startswith(f".eval_results_{candidate}_")
        ]
        if filename_matches:
            return max(filename_matches, key=len)

        # Portable per-run results are named with the immutable runId, while
        # the query remains tied to the existing screenshot path inside each
        # unit. Resolve that already-present fact against the accepted
        # manifests instead of depending on a query-bearing filename.
        raw_results = normalize_results(read_json(path))
        screenshots = {
            str(unit.get("details", {}).get("screenshot") or "").strip()
            for result in raw_results
            for unit in result.get("units", [])
            if isinstance(unit, dict) and isinstance(unit.get("details"), dict)
        }
        screenshots.discard("")
        screenshot_matches = {
            candidate
            for candidate, by_screenshot in manifests.items()
            if screenshots.intersection(by_screenshot)
        }
        return next(iter(screenshot_matches)) if len(screenshot_matches) == 1 else None

    # 各词独立执行会保留不同命名的最终合并结果；优先消费已经通过
    # Phase4 回写的 all-results，确保治理看板引用的是最终证据路径而非 Phase3 初稿。
    if result_paths is None:
        discovered_result_paths: list[Path] = []
        for pattern in (
            ".eval_results_*.json", "评测原始结果_*.json", "*all-results*.json",
            "eval_results_*.json", "eval-results*.json", "phase3-results.json",
        ):
            discovered_result_paths.extend(artifact_dir.rglob(pattern))
    else:
        discovered_result_paths = result_paths
    for path in discovered_result_paths:
        if "audit" in path.name.lower() or "target" in path.name.lower():
            continue
        query = resolve_result_query(path)
        if query:
            candidates_by_query[query].append(path)

    selected_result_paths: list[Path] = []
    for query, candidates in candidates_by_query.items():
        # A verified recheck supersedes the initial result for the same query;
        # otherwise prefer a combined (all-skill) document over partial files.
        rechecks = [path for path in candidates if "phase3-recheck" in path.parts]
        # all-results 是 Phase4 回写后的最终交接文件，优先级高于初始 Phase3 原始结果。
        finalized = [path for path in (rechecks or candidates) if "all-results" in path.name]
        combined = [path for path in (finalized or rechecks or candidates) if "card_or_component_page_framework" in path.name]
        pool = combined or finalized or rechecks or candidates
        selected_result_paths.append(max(pool, key=lambda path: path.stat().st_mtime))

    used_queries: set[str] = set()
    for result_path in sorted(selected_result_paths):
        query = resolve_result_query(result_path)
        if not query:
            continue
        raw_results = read_json(result_path)
        # 每词子任务会额外保留一个 all-results 交接包装文件。它只保存
        # 已验收的原始结果路径和摘要，需在这里解引用，不能把它误当空结果跳过。
        if isinstance(raw_results, dict):
            handoff_path = raw_results.get("resultFile") or raw_results.get("results")
            if isinstance(handoff_path, str) and handoff_path:
                referenced = read_json(Path(handoff_path))
                if referenced is not None:
                    raw_results = referenced
        results = normalize_results(raw_results)
        if not results:
            continue
        used_queries.add(query)
        query_manifest_contexts = [(query, screenshot) for screenshot in manifests[query]]
        default_context = query_manifest_contexts[0] if len(query_manifest_contexts) == 1 else None
        for result in results:
            if not isinstance(result, dict):
                continue
            dimension = str(result.get("dimension", ""))
            skill = str(result.get("skill", ""))
            level_name, level_code, _ = LEVELS.get(dimension, ("其他维度", "other", "#64748b"))
            metric_name, metric_code = METRICS.get(skill, (skill, skill))
            for unit in result.get("units", []):
                if not isinstance(unit, dict):
                    continue
                tab = str(unit.get("tab", "全部"))
                detail = unit.get("details") or {}
                issues = detail.get("issues") or []
                if excluded_issue_keys:
                    issues = [
                        issue for issue in issues
                        if not (
                            isinstance(issue, dict)
                            and (query, str(issue.get("elementId") or "")) in excluded_issue_keys
                        )
                    ]
                requested_screenshot = str(detail.get("screenshot") or "")
                context = (query, requested_screenshot)
                if context not in manifest_data:
                    context = default_context
                if context is None or context not in manifest_data:
                    unknown.append({
                        "query": query,
                        "screenshot": requested_screenshot,
                        "cardId": "",
                        "reason": "评测单元无法与本批 Phase2 manifest 的原图一一对应",
                    })
                    continue
                manifest = manifest_data[context]
                screenshot = str(manifest.get("screenshot", ""))
                screenshot_ref = Path(screenshot).name or screenshot
                annotated = str(manifest.get("annotatedImage", ""))
                query_details[query].append({
                    "level": level_code, "levelName": level_name, "skill": skill,
                    "metricName": metric_name, "metricCode": metric_code, "tab": tab,
                    "rating": str(unit.get("rating", "")), "reason": str(unit.get("reason", "")),
                    "evidenceMode": str(detail.get("evidenceMode", "")), "issues": issues,
                    # 原图来自统一清单；Phase4 将同一路径写入 issue.evidenceImage。
                    "screenshot": screenshot, "annotatedImage": annotated,
                })
                # 看板的待优化对象包含“达标”和“不达标”：只有“优秀”不进入问题治理。
                problem_issues = [
                    issue for issue in issues
                    if isinstance(issue, dict) and str(issue.get("rating", unit.get("rating", ""))) in {"达标", "不达标", "🟡", "🔴"}
                ]
                for issue in problem_issues:
                    element_id = str(issue.get("elementId", ""))
                    element_label = element_labels[context].get(element_id, humanize_issue_element(issue))
                    card_id = element_cards[context].get(element_id, str(issue.get("component", "")))
                    classification = classifications[context].get(card_id)
                    # 页面框架是评测维度而非业务线。页面级达标/不达标结论按同一截图
                    # 中可见业务归属，写入各业务 Tab 的问题明细；同一业务每页仅保留一份，
                    # 不创建“页面框架”业务 Tab，也不在“全部”页签展示问题明细。
                    if level_code == "page" or issue.get("isAssessmentLevel"):
                        visible_businesses = {
                            item["businessCode"]: item
                            for item in classifications[context].values()
                            if item["scope"] == "business"
                        }
                        target_classifications = [
                            {
                                **item, "cardTypeCode": "page",
                                "cardTypeName": "页面级结论",
                            }
                            for item in visible_businesses.values()
                        ]
                        card_id = f"page:{query}:{screenshot_ref}"
                    elif classification and classification["scope"] == "business":
                        target_classifications = [classification]
                    elif classification and classification["scope"] == "platform":
                        # Platform components are deliberately outside business
                        # Tab aggregation.  Their ownership is known, so they
                        # must not be reported as an unresolved business card.
                        continue
                    elif level_code == "element":
                        target_classifications = [
                            item for item in classifications[context].values()
                            if item["scope"] == "business"
                        ]
                    else:
                        unknown.append({
                            "query": query,
                            "cardId": card_id,
                            "reason": "平台、混合或无法确认业务归属",
                        })
                        continue
                    if not target_classifications:
                        unknown.append({
                            "query": query,
                            "cardId": card_id,
                            "reason": "未找到可归属的业务卡",
                        })
                        continue
                    finding = issue_code(skill, issue)
                    for target in target_classifications:
                        related_card_ids = [str(value) for value in issue.get("relatedCardIds", []) if value]
                        target_card_id = (
                            f"{screenshot_ref}:cross:" + "+".join(sorted(related_card_ids))
                            if related_card_ids else f"{screenshot_ref}:" + (card_id if classification else f"{level_code}:{query}")
                        )
                        # 治理优先级的唯一统计单元：业务线 + 维度 + 指标；卡型只保留为
                        # 覆盖范围元数据，不能将同一指标拆成多个优先级票池。
                        key = (target["businessCode"], metric_code, level_code)
                        group = stats.setdefault(key, {
                            **target, "metricCode": metric_code, "metricName": metric_name,
                            "level": level_code, "levelName": level_name, "issues": [], "problemCards": set(),
                            "evaluatedCards": set(), "queries": set(), "findingCounts": Counter(),
                            "cardTypeCodes": set(), "voteCountedSignatures": set(),
                            "failVoteCount": 0, "passVoteCount": 0,
                        })
                        group["cardTypeCodes"].add(target["cardTypeCode"])
                        if level_code == "page" or issue.get("isAssessmentLevel"):
                            location_label = "页面框架"
                        else:
                            location_label = str(issue.get("locationLabel") or location_labels[context].get(card_id) or "页面公共区域")
                        evidence = {"query": query, "tab": tab, "cardId": target_card_id, "elementId": element_id,
                                    "elementLabel": element_label,
                                    "locationLabel": location_label,
                                    "relatedCardIds": related_card_ids,
                                    "rating": str(issue.get("rating", unit.get("rating", ""))),
                                    "assessmentLevel": bool(issue.get("isAssessmentLevel", False)),
                                    "description": str(issue.get("description", "")),
                                    "recommendation": str(issue.get("recommendation", "")),
                                    "component": str(issue.get("component", "")), "annotatedImage": annotated,
                                    "screenshot": screenshot, "coord": issue.get("coord", []),
                    "evidenceImage": str(issue.get("evidenceImage", ""))}
                        signature = (query, screenshot_ref, tab, target_card_id, metric_code, finding)
                        if not any(item["signature"] == signature for item in group["issues"]):
                            group["issues"].append({"signature": signature, **evidence})
                        if signature not in group["voteCountedSignatures"]:
                            vote_rating = str(issue.get("rating", unit.get("rating", "")))
                            if vote_rating in FAIL_RATINGS:
                                group["failVoteCount"] += 1
                            elif vote_rating in PASS_RATINGS:
                                group["passVoteCount"] += 1
                            group["voteCountedSignatures"].add(signature)
                        group["problemCards"].add((query, tab, target_card_id))
                        group["queries"].add(query)
                        group["findingCounts"][finding] += 1

    # Add denominators per business/card-type/metric based on all classified cards.
    for (query, screenshot), cards in classifications.items():
        if query not in used_queries:
            continue
        screenshot_ref = Path(screenshot).name or screenshot
        for card_id, classification in cards.items():
            if classification["scope"] != "business":
                continue
            for key, group in stats.items():
                if key[0] == classification["businessCode"] and classification["cardTypeCode"] in group["cardTypeCodes"]:
                    group["evaluatedCards"].add((query, "全部", f"{screenshot_ref}:{card_id}"))

    groups = []
    for group in stats.values():
        denominator = len(group["evaluatedCards"])
        problems = len(group["problemCards"])
        rate = round(problems / denominator * 100, 1) if denominator else 0
        group["evaluatedCardCount"] = denominator
        group["problemCardCount"] = problems
        group["problemRate"] = rate
        group["queryCount"] = len(group["queries"])
        group["findingDistribution"] = [{"code": code, "count": count} for code, count in group["findingCounts"].most_common()]
        priority = priority_from_vote_counts(group["failVoteCount"], group["passVoteCount"])
        if priority is None:
            raise ValueError("待优化治理分组缺少达标/不达标票，无法计算优先级")
        group["priority"] = priority
        group["priorityReason"] = priority_reason_from_vote_counts(
            group["failVoteCount"], group["passVoteCount"], priority
        )
        group["evidence"] = [{
            **{k: v for k, v in item.items() if k != "signature"},
            "priority": priority,
            "priorityReason": group["priorityReason"],
        } for item in group["issues"]]
        group["problemCardRefs"] = sorted("|".join(item) for item in group["problemCards"])
        group["evaluatedCardRefs"] = sorted("|".join(item) for item in group["evaluatedCards"])
        for key in ("issues", "problemCards", "evaluatedCards", "queries", "findingCounts", "cardTypeCodes", "voteCountedSignatures"):
            group.pop(key, None)
        groups.append(group)
    groups.sort(key=lambda item: ({"P0": 0, "P1": 1, "P2": 2, "待判定": 3}.get(item["priority"], 4), -item["problemRate"], -item["problemCardCount"]))

    # Keep all evaluation levels visible in per-query review. A deliberately
    # unselected dimension is an explicit scope fact, not a fabricated rating.
    # The frozen task scopes are supplied by the control plane when available;
    # direct compatibility calls retain the historical three-level display.
    scope_by_query = {
        str(item.get("query") or ""): item
        for item in (evaluation_scope or {}).get("queryScopes", [])
        if isinstance(item, dict) and str(item.get("query") or "")
    }
    for query in sorted(used_queries):
        units = query_details[query]
        query_scope = scope_by_query.get(query, {})
        selected_dimensions = {
            str(value) for value in query_scope.get("dimensions", [])
            if isinstance(value, str)
        }
        for dimension, (level_name, level_code, _) in LEVEL_ORDER:
            if any(unit["level"] == level_code for unit in units):
                continue
            scope_label = "未选择" if query_scope and dimension not in selected_dimensions else "未执行"
            reason = (
                f"本批次冻结评测范围未选择{level_name}，因此未生成该维度结论。"
                if scope_label == "未选择"
                else f"本批次过程评测结果未包含{level_name}，暂无可复核的{level_name}结论。"
            )
            units.append({
                "level": level_code, "levelName": level_name, "skill": "",
                "metricName": f"{level_name}评测", "metricCode": f"{level_code}_pending",
                "tab": "全部", "rating": scope_label, "reason": reason,
                "evidenceMode": "", "issues": [], "annotatedImage": "",
            })

    business_summary: dict[str, dict[str, Any]] = {}
    for group in groups:
        # 页面框架是评测层级，不能成为业务线；页面级问题只用于独立问题展示。
        if group["businessCode"] == "page_framework":
            continue
        item = business_summary.setdefault(group["businessCode"], {
            "businessCode": group["businessCode"], "businessName": group["businessName"], "issueCount": 0,
            "problemCards": set(), "evaluatedCards": set(), "componentProblemCards": set(), "componentEvaluatedCards": set(),
        })
        item["issueCount"] += group["problemCardCount"]
        item["problemCards"].update(group["problemCardRefs"])
        item["evaluatedCards"].update(group["evaluatedCardRefs"])
        if group["level"] == "component":
            item["componentProblemCards"].update(group["problemCardRefs"])
            item["componentEvaluatedCards"].update(group["evaluatedCardRefs"])
    # 即使某业务没有待优化问题，只要当前批次存在可见业务卡，也要保留业务 Tab。
    for (query, screenshot), cards in classifications.items():
        if query not in used_queries:
            continue
        screenshot_ref = Path(screenshot).name or screenshot
        for card_id, classification in cards.items():
            if classification["scope"] != "business":
                continue
            summary = business_summary.setdefault(classification["businessCode"], {
                "businessCode": classification["businessCode"], "businessName": classification["businessName"], "issueCount": 0,
                "problemCards": set(), "evaluatedCards": set(), "componentProblemCards": set(), "componentEvaluatedCards": set(),
            })
            # The business card rate uses the full visible-card inventory as
            # denominator, including cards whose component metrics are all
            # excellent and therefore produce no governance group.
            summary["componentEvaluatedCards"].add("|".join((query, "全部", f"{screenshot_ref}:{card_id}")))

    business_rows = []
    for item in business_summary.values():
        # Page-level findings use synthetic ``page:<query>`` references.  They
        # remain in issue counts and evidence, but must not inflate the metric
        # explicitly labelled as a business-card problem rate above 100%.
        total = len(item["componentEvaluatedCards"])
        problems = len(item["componentProblemCards"])
        business_rows.append({
            **{k: v for k, v in item.items() if k not in {"problemCards", "evaluatedCards", "componentProblemCards", "componentEvaluatedCards"}},
            "evaluatedCards": total, "problemCards": problems,
            "problemRate": round(problems / total * 100, 1) if total else 0,
            # 本批次是月度问题跟踪的首个基线：所有本批发现均计为新增，
            # 尚无可验证的闭环记录时不虚构已解决数量。
            "tracking": {"newIssueCount": int(item["issueCount"]), "resolvedIssueCount": 0, "baseline": "monthly_tracking_initial"},
        })
    business_rows.sort(key=lambda item: (-item["issueCount"], item["businessName"]))
    manifest_count = sum(len(by_screenshot) for by_screenshot in manifests.values())
    return {
        "generatedAt": str(date.today()),
        "queryCount": len(used_queries),
        "groups": groups,
        "businesses": business_rows,
        "queryDetails": dict(sorted(query_details.items())),
        "unknown": unknown,
        "manifests": manifest_count,
        "evaluationScope": evaluation_scope or {},
    }


def validate_dataset(
    data: dict[str, Any],
    artifact_dir: Path,
    expected_business_tabs: set[str],
    expected_queries: set[str] | None = None,
    allow_unknown_business: bool = False,
) -> None:
    """Fail early when a dashboard would silently mix batches or lose audit evidence."""
    if not data["queryCount"]:
        raise ValueError(f"未从评测产物读取到有效搜索词：{artifact_dir}")
    if data["queryCount"] != len(data["queryDetails"]):
        raise ValueError("搜索词计数与逐词详情不一致，停止生成以避免交付不完整看板")
    if expected_queries is not None and set(data["queryDetails"]) != expected_queries:
        missing = sorted(expected_queries - set(data["queryDetails"]))
        extra = sorted(set(data["queryDetails"]) - expected_queries)
        raise ValueError(
            "报告搜索词不满足本批任务集合："
            f"缺失={','.join(missing) or '无'}；多出={','.join(extra) or '无'}"
        )
    if data.get("unknown") and not allow_unknown_business:
        unresolved = "; ".join(
            f"{item.get('query')}:{item.get('cardId')}（{item.get('reason')}）"
            for item in data["unknown"]
        )
        raise ValueError(f"存在无法由当前商卡语义与履约事实判定的业务归属，停止业务Tab聚合：{unresolved}")
    for query, units in data["queryDetails"].items():
        if not units:
            raise ValueError(f"搜索词 {query} 没有评测明细")
        for unit in units:
            if unit.get("rating") not in {"未执行", "未选择"} and not unit.get("screenshot"):
                raise ValueError(f"搜索词 {query} 缺少统一元素清单声明的原图路径")
            for issue in unit.get("issues", []):
                if not isinstance(issue, dict) or str(issue.get("rating", "")) not in {"达标", "不达标", "🟡", "🔴"}:
                    continue
                screenshot = str(unit.get("screenshot") or "")
                evidence_image = str(issue.get("evidenceImage") or "")
                if not evidence_image or not Path(evidence_image).is_file():
                    raise ValueError(f"搜索词 {query} 的待优化问题缺少 Phase4 原始截图证据")
                if Path(evidence_image).resolve() != Path(screenshot).resolve():
                    raise ValueError(f"搜索词 {query} 的问题证据未引用所属评测单元原图")
    allowed_codes = set(EXPECTED_REPORT_BUSINESS_TABS)
    actual_businesses = {item.get("businessCode"): item for item in data["businesses"]}
    unexpected_codes = sorted(set(actual_businesses) - allowed_codes)
    if unexpected_codes:
        raise ValueError(f"报告业务Tab不满足预期口径，发现未允许业务：{','.join(unexpected_codes)}")
    missing_codes = sorted(expected_business_tabs - set(actual_businesses))
    extra_codes = sorted(set(actual_businesses) - expected_business_tabs)
    if missing_codes or extra_codes:
        raise ValueError(
            "报告业务Tab不满足本批次预期："
            f"缺失={','.join(missing_codes) or '无'}；多出={','.join(extra_codes) or '无'}"
        )
    mismatched_names = sorted(
        code for code, item in actual_businesses.items()
        if item.get("businessName") != EXPECTED_REPORT_BUSINESS_TABS[code]
    )
    if mismatched_names:
        raise ValueError(f"报告业务Tab名称不满足预期口径：{','.join(mismatched_names)}")
    valid_queries = set(data["queryDetails"])
    for group in data["groups"]:
        for evidence in group.get("evidence", []):
            if evidence.get("query") not in valid_queries:
                raise ValueError("治理卡证据引用了当前批次之外的搜索词")
            if str(evidence.get("rating", "")) in {"达标", "不达标", "🟡", "🔴"}:
                if not str(evidence.get("description", "")).strip():
                    raise ValueError(f"问题 {evidence.get('query')}:{evidence.get('elementId') or evidence.get('cardId')} 缺少问题级 description")
                if not str(evidence.get("recommendation", "")).strip():
                    raise ValueError(f"问题 {evidence.get('query')}:{evidence.get('elementId') or evidence.get('cardId')} 缺少问题级个性化优化建议")


def visible_business_tabs(data: dict[str, Any]) -> set[str]:
    """Derive the batch's tabs from accepted current-screen merchant-card facts.

    Search terms, task-time UI Tabs and controller defaults are deliberately
    absent. ``classify_card`` rejects cards whose visible semantics or
    fulfilment facts are insufficient or conflict with a Phase2 ownership hint.
    """
    return {
        str(item.get("businessCode"))
        for item in data.get("businesses", [])
        if str(item.get("businessCode")) in EXPECTED_REPORT_BUSINESS_TABS
    }


def replace_issue_evidence_with_original_screenshots(data: dict[str, Any]) -> None:
    """Normalize legacy datasets to the current original-screenshot policy."""
    for units in data.get("queryDetails", {}).values():
        for unit in units:
            screenshot = str(unit.get("screenshot") or "")
            if not screenshot:
                continue
            for issue in unit.get("issues", []):
                if isinstance(issue, dict):
                    issue["screenshot"] = screenshot
                    issue["evidenceImage"] = screenshot
    for group in data.get("groups", []):
        for issue in group.get("evidence", []):
            if not isinstance(issue, dict):
                continue
            screenshot = str(issue.get("screenshot") or "")
            if screenshot:
                issue["evidenceImage"] = screenshot


def parse_excluded_issue_keys(values: list[str]) -> set[tuple[str, str]]:
    """Parse report-only exclusions as ``<query>:<elementId>`` pairs."""
    keys: set[tuple[str, str]] = set()
    for value in values:
        query, separator, element_id = str(value).partition(":")
        query, element_id = query.strip(), element_id.strip()
        if not separator or not query or not element_id:
            raise ValueError("--exclude-issue 必须使用 <搜索词>:<元素ID> 格式")
        keys.add((query, element_id))
    return keys


def render(data: dict[str, Any]) -> str:
    """Render only through the canonical Phase5 dashboard renderer."""
    return render_dashboard(data)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the search result experience dashboard")
    parser.add_argument("--project-dir", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dataset-output", type=Path)
    parser.add_argument("--batch-name", help="当前隔离评测批次名；不传时使用 artifact-dir 目录名")
    parser.add_argument(
        "--expected-business-tabs",
        default="",
        help="可选业务 Tab 事后断言（逗号分隔 businessCode）；省略时由当前截图中已验收商卡事实推导",
    )
    parser.add_argument("--expected-query", action="append", default=[], help="重复传入本批每个预期搜索词。")
    parser.add_argument("--manifest", action="append", type=Path, default=[], help="重复传入已验收的 Phase2 manifest。")
    parser.add_argument("--result", action="append", type=Path, default=[], help="重复传入已验收且已回写证据的 Phase3/4 结果。")
    parser.add_argument("--allow-unknown-business", action="store_true", help="本地部分报告允许未归属商卡不进入业务 Tab，并在报告范围中显式标注。")
    parser.add_argument("--evaluation-scope", default="{}", help="控制面传入的冻结评测范围 JSON；报告仅呈现此范围内已执行的结果。")
    parser.add_argument("--execution-note", action="append", default=[], help="外层批次控制器写入的未完成/阻断范围说明。")
    parser.add_argument(
        "--original-screenshot-evidence",
        action="store_true",
        help="旧结果兼容：在报告内把历史问题证据归一为对应原图；新 Phase4 结果无需此参数。",
    )
    parser.add_argument(
        "--exclude-issue",
        action="append",
        default=[],
        help="报告展示排除项，格式为 <搜索词>:<元素ID>；不改写原始 Phase3/4 结果。",
    )
    args = parser.parse_args()
    project = args.project_dir.resolve()
    artifact_dir = args.artifact_dir or project / ".artifacts" / "过程文件-评测结果与审计"
    output = args.output or project / "reports" / "meituan_search_experience_dashboard_五图全维度.html"
    dataset_output = args.dataset_output or project / "reports" / ".governance_dataset_五图全维度.json"
    try:
        evaluation_scope = json.loads(args.evaluation_scope)
    except json.JSONDecodeError as exc:
        raise ValueError("--evaluation-scope 必须是 JSON 对象") from exc
    if not isinstance(evaluation_scope, dict):
        raise ValueError("--evaluation-scope 必须是 JSON 对象")
    excluded_issue_keys = parse_excluded_issue_keys(args.exclude_issue)
    data = collect(
        project,
        artifact_dir,
        manifest_paths=args.manifest or None,
        result_paths=args.result or None,
        evaluation_scope=evaluation_scope,
        excluded_issue_keys=excluded_issue_keys,
    )
    data["batch"] = args.batch_name or artifact_dir.name
    scope_note = str(evaluation_scope.get("note") or "").strip()
    data["executionNotes"] = [*args.execution_note, *([scope_note] if scope_note else [])]
    data["unclassifiedCardCount"] = len(data.get("unknown") or [])
    if args.original_screenshot_evidence:
        replace_issue_evidence_with_original_screenshots(data)
    supplied_business_tabs = {code.strip() for code in args.expected_business_tabs.split(",") if code.strip()}
    invalid_expected_codes = sorted(supplied_business_tabs - set(EXPECTED_REPORT_BUSINESS_TABS))
    if invalid_expected_codes:
        raise ValueError(f"--expected-business-tabs 包含未允许的业务：{','.join(invalid_expected_codes)}")
    expected_business_tabs = supplied_business_tabs or visible_business_tabs(data)
    expected_queries = set(args.expected_query) if args.expected_query else None
    validate_dataset(data, artifact_dir, expected_business_tabs, expected_queries, args.allow_unknown_business)
    output.parent.mkdir(parents=True, exist_ok=True)
    dataset_output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output.write_text(render(data), encoding="utf-8")
    print(json.dumps({"dashboard": str(output), "dataset": str(dataset_output), "businessTabs": sorted(expected_business_tabs), "businesses": len(data["businesses"]), "groups": len(data["groups"]), "queries": data["queryCount"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
