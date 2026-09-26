#!/usr/bin/env python3
"""Generate the manually adjudicated Phase3 result for final30 q8."""

import json
from itertools import combinations
from pathlib import Path

ROOT = Path("/Users/qianjing/Documents/ChatGPT/search-eval-project-v2")
RUN = "batch-20260920-09-2-final30-r1-q8"
BATCH = "batch-20260920-09-2-final30-r1"
QUERY = "自体脂肪隆鼻"
STEM = "自体脂肪隆鼻_全部_1"
SHOT = str(ROOT / f"screenshots/{STEM}.png")
MANIFEST = ROOT / f"screenshots-out/elements_{STEM}_{RUN}.json"
AUDIT = ROOT / f"screenshots-out/elements_{STEM}_{RUN}.audit.json"
BASE = ROOT / f".artifacts/过程文件-评测结果与审计/{BATCH}/{RUN}"
MEASURE = BASE / f"phase3/measurements/elements_{STEM}_{RUN}.component-color-families.json"
OUT = BASE / f"results/评测原始结果_{RUN}.json"

# Use the graph-complete generator only as a schema shell and repair its old
# duplicated declaration in memory. All page-specific judgements are replaced.
scaffold = ROOT / "scripts/generate_q8_next35_phase3_results.py"
source = scaffold.read_text(encoding="utf-8")
source = source.replace("duplicate_specs = {\nduplicate_specs = {", "duplicate_specs = {")
source = source.replace('RUN = "batch-20260920-09-2-next35-r1-q8"', f'RUN = "{RUN}"')
source = source.replace('BATCH = "batch-20260920-09-2-next35-r1"', f'BATCH = "{BATCH}"')
source = source.replace('QUERY = "新食味隆江猪脚饭"', f'QUERY = "{QUERY}"')
source = source.replace('STEM = "新食味隆江猪脚饭_全部_1"', f'STEM = "{STEM}"')
exec(compile(source, str(scaffold), "exec"), {"__name__": "__main__", "__file__": str(scaffold)})

manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
audit = json.loads(AUDIT.read_text(encoding="utf-8"))
colors = json.loads(MEASURE.read_text(encoding="utf-8"))["components"]
results = json.loads(OUT.read_text(encoding="utf-8"))
all_cards = manifest["cards"]
cards = [card for card in all_cards if card["structure"]["visibleStatus"] == "complete"]
card_ids = [card["cardId"] for card in cards]
source_total = audit["total"]


def component_unit(skill):
    return next(item["units"][0] for item in results if item["dimension"] == "phase3-card_or_component-eval" and item["skill"] == skill)


def page_unit(skill):
    return next(item["units"][0] for item in results if item["dimension"] == "phase3-page_framework-eval" and item["skill"] == skill)


def elements(card):
    return [element for region in card["regions"] for element in region["elements"]]


def text_elements(card):
    return [element for element in elements(card) if not element.get("render", {}).get("isPhoto")]


def region_names(card):
    return [region["name"] for region in card["regions"]]


def set_overview(unit, total, excellent, passed=0, failed=0):
    unit["details"]["overview"] = {
        "total": total,
        "excellent": excellent,
        "pass": passed,
        "fail": failed,
        "failRate": f"{(failed / total * 100):.1f}%" if total else "0.0%",
    }


cropped = [{"componentId": "C5", "reason": "底部自然裁切，仅保留当前可见事实，不用于完整商卡结论。"}]
for skill in (
    "eval-1-supply-completeness", "eval-2-visual-order-alignment",
    "eval-4-element-complexity", "eval-5-info-hierarchy",
    "eval-6-info-partitioning", "eval-7-info-authenticity",
    "eval-8-info-redundancy",
):
    component_unit(skill)["details"]["evidence"]["excludedUnits"] = cropped

# Supply completeness.
u = component_unit("eval-1-supply-completeness")
u["rating"] = "优秀"
u["reason"] = "5张完整医美商家卡均呈现商家标题、评分、位置、资质权益及可读文字下挂；第6张为底部自然裁切，不作为缺失样本。"
u["details"]["evidence"] = {"sourceManifestTotal": source_total, "evaluatedUnitCount": 5, "assessmentRows": [], "excludedUnits": cropped}
u["details"]["issues"] = []
set_overview(u, 5, 5)

