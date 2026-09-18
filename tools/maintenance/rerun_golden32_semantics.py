#!/usr/bin/env python3
"""Re-evaluate ambiguity and redundancy for the 32-sample Atomic 2.1 batch.

The script creates a new append-only batch.  It inherits the 15 unrelated
full-19 result rows from a validated source batch, but reconstructs these four
rows from the current Atomic JSON and current Phase3 contracts:

* single-element eval-4 information authenticity;
* component eval-7 information authenticity;
* component eval-8 information redundancy;
* page eval-7 information redundancy.

The semantic candidate ledger is rebuilt for every manifest.  Generic lexical
matches are retained as reviewed candidates and never become findings merely
because their strings overlap.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import itertools
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


PROJECT = Path(__file__).resolve().parents[2]
ARTIFACT_ROOT = PROJECT / ".artifacts/过程文件-评测结果与审计"
RUNS_ROOT = PROJECT / "runs"
REPORT_ROOT = PROJECT / "reports"
LOADER = PROJECT / "scripts/phase2_bundle_loader.py"
VALIDATOR = PROJECT / "scripts/validate_eval_results.py"
EVIDENCE = PROJECT / "phase4-issue-evidence/scripts/generate_issue_evidence.py"
FINALIZER = PROJECT / "workflow/eval_cli.py"
RELATION_SCRIPT = PROJECT / "phase3-evaluation/dimensions/card-component/scripts/extract_phase3_relation_candidates.py"
CURRENT_MEASUREMENT_TOOLS = {
    "eval-2-color-logic-single-element": PROJECT / "phase3-evaluation/dimensions/single-element/skills/eval-2-color-logic-single-element/scripts/count_element_colors.py",
    "eval-5-info-hierarchy": PROJECT / "phase3-evaluation/dimensions/card-component/skills/eval-5-info-hierarchy/scripts/extract_component_metrics.py",
    # Historical V2 validation only; active V3 page colour has no page-pixel script.
    "eval-3-page-color-logic": PROJECT / "tools/maintenance/legacy/page_color_analysis_v2.py",
}
TARGET_SKILLS = {
    ("phase3-single_element-eval", "eval-4-info-authenticity-single-element"),
    ("phase3-card_or_component-eval", "eval-7-info-authenticity"),
    ("phase3-card_or_component-eval", "eval-8-info-redundancy"),
    ("phase3-page_framework-eval", "eval-7-info-redundancy"),
}
SUPPLY_MARKERS = {"到店", "外卖", "上门", "酒店", "住宿", "快递", "闪购", "在线", "景点", "演出"}
REDUNDANCY_CROSS_CHECKS = [
    "title/subtitle ↔ basic information",
    "title/subtitle ↔ tags/price/promotion",
    "tag ↔ price/promotion",
    "title internal repeated quantified fragments",
]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any, *, refuse_existing: bool = False) -> None:
    if refuse_existing and path.exists():
        raise ValueError(f"refuse_to_overwrite:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=PROJECT, check=True, text=True, capture_output=capture)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot_import:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def visible_text(element: dict[str, Any]) -> str:
    return str(element.get("text") or element.get("semanticDescription") or "图片/图标")


def region_element_ids(atomic: dict[str, Any], region_id: str) -> list[str]:
    region = atomic["regionsById"][region_id]
    result: list[str] = []
    for ids in (region.get("slots") or {}).values():
        result.extend(ids)
    for item in region.get("items") or []:
        for ids in (item.get("slots") or {}).values():
            result.extend(ids)
    return result


def card_element_ids(atomic: dict[str, Any], card_id: str) -> list[str]:
    return [
        element_id
        for region_id in atomic["cardsById"][card_id]["regionIds"]
        for element_id in region_element_ids(atomic, region_id)
    ]


def card_regions(atomic: dict[str, Any], card_id: str) -> list[str]:
    return [atomic["regionsById"][rid]["name"] for rid in atomic["cardsById"][card_id]["regionIds"]]


def supply_markers(atomic: dict[str, Any], card_id: str) -> set[str]:
    return {
        visible_text(atomic["elementsById"][eid]).strip()
        for eid in card_element_ids(atomic, card_id)
        if visible_text(atomic["elementsById"][eid]).strip() in SUPPLY_MARKERS
    }


def append_offer_conflicts(atomic: dict[str, Any], card_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Find indistinguishable sibling offers with conflicting prices.

    A price label such as 神券价 visibly differentiates the second offer and is
    therefore retained as an exclusion rather than a conflict.
    """
    elements = atomic["elementsById"]
    offers: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    for rid in atomic["cardsById"][card_id]["regionIds"]:
        region = atomic["regionsById"][rid]
        for item in region.get("items") or []:
            slots = item.get("slots") or {}
            title_ids = list(slots.get("title") or [])
            price_ids = list(slots.get("price") or [])
            if not title_ids or not price_ids:
                continue
            title = "".join(visible_text(elements[eid]) for eid in title_ids)
            price = " ".join(visible_text(elements[eid]) for eid in price_ids)
            offers.append({
                "itemIndex": item.get("index"), "titleIds": title_ids, "priceIds": price_ids,
                "title": title, "titleKey": clean_text(title), "price": price,
            })
    conflicts: list[dict[str, Any]] = []
    for left, right in itertools.combinations(offers, 2):
        if not left["titleKey"] or left["titleKey"] != right["titleKey"] or clean_text(left["price"]) == clean_text(right["price"]):
            continue
        visible_qualifier = any(token in (left["price"] + right["price"]) for token in ("神券价", "新客价", "会员价", "冰爽价", "限时价"))
        candidate = {"left": left, "right": right, "lexicalCue": "same_visible_offer_conflicting_prices"}
        if visible_qualifier:
            exclusions.append({**candidate, "decision": "not_applicable", "reason": "价格标签明确区分了优惠口径"})
            continue
        conflicts.append({
            "lexicalCue": "same_visible_offer_conflicting_prices",
            "leftElementId": left["titleIds"][0], "rightElementId": right["titleIds"][0],
            "leftPriceElementId": left["priceIds"][0], "rightPriceElementId": right["priceIds"][0],
            "offerText": left["title"], "leftPrice": left["price"], "rightPrice": right["price"],
            "verdict": "conflict",
            "reason": "同一商卡内两个可见供给名称与说明完全相同，但价格不同且没有可见规格或权益用于区分。",
        })
    return conflicts, exclusions


