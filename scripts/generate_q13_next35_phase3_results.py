#!/usr/bin/env python3
"""Generate q13 from the validated merchant-card scaffold, then apply q13 judgements."""

import json
from pathlib import Path

ROOT = Path("/Users/qianjing/Documents/ChatGPT/search-eval-project-v2")
RUN = "batch-20260920-09-2-next35-r1-q13"
BATCH = "batch-20260920-09-2-next35-r1"
QUERY = "有福羊肉面"
STEM = "有福羊肉面_全部_1"
SHOT = str(ROOT / f"screenshots/{STEM}.png")
MANIFEST = ROOT / f"screenshots-out/elements_{STEM}_{RUN}.json"
AUDIT = ROOT / f"screenshots-out/elements_{STEM}_{RUN}.audit.json"
BASE = ROOT / f".artifacts/过程文件-评测结果与审计/{BATCH}/{RUN}"
MEASURE = BASE / f"phase3/measurements/elements_{STEM}_{RUN}.component-color-families.json"
OUT = BASE / f"results/评测原始结果_{RUN}.json"

# Reuse the already validated 15-dimension merchant-card scaffold with q13 paths.
source_path = ROOT / "scripts/generate_q8_next35_phase3_results.py"
source = source_path.read_text(encoding="utf-8")
source = source.replace('RUN = "batch-20260920-09-2-next35-r1-q8"', f'RUN = "{RUN}"')
source = source.replace('QUERY = "新食味隆江猪脚饭"', f'QUERY = "{QUERY}"')
source = source.replace('STEM = "新食味隆江猪脚饭_全部_1"', f'STEM = "{STEM}"')
namespace = {"__name__": "__main__", "__file__": str(source_path)}
exec(compile(source, str(source_path), "exec"), namespace)

manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
audit = json.loads(AUDIT.read_text(encoding="utf-8"))
active = {item["id"]: item for item in audit["activeElements"]}
colors = json.loads(MEASURE.read_text(encoding="utf-8"))["components"]
results = json.loads(OUT.read_text(encoding="utf-8"))
cards = manifest["cards"]


def unit(skill):
    return next(item["units"][0] for item in results if item["skill"] == skill and item["dimension"] == "phase3-card_or_component-eval")


def page_unit(skill):
    return next(item["units"][0] for item in results if item["skill"] == skill and item["dimension"] == "phase3-page_framework-eval")


def elems(card):
    return [element for region in card["regions"] for element in region["elements"]]


def text_elems(card):
    return [element for element in elems(card) if not element.get("render", {}).get("isPhoto")]


def regions(card):
    return [region["name"] for region in card["regions"]]


def issue(element_id, component, description, recommendation, rating="不达标"):
    return {
        "elementId": element_id,
        "coord": active[element_id]["coord"],
        "component": component,
        "description": description,
        "rating": rating,
        "recommendation": recommendation,
        "evidenceImage": SHOT,
    }


cropped = [{"componentId": "C4", "reason": "底部自然裁切，不用于完整卡结论。"}]
for skill in ("eval-1-supply-completeness", "eval-2-visual-order-alignment", "eval-4-element-complexity", "eval-5-info-hierarchy", "eval-7-info-authenticity"):
    unit(skill)["details"]["evidence"]["excludedUnits"] = cropped

# Component color: C2 has five effective color families and is a pass.
u = unit("eval-3-color-logic")
u["rating"] = "达标"
u["reason"] = "4张可见商家卡的有效界面色系数分别为4、5、3、2；第2张因5种色系达标，其余优秀。"
u["details"]["overview"] = {"total": 4, "excellent": 3, "pass": 1, "fail": 0, "failRate": "0.0%"}
u["details"]["evidence"] = {"sourceManifestTotal": audit["total"], "evaluatedUnitCount": 4, "assessmentRows": colors}
u["details"]["issues"] = [issue(
    "C2-T10", "C2",
    "商卡2的可见界面色系为红、橙、黄、绿、青共5种，达到色彩逻辑的达标档，强调色角色偏多。",
    "统一商卡2中品牌、促销和到店标识的强调色，减少低频色彩角色；验收时确认有效界面色系不超过4种。",
    "达标",
)]

