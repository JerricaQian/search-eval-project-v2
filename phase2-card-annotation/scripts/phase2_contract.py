"""Canonical full card-type topology contract.

Earlier pipelines allowed the visual-review hint, semantic mapper, and
recognition gate to infer a merchant variant differently. This contract makes the
reviewed topology a single, all-card-type input; ordinary card contracts still
validate the remaining visible facts.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


MERCHANT_HEAD_AND_INFO = {"merchant_head", "merchant_info"}
ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "card-type-registry.v1.json"
TAXONOMY_PATH = ROOT / "phase2-card-annotation/references/search_card_taxonomy.v1.json"
RECOGNITION_CONTRACTS_PATH = ROOT / "phase2-card-annotation/references/card_recognition_contracts.v1.json"
GOLDEN_ROOT = ROOT / "phase2-card-annotation/golden-atomic-2.0"

# Atomic-v3 golden manifests use implementation-facing names.  Keep this
# mapping explicit so a new/renamed golden sample cannot silently be used for
# a different registry type.
GOLDEN_CARD_TYPE_ALIASES = {
    "商品卡片": {"merchant_product_card"},
    "商家卡片_文字下挂": {"merchant_text_append"},
    "商家卡片_图文下挂": {"merchant_graphic_append"},
    "酒店卡片": {"hotel"},
    "演出电影卡片": {"performance_movie"},
}

# The canonical visual structure layer. It covers every registry type and is
# checked against the richer taxonomy/recognition sources below.  ``regions``
# describe the complete-card anatomy; ``requiredTopologySlots`` are the
# smaller current-pixel anchors required during review.
STRUCTURE_BLUEPRINTS = {
    "商品卡片": {"regions": ["头图区", "标题区", "副标题区", "价格区", "商家区"], "requiredTopologySlots": {"head_media", "title", "price"}, "itemPolicy": "单商品主图、标题和价格同卡；不吸附商家下挂"},
    "商家卡片_图文下挂": {"regions": ["头图区", "标题区", "商家信息区", "标签区", "下挂商品区"], "requiredTopologySlots": {"merchant_head", "merchant_info", "attached_goods"}, "itemPolicy": "每个下挂项必须有 CV 图片锚点、标题、价格和独立 itemIndex"},
    "商家卡片_文字下挂": {"regions": ["头图区", "标题区", "商家信息区", "标签区", "下挂区"], "requiredTopologySlots": {"merchant_head", "merchant_info", "text_attachment"}, "itemPolicy": "每个文字/服务下挂项必须有独立 attachedItems 坐标；不得伪造图片"},
    "商家卡片_无下挂": {"regions": ["头图区", "标题区", "商家信息区", "标签区", "AI推荐理由"], "requiredTopologySlots": {"merchant_head", "merchant_info"}, "itemPolicy": "没有 attachedItems；不得因基础信息回退异构卡"},
    "酒店卡片": {"regions": ["头图区", "标题区", "评分与推荐理由", "位置信息", "标签区", "价格区", "基础信息区（双列变体）"], "requiredTopologySlots": {"head_media", "title", "price"}, "itemPolicy": "单列逐卡头图切分；双列按独立网格，不跨列吸附"},
    "度假酒店套餐卡片": {"regions": ["头图区", "标题区", "套餐概要", "标签区", "价格区"], "requiredTopologySlots": {"head_media", "title", "package_summary", "price"}, "itemPolicy": "套餐概要与固定价格必须同卡，不得按普通酒店卡切分"},
    "演出电影卡片": {"regions": ["头图区（演出）", "标题区", "演出信息区", "商家信息区（电影）", "价格区"], "requiredTopologySlots": {"title", "price"}, "itemPolicy": "演出按竖版海报+演出信息；电影按影院标题+场次块"},
    "主点卡片": {"regions": ["实体标题区", "实体信息区", "领域下挂区"], "requiredTopologySlots": {"entity_title", "entity_info"}, "itemPolicy": "列表前 POI 模块，不占普通结果 listPosition"},
    "广告卡": {"regions": ["媒体区", "主要信息区", "辅助信息区", "操作区"], "requiredTopologySlots": {"primary_info"}, "itemPolicy": "必须有明确广告/推广证据；分类失败不得转广告"},
    "异构卡": {"regions": ["主要信息区", "媒体区", "辅助信息区", "操作区"], "requiredTopologySlots": {"primary_info"}, "itemPolicy": "仅在稳定独立单元且所有已知卡型不满足时使用"},
}


@lru_cache(maxsize=1)
def authoritative_contracts() -> dict[str, dict[str, Any]]:
    """Merge the three existing sources without redefining card knowledge.

    Registry owns IDs/display names, search taxonomy owns visible regions and
    classification evidence, and recognition contracts own minimum evidence,
    boundary and exclusion rules. The pipeline fails closed if those sources drift.
    """
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    taxonomy = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    recognition = json.loads(RECOGNITION_CONTRACTS_PATH.read_text(encoding="utf-8"))
    registry_by_id = {str(item["id"]): item for item in registry.get("resultCardTypes", []) if isinstance(item, dict) and item.get("id")}
    taxonomy_by_id = {str(item["id"]): item for item in taxonomy.get("cardTypes", []) if isinstance(item, dict) and item.get("id")}
    recognition_by_id = {str(item["cardType"]): item for item in recognition.get("contracts", []) if isinstance(item, dict) and item.get("cardType")}
    ids = set(registry_by_id)
    if ids != set(taxonomy_by_id) or ids != set(recognition_by_id):
        raise ValueError("card_contract_source_drift")
    return {
        card_type: {
            "id": card_type,
            "registry": registry_by_id[card_type],
            "taxonomy": taxonomy_by_id[card_type],
            "recognition": recognition_by_id[card_type],
        }
        for card_type in sorted(ids)
    }


def registered_card_types() -> set[str]:
    return set(authoritative_contracts())


@lru_cache(maxsize=1)
def fulfillment_tag_values() -> frozenset[str]:
    """Return the shared fulfillment enum owned by the search taxonomy.

    Recognition, manifest assembly and validation must not maintain separate
    handwritten copies of these labels.  Golden manifests use the same enum,
    so this is also the compatibility point for golden-contract versioning.
    """
    taxonomy = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    values = taxonomy.get("commonElementVocabulary", {}).get("fulfillment", [])
    return frozenset(str(value).strip() for value in values if str(value).strip())


def fulfillment_semantic_kind(value: str) -> str:
    """Classify a complete visible field as fulfillment, or return ``""``.

    Full-field matching is intentional: a product title that happens to contain
    “酒店” or “外卖” must remain a title.  Structured delivery rows are covered
    in addition to the short badge enum because golden/Phase3 facts include
    duration, minimum-order, delivery-fee and pickup variants.
    """
    compact = re.sub(r"[\s·•|]+", "", str(value).strip())
    if not compact:
        return ""
    if compact in {re.sub(r"[\s·•|]+", "", item) for item in fulfillment_tag_values()}:
        return "fulfillment_tag"
    patterns = (
        ("delivery_time", r"^(?:约)?\d{1,3}分钟$|^预计.{0,8}(?:送达|达)$|^\d{1,2}:\d{2}(?:前)?送达$"),
        ("minimum_order", r"^起送[¥￥]?\d+(?:\.\d+)?(?:元)?$"),
        ("delivery_fee", r"^(?:配送(?:费)?(?:约)?[¥￥]?\d+(?:\.\d+)?|免配送费|免费配送|满[¥￥]?\d+(?:\.\d+)?(?:包邮|免配送费|配送(?:费)?[¥￥]?\d+(?:\.\d+)?))$"),
        ("pickup", r"^(?:可自取|到店取|线上点到店取|门店自提)$"),
        ("delivery_status", r"^(?:\d{1,2}:\d{2}|明天\d{1,2}:\d{2})(?:营业|配送|后配送)$"),
        ("fulfillment_row", r"^(?=.{2,80}$)(?=.*(?:起送|配送|包邮|自取|送达|分钟))(?:起送[¥￥]?\d+(?:\.\d+)?|满[¥￥]?\d+(?:\.\d+)?(?:免配送费|包邮|配送(?:费)?[¥￥]?\d+(?:\.\d+)?)|免配送费|免费配送|配送(?:费)?(?:约)?[¥￥]?\d+(?:\.\d+)?|(?:约)?\d{1,3}分钟|预计.{0,8}(?:送达|达)|可自取|到店取|\d+(?:\.\d+)?(?:km|公里|m|米))+$"),
    )
    return next((kind for kind, pattern in patterns if re.fullmatch(pattern, compact)), "")


def structure_blueprint(card_type: str) -> dict[str, Any]:
    if card_type not in STRUCTURE_BLUEPRINTS or card_type not in authoritative_contracts():
        raise ValueError(f"structure_blueprint_missing:{card_type}")
    blueprint = STRUCTURE_BLUEPRINTS[card_type]
    taxonomy_names = {
        str(region.get("name", ""))
        for region in authoritative_contracts()[card_type]["taxonomy"].get("regions", [])
        if isinstance(region, dict)
    }
    recognition_required = set(authoritative_contracts()[card_type]["recognition"].get("requiredRegions", []))
    if not set(blueprint["regions"]).issubset(taxonomy_names) or not recognition_required.issubset(blueprint["regions"]):
        raise ValueError(f"structure_blueprint_source_drift:{card_type}")
    return {"regions": list(blueprint["regions"]), "requiredTopologySlots": sorted(blueprint["requiredTopologySlots"]), "itemPolicy": blueprint["itemPolicy"]}


def card_contract(card_type: str) -> dict[str, Any]:
    """Return the complete canonical view of an existing card type contract."""
    contracts = authoritative_contracts()
    if card_type not in contracts:
        raise ValueError(f"card_type_not_in_shared_registry:{card_type}")
    source = contracts[card_type]
    registry, taxonomy, recognition = source["registry"], source["taxonomy"], source["recognition"]
    golden_examples = golden_structure_examples(card_type)
    return {
        "contract": "phase2.card-type",
        "id": card_type,
        "displayName": registry.get("displayName"),
        "officerFamily": registry.get("officerFamily"),
        "formal": registry.get("formal"),
        "scope": taxonomy.get("scope"),
        "classificationEvidence": taxonomy.get("classificationEvidence", {}),
        "taxonomyRegions": taxonomy.get("regions", []),
        "minimumEvidenceGroups": recognition.get("minimumEvidenceGroups", []),
        "supportingFeatures": recognition.get("supportingFeatures", []),
        "forbiddenFeatures": recognition.get("forbiddenFeatures", []),
        "boundaryStrategy": recognition.get("boundaryStrategy"),
        "distinguishFrom": recognition.get("distinguishFrom", {}),
        "requiredRegions": recognition.get("requiredRegions", []),
        "optionalRegions": recognition.get("optionalRegions", []),
        "reviewTopologySlots": sorted(review_topology_slots(card_type)),
        "structureBlueprint": structure_blueprint(card_type),
        "goldenStructureExamples": golden_examples,
        "goldenCoverage": "atomic_v3_examples" if golden_examples else "taxonomy_only_no_matching_atomic_v3_golden",
    }


@lru_cache(maxsize=1)
def _atomic_golden_payloads() -> tuple[tuple[str, dict[str, Any]], ...]:
    payloads: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(GOLDEN_ROOT.rglob("*.atomic.v3.json")):
        payloads.append((str(path.relative_to(ROOT)), json.loads(path.read_text(encoding="utf-8"))))
    return tuple(payloads)


@lru_cache(maxsize=None)
def golden_structure_examples(card_type: str) -> list[dict[str, Any]]:
    """Extract real region/slot structures from the atomic-v3 golden JSONs.

    No golden entry is fabricated: types without a matching card-level golden
    remain explicitly taxonomy-only. Primary-point is a page module in the
    atomic goldens, so its examples retain module scope rather than pretending
    it is an ordinary result-list card.
    """
    examples: list[dict[str, Any]] = []
    aliases = GOLDEN_CARD_TYPE_ALIASES.get(card_type, set())
    for source_file, payload in _atomic_golden_payloads():
        regions = payload.get("regionsById", {})
        for card_id, card in payload.get("cardsById", {}).items():
            if not isinstance(card, dict) or card.get("cardType") not in aliases:
                continue
            region_examples = []
            for region_id in card.get("regionIds", []):
                region = regions.get(region_id, {})
                if isinstance(region, dict):
                    region_examples.append({"name": region.get("name"), "slots": sorted(region.get("slots", {}))})
            example = {"source": source_file, "scope": "result_card", "variant": card.get("variant", ""), "regions": region_examples}
            if example not in examples:
                examples.append(example)
        if card_type == "主点卡片":
            for module in payload.get("modulesById", {}).values():
                if isinstance(module, dict) and module.get("type") in {"primary_point", "primary_point_disambiguation"}:
                    example = {"source": source_file, "scope": "page_module", "variant": module.get("type"), "regions": [], "moduleSlots": sorted(module.get("slots", {}))}
                    if example not in examples:
                        examples.append(example)
    return examples


def review_topology_slots(card_type: str) -> set[str]:
    return set(structure_blueprint(card_type)["requiredTopologySlots"])


def topology_parts(topology: dict[str, Any] | None) -> tuple[set[str], list[dict[str, Any]]]:
    topology = topology if isinstance(topology, dict) else {}
    slots = {
        str(region.get("slot", ""))
        for region in topology.get("regions", [])
        if isinstance(region, dict)
    }
    items = [item for item in topology.get("attachedItems", []) if isinstance(item, dict)]
    return slots, items


def merchant_variant(topology: dict[str, Any] | None) -> str:
    """Return the merchant card type, or ``""`` when topology is not merchant.

    A text downhang is a visible service/supply item, not merely a region label:
    it therefore requires at least one attached item.  The absence of any
    attachment is a known merchant base form, never an excuse to use the
    heterogeneous fallback.
    """
    slots, items = topology_parts(topology)
    if not MERCHANT_HEAD_AND_INFO.issubset(slots):
        return ""
    if "attached_goods" in slots:
        return "商家卡片_图文下挂" if items else ""
    if "text_attachment" in slots:
        return "商家卡片_文字下挂" if items else ""
    if not items:
        return "商家卡片_无下挂"
    return ""


def topology_errors(card_type: str, topology: dict[str, Any] | None) -> list[str]:
    """Validate the topology union for every shared registry type."""
    slots, items = topology_parts(topology)
    merchant_slots = MERCHANT_HEAD_AND_INFO.issubset(slots)
    errors: list[str] = []
    def require(required: set[str], code: str) -> None:
        missing = sorted(required - slots)
        if missing:
            errors.append(f"{code}_missing:{','.join(missing)}")

    def forbid(forbidden: set[str], code: str) -> None:
        present = sorted(forbidden & slots)
        if present:
            errors.append(f"{code}_forbidden:{','.join(present)}")

    if card_type not in registered_card_types():
        return ["card_type_not_in_shared_registry"]
    if card_type == "商家卡片_文字下挂":
        if not merchant_slots or "text_attachment" not in slots or not items:
            errors.append("merchant_text_hang_requires_head_info_text_attachment_and_attached_items")
        if "attached_goods" in slots:
            errors.append("merchant_text_hang_must_not_declare_attached_goods")
    elif card_type == "商家卡片_图文下挂":
        if not merchant_slots or "attached_goods" not in slots or not items:
            errors.append("merchant_graphic_hang_requires_head_info_attached_goods_and_attached_items")
        if "text_attachment" in slots:
            errors.append("merchant_graphic_hang_must_not_declare_text_attachment")
    elif card_type == "商家卡片_无下挂":
        if not merchant_slots or items or ({"text_attachment", "attached_goods"} & slots):
            errors.append("merchant_plain_requires_head_info_and_no_attached_items")
    elif card_type == "商品卡片":
        require({"head_media", "title", "price"}, "product_card")
        forbid({"merchant_head", "merchant_info", "text_attachment", "attached_goods"}, "product_card")
        if items:
            errors.append("product_card_forbids_merchant_attached_items")
    elif card_type == "酒店卡片":
        require({"head_media", "title", "price"}, "hotel_card")
        forbid({"package_summary", "attached_goods", "text_attachment"}, "hotel_card")
        if items:
            errors.append("hotel_card_forbids_merchant_attached_items")
    elif card_type == "度假酒店套餐卡片":
        require({"head_media", "title", "package_summary", "price"}, "hotel_package_card")
        forbid({"attached_goods", "text_attachment"}, "hotel_package_card")
        if items:
            errors.append("hotel_package_card_forbids_merchant_attached_items")
    elif card_type == "演出电影卡片":
        require({"title", "price"}, "performance_movie_card")
        has_performance_structure = {"head_media", "performance_info"}.issubset(slots)
        has_cinema_structure = "merchant_info" in slots
        if not (has_performance_structure or has_cinema_structure):
            errors.append("performance_movie_card_requires_performance_poster_info_or_cinema_info")
        forbid({"package_summary", "attached_goods", "text_attachment"}, "performance_movie_card")
        if items:
            errors.append("performance_movie_card_forbids_merchant_attached_items")
    elif card_type == "主点卡片":
        require({"entity_title", "entity_info"}, "primary_point_card")
        forbid({"attached_goods", "text_attachment"}, "primary_point_card")
        if items:
            errors.append("primary_point_card_forbids_merchant_attached_items")
    elif card_type == "广告卡":
        require({"primary_info"}, "advertisement_card")
        # Promotion proof itself is a semantic feature in the canonical card
        # contract; topology only ensures it remains an independent unit.
        if "action" in slots and "media" not in slots and "secondary_info" not in slots:
            errors.append("advertisement_card_action_without_media_or_secondary_info")
    elif card_type == "异构卡":
        require({"primary_info"}, "heterogeneous_card")
        if merchant_slots:
            errors.append("heterogeneous_card_must_not_bypass_merchant_variant")
    return errors


def reviewed_card_type(card_type: str, topology: dict[str, Any] | None) -> str:
    """Return the reviewed type that the semantic mapper must confirm."""
    if card_type.startswith("商家卡片_"):
        return merchant_variant(topology)
    return card_type if card_type in registered_card_types() else ""