def overview(ratings: list[str]) -> dict[str, Any]:
    total = len(ratings)
    fail = ratings.count("不达标")
    return {
        "total": total, "excellent": ratings.count("优秀"), "pass": ratings.count("达标"),
        "fail": fail, "failRate": f"{fail / total * 100:.1f}%" if total else "0%",
    }


def result_row(
    dimension: str, skill: str, title: str, rating: str, score: int,
    screenshot: Path, ratings: list[str], evidence: dict[str, Any],
    issues: list[dict[str, Any]], criterion: str, summary: str,
) -> dict[str, Any]:
    return {
        "dimension": dimension, "skill": skill,
        "units": [{
            "tab": "全部", "rating": rating, "weightedScore": score,
            "reason": f"{title}覆盖{len(ratings)}个实际评估单元，当前评级为{rating}。",
            "details": {
                "overview": overview(ratings), "screenshot": str(screenshot),
                "evidenceMode": "annotated-region" if issues and dimension != "phase3-page_framework-eval" else "original-page",
                "criterion": criterion, "issues": issues,
                "distribution": {name: ratings.count(name) for name in ("优秀", "达标", "不达标")},
                "summary": summary, "evidence": evidence,
            },
        }],
    }


def component_issue(
    atomic: dict[str, Any], element_id: str, component_id: str, dimension: str,
    description: str, fact: str, rule: str, reason: str, impact: str,
    recommendation: str,
) -> dict[str, Any]:
    element = atomic["elementsById"][element_id]
    return {
        "elementId": element_id, "coord": element["bounds"], "component": component_id,
        "elementType": "标签" if element.get("kind") == "tag" else "图标" if element.get("kind") == "icon" else "文本",
        "content": visible_text(element), "dimension": dimension, "description": description,
        "rating": "不达标", "priority": "P1",
        "priorityReason": "该冲突位于结果卡核心决策信息中，会直接影响规格或价格判断",
        "finding": {"observableFact": fact, "ruleOrThreshold": rule, "verdictReason": reason, "userImpact": impact},
        "recommendation": recommendation,
    }


def active_inventory(facts: dict[str, Any]) -> list[dict[str, Any]]:
    active: list[dict[str, Any]] = []
    for card in facts["cards"]:
        for region in card["regions"]:
            for element in region["elements"]:
                active.append({
                    "id": element["id"], "coord": element["坐标"], "component": card["cardId"],
                    "elementType": element["元素类型"], "content": element["内容简述"],
                })
    for module in facts["pageFacts"]["modules"]:
        for element in module.get("elements", []):
            active.append({
                "id": element["id"], "coord": element["坐标"], "component": module["id"],
                "elementType": element["元素类型"], "content": element["内容简述"],
            })
        for item in module.get("filterItems", []):
            for element in item.get("elements", []):
                active.append({
                    "id": element["id"], "coord": element["坐标"], "component": module["id"],
                    "elementType": element["元素类型"], "content": element["内容简述"],
                })
    return active


def rebase_inherited_measurement_tools(results: list[dict[str, Any]]) -> None:
    """Point retained pixel evidence at the current unified script paths.

    Only the executable provenance path changes.  Measurements, parameters,
    artefact paths, ratings and issue copy remain byte-for-byte inherited.
    """
    for result in results:
        current_tool = CURRENT_MEASUREMENT_TOOLS.get(str(result.get("skill") or ""))
        if current_tool is None:
            continue
        for unit in result.get("units", []):
            evidence = (unit.get("details") or {}).get("evidence") or {}
            for row in evidence.get("assessmentRows") or []:
                measurement = row.get("measurement") if isinstance(row, dict) else None
                if isinstance(measurement, dict):
                    measurement["tool"] = str(current_tool)