# Full redundancy scan: filter plus all four visible merchant cards.
checks = [
    "title/subtitle ↔ basic information",
    "title/subtitle ↔ tags/price/promotion",
    "tag ↔ price/promotion",
    "title internal repeated quantified fragments",
]
specs = {
    "C1": [
        ("C1-T1", "C1-T8", "崔有福 ↔ 图内崔有福", "商家品牌崔有福"),
    ],
    "C2": [
        ("C2-T1", "C2-T9", "豫福源·羊肉烩面 ↔ 店内提供豫福源羊肉烩面", "豫福源羊肉烩面供给"),
        ("C2-T1", "C2-T10", "豫福源 ↔ 图内豫福源", "商家品牌豫福源"),
        ("C2-T1", "C2-T11", "家常菜·羊肉烩面 ↔ 图内家常菜·羊肉烩面", "商家品类家常菜与羊肉烩面"),
    ],
    "C3": [
        ("C3-T1", "C3-T8", "羊福记 ↔ 图内羊福记", "商家品牌羊福记"),
        ("C3-T1", "C3-T6", "羊肉汤 ↔ 品类羊肉汤", "商家品类羊肉汤"),
    ],
}
red_rows = [{
    "componentId": "M4", "scannedRegions": ["位置与排序筛选区"], "examinedElements": ["M4"],
    "candidatePairs": [], "pairJudgements": [], "selfRepeatCandidates": [], "selfRepeatJudgements": [],
    "duplicates": [], "duplicateCount": 0,
    "scanCoverage": {"status": "completed", "textAtomCount": 1, "scannedElementIds": ["M4"], "scannedRegions": ["位置与排序筛选区"], "crossChecks": checks,
                     "crossCheckResults": [{"checkType": check, "status": "completed", "candidateCount": 0, "judgementCount": 0, "reason": "该交叉类型未发现额外候选。"} for check in checks]},
    "evidenceSource": "phase2_json_full_redundancy_scan", "rating": "优秀",
}]
red_issues = []
for card in cards:
    card_specs = specs.get(card["cardId"], [])
    ids = [element["id"] for element in text_elems(card)]
    pairs = [{"leftElementId": left, "rightElementId": right, "relation": "商家标题与图内或基础信息"} for left, right, _, _ in card_specs]
    duplicates = [{
        "leftElementId": left, "rightElementId": right, "lexicalCue": cue, "normalizedFact": fact,
        "noLossReason": "两处表达同一商家品牌或品类事实，删除任一处不损失独立决策信息。",
        "verdict": "duplicate",
    } for left, right, cue, fact in card_specs]
    cross_results = []
    for check in checks:
        count = len(pairs) if check == checks[0] else 0
        cross_results.append({"checkType": check, "status": "completed", "candidateCount": count, "judgementCount": count,
                              "reason": "已逐对核对商家标题、头图文字、基础信息、促销与商品价格。" if check == checks[0] else "该交叉类型未发现额外候选。"})
    rating = "不达标" if duplicates else "优秀"
    red_rows.append({
        "componentId": card["cardId"], "scannedRegions": regions(card), "examinedElements": ids,
        "candidatePairs": pairs, "pairJudgements": ["duplicate"] * len(pairs), "selfRepeatCandidates": [], "selfRepeatJudgements": [],
        "duplicates": duplicates, "duplicateCount": len(duplicates),
        "scanCoverage": {"status": "completed", "textAtomCount": len(ids), "scannedElementIds": ids, "scannedRegions": regions(card), "crossChecks": checks, "crossCheckResults": cross_results},
        "evidenceSource": "phase2_json_full_redundancy_scan", "rating": rating,
    })
    if duplicates:
        index = card["structure"]["listPosition"]
        if card["cardId"] == "C1":
            description = "商卡1标题中的“崔有福”与商家头图文字重复同一品牌事实，删除其中一处不损失独立决策信息。"
        elif card["cardId"] == "C2":
            description = "商卡2的标题、副标题与商家头图重复“豫福源”品牌和“家常菜·羊肉烩面”品类信息，共3项无新增决策价值。"
        else:
            description = "商卡3的标题与商家头图重复“羊福记”品牌，标题又与品类字段重复“羊肉汤”，共2项无新增决策价值。"
        red_issues.append(issue(
            duplicates[0]["rightElementId"], card["cardId"], description,
            f"删除或改写商卡{index}标题、副标题、品类与头图中无新增价值的重复品牌或品类文字，只保留一处完整表达；验收时确认整卡语义重复数为0。",
        ))

u = unit("eval-8-info-redundancy")
u["rating"] = "不达标"
u["reason"] = "已扫描筛选区和4张可见商家卡；崔有福、豫福源与羊福记三张卡均存在商家标题、头图或品类字段重复，确认3张问题卡。"
u["details"]["overview"] = {"total": 5, "excellent": 2, "pass": 0, "fail": 3, "failRate": "60.0%"}
u["details"]["evidence"] = {"sourceManifestTotal": audit["total"], "evaluatedUnitCount": 5, "evaluatedUnitIds": ["M4", "C1", "C2", "C3", "C4"], "assessmentRows": red_rows}
u["details"]["issues"] = red_issues

# Page flow includes the naturally cropped fourth merchant card.
u = page_unit("eval-5-browsing-flow-smoothness")
row = u["details"]["evidence"]["assessmentRows"][0]
row["listPositions"] = [{"position": card["structure"]["listPosition"], "componentId": card["cardId"], "cardType": card["cardTypeName"], "isHeterogeneous": False, "visibleStatus": card["structure"]["visibleStatus"]} for card in cards]
row["visibleListPositionCount"] = 4
u["reason"] = "排序筛选下方4个可见列表位均为同型商家卡；中部提示仅承担结果语义衔接，不构成独占异构列表位。"

# Page color union is five families and remains excellent.
u = page_unit("eval-3-page-color-logic")
u["reason"] = "4张可见商家卡的有效界面色系并集为红、橙、黄、绿、青共5种，未超过优秀档上限。"

OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(OUT)