# Visual order.
layout_signatures = []
order_checks = []
for card in cards:
    layout_signatures.append({
        "componentId": card["cardId"],
        "layoutMode": card["structure"]["layoutMode"],
        "layoutSignature": "merchant_info_then_text_attachment",
        "regions": [{"region": region["name"], "elementIds": [element["id"] for element in region["elements"]], "contentBounds": region["coord"]} for region in card["regions"]],
        "relations": ["头图左置、商家信息右置", "文字项目位于商家主体下方"],
    })
    order_checks.append({
        "componentId": card["cardId"],
        "expectedOrder": ["商家标题与头图", "评分、品类、位置与距离", "资质权益", "项目与价格"],
        "observedOrder": ["商家标题与头图", "评分、品类、位置与距离", "资质权益", "项目与价格"],
        "attentionSignals": ["粗体标题与左侧头图先建立主体", "红色价格与项目保持次级"],
        "dominantRegion": "基础信息区",
        "auxiliaryDominance": False,
        "competingFoci": False,
        "ownershipAmbiguity": False,
        "pathInversion": False,
        "localDetour": False,
        "reason": "商家主体先于资质权益和项目价格进入注意力路径，信息归属清楚。",
        "status": "consistent",
    })
u = component_unit("eval-2-visual-order-alignment")
u["rating"] = "优秀"
u["reason"] = "5张完整同型商家卡均保持商家主体在上、资质权益居中、项目与价格在下的稳定扫读顺序。"
u["details"]["evidence"] = {
    "sourceManifestTotal": source_total,
    "evaluatedUnitCount": 1,
    "assessmentRows": [{
        "comparisonGroupKey": cards[0]["structure"]["comparisonGroupKey"],
        "members": card_ids,
        "layoutSignatures": layout_signatures,
        "readingOrderChecks": order_checks,
        "evidenceSource": "original_screenshot_visual_review",
        "rating": "优秀",
    }],
    "excludedUnits": cropped,
}
u["details"]["issues"] = []
set_overview(u, 1, 1)

# Component color.
u = component_unit("eval-3-color-logic")
u["rating"] = "优秀"
u["reason"] = "6张可见商家卡的有效界面色系均为红、橙2种，全部不超过4种的优秀档上限。"
u["details"]["evidence"] = {"sourceManifestTotal": source_total, "evaluatedUnitCount": len(colors), "assessmentRows": colors}
u["details"]["issues"] = []
set_overview(u, len(colors), len(colors))

# Element complexity.
complexity_rows = []
for card in cards:
    included, excluded, ledger = [], [], []
    for element in elements(card):
        role = element.get("textFacts", {}).get("semanticRole", "")
        color = element.get("visual", {}).get("colorRole", "unknown")
        text = element.get("textFacts", {}).get("rawText", "")
        include = color not in {"neutral", "unknown", ""} and (role in {"tag", "recommendation", "promotion"})
        if include:
            style_key = element.get("visual", {}).get("styleKey", f"标签|{color}|{role}|无容器|无")
            ledger.append({"elementId": element["id"], "decision": "included_tag", "reason": "独立彩色资质、榜单或促销标签逐实例纳入", "styleKey": style_key})
            included.append({
                "content": text,
                "styleKey": style_key,
                "elementIds": [element["id"]],
                "countDecision": "独立可理解的异色标签计1个",
                "dedupDecision": "不同权益或项目位的独立实例不去重",
            })
        else:
            if element.get("render", {}).get("isPhoto"):
                reason = "商家广告主图素材不计入界面附加样式"
            elif role in {"title", "price", "rating"}:
                reason = "标题、价格或评分属于核心字段"
            elif role in {"attachment", "other", "review_count", "category", "location", "distance"}:
                reason = "项目标题、消费数或普通基础信息不构成独立附加标签"
            elif color in {"neutral", "unknown", ""}:
                reason = "中性普通信息或中性标签排除"
            else:
                reason = "普通辅助信息不构成独立附加功能标签"
            ledger.append({"elementId": element["id"], "decision": "excluded", "reason": reason})
            excluded.append({"elementId": element["id"], "reason": reason})
    complexity_rows.append({
        "componentId": card["cardId"],
        "expectedRegions": region_names(card),
        "scannedRegions": region_names(card),
        "unscannedRegions": [],
        "scannedElementIds": [element["id"] for element in elements(card)],
        "candidateLedger": ledger,
        "phase2ReviewCandidates": [],
        "coverageStatus": "completed",
        "includedTagStyles": included,
        "includedIconStyles": [],
        "excludedEntities": excluded,
        "tagStyleCount": len(included),
        "iconStyleCount": 0,
        "evidenceSource": "phase2_json_visual_inventory",
        "rating": "优秀",
    })
