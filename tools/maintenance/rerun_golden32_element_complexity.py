#!/usr/bin/env python3
"""Re-evaluate Golden32 element complexity from current Atomic v3 JSON.

This append-only maintenance run replaces only component eval-4.  It excludes
cropped cards and classifies every atom before building five-part style keys;
neutral, containerless auxiliary text is never counted merely because Phase2
uses ``kind=tag`` for its semantic boundary.
"""
from __future__ import annotations

import argparse
import colorsys
import copy
import importlib.util
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
BASE_SCRIPT = PROJECT / "tools/maintenance/rerun_golden32_semantics.py"
TARGET = ("phase3-card_or_component-eval", "eval-4-element-complexity")
FULFILLMENT_SLOTS = {"fulfillment", "fulfillment_tag", "delivery_time", "delivery_time_tag"}
FULFILLMENT_TEXT = {"到店", "外卖", "快递", "酒店", "住宿", "上门", "在线", "景点", "闪购"}
APPEND_REGIONS = {"text_append", "append_items"}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot_import:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = load_module("golden32_element_complexity_base", BASE_SCRIPT)


def run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=PROJECT, check=True, text=True, capture_output=capture)


def text_of(element: dict[str, Any]) -> str:
    return str(element.get("text") or element.get("semanticDescription") or "图片/图标")


def normalize_hex(value: Any) -> tuple[int, int, int] | None:
    token = str(value or "").strip().lstrip("#")
    if len(token) == 3:
        token = "".join(character * 2 for character in token)
    if len(token) not in {6, 8}:
        return None
    try:
        return tuple(int(token[index:index + 2], 16) for index in (0, 2, 4))
    except ValueError:
        return None


def color_family(value: Any) -> str:
    rgb = normalize_hex(value)
    if rgb is None:
        return "neutral"
    red, green, blue = (channel / 255 for channel in rgb)
    hue, saturation, brightness = colorsys.rgb_to_hsv(red, green, blue)
    if saturation < 0.12 or brightness < 0.18:
        return "neutral"
    degrees = hue * 360
    if degrees < 15 or degrees >= 345:
        return "red"
    if degrees < 45:
        return "orange"
    if degrees < 70:
        return "yellow"
    if degrees < 165:
        return "green"
    if degrees < 195:
        return "cyan"
    if degrees < 255:
        return "blue"
    if degrees < 345:
        return "purple"
    return "red"


def visual_facts(element: dict[str, Any]) -> dict[str, Any]:
    visual = element.get("visual") if isinstance(element.get("visual"), dict) else {}
    families = {
        field: color_family(visual.get(field))
        for field in ("textColor", "backgroundColor", "borderColor")
    }
    non_neutral = [family for family in families.values() if family != "neutral"]
    container = str(visual.get("container") or "none").strip().lower()
    graphic = str(visual.get("graphicAssist") or "none").strip().lower()
    return {
        "families": families,
        "colorRole": non_neutral[0] if non_neutral else "neutral",
        "chromatic": bool(non_neutral),
        "container": container,
        "hasContainer": container not in {"", "none", "无容器"},
        "graphicAssist": graphic,
    }


def element_contexts(atomic: dict[str, Any], card_id: str) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for region_id in atomic["cardsById"][card_id]["regionIds"]:
        region = atomic["regionsById"][region_id]
        region_name = str(region.get("name") or "")
        for slot, element_ids in (region.get("slots") or {}).items():
            for element_id in element_ids:
                contexts.append({"elementId": element_id, "region": region_name, "slot": str(slot), "itemIndex": None})
        for item in region.get("items") or []:
            for slot, element_ids in (item.get("slots") or {}).items():
                for element_id in element_ids:
                    contexts.append({"elementId": element_id, "region": region_name, "slot": str(slot), "itemIndex": item.get("index")})
    return contexts