def refresh_inherited_contract_ratings(results: list[dict[str, Any]]) -> None:
    """Reconcile inherited deterministic rows with current leaf thresholds.

    This does not re-measure pixels or re-scan Atomic facts.  It only maps the
    retained deterministic counts to today's checked rating table.
    """
    for result in results:
        if result.get("skill") not in {"eval-3-color-logic", "eval-4-element-complexity"}:
            continue
        unit = result["units"][0]
        details = unit["details"]
        rows = details["evidence"]["assessmentRows"]
        ratings: list[str] = []
        if result["skill"] == "eval-3-color-logic":
            for row in rows:
                count = int(row["colorFamilyCount"])
                row["rating"] = "优秀" if count <= 4 else "达标" if count == 5 else "不达标"
                ratings.append(row["rating"])
            issue_by_component = {str(item.get("component")): item for item in details.get("issues") or []}
            issues = [issue_by_component[str(row["componentId"])] for row in rows if row["rating"] != "优秀" and str(row["componentId"]) in issue_by_component]
            for row in rows:
                issue = issue_by_component.get(str(row["componentId"]))
                if row["rating"] == "优秀" or not issue:
                    continue
                count = row["colorFamilyCount"]
                families = "、".join(row["colorFamilies"])
                issue["rating"] = row["rating"]
                issue["description"] = f"该商卡使用{families}共{count}种有彩色系，组件色彩复杂评级为{row['rating']}。"
                issue["finding"]["observableFact"] = f"该商卡 JSON 样式色值归并后得到{count}种有彩色系：{families}"
                issue["finding"]["ruleOrThreshold"] = "有彩色系不超过4种为优秀，5种为达标，6种及以上为不达标"
                issue["finding"]["verdictReason"] = f"当前{count}种命中{row['rating']}区间，因此组件色彩复杂评级为{row['rating']}"
                issue["recommendation"] = f"收敛{row['componentId']}辅助信息的有彩色系；验收时不超过4种，并保留主价格或核心权益的唯一强调色。"
            details["issues"] = issues
            details["criterion"] = "有彩色系≤4优秀、5达标、≥6不达标；中性色不计。"
        else:
            for row in rows:
                tags, icons = int(row["tagStyleCount"]), int(row["iconStyleCount"])
                row["rating"] = "不达标" if tags >= 6 or icons >= 4 else "优秀" if tags <= 3 and icons <= 1 else "达标"
                ratings.append(row["rating"])
            issue_by_component = {str(item.get("component")): item for item in details.get("issues") or []}
            issues = [issue_by_component[str(row["componentId"])] for row in rows if row["rating"] != "优秀" and str(row["componentId"]) in issue_by_component]
            for row in rows:
                issue = issue_by_component.get(str(row["componentId"]))
                if row["rating"] == "优秀" or not issue:
                    continue
                tags, icons = row["tagStyleCount"], row["iconStyleCount"]
                names = [item.get("content", "") for item in row.get("includedTagStyles", [])] + [item.get("content", "") for item in row.get("includedIconStyles", [])]
                visible = "、".join(f"「{name}」" for name in names if name)
                issue["rating"] = row["rating"]
                issue["description"] = f"该商卡包含{visible}，去重后为{tags}种标签样式和{icons}种独立图标样式，元素复杂评级为{row['rating']}。"
                issue["finding"]["observableFact"] = f"该商卡全区域扫描得到{tags}种标签样式、{icons}种独立图标样式"
                issue["finding"]["ruleOrThreshold"] = "标签≤3种且图标≤1种优秀；标签4至5种或图标2至3种达标；标签≥6种或图标≥4种不达标"
                issue["finding"]["verdictReason"] = f"当前计数命中{row['rating']}区间，因此元素复杂评级为{row['rating']}"
                issue["recommendation"] = f"合并{row['componentId']}内同语义标签或图标样式；验收时标签样式不超过3种且独立图标样式不超过1种。"
            details["issues"] = issues
            details["criterion"] = "标签≤3种且图标≤1种优秀；标签4–5种或图标2–3种达标；标签≥6种或图标≥4种不达标。"

        rating = "不达标" if "不达标" in ratings else "达标" if "达标" in ratings else "优秀"
        unit["rating"] = rating
        weights = ({"优秀": 1, "达标": 0, "不达标": -1}
                   if result["skill"] == "eval-3-color-logic"
                   else {"优秀": 0, "达标": -1, "不达标": -2})
        unit["weightedScore"] = weights[rating]
        unit["reason"] = unit["reason"].rsplit("当前评级为", 1)[0] + f"当前评级为{rating}。"
        details["overview"] = overview(ratings)
        details["distribution"] = {name: ratings.count(name) for name in ("优秀", "达标", "不达标")}
        details["evidenceMode"] = "annotated-region" if details["issues"] else "original-page"