u = component_unit("eval-4-element-complexity")
u["rating"] = "优秀"
u["reason"] = "5张完整商家卡的独立彩色标签实例数分别为3、2、4、4、3，附加图标均为0种，全部命中优秀档。"
u["details"]["evidence"] = {"sourceManifestTotal": source_total, "evaluatedUnitCount": 5, "assessmentRows": complexity_rows, "excludedUnits": cropped}
u["details"]["issues"] = []
set_overview(u, 5, 5)

# Hierarchy.
hierarchy_rows = []
for card in cards:
    texts = text_elements(card)
    title = next(element for element in texts if element.get("textFacts", {}).get("semanticRole") == "title")
    basic = [element for element in texts if element.get("textFacts", {}).get("semanticRole") in {"rating", "review_count", "category", "location", "distance"}][:4]
    lower = [element for element in texts if element.get("textFacts", {}).get("semanticRole") in {"tag", "recommendation", "promotion", "attachment", "price"}][-4:]
    selected = [title] + basic + lower
    hierarchy_rows.append({
        "componentId": card["cardId"],
        "sourceElements": [{
            "elementId": element["id"],
            "content": element.get("textFacts", {}).get("rawText", ""),
            "visualSignal": "粗体商家标题" if element["id"] == title["id"] else ("基础决策字段" if element in basic else "次级权益或项目字段"),
        } for element in selected],
        "weightSequence": ["商家标题与头图", "评分与位置", "资质权益", "项目与价格"],
        "tierTrace": [
            {"tier": 1, "elements": [title["id"]], "basis": "大号粗体标题先建立商家主体"},
            {"tier": 2, "elements": [element["id"] for element in basic], "basis": "评分、品类与位置形成连续基础信息层"},
            {"tier": 3, "elements": [element["id"] for element in lower], "basis": "资质权益和项目价格位于次级区域"},
        ],
        "levelCount": 3,
        "rating": "优秀",
    })
u = component_unit("eval-5-info-hierarchy")
u["rating"] = "优秀"
u["reason"] = "5张完整商家卡均以标题和头图建立主体，评分位置承接，资质权益与项目价格保持次级，未形成竞争主焦点。"
u["details"]["evidence"] = {"sourceManifestTotal": source_total, "evaluatedUnitCount": 5, "assessmentRows": hierarchy_rows, "excludedUnits": cropped}
u["details"]["issues"] = []
set_overview(u, 5, 5)

# Partitioning.
u = component_unit("eval-6-info-partitioning")
u["rating"] = "优秀"
u["reason"] = "5张完整商家卡的基础信息、资质权益和文字项目通过稳定对齐、留白与卡间分隔清楚区分，未发现粘连或错归属。"
u["details"]["evidence"] = {"sourceManifestTotal": source_total, "evaluatedUnitCount": 5, "assessmentRows": [], "excludedUnits": cropped}
u["details"]["issues"] = []
set_overview(u, 5, 5)

# Authenticity.
auth_rows = []
for card in cards:
    ids = [element["id"] for element in elements(card)]
    auth_rows.append({
        "componentId": card["cardId"],
        "candidatePairs": [],
        "pairJudgements": [],
        "inapplicableChecks": ["不使用外部医疗机构资质、实时消费或线下项目事实校验"],
        "scanCoverage": {
            "status": "completed",
            "scannedElementIds": ids,
            "scannedRegions": region_names(card),
            "crossChecks": ["商家标题与头图主体", "评分位置与商家主体", "资质权益与当前商家归属", "项目标题与同行价格消费数归属"],
        },
        "conflicts": [],
        "conflictCount": 0,
        "evidenceSource": "phase2_json_and_original_screenshot",
        "rating": "优秀",
    })