def is_core_field(slot: str, text: str, kind: str) -> str | None:
    compact = re.sub(r"\s+", "", text)
    if slot == "title":
        return "主标题排除"
    if re.fullmatch(r"\d(?:\.\d+)?分|\d+%", compact):
        return "核心评分值排除"
    if kind == "text" and re.match(r"^\d(?:\.\d+)?分", compact):
        return "评分开头的基础信息混合行排除"
    if slot in {"price", "price_and_trade", "price_and_sales", "average_spend"}:
        if kind == "text" and ("￥" in compact or "¥" in compact or compact.startswith("人均")):
            return "主价格及价格数字排除"
    if slot in {"merchant"}:
        return "主商家名称排除"
    return None


def classify_element(element: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    element_id = context["elementId"]
    text = text_of(element)
    compact = re.sub(r"\s+", "", text)
    kind = str(element.get("kind") or "")
    slot = context["slot"]
    visual = visual_facts(element)
    common = {
        "elementId": element_id, "region": context["region"], "slot": slot,
        "content": text, "entityKind": kind, "visual": visual,
    }
    if slot in FULFILLMENT_SLOTS or compact in FULFILLMENT_TEXT:
        return {**common, "decision": "excluded", "reason": "履约标排除"}
    core_reason = is_core_field(slot, text, kind)
    if core_reason:
        return {**common, "decision": "excluded", "reason": core_reason}
    if compact.startswith("新店入驻"):
        return {
            **common, "sourceContent": text, "content": "新店入驻",
            "decision": "included_tag",
            "reason": "混合基础信息行中可由 JSON 文本明确识别的彩色状态标签前缀",
        }
    if kind == "media":
        return {**common, "decision": "excluded", "reason": "供给图片或营销素材不计"}
    if kind == "icon":
        if visual["hasContainer"] or visual["graphicAssist"] not in {"", "none"}:
            return {**common, "decision": "included_icon", "reason": "脱离标签文字的独立图标样式"}
        return {**common, "decision": "included_icon", "reason": "已确认的独立功能图标样式"}
    if visual["hasContainer"] or visual["chromatic"]:
        return {
            **common, "decision": "included_tag",
            "reason": "存在独立容器形态或非中性色辅助表达",
        }
    return {
        **common, "decision": "excluded",
        "reason": "中性色文字、无容器且无图形辅助，不属于异形/异色标签",
    }


def style_key(candidate: dict[str, Any], kind: str) -> str:
    visual = candidate["visual"]
    entity = "标签" if kind == "tag" else "图标"
    return "|".join([
        entity, visual["colorRole"], candidate["slot"],
        visual["container"] or "none", visual["graphicAssist"] or "none",
    ])


def component_issue(
    atomic: dict[str, Any], card_id: str, number: int, row: dict[str, Any],
) -> dict[str, Any]:
    candidates = row["includedTagStyles"] + row["includedIconStyles"]
    anchor_id = candidates[0]["elementIds"][0]
    element = atomic["elementsById"][anchor_id]
    names = [item["content"] for item in candidates]
    visible = "、".join(f"「{name}」" for name in names)
    tags, icons, rating = row["tagStyleCount"], row["iconStyleCount"], row["rating"]
    return {
        "elementId": anchor_id, "coord": element["bounds"], "component": card_id,
        "elementType": "标签" if element.get("kind") == "tag" else "图标" if element.get("kind") == "icon" else "文本",
        "content": text_of(element), "dimension": "静态元素复杂度",
        "description": f"商卡{number}包含{visible}，去重后为{tags}种标签样式和{icons}种独立图标样式，元素复杂评级为{rating}。",
        "rating": rating, "priority": "P1" if rating == "不达标" else "P2",
        "priorityReason": "多种异形异色标签或独立图标同时出现，会与标题和主价格竞争视觉注意力",
        "finding": {
            "observableFact": f"商卡{number}全区域扫描得到{tags}种标签样式、{icons}种独立图标样式",
            "ruleOrThreshold": "标签不超过3种且图标不超过1种为优秀；标签4至5种或图标2至3种为达标；标签不少于6种或图标不少于4种为不达标",
            "verdictReason": f"当前计数命中{rating}区间，因此元素复杂评级为{rating}",
            "userImpact": "标签或图标样式偏多会削弱标题、主价格和核心权益的视觉优先级",
        },
        "recommendation": f"合并商卡{number}内语义相近的标签或图标样式；验收时标签样式不超过3种且独立图标样式不超过1种。",
    }


def rebuild_result(atomic: dict[str, Any], screenshot: Path, title: str) -> tuple[dict[str, Any], dict[str, Any]]:
    cards = atomic["cardsById"]
    elements = atomic["elementsById"]
    result_ids = [
        card_id for module in atomic["modulesById"].values()
        if module.get("type") == "result_list"
        for card_id in module.get("cardIds", [])
    ]
    complete_ids = [card_id for card_id in result_ids if cards[card_id].get("visibility") == "complete"]
    rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    decision_audit: list[dict[str, Any]] = []
    for number, card_id in enumerate(complete_ids, start=1):
        contexts = element_contexts(atomic, card_id)
        ledger = [classify_element(elements[context["elementId"]], context) for context in contexts]
        tag_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        icon_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for candidate in ledger:
            if candidate["decision"] == "included_tag":
                candidate["styleKey"] = style_key(candidate, "tag")
                tag_groups[candidate["styleKey"]].append(candidate)
            elif candidate["decision"] == "included_icon":
                candidate["styleKey"] = style_key(candidate, "icon")
                icon_groups[candidate["styleKey"]].append(candidate)
        included_tags = [{
            "content": "、".join(item["content"] for item in members),
            "styleKey": key, "elementIds": [item["elementId"] for item in members],
            "countDecision": "异形容器或非中性色辅助表达计入",
            "dedupDecision": "五段式样式键相同的实例合并为一种",
        } for key, members in tag_groups.items()]
        included_icons = [{
            "content": "、".join(item["content"] for item in members),
            "elementId": members[0]["elementId"],
            "styleKey": key, "elementIds": [item["elementId"] for item in members],
            "countDecision": "脱离标签容器的独立图标计入",
            "dedupDecision": "五段式样式键相同的实例合并为一种",
        } for key, members in icon_groups.items()]
        tag_count, icon_count = len(included_tags), len(included_icons)
        rating = "不达标" if tag_count >= 6 or icon_count >= 4 else "优秀" if tag_count <= 3 and icon_count <= 1 else "达标"
        expected_regions = [atomic["regionsById"][region_id]["name"] for region_id in cards[card_id]["regionIds"]]
        row = {
            "componentId": card_id, "expectedRegions": expected_regions,
            "scannedRegions": expected_regions, "unscannedRegions": [],
            "scannedElementIds": [context["elementId"] for context in contexts],
            "candidateLedger": ledger, "phase2ReviewCandidates": [], "coverageStatus": "completed",
            "includedTagStyles": included_tags, "includedIconStyles": included_icons,
            "excludedEntities": [item["elementId"] for item in ledger if item["decision"] == "excluded"],
            "tagStyleCount": tag_count, "iconStyleCount": icon_count,
            "evidenceSource": "phase2_json_visual_inventory", "rating": rating,
        }
        rows.append(row)
        decision_audit.append({"componentId": card_id, "rating": rating, "candidateLedger": ledger,
                               "tagStyleCount": tag_count, "iconStyleCount": icon_count})
        if rating != "优秀":
            issues.append(component_issue(atomic, card_id, number, row))
    ratings = [row["rating"] for row in rows]
    rating = "不达标" if "不达标" in ratings else "达标" if "达标" in ratings else "优秀"
    evidence = {
        "sourceManifestTotal": len(elements), "evaluatedUnitCount": len(rows),
        "evaluatedUnitIds": complete_ids,
        "excludedUnits": [{"id": card_id, "reason": "naturally_cropped_or_incomplete_component"} for card_id in result_ids if card_id not in complete_ids],
        "assessmentRows": rows,
    }
    result = base.result_row(
        "phase3-card_or_component-eval", "eval-4-element-complexity", title,
        rating, {"优秀": 0, "达标": -1, "不达标": -2}[rating],
        screenshot, ratings, evidence, issues,
        "异形/异色标签样式不超过3种且独立图标不超过1种为优秀；标签4至5种或图标2至3种为达标；标签不少于6种或图标不少于4种为不达标。",
        "已扫描所有完整商卡的全部原子；中性色无容器文字、履约标、核心标题/评分/价格和自然裁切卡均已排除。",
    )
    return result, {"components": decision_audit, "excludedUnits": evidence["excludedUnits"]}


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
        f"<title>{query}元素复杂复评</title><style>body{{font-family:-apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif;background:#f7f8fa;color:#18212f;margin:0}}main{{max-width:1120px;margin:auto;padding:32px}}header,section,article{{background:#fff;border-radius:12px;padding:22px;margin-bottom:18px;box-shadow:0 4px 18px #18212f0d}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:10px;border-bottom:1px solid #e8ebf0;vertical-align:top}}img{{width:420px;max-height:900px;object-fit:contain;object-position:top;border:1px solid #e8ebf0;border-radius:8px}}</style>"
        f"<main><header><h1>{query} · 元素复杂复评</h1><p>本轮重新执行元素复杂度；其余18项继承已验收批次。runId={run_id}</p></header>"
        f"<section><h2>19项结果</h2><table><tr><th>评测项</th><th>评级</th><th>分值</th><th>摘要</th></tr>{rows}</table></section>"
        f"<section><h2>待优化项</h2>{issues or '<p>本轮未发现待优化项。</p>'}</section></main></html>", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Rerun Golden32 element complexity")
    parser.add_argument("--source-batch", default="golden32-hierarchy-comparability-final2-v2.1-20260831")
    parser.add_argument("--batch-id", default="golden32-element-complexity-rereview-final3-v2.1-20260831")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    target_root = ARTIFACT_ROOT / args.batch_id
    if target_root.exists():
        raise ValueError(f"refuse_to_overwrite_batch:{target_root}")
    source_index = base.read_json(ARTIFACT_ROOT / args.source_batch / "task-index.json")
    tasks = source_index["tasks"][: args.limit] if args.limit else source_index["tasks"]
    sys.path.insert(0, str(PROJECT / "scripts"))
    from phase2_bundle_loader import load_phase2_facts
    first_source = base.read_json(ARTIFACT_ROOT / args.source_batch / tasks[0]["query"] / "phase3/eval-results.json")
    title = next(row["units"][0]["reason"].split("覆盖", 1)[0] for row in first_source if (row["dimension"], row["skill"]) == TARGET)
    target_index = {"batchId": args.batch_id, "sourceBatch": args.source_batch, "count": len(tasks), "tasks": []}
    changes: list[dict[str, Any]] = []
    for task_row in tasks:
        sequence, query = int(task_row["sequence"]), task_row["query"]
        source_task = base.read_json(Path(task_row["taskPath"]))
        manifest = Path(source_task["workflowArgs"]["goldenManifest"])
        atomic = base.read_json(manifest)
        screenshot = Path(atomic["source"]["screenshot"])
        if not screenshot.is_absolute():
            screenshot = PROJECT / screenshot
        if base.sha256(screenshot) != atomic["source"]["sha256"]:
            raise RuntimeError(f"source_hash_mismatch:{query}")
        facts = load_phase2_facts(manifest_path=manifest)
        active = base.active_inventory(facts)
        if len({row["id"] for row in active}) != len(atomic["elementsById"]):
            raise RuntimeError(f"atomic_projection_incomplete:{query}")
        run_id = f"{args.batch_id}-{sequence:02d}"
        artifact = target_root / query
        phase2, phase3 = artifact / "phase2", artifact / "phase3"
        loader_audit = phase2 / "phase2-fact-view.audit.json"
        run([sys.executable, str(LOADER), str(manifest), "--audit", str(loader_audit)])
        acceptance = {
            "valid": True, "protocol": "GOLDEN_ATOMIC_V3_ACCEPTANCE_V1", "runId": run_id, "query": query,
            "manifest": str(manifest), "manifestSha256": base.sha256(manifest), "sourceScreenshot": str(screenshot),
            "sourceScreenshotActualSha256": base.sha256(screenshot), "sourceScreenshotExpectedSha256": atomic["source"]["sha256"],
            "sourceScreenshotHashMatches": True, "publishedAtomicElementCount": len(atomic["elementsById"]),
            "phase3ActiveElementCount": len(active), "total": len(active), "activeElements": active, "errors": [],
            "loaderAudit": str(loader_audit),
        }
        acceptance_path = phase2 / "golden-acceptance-audit.json"
        base.write_json(acceptance_path, acceptance)
        rebuilt, decision_audit = rebuild_result(atomic, screenshot, title)
        source_results = base.read_json(ARTIFACT_ROOT / args.source_batch / query / "phase3/eval-results.json")
        results: list[dict[str, Any]] = []
        before_target: dict[str, Any] | None = None
        for source_row in source_results:
            if (source_row["dimension"], source_row["skill"]) == TARGET:
                before_target = source_row
                results.append(rebuilt)
            else:
                results.append(copy.deepcopy(source_row))
        if before_target is None:
            raise RuntimeError(f"target_skill_missing:{query}")
        result_path, audit_path = phase3 / "eval-results.json", phase3 / "eval-audit.json"
        review_path, decision_path = phase3 / "phase2-review.json", phase3 / "element-complexity-decisions.json"
        base.write_json(result_path, results)
        base.write_json(decision_path, {"valid": True, "query": query, "manifest": str(manifest), **decision_audit})
        run([sys.executable, str(VALIDATOR), "--manifest-audit", str(acceptance_path), "--results", str(result_path), "--audit", str(audit_path), "--phase2-review", str(review_path)])
        evidence_run = run([sys.executable, str(EVIDENCE), "--results", str(result_path), "--manifest", str(manifest)], capture=True)
        evidence_info = json.loads(evidence_run.stdout.strip().splitlines()[-1])
        run([sys.executable, str(VALIDATOR), "--manifest-audit", str(acceptance_path), "--results", str(result_path), "--audit", str(audit_path), "--phase2-review", str(review_path), "--require-evidence"])
        report = REPORT_ROOT / f"meituan_eval_report_{query}_{run_id}_full19.html"
        html_report(query, run_id, base.read_json(result_path), report)
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
            "hostInstructions": ["Offline Golden Atomic v3 element-complexity re-evaluation; validate complete-card scope and full JSON inventory."],
        }
        base.write_json(task_path, task, refuse_existing=True)
        agent_result = {
            "ok": True, "query": query,
            "stageA": {"elementListPaths": [str(manifest)], "elementAuditPaths": [str(acceptance_path)], "elementCount": len(active), "annotated": []},
            "stageB": {"evalResultFile": str(result_path), "evalAuditFile": str(audit_path), "evalCount": 19},
            "stageC": {"evidenceImages": evidence_info.get("referenced", []), "skipped": evidence_info.get("skipped", [])},
            "stageD": {"reportPath": str(report), "summary": []}, "blockedAt": "", "error": "",
        }
        base.write_json(agent_result_path, agent_result, refuse_existing=True)
        run(task["completionCommand"])
        before, after = before_target["units"][0], rebuilt["units"][0]
        changes.append({
            "query": query, "runId": run_id,
            "beforeRating": before["rating"], "afterRating": after["rating"],
            "beforeIssueCount": len(before["details"]["issues"]), "afterIssueCount": len(after["details"]["issues"]),
            "decisionAudit": str(decision_path), "report": str(report),
        })
        target_index["tasks"].append({"sequence": sequence, "query": query, "taskPath": str(task_path), "runId": run_id})
        print(json.dumps({"completed": len(changes), "query": query}, ensure_ascii=False), flush=True)
    base.write_json(target_root / "task-index.json", target_index)
    batch_audit = target_root / "element-complexity-rereview-batch-audit.json"
    base.write_json(batch_audit, {"valid": True, "batchId": args.batch_id, "sourceBatch": args.source_batch, "count": len(changes), "queries": changes})
    base.write_json(target_root / "batch-completion.json", {"batchId": args.batch_id, "count": len(changes), "completed": changes})
    print(json.dumps({"valid": True, "batchId": args.batch_id, "count": len(changes), "audit": str(batch_audit)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