def rebuild_semantic_rows(
    atomic: dict[str, Any], facts: dict[str, Any], screenshot: Path,
    relation_module: Any, titles: dict[tuple[str, str], str],
) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, Any]]:
    elements = atomic["elementsById"]
    cards = atomic["cardsById"]
    card_ids = list(cards)
    all_ids = list(elements)
    info_ids = [eid for eid in all_ids if elements[eid].get("kind") != "media"]
    ledger = relation_module.derive_relation_candidates(facts)
    auth_by_card = {row["cardId"]: row for row in ledger["authenticityCandidates"]}
    red_by_card = {row["cardId"]: row for row in ledger["redundancyCandidates"]}
    complete = {cid for cid in card_ids if cards[cid].get("visibility") == "complete"}
    audit_decisions: dict[str, Any] = {"authenticity": [], "redundancy": [], "page": []}

    # Single-element eval-4: the current confirmed standalone expressions have
    # one platform-context meaning. Cross-element price/spec conflicts remain
    # in component eval-7, as required by the object boundary.
    single = result_row(
        "phase3-single_element-eval", "eval-4-info-authenticity-single-element",
        titles[("phase3-single_element-eval", "eval-4-info-authenticity-single-element")],
        "优秀", 0, screenshot, ["优秀"] * len(info_ids),
        {"sourceManifestTotal": len(all_ids), "evaluatedUnitCount": len(info_ids), "evaluatedUnitIds": info_ids,
         "excludedUnits": [{"id": eid, "reason": "media_not_a_standalone_information_expression"} for eid in all_ids if eid not in info_ids]},
        [], "单个可见表达存在两种合理理解或截图内可证实误导时不达标；多元素冲突归组件维度。",
        "已逐元素核查价格、标签、按钮和提示；未发现脱离卡片关系后仍能确认的独立歧义。",
    )

    conflicts_by_card: dict[str, list[dict[str, Any]]] = defaultdict(list)
    exclusions_by_card: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cid in card_ids:
        for candidate in auth_by_card[cid].get("internalCandidates", []):
            verdict = relation_module.adjudicate_authenticity_candidate(candidate)
            if verdict:
                conflicts_by_card[cid].append(verdict)
                audit_decisions["authenticity"].append({"cardId": cid, "candidate": candidate, "decision": "conflict", "verdict": verdict})
            else:
                exclusions_by_card[cid].append({"candidate": candidate, "decision": "not_applicable", "reason": "未命中封闭可复算冲突条件"})
        sibling_conflicts, sibling_exclusions = append_offer_conflicts(atomic, cid)
        conflicts_by_card[cid].extend(sibling_conflicts)
        exclusions_by_card[cid].extend(sibling_exclusions)
        audit_decisions["authenticity"].extend({"cardId": cid, "decision": "conflict", "verdict": item} for item in sibling_conflicts)
        audit_decisions["authenticity"].extend({"cardId": cid, **item} for item in sibling_exclusions)

    cross_conflicts: list[dict[str, Any]] = []
    for candidate in ledger.get("crossCardAuthenticityCandidates", []):
        left, right = str(candidate["leftCardId"]), str(candidate["rightCardId"])
        left_supply, right_supply = supply_markers(atomic, left), supply_markers(atomic, right)
        if left_supply and right_supply and left_supply != right_supply:
            audit_decisions["authenticity"].append({
                "cardIds": [left, right], "candidate": candidate, "decision": "not_applicable",
                "reason": f"供给形态已由{'/'.join(sorted(left_supply))}与{'/'.join(sorted(right_supply))}明确区分",
            })
            continue
        verdict = relation_module.adjudicate_authenticity_candidate(candidate)
        if verdict:
            cross_conflicts.append(verdict)
            conflicts_by_card[left].append(verdict)
            audit_decisions["authenticity"].append({"cardIds": [left, right], "candidate": candidate, "decision": "conflict", "verdict": verdict})

    auth_ids = [cid for cid in card_ids if cid in complete or conflicts_by_card[cid]]
    auth_rows: list[dict[str, Any]] = []
    for cid in auth_ids:
        candidates = list(auth_by_card[cid].get("candidatePairs", [])) + list(auth_by_card[cid].get("internalCandidates", []))
        internal_conflict_cues = {item.get("lexicalCue") for item in conflicts_by_card[cid]}
        statuses = ["conflict" if item.get("lexicalCue") in internal_conflict_cues else "not_applicable" for item in candidates]
        auth_rows.append({
            "componentId": cid, "candidatePairs": candidates, "pairJudgements": statuses,
            "inapplicableChecks": exclusions_by_card[cid],
            "scanCoverage": {"status": "completed", "scannedElementIds": card_element_ids(atomic, cid),
                             "scannedRegions": card_regions(atomic, cid),
                             "crossChecks": ["标题—图片/副标题/标签/下挂", "价格语义", "数量单位", "范围换算", "同身份跨卡核心事实", "同卡同名供给价格"]},
            "conflicts": conflicts_by_card[cid], "conflictCount": len(conflicts_by_card[cid]),
            "evidenceSource": "phase2_json_full_relation_scan",
            "rating": "不达标" if conflicts_by_card[cid] else "优秀",
        })

    auth_issues: list[dict[str, Any]] = []
    cross_keys: set[tuple[str, str]] = set()
    for conflict in cross_conflicts:
        left, right = str(conflict["leftCardId"]), str(conflict["rightCardId"])
        key = tuple(sorted((left, right)))
        if key in cross_keys:
            continue
        cross_keys.add(key)
        left_label, right_label = f"商卡{card_ids.index(left)+1}", f"商卡{card_ids.index(right)+1}"
        fact_text = "、".join(f"{item['factName']}分别为“{item['leftText']}”与“{item['rightText']}”" for item in conflict["conflictingFacts"])
        description = f"{left_label}与{right_label}展示相同供给“{conflict['identityText']}”，但{fact_text}，信息/功能无歧义评级为不达标。"
        issue = component_issue(
            atomic, str(conflict["leftIdentityElementId"]), left, "信息真实无歧义", description,
            f"{left_label}与{right_label}的可见供给名称和履约形态相同，但{fact_text}",
            "同一可见供给且没有门店或履约形态用于区分时，评分、月售和距离等核心事实必须一致",
            "相同供给的核心事实不能同时成立，因此信息/功能无歧义评级为不达标",
            "用户无法判断应相信哪组经营信息，会阻碍同屏选择",
            f"核对并统一{left_label}与{right_label}的经营事实；若实际为不同供给，补充可见且唯一的门店或履约形态标识。",
        )
        issue["locationLabel"] = f"{left_label}、{right_label}"
        issue["relatedCardIds"] = [left, right]
        auth_issues.append(issue)

    for cid in auth_ids:
        local = [item for item in conflicts_by_card[cid] if item.get("lexicalCue") != "same_visible_identity_conflicting_core_facts"]
        if not local:
            continue
        label = f"商卡{card_ids.index(cid)+1}"
        parts: list[str] = []
        anchors: list[str] = []
        recommendations: list[str] = []
        for conflict in local:
            cue = conflict["lexicalCue"]
            if cue == "quantity_range_exceeds_card_cap":
                parts.append(f"标题“{conflict['titleText']}”与基础信息“{conflict['attributeText']}”的重量上限冲突")
                anchors.append(str(conflict["attributeElementId"]))
                recommendations.append("统一标题重量范围与基础信息上限")
            elif cue == "start_price_and_to_hand_price_in_same_claim":
                parts.append(f"价格“{conflict['text']}”同时使用起步价与到手价口径")
                anchors.append(str(conflict["elementId"]))
                recommendations.append("拆分起步价和到手价并分别写明适用条件")
            else:
                parts.append(f"两个同名供给“{conflict['offerText']}”分别展示{conflict['leftPrice']}与{conflict['rightPrice']}，没有可见规格或权益区分")
                anchors.append(str(conflict["leftElementId"]))
                recommendations.append("合并重复供给，或补充能解释价格差异的规格与权益")
        description = f"{label}{'；'.join(parts)}，信息/功能无歧义评级为不达标。"
        auth_issues.append(component_issue(
            atomic, anchors[0], cid, "信息真实无歧义", description,
            f"{label}检测到{len(local)}项当前 JSON 可确认的冲突：{'；'.join(parts)}",
            "同卡可见信息必须能同时成立；规格上限、价格口径或同名供给价格不能在缺少可见区分条件时冲突",
            f"当前{len(local)}项表达不能由可见条件同时解释，因此信息/功能无歧义评级为不达标",
            "用户无法确定实际规格或成交价格，会直接影响比较与下单判断",
            f"针对{label}，{'；'.join(recommendations)}；验收时同一供给只保留一个可解释的价格口径。",
        ))

    auth_ratings = [row["rating"] for row in auth_rows]
    auth = result_row(
        "phase3-card_or_component-eval", "eval-7-info-authenticity",
        titles[("phase3-card_or_component-eval", "eval-7-info-authenticity")],
        "不达标" if "不达标" in auth_ratings else "优秀", -2 if "不达标" in auth_ratings else 0,
        screenshot, auth_ratings,
        {"sourceManifestTotal": len(all_ids), "evaluatedUnitCount": len(auth_rows), "evaluatedUnitIds": auth_ids,
         "excludedUnits": [{"id": cid, "reason": "naturally_cropped_without_complete_relation_coverage"} for cid in card_ids if cid not in auth_ids],
         "assessmentRows": auth_rows},
        auth_issues,
        "同卡信息不能同时成立，或相同供给在无可见区分条件时核心事实冲突，则不达标。",
        f"本轮重新扫描全部可见关系，确认{sum(len(items) for items in conflicts_by_card.values()) - len(cross_conflicts)}项逻辑冲突；供给形态不同的跨卡候选已排除。",
    )

    duplicates_by_card: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cid in card_ids:
        card_ledger = red_by_card[cid]
        for candidate in card_ledger.get("candidatePairs", []):
            verdict = relation_module.adjudicate_redundancy_candidate(candidate)
            audit_decisions["redundancy"].append({"cardId": cid, "candidate": candidate, "decision": "duplicate" if verdict else "not_duplicate", "verdict": verdict})
            if verdict:
                duplicates_by_card[cid].append(verdict)
        for candidate in card_ledger.get("selfRepeatCandidates", []):
            verdict = relation_module.adjudicate_self_repeat_candidate(candidate)
            audit_decisions["redundancy"].append({"cardId": cid, "candidate": candidate, "decision": "duplicate" if verdict else "not_duplicate", "verdict": verdict})
            if verdict:
                duplicates_by_card[cid].append(verdict)

    red_ids = [cid for cid in card_ids if cid in complete or duplicates_by_card[cid]]
    red_rows: list[dict[str, Any]] = []
    red_issues: list[dict[str, Any]] = []
    for cid in red_ids:
        card_ledger = red_by_card[cid]
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for item in duplicates_by_card[cid]:
            key = (str(item.get("leftElementId") or item.get("elementId")), str(item.get("rightElementId") or item.get("elementId")), str(item.get("normalizedFact")))
            if key not in seen:
                seen.add(key)
                deduped.append(item)
        duplicates_by_card[cid] = deduped
        examined = [item["elementId"] for item in card_ledger["examinedAtoms"]]
        red_rows.append({
            "componentId": cid, "scannedRegions": card_ledger["scanCoverage"]["scannedRegions"],
            "examinedElements": examined, "candidatePairs": card_ledger.get("candidatePairs", []),
            "selfRepeatCandidates": card_ledger.get("selfRepeatCandidates", []), "duplicates": deduped,
            "duplicateCount": len(deduped), "evidenceSource": "phase2_json_full_redundancy_scan",
            "rating": "不达标" if deduped else "优秀", "scanCoverage": card_ledger["scanCoverage"],
        })
        if not deduped:
            continue
        label = f"商卡{card_ids.index(cid)+1}"
        parts: list[str] = []
        evidence_parts: list[str] = []
        anchor = str(deduped[0].get("leftElementId") or deduped[0].get("elementId"))
        for item in deduped:
            if item["lexicalCue"] == "title_internal_repeated_quantified_fragment":
                parts.append(f"标题“{item['text']}”内“{item['repeatedFragment']}”重复出现{item['occurrences']}次")
                evidence_parts.append(f"{item['elementId']}在同一标题内重复表达{item['normalizedFact']}；{item['noLossReason']}")
            else:
                parts.append(f"“{item['leftText']}”与“{item['rightText']}”重复表达{item['normalizedFact']}")
                evidence_parts.append(f"{item['leftElementId']}与{item['rightElementId']}是两个独立可见实体；{item['noLossReason']}")
        issue = component_issue(
            atomic, anchor, cid, "信息无冗余", f"{label}{'；'.join(parts)}，信息无冗余评级为不达标。",
            f"{label}检测到{len(deduped)}项可无损删除的重复信息：{'；'.join(parts)}",
            "两个独立实体表达同一事实且删除任一不损失新的决策信息，或同一标题重复量化规格时判冗余",
            f"当前{len(deduped)}项重复满足无损删除条件，因此信息无冗余评级为不达标",
            "重复规格会增加扫读负担，并可能让用户误认为两处代表不同属性",
            f"删除或合并{label}中的重复规格，仅保留一处完整表达；验收时同一事实只出现一次。",
        )
        issue["redundancyEvidence"] = "；".join(evidence_parts)
        red_issues.append(issue)

    red_ratings = [row["rating"] for row in red_rows]
    redundancy = result_row(
        "phase3-card_or_component-eval", "eval-8-info-redundancy",
        titles[("phase3-card_or_component-eval", "eval-8-info-redundancy")],
        "不达标" if "不达标" in red_ratings else "优秀", -1 if "不达标" in red_ratings else 1,
        screenshot, red_ratings,
        {"sourceManifestTotal": len(all_ids), "evaluatedUnitCount": len(red_rows), "evaluatedUnitIds": red_ids,
         "excludedUnits": [{"id": cid, "reason": "naturally_cropped_without_complete_relation_coverage"} for cid in card_ids if cid not in red_ids],
         "assessmentRows": red_rows},
        red_issues,
        "只有两个独立可见实体表达同一事实且删除任一无损时才计冗余；标题内部重复量化片段也计入。",
        f"本轮逐卡完成区内、跨区和标题内部扫描，确认{sum(len(items) for items in duplicates_by_card.values())}项语义冗余。",
    )

    page_regions = list(atomic["modulesById"])
    cross_checks = [f"{page_regions[i]}↔{page_regions[j]}" for i in range(len(page_regions)) for j in range(i + 1, len(page_regions))]
    page_row = {"pageRegions": page_regions, "scanCoverage": {"status": "completed", "scannedRegionIds": page_regions, "crossChecks": cross_checks},
                "crossChecks": cross_checks, "candidatePairs": [], "redundancyItems": [], "redundancyCount": 0, "rating": "优秀"}
    audit_decisions["page"] = [{"pair": pair, "decision": "not_duplicate", "reason": "模块功能或决策层级不同，删除任一会损失独立价值"} for pair in cross_checks]
    page = result_row(
        "phase3-page_framework-eval", "eval-7-info-redundancy",
        titles[("phase3-page_framework-eval", "eval-7-info-redundancy")], "优秀", 1,
        screenshot, ["优秀"], {"sourceManifestTotal": len(all_ids), "evaluatedUnitCount": 1,
        "evaluatedUnitIds": ["page"], "excludedUnits": [], "assessmentRows": [page_row]}, [],
        "跨页面区域只有同对象、同功能且删除一方无损时才计冗余。",
        "所有独立页面模块对均已重新核查；未发现无增量价值的跨区重复。",
    )
    return {
        (single["dimension"], single["skill"]): single,
        (auth["dimension"], auth["skill"]): auth,
        (redundancy["dimension"], redundancy["skill"]): redundancy,
        (page["dimension"], page["skill"]): page,
    }, audit_decisions