u = component_unit("eval-7-info-authenticity")
u["rating"] = "优秀"
u["reason"] = "逐卡核对标题、头图、评分位置、资质权益、项目价格与消费数的语义及视觉归属，未发现不能同时成立或错归主体的关系。"
u["details"]["evidence"] = {"sourceManifestTotal": source_total, "evaluatedUnitCount": 5, "evaluatedUnitIds": card_ids, "assessmentRows": auth_rows, "excludedUnits": cropped}
u["details"]["issues"] = []
set_overview(u, 5, 5)

# Redundancy: two merchant advertising images repeat the brand already stated
# in the adjacent merchant title. The fifth complete card and other images use
# different project-oriented copy.
duplicate_specs = {
    "C0": ("荔颜荔禾医美门诊部 LYCHEE MEDICAL", "LYCHEE MEDICAL", "商家标题与头图内英文品牌名重复"),
    "C3": ("北京联合丽格医疗美容", "联合丽格", "商家标题与头图内联合丽格品牌名重复"),
}
red_rows = []
red_issues = []
for card in cards:
    ids = [element["id"] for element in elements(card)]
    spec = duplicate_specs.get(card["cardId"])
    pairs = [{"leftElementId": f"{card['cardId']}-T1", "rightElementId": f"{card['cardId']}-P1", "relation": spec[2]}] if spec else []
    duplicates = [{
        "leftElementId": f"{card['cardId']}-T1",
        "rightElementId": f"{card['cardId']}-P1",
        "lexicalCue": f"{spec[0]} ↔ 图内{spec[1]}",
        "normalizedFact": spec[1],
        "noLossReason": "标题与头图内品牌字表达同一商家身份，删除图内重复品牌字或标题重复片段不损失独立决策信息。",
        "verdict": "duplicate",
    }] if spec else []
    red_rows.append({
        "componentId": card["cardId"],
        "scannedRegions": region_names(card),
        "examinedElements": ids,
        "candidatePairs": pairs,
        "pairJudgements": ["duplicate"] if spec else [],
        "selfRepeatCandidates": [],
        "selfRepeatJudgements": [],
        "duplicates": duplicates,
        "duplicateCount": len(duplicates),
        "scanCoverage": {
            "status": "completed",
            "textAtomCount": len(ids),
            "scannedElementIds": ids,
            "scannedRegions": region_names(card),
            "crossChecks": [
                "title/subtitle ↔ basic information",
                "title/subtitle ↔ tags/price/promotion",
                "tag ↔ price/promotion",
                "title internal repeated quantified fragments",
            ],
            "crossCheckResults": [{
                "checkType": check,
                "status": "completed",
                "candidateCount": 1 if spec and check == "title/subtitle ↔ basic information" else 0,
                "judgementCount": 1 if spec and check == "title/subtitle ↔ basic information" else 0,
                "reason": "已终判标题与头图品牌字候选。" if spec and check == "title/subtitle ↔ basic information" else "该交叉类型未发现额外可无损删除候选。",
            } for check in [
                "title/subtitle ↔ basic information",
                "title/subtitle ↔ tags/price/promotion",
                "tag ↔ price/promotion",
                "title internal repeated quantified fragments",
            ]],
        },
        "evidenceSource": "phase2_json_full_redundancy_scan",
        "rating": "不达标" if spec else "优秀",
    })
    if spec:
        visible_index = card["structure"]["listPosition"] + 1
        red_issues.append({
            "elementId": f"{card['cardId']}-P1",
            "coord": next(element["坐标"] for element in elements(card) if element["id"] == f"{card['cardId']}-P1"),
            "component": card["cardId"],
            "description": f"商卡{visible_index}的标题“{spec[0]}”与左侧头图内“{spec[1]}”重复同一商家品牌，删除其中一处不损失独立决策信息。",
            "rating": "不达标",
            "recommendation": f"删除或弱化商卡{visible_index}头图内与标题重复的品牌文字，仅保留项目宣传信息；验收时确认整卡语义重复数为0。",
            "evidenceImage": SHOT,
        })
