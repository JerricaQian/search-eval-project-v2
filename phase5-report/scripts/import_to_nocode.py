#!/usr/bin/env python3
"""将治理看板数据集导入 NoCode 数据库。

用法：
  python3 phase5-report/scripts/import_to_nocode.py <dataset_json> <chat_id>

导入规则：
- 每次均创建一个 `evaluation_batches` 批次，并读取数据库返回的真实 batch_id。
- 所有明细表必须使用该真实 batch_id，禁止使用固定值。
- 批次、业务汇总、归因、桑基关联、逐词详情和规则均从同一 dataset 生成。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

BATCH_SIZE = 20


def invoke_nocode(args: list[str]) -> dict[str, Any]:
    """调用 NoCode CLI，并在失败时抛出可读错误。"""
    result = subprocess.run(
        ["nocode", *args],
        capture_output=True,
        text=True,
        timeout=90,
    )
    output = result.stdout.strip()
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or output or "NoCode CLI 调用失败")
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"NoCode CLI 返回非 JSON：{output[:500]}") from exc
    if payload.get("status") != "success":
        raise RuntimeError(payload.get("message") or f"NoCode 操作失败：{payload}")
    return payload


def insert_rows(chat_id: str, table: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按批插入，任一批失败即停止，避免错误地输出“导入成功”。"""
    inserted: list[dict[str, Any]] = []
    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start : start + BATCH_SIZE]
        print(f"  写入 {table} [{start}~{start + len(batch) - 1}]（{len(batch)} 行）…")
        payload = invoke_nocode([
            "database", "insert", chat_id,
            "--table", table,
            "--data", json.dumps(batch, ensure_ascii=False),
        ])
        inserted.extend(payload.get("data") or [])
        print("    ✓ 成功")
    return inserted


def priority_number(priority: str) -> int:
    return {"P0": 0, "P1": 1, "P2": 2, "观察": 3}.get(priority, 3)


def report_scope_query_count(batch_name: str, dataset_query_count: int) -> int:
    """Use the batch scope (for example, ``32词``) when it is explicitly named."""
    match = re.search(r"(\d+)词", batch_name)
    return int(match.group(1)) if match else dataset_query_count