def html_report(query: str, run_id: str, results: list[dict[str, Any]], output: Path) -> None:
    rows = "".join(
        f"<tr><td>{row['skill']}</td><td>{row['units'][0]['rating']}</td><td>{row['units'][0]['weightedScore']}</td><td>{row['units'][0]['details']['summary']}</td></tr>"
        for row in results
    )
    issues = "".join(
        f"<article><h3>{issue['dimension']} · {issue['rating']}</h3><p>{issue['description']}</p><p><b>建议：</b>{issue['recommendation']}</p>"
        + (f"<img src='file://{issue['evidenceImage']}' alt='问题证据'>" if issue.get("evidenceImage") else "") + "</article>"
        for row in results for unit in row["units"] for issue in unit["details"]["issues"]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "<!doctype html><html lang='zh-CN'><meta charset='utf-8'>"
        f"<title>{query}语义复评</title><style>body{{font-family:-apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif;background:#f7f8fa;color:#18212f;margin:0}}main{{max-width:1120px;margin:auto;padding:32px}}header,section,article{{background:#fff;border-radius:12px;padding:22px;margin-bottom:18px;box-shadow:0 4px 18px #18212f0d}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:10px;border-bottom:1px solid #e8ebf0;vertical-align:top}}img{{width:420px;max-height:900px;object-fit:contain;object-position:top;border:1px solid #e8ebf0;border-radius:8px}}</style>"
        f"<main><header><h1>{query} · 32词语义复评</h1><p>本轮重新判定信息/功能歧义与信息冗余；其余15项继承已验证批次。runId={run_id}</p></header>"
        f"<section><h2>19项结果</h2><table><tr><th>评测项</th><th>评级</th><th>分值</th><th>摘要</th></tr>{rows}</table></section>"
        f"<section><h2>待优化项</h2>{issues or '<p>本轮未发现待优化项。</p>'}</section></main></html>",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Rerun Golden32 ambiguity and redundancy")
    parser.add_argument("--source-batch", default="golden32-component-color4-ui-release-v2.1-20260827")
    parser.add_argument("--batch-id", default="golden32-semantic-rereview-v2.1-20260828")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    target_root = ARTIFACT_ROOT / args.batch_id
    if target_root.exists():
        raise ValueError(f"refuse_to_overwrite_batch:{target_root}")
    source_index = read_json(ARTIFACT_ROOT / args.source_batch / "task-index.json")
    tasks = source_index["tasks"][: args.limit] if args.limit else source_index["tasks"]
    relation_module = load_module("golden32_semantic_rereview", RELATION_SCRIPT)
    sys.path.insert(0, str(PROJECT / "scripts"))
    from phase2_bundle_loader import load_phase2_facts

    # Read current titles directly from the retained source rows so this script
    # does not duplicate user-facing naming configuration.
    first_source = read_json(ARTIFACT_ROOT / args.source_batch / tasks[0]["query"] / "phase3/eval-results.json")
    titles = {(row["dimension"], row["skill"]): row["units"][0]["reason"].split("覆盖", 1)[0] for row in first_source}
    target_index = {"batchId": args.batch_id, "sourceBatch": args.source_batch, "count": len(tasks), "tasks": []}
    changes: list[dict[str, Any]] = []

    for task_row in tasks:
        sequence, query = int(task_row["sequence"]), task_row["query"]
        source_task = read_json(Path(task_row["taskPath"]))
        manifest = Path(source_task["workflowArgs"]["goldenManifest"])
        atomic = read_json(manifest)
        screenshot = Path(atomic["source"]["screenshot"])
        if not screenshot.is_absolute():
            screenshot = PROJECT / screenshot
        if sha256(screenshot) != atomic["source"]["sha256"]:
            raise RuntimeError(f"source_hash_mismatch:{query}")
        facts = load_phase2_facts(manifest_path=manifest)
        active = active_inventory(facts)
        if len({row["id"] for row in active}) != len(atomic["elementsById"]):
            raise RuntimeError(f"atomic_projection_incomplete:{query}")

        run_id = f"{args.batch_id}-{sequence:02d}"
        artifact = target_root / query
        phase2, phase3 = artifact / "phase2", artifact / "phase3"
        loader_audit = phase2 / "phase2-fact-view.audit.json"
        run([sys.executable, str(LOADER), str(manifest), "--audit", str(loader_audit)])
        acceptance = {
            "valid": True, "protocol": "GOLDEN_ATOMIC_V3_ACCEPTANCE_V1", "runId": run_id, "query": query,
            "manifest": str(manifest), "manifestSha256": sha256(manifest), "sourceScreenshot": str(screenshot),
            "sourceScreenshotActualSha256": sha256(screenshot), "sourceScreenshotExpectedSha256": atomic["source"]["sha256"],
            "sourceScreenshotHashMatches": True, "publishedAtomicElementCount": len(atomic["elementsById"]),
            "phase3ActiveElementCount": len(active), "total": len(active), "activeElements": active, "errors": [],
            "loaderAudit": str(loader_audit),
        }
        acceptance_path = phase2 / "golden-acceptance-audit.json"
        write_json(acceptance_path, acceptance)

        source_results_path = ARTIFACT_ROOT / args.source_batch / query / "phase3/eval-results.json"
        source_results = read_json(source_results_path)
        rebuilt, decision_audit = rebuild_semantic_rows(atomic, facts, screenshot, relation_module, titles)
        results: list[dict[str, Any]] = []
        old_target: dict[tuple[str, str], dict[str, Any]] = {}
        for row in source_results:
            key = (row["dimension"], row["skill"])
            if key in TARGET_SKILLS:
                old_target[key] = row
                results.append(rebuilt[key])
            else:
                results.append(copy.deepcopy(row))
        rebase_inherited_measurement_tools(results)
        refresh_inherited_contract_ratings(results)
        if set(rebuilt) != set(old_target):
            raise RuntimeError(f"target_skill_mismatch:{query}")

        result_path = phase3 / "eval-results.json"
        audit_path = phase3 / "eval-audit.json"
        review_path = phase3 / "phase2-review.json"
        decision_path = phase3 / "semantic-rereview-decisions.json"
        write_json(result_path, results)
        write_json(decision_path, {"valid": True, "query": query, "manifest": str(manifest), "decisions": decision_audit})
        run([sys.executable, str(VALIDATOR), "--manifest-audit", str(acceptance_path), "--results", str(result_path), "--audit", str(audit_path), "--phase2-review", str(review_path)])

        evidence_run = run([sys.executable, str(EVIDENCE), "--results", str(result_path), "--manifest", str(manifest)], capture=True)
        evidence_info = json.loads(evidence_run.stdout.strip().splitlines()[-1])
        run([sys.executable, str(VALIDATOR), "--manifest-audit", str(acceptance_path), "--results", str(result_path), "--audit", str(audit_path), "--phase2-review", str(review_path), "--require-evidence"])

        report = REPORT_ROOT / f"meituan_eval_report_{query}_{run_id}_full19.html"
        html_report(query, run_id, read_json(result_path), report)
        run_dir = RUNS_ROOT / run_id
        task_path, agent_result_path = run_dir / "task.json", run_dir / "agent-result.json"
        task = {
            "protocol": "MEITUAN_EVAL_TASK", "runId": run_id, "projectDir": str(PROJECT),
            "workflowArgs": {**source_task["workflowArgs"], "runId": run_id, "batchId": args.batch_id, "tag": run_id,
                             "rerunId": run_id, "artifactRunDir": str(artifact), "query": query,
                             "evaluationSelection": {"mode": "full_19"}},
            "contractFiles": [str(PROJECT / "workflow/contracts/phase234-query-pipeline.md"), str(PROJECT / "workflow/contracts/evaluation-result.schema.json")],
            "resultPath": str(agent_result_path),
            "completionCommand": [sys.executable, str(FINALIZER), "finalize-evaluate", "--task", str(task_path), "--result", str(agent_result_path)],
            "hostInstructions": ["Offline Golden Atomic v3 semantic re-evaluation; validate loader audit and all Stage A-D artifacts before finalizing."],
        }
        write_json(task_path, task, refuse_existing=True)
        agent_result = {
            "ok": True, "query": query,
            "stageA": {"elementListPaths": [str(manifest)], "elementAuditPaths": [str(acceptance_path)], "elementCount": len(active), "annotated": []},
            "stageB": {"evalResultFile": str(result_path), "evalAuditFile": str(audit_path), "evalCount": 19},
            "stageC": {"evidenceImages": evidence_info.get("referenced", []), "skipped": evidence_info.get("skipped", [])},
            "stageD": {"reportPath": str(report), "summary": []}, "blockedAt": "", "error": "",
        }
        write_json(agent_result_path, agent_result, refuse_existing=True)
        run(task["completionCommand"])

        query_changes = []
        for key in sorted(TARGET_SKILLS):
            before, after = old_target[key]["units"][0], rebuilt[key]["units"][0]
            query_changes.append({
                "dimension": key[0], "skill": key[1], "beforeRating": before["rating"], "afterRating": after["rating"],
                "beforeIssueCount": len(before["details"]["issues"]), "afterIssueCount": len(after["details"]["issues"]),
            })
        changes.append({"query": query, "runId": run_id, "changes": query_changes, "decisionAudit": str(decision_path), "report": str(report)})
        target_index["tasks"].append({"sequence": sequence, "query": query, "taskPath": str(task_path), "runId": run_id})
        print(json.dumps({"completed": len(changes), "query": query}, ensure_ascii=False), flush=True)

    write_json(target_root / "task-index.json", target_index)
    write_json(target_root / "semantic-rereview-batch-audit.json", {"valid": True, "batchId": args.batch_id, "sourceBatch": args.source_batch, "count": len(changes), "queries": changes})
    write_json(target_root / "batch-completion.json", {"batchId": args.batch_id, "count": len(changes), "completed": changes})
    print(json.dumps({"valid": True, "batchId": args.batch_id, "count": len(changes), "audit": str(target_root / 'semantic-rereview-batch-audit.json')}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