u = component_unit("eval-8-info-redundancy")
u["rating"] = "不达标"
u["reason"] = "已完整扫描5张商家卡的标题、头图、基础信息、资质权益和项目；商卡1与商卡4均存在标题与头图品牌字重复，共确认2张问题卡。"
u["details"]["evidence"] = {"sourceManifestTotal": source_total, "evaluatedUnitCount": 5, "evaluatedUnitIds": card_ids, "assessmentRows": red_rows, "excludedUnits": cropped}
u["details"]["issues"] = red_issues
set_overview(u, 5, 3, failed=2)

# Page supply.
u = page_unit("eval-1-supply-module-completeness")
u["rating"] = "优秀"
u["reason"] = "搜索与业务Tab、位置排序筛选及医美商家结果列表均完整加载，未见适用核心或辅助模块缺失。"
u["details"]["evidence"] = {"assessmentRows": []}
u["details"]["issues"] = []
set_overview(u, 1, 1)

# Page visual order.
u = page_unit("eval-2-visual-order-alignment")
page_alignment = {
    "pageRegions": [
        {"region": "搜索与业务Tab", "observedRole": "建立查询和结果范围", "visualSignals": ["顶部稳定入口", "选中Tab使用黄色下划线"]},
        {"region": "位置与排序筛选", "observedRole": "调整地域、排序与筛选条件", "visualSignals": ["单行浅色控件", "与列表留白分隔"]},
        {"region": "医美商家结果列表", "observedRole": "连续呈现机构、资质与项目", "visualSignals": ["同型商家卡纵向排列", "稳定卡间节奏"]},
    ],
    "sameTypeComparisons": [{"members": ["商卡1", "商卡2", "商卡3", "商卡4", "商卡5"], "result": "标题、基础信息、资质权益和文字项目主锚点一致"}],
    "primaryFocus": "医美商家结果列表",
    "flowChecks": [{
        "expectedOrder": ["搜索与Tab", "位置与排序筛选", "医美商家结果列表"],
        "observedOrder": ["搜索与Tab", "位置与排序筛选", "医美商家结果列表"],
        "visualSignals": ["自上而下单列推进", "筛选区与结果区边界清楚"],
        "reason": "页面按查询、筛选、浏览结果的顺序推进，未出现辅助模块抢占主焦点。",
        "status": "consistent",
    }],
    "evidenceSource": "original_screenshot_visual_review",
    "rating": "优秀",
}
u["rating"] = "优秀"
u["reason"] = "页面由搜索与业务Tab进入位置排序筛选，再进入连续医美商家结果列表，主焦点与浏览顺序稳定。"
u["details"]["evidence"] = {"assessmentRows": [page_alignment]}
u["details"]["issues"] = []
set_overview(u, 1, 1)

# Page color.
u = page_unit("eval-3-page-color-logic")
summaries = [{"componentId": item["componentId"], "colorFamilies": item["colorFamilies"], "colorFamilyCount": item["colorFamilyCount"]} for item in colors]
families = sorted({family for item in summaries for family in item["colorFamilies"]})
u["rating"] = "优秀"
u["reason"] = "全页可见商家组件的有效界面色系并集为红、橙共2种，未超过5种的页面优秀档上限。"
u["details"]["evidence"] = {"assessmentRows": [{
    "colorLogicContractVersion": "4.0",
    "componentColorArtifact": str(MEASURE),
    "componentColorSummaries": summaries,
    "colorFamilies": families,
    "colorFamilyCount": len(families),
    "evidenceSource": "component_pixel_color_aggregation",
    "rating": "优秀",
}]}
u["details"]["issues"] = []
set_overview(u, 1, 1)

