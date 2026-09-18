#!/usr/bin/env python3
"""Measure canonical seven-colour UI families from the bound screenshot.

Phase2 supplies component membership, element bounds and exclusion semantics.
Rendered pixels supply the colour evidence.  The resulting component artifact
is shared by card and page colour evaluation.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[6]
SHARED_SCRIPTS = ROOT / "scripts"
ELEMENT_COLOR_SCRIPTS = (
    ROOT / "phase3-evaluation" / "dimensions" / "single-element" / "skills"
    / "eval-2-color-logic-single-element" / "scripts"
)
for directory in (SHARED_SCRIPTS, ELEMENT_COLOR_SCRIPTS):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from count_element_colors import count_colors
from phase2_bundle_loader import load_phase2_facts


CONTRACT_VERSION = "component-color-families.v4"
FAMILY_ORDER = ("red", "orange", "yellow", "green", "cyan", "blue", "purple")
FAMILY_ZH = {
    "red": "红", "orange": "橙", "yellow": "黄", "green": "绿",
    "cyan": "青", "blue": "蓝", "purple": "紫",
}
FILTER_COMPONENT_TYPES = {
    "image_filter", "business_image_filter", "graphic_filter", "business_graphic_filter",
}


def _coord(payload: dict[str, Any]) -> list[int] | None:
    value = payload.get("coord") or payload.get("bounds") or payload.get("坐标")
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        x, y, width, height = (int(round(float(item))) for item in value)
    except (TypeError, ValueError):
        return None
    return [x, y, width, height] if width > 0 and height > 0 else None


def visual_element_is_excluded(element: dict[str, Any]) -> str | None:
    render = element.get("render") if isinstance(element.get("render"), dict) else {}
    visual = element.get("visual") if isinstance(element.get("visual"), dict) else {}
    if element.get("isExcluded"):
        return str(element.get("excludeReason") or "phase2_excluded")
    if render.get("visibleStatus") not in {None, "confirmed"}:
        return "visual_not_confirmed"
    if render.get("isPhoto") or visual.get("entityKind") == "image" or element.get("元素类型") == "图片":
        return "photo_or_image"
    if visual.get("entityKind") == "icon" or element.get("元素类型") == "图标":
        return "graphic_or_icon"
    if _coord(element) is None:
        return "missing_pixel_boundary"
    return None


def component_is_filter(card: dict[str, Any]) -> bool:
    values = (
        card.get("cardTypeCode"), card.get("cardType"), card.get("componentType"),
        card.get("moduleType"), card.get("contentRole"), card.get("卡片类型"),
    )
    for value in values:
        if not isinstance(value, str):
            continue
        normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized in FILTER_COMPONENT_TYPES or "图筛" in value:
            return True
    return False


def component_rating(color_count: int) -> str:
    if color_count <= 4:
        return "优秀"
    if color_count == 5:
        return "达标"
    return "不达标"


def iter_card_elements(card: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for region in card.get("regions", []):
        if not isinstance(region, dict):
            continue
        for element in region.get("elements", []):
            if isinstance(element, dict):
                yield element


def _crop(image_rgb: np.ndarray, bounds: list[int]) -> np.ndarray | None:
    x, y, width, height = bounds
    image_height, image_width = image_rgb.shape[:2]
    left = max(0, min(image_width, x))
    top = max(0, min(image_height, y))
    right = max(left, min(image_width, x + width))
    bottom = max(top, min(image_height, y + height))
    if right <= left or bottom <= top:
        return None
    return image_rgb[top:bottom, left:right]


def component_colour_families(
    card: dict[str, Any], image_rgb: np.ndarray, min_ratio_pct: float,
) -> tuple[list[str], list[str], list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    scanned_ids: list[str] = []
    excluded_ids: list[str] = []
    neutral_values: list[dict[str, Any]] = []
    source_values: list[dict[str, Any]] = []
    family_keys: set[str] = set()
    for element in iter_card_elements(card):
        element_id = element.get("id")
        if not isinstance(element_id, str) or not element_id:
            continue
        excluded_reason = visual_element_is_excluded(element)
        if excluded_reason:
            excluded_ids.append(element_id)
            continue
        bounds = _coord(element)
        crop = _crop(image_rgb, bounds or [])
        if crop is None:
            excluded_ids.append(element_id)
            continue
        scanned_ids.append(element_id)
        measured = count_colors(crop, min_ratio_pct=min_ratio_pct, drop_bg=False)
        sampled = int(measured.get("sampled", measured.get("total_pixels", 0)) or 0)
        neutral = int(measured.get("neutral_pixels", 0) or 0)
        neutral_values.append({
            "elementId": element_id,
            "field": "sampledPixels",
            "value": f"neutral={neutral}/{sampled}",
        })
        for colour in measured.get("colors", []):
            family = str(colour.get("key") or "")
            if family not in FAMILY_ZH:
                continue
            family_keys.add(family)
            source_values.append({
                "elementId": element_id,
                "field": "sampledPixels",
                "value": f"ratio={colour.get('ratio', 0)}%",
                "colorFamily": FAMILY_ZH[family],
            })
    ordered = [family for family in FAMILY_ORDER if family in family_keys]
    return scanned_ids, excluded_ids, [FAMILY_ZH[family] for family in ordered], neutral_values, source_values


def compute_components(
    facts: dict[str, Any], image_rgb: np.ndarray, min_ratio_pct: float = 1.0,
) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    for card in facts.get("cards", []):
        if not isinstance(card, dict) or not isinstance(card.get("cardId"), str):
            continue
        if component_is_filter(card):
            continue
        scanned_ids, excluded_ids, families, neutral_values, source_values = component_colour_families(
            card, image_rgb, min_ratio_pct
        )
        components.append({
            "componentId": card["cardId"],
            "scannedElementIds": scanned_ids,
            "excludedElementIds": excluded_ids,
            "neutralColorValues": neutral_values,
            "sourceColorValues": source_values,
            "colorFamilies": families,
            "colorFamilyCount": len(families),
            "rating": component_rating(len(families)),
            "evidenceSource": "original_screenshot_pixels",
        })
    return components


def main() -> int:
    parser = argparse.ArgumentParser(description="从当前原图像素计算结果卡七色系")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--min-ratio", type=float, default=1.0)
    args = parser.parse_args()
    facts = load_phase2_facts(manifest_path=args.manifest)
    screenshot = Path(str(facts.get("screenshot") or ""))
    if not screenshot.is_file():
        raise ValueError(f"source_screenshot_missing:{screenshot}")
    image_rgb = np.asarray(Image.open(screenshot).convert("RGB"))
    result = {
        "contract": "component-color-families",
        "contractVersion": CONTRACT_VERSION,
        "manifest": str(args.manifest.resolve()),
        "screenshot": str(screenshot.resolve()),
        "minRatioPct": args.min_ratio,
        "components": compute_components(facts, image_rgb, args.min_ratio),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