def phase4_filename(query: str, image_path: Any) -> str:
    """Create a collision-free public filename from a dataset-owned evidence path."""
    path = str(image_path or "")
    return f"{query}__{path.rsplit('/', 1)[-1]}" if path else ""


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("用法：python3 phase5-report/scripts/import_to_nocode.py <dataset_json> <chat_id>")

    dataset_path, chat_id = sys.argv[1:]
    with open(dataset_path, encoding="utf-8") as file:
        dataset = json.load(file)

    batch_name = str(dataset.get("batch") or "未命名批次")
    dataset_query_count = int(dataset.get("queryCount") or 0)
    query_count = report_scope_query_count(batch_name, dataset_query_count)
    groups = list(dataset.get("groups") or [])
    businesses = list(dataset.get("businesses") or [])
    query_details = dataset.get("queryDetails") or {}
    if dataset_query_count <= 0 or dataset_query_count != len(query_details):
        raise RuntimeError("数据集搜索词计数与逐词详情不一致，停止导入")
    for word, units in query_details.items():
        if not units:
            raise RuntimeError(f"搜索词 {word} 没有评测明细，停止导入")
    valid_words = set(query_details)
    # 轻量 Phase2 模式不产出整页标注图；Phase4 evidenceImage 必须精确引用
    # 当前评测单元原图，不能把可选 annotatedImage 当作导入前置条件。
    for word, units in query_details.items():
        for unit in units:
            if unit.get("rating") != "未执行" and not unit.get("screenshot"):
                raise RuntimeError(f"搜索词 {word} 缺少原始截图路径，停止导入")
            screenshot = str(unit.get("screenshot") or "")
            for issue in unit.get("issues") or []:
                if not isinstance(issue, dict) or issue.get("rating") not in {"达标", "不达标", "🟡", "🔴"}:
                    continue
                evidence_image = str(issue.get("evidenceImage") or "")
                if not evidence_image or Path(evidence_image).resolve() != Path(screenshot).resolve():
                    raise RuntimeError(f"搜索词 {word} 的问题证据未引用所属原始截图，停止导入")
    for group in groups:
        for evidence_item in group.get("evidence") or []:
            if evidence_item.get("query") not in valid_words:
                raise RuntimeError("治理卡典型证据引用了当前批次之外的搜索词，停止导入")
            screenshot = str(evidence_item.get("screenshot") or "")
            evidence_image = str(evidence_item.get("evidenceImage") or "")
            if not screenshot or not evidence_image or Path(evidence_image).resolve() != Path(screenshot).resolve():
                raise RuntimeError("治理卡问题证据未引用所属原始截图，停止导入")
    print(f"数据集：{batch_name}；评测范围：{query_count} 词；有逐词明细：{dataset_query_count} 词；治理分组：{len(groups)}；业务线：{len(businesses)}")

    print("\n1. 创建评测批次")
    batch_rows = insert_rows(chat_id, "evaluation_batches", [{
        "batch_name": batch_name,
        "batch_date": dataset.get("generatedAt") or None,
        "description": f"查询数={query_count}",
    }])
    if len(batch_rows) != 1 or batch_rows[0].get("id") is None:
        raise RuntimeError("未获得新建批次的 batch_id，停止写入明细数据")
    batch_id = int(batch_rows[0]["id"])
    print(f"  当前 batch_id：{batch_id}")

    print("\n2. 写入业务汇总")
    # 汇总表按业务线一行写入问题项数和问题率，不计算或传递分数。
    summary_rows = [{
        "batch_id": batch_id,
        "metric_name": "业务线综合评测",
        "metric_value": business.get("issueCount", 0),
        "metric_unit": "项",
        "trend": "",
        "trend_value": business.get("problemRate", 0),
        "category": str(business.get("businessName", "")),
        "description": json.dumps({
            "level": "overall",
            "levelName": "业务总览",
            "businessCode": business.get("businessCode"),
            "businessName": business.get("businessName"),
            "issueCount": business.get("issueCount"),
            "problemCards": business.get("problemCards"),
            "evaluatedCards": business.get("evaluatedCards"),
            "problemRate": business.get("problemRate"),
        }, ensure_ascii=False),
    } for business in businesses]
    insert_rows(chat_id, "business_summary", summary_rows)

    print("\n3. 写入问题归因")
    # 每条数据库记录一一对应本地报告的一条问题 evidence，禁止将同指标下多
    # 个搜索词/卡片拼接成一段抽象描述或使用组级建议。这样两端的描述、优先级
    # 与 Phase4 绑定的原始截图证据才能逐条一致。
    issue_rows = []
    for group in groups:
        for evidence in group.get("evidence") or []:
            if not isinstance(evidence, dict) or evidence.get("rating") not in {"达标", "不达标", "🟡", "🔴"}:
                continue
            issue_priority = str(evidence.get("priority") or group.get("priority") or "P2")
            query = str(evidence.get("query") or "")
            description = str(evidence.get("description") or "")
            recommendation = str(evidence.get("recommendation") or "")
            issue_rows.append({
                "batch_id": batch_id,
                "issue_type": ", ".join(item.get("code", "") for item in group.get("findingDistribution", [])),
                "issue_title": f"{group.get('businessName', '')} - {group.get('levelName', '')} · {group.get('metricName', '')}",
                "issue_desc": description,
                "severity": {"P0": "high", "P1": "medium", "P2": "low"}.get(issue_priority, "low"),
                "suggestion": recommendation,
                "affected_count": 1,
                "priority": priority_number(issue_priority),
                "evidence_list": [{
                    "word": query,
                    "annotated_screenshot_file": phase4_filename(query, evidence.get("evidenceImage")),
                    "locate_desc": description,
                }],
            })
    insert_rows(chat_id, "issue_attribution", issue_rows)

    print("\n4. 写入业务 × 指标关联")
    relation_rows = [{
        "batch_id": batch_id,
        "source_node": group.get("businessName", ""),
        "target_node": f"{group.get('levelName', '')}·{group.get('metricName', '')}",
        "value": float(group.get("problemCardCount", 0)),
        "strength": "strong" if group.get("problemRate", 0) >= 50 else "medium" if group.get("problemRate", 0) >= 30 else "weak",
    } for group in groups if group.get("problemCardCount")]
    insert_rows(chat_id, "business_metric_relations", relation_rows)

    print("\n5. 写入逐词评测详情")
    # 逐词表必须覆盖本批次的全部评测项（不只是问题项），才能展示全部受评图片与
    # 完整评级；问题项优先写入最细粒度的 issue 描述作为判定依据。
    detail_rows = []
    for word, units in (dataset.get("queryDetails") or {}).items():
        for unit in units:
            issues = [item for item in (unit.get("issues") or []) if isinstance(item, dict)]
            evidence = "；".join(str(item.get("description", "")) for item in issues if item.get("description"))
            detail_rows.append({
                "batch_id": batch_id,
                "word": word,
                "card_type": "本轮评测项",
                "dimension": unit.get("levelName", ""),
                "metric_name": unit.get("metricName", ""),
                "rating": unit.get("rating", ""),
                # 不能截断判定依据：数据库 text/varchar 可保留完整可读描述，
                # 前端再通过弹窗/展开区承载长文本。
                "evidence": evidence or str(unit.get("reason", "")),
                "raw_screenshot_file": str(unit.get("screenshot", "")).rsplit("/", 1)[-1],
                "annotated_screenshot_file": phase4_filename(word, next((item.get("evidenceImage", "") for item in issues if item.get("evidenceImage")), unit.get("annotatedImage", ""))),
            })
    insert_rows(chat_id, "word_evaluation_details", detail_rows)

    print("\n6. 写入评测规则")
    unique_rules: dict[tuple[str, str], dict[str, Any]] = {}
    for group in groups:
        key = (str(group.get("levelName", "")), str(group.get("metricCode", "")))
        unique_rules.setdefault(key, {
            "rule_name": group.get("metricCode", ""),
            "rule_desc": group.get("metricName", ""),
            "dimension": group.get("levelName", ""),
        })
    insert_rows(chat_id, "evaluation_rules", list(unique_rules.values()))

    print("\n导入完成")
    print(json.dumps({
        "batchId": batch_id,
        "batch": batch_name,
        "businessSummary": len(summary_rows),
        "issueAttribution": len(issue_rows),
        "relations": len(relation_rows),
        "wordDetails": len(detail_rows),
        "rules": len(unique_rules),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