# Page static component complexity.
u = page_unit("eval-4-static-component-complexity")
u["rating"] = "优秀"
u["reason"] = "排除顶部搜索框并合并重复识别的结果列表后，首屏有业务Tab、位置与排序筛选、医美商家结果列表共3个独立功能区。"
u["details"]["evidence"] = {"assessmentRows": [{
    "firstScreenBounds": [0, 0, manifest["pageFacts"]["viewport"]["width"], manifest["pageFacts"]["viewport"]["height"]],
    "functionalModules": [
        {"name": "业务Tab栏", "sourceModuleIds": ["M1", "M2"]},
        {"name": "位置与排序筛选", "sourceModuleIds": ["M3"]},
        {"name": "医美商家结果列表", "sourceModuleIds": ["M4", "M5"]},
    ],
    "moduleCount": 3,
    "observableFact": "排除顶部搜索框并将重复识别的列表区域合并后，共3个独立功能区。",
    "rating": "优秀",
}]}
u["details"]["issues"] = []
set_overview(u, 1, 1)

# Browsing flow.
u = page_unit("eval-5-browsing-flow-smoothness")
u["rating"] = "优秀"
u["reason"] = "排序筛选下方6个可见列表位均为同型标准医美商家卡，前10位当前可见范围内异构数为0。"
u["details"]["evidence"] = {"assessmentRows": [{
    "listPositions": [{
        "position": card["structure"]["listPosition"],
        "componentId": card["cardId"],
        "cardType": card["cardTypeName"],
        "isHeterogeneous": False,
        "visibleStatus": card["structure"]["visibleStatus"],
    } for card in all_cards],
    "visibleListPositionCount": len(all_cards),
    "coverageStatus": "partial",
    "heterogeneousCount": 0,
    "frontTenHeterogeneousCount": 0,
    "allHeterogeneousItems": [],
    "heterogeneousItems": [],
    "rating": "优秀",
}]}
u["details"]["issues"] = []
set_overview(u, 1, 1)

# Comparability.
u = page_unit("eval-6-info-comparability")
u["rating"] = "优秀"
u["reason"] = "5张完整同型医美商家卡均在固定基础信息区呈现评分、评论数、品类、位置和距离，字段口径与锚点一致，可直接横向比较。"
u["details"]["evidence"] = {"assessmentRows": [{
    "cardGroups": [{"comparisonGroupKey": cards[0]["structure"]["comparisonGroupKey"], "members": card_ids}],
    "comparableFields": ["评分", "评论数", "医学美容品类", "位置", "距离"],
    "comparisons": [{
        "comparisonGroupKey": cards[0]["structure"]["comparisonGroupKey"],
        "semanticRole": "rating_review_category_location_distance",
        "fieldMatchKey": "同一主商家层的评分、评论、品类、位置与距离槽位",
        "observations": [{"componentId": card["cardId"], "present": True, "anchor": "基础信息区固定行与右侧距离位"} for card in cards],
        "detectedDifferences": {"missing": [], "formatMismatch": False, "anchorMismatch": False, "styleSemanticMismatch": False},
        "materialImpact": False,
        "phase3Judgement": "consistent",
    }],
    "inconsistencyCount": 0,
    "evidenceSource": "phase2_json_cross_card_comparison",
    "rating": "优秀",
}]}
u["details"]["issues"] = []
set_overview(u, 1, 1)

# Page redundancy.
u = page_unit("eval-7-info-redundancy")
page_regions = ["搜索与业务Tab", "位置与排序筛选", "医美商家结果列表"]
page_pairs = list(combinations(page_regions, 2))
u["rating"] = "优秀"
u["reason"] = "已覆盖搜索与Tab、位置排序筛选和医美商家结果列表并完成3组两两检查；各区域职责不同，跨区域冗余数为0。"
u["details"]["evidence"] = {"assessmentRows": [{
    "pageRegions": page_regions,
    "candidatePairs": [],
    "scanCoverage": {
        "status": "completed",
        "scannedRegionIds": page_regions,
        "crossChecks": [f"{left} ↔ {right}" for left, right in page_pairs],
    },
    "crossChecks": [{"regions": [left, right], "judgement": "distinct", "reason": "两区域承担不同页面任务或提供不同决策信息。"} for left, right in page_pairs],
    "redundancyItems": [],
    "redundancyCount": 0,
    "rating": "优秀",
}]}
u["details"]["issues"] = []
set_overview(u, 1, 1)

OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(OUT)
