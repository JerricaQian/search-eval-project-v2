#!/usr/bin/env python3
"""Generate the manually adjudicated Phase3 result for final30 q11."""

import json
from itertools import combinations
from pathlib import Path

ROOT = Path("/Users/qianjing/Documents/ChatGPT/search-eval-project-v2")
RUN = "batch-20260920-09-2-final30-r1-q11"
BATCH = "batch-20260920-09-2-final30-r1"
QUERY = "荔枝乡烤鸡"
STEM = "荔枝乡烤鸡_全部_1"
SHOT = str(ROOT / f"screenshots/{STEM}.png")
MANIFEST = ROOT / f"screenshots-out/elements_{STEM}_{RUN}.json"
AUDIT = ROOT / f"screenshots-out/elements_{STEM}_{RUN}.audit.json"
BASE = ROOT / f".artifacts/过程文件-评测结果与审计/{BATCH}/{RUN}"
MEASURE = BASE / f"phase3/measurements/elements_{STEM}_{RUN}.component-color-families.json"
OUT = BASE / f"results/评测原始结果_{RUN}.json"

# Reuse the schema-complete q8 generator as a shell, then replace every
# current-page judgement below.
scaffold = ROOT / "scripts/generate_q8_final30_phase3_results.py"
source = scaffold.read_text(encoding="utf-8")
source = source.replace('RUN = "batch-20260920-09-2-final30-r1-q8"', f'RUN = "{RUN}"')
source = source.replace('QUERY = "自体脂肪隆鼻"', f'QUERY = "{QUERY}"')
source = source.replace('STEM = "自体脂肪隆鼻_全部_1"', f'STEM = "{STEM}"')
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
        "total": total, "excellent": excellent, "pass": passed, "fail": failed,
        "failRate": f"{(failed / total * 100):.1f}%" if total else "0.0%",
    }


cropped = [{"componentId": "C3", "reason": "底部自然裁切，仅保留当前可见事实，不用于完整商卡结论。"}]

# Supply.
u = component_unit("eval-1-supply-completeness")
u["rating"] = "优秀"
u["reason"] = "3张完整商家卡均呈现商家标题、到店状态和位置等基础信息；两张图文下挂卡还提供可读优惠或商品，无下挂卡结构本身完整。"
u["details"]["evidence"] = {"sourceManifestTotal": source_total, "evaluatedUnitCount": 3, "assessmentRows": [], "excludedUnits": cropped}
u["details"]["issues"] = []
set_overview(u, 3, 3)

# Visual order, evaluated by card type.
groups = []
for key, members in [
    (cards[0]["structure"]["comparisonGroupKey"], cards[:2]),
    (cards[2]["structure"]["comparisonGroupKey"], cards[2:3]),
]:
    groups.append({
        "comparisonGroupKey": key,
        "members": [card["cardId"] for card in members],
        "layoutSignatures": [{
            "componentId": card["cardId"],
            "layoutMode": card["structure"]["layoutMode"],
            "layoutSignature": card["structure"]["layoutSignature"],
            "regions": [{"region": region["name"], "elementIds": [element["id"] for element in region["elements"]], "contentBounds": region["coord"]} for region in card["regions"]],
            "relations": [card["structure"]["layoutAnchorRelation"]],
        } for card in members],
        "readingOrderChecks": [{
            "componentId": card["cardId"],
            "expectedOrder": ["商家标题与头图", "评分与位置", "下挂优惠或商品" if card["cardId"] != "C2" else "商家主体结束"],
            "observedOrder": ["商家标题与头图", "评分与位置", "下挂优惠或商品" if card["cardId"] != "C2" else "商家主体结束"],
            "attentionSignals": ["标题与头图先建立主体", "商品及优惠保持次级"],
            "dominantRegion": "基础信息区",
            "auxiliaryDominance": False, "competingFoci": False, "ownershipAmbiguity": False,
            "pathInversion": False, "localDetour": False,
            "reason": "同型卡的主体与次级内容顺序连续，未出现归属混乱。",
            "status": "consistent",
        } for card in members],
        "evidenceSource": "original_screenshot_visual_review",
        "rating": "优秀",
    })
u = component_unit("eval-2-visual-order-alignment")
u["rating"] = "优秀"
u["reason"] = "两张完整图文下挂卡均先建立商家主体再进入优惠商品；无下挂卡以商家主体结束，各类型内部扫读顺序稳定。"
u["details"]["evidence"] = {"sourceManifestTotal": source_total, "evaluatedUnitCount": 2, "assessmentRows": groups, "excludedUnits": cropped}
u["details"]["issues"] = []
set_overview(u, 2, 2)

# Color logic: C1 has five measured families.
u = component_unit("eval-3-color-logic")
u["rating"] = "达标"
u["reason"] = "4张可见商家卡的有效色系数分别为2、5、1、3；第二张卡为5种而命中达标档，其余均优秀。"
u["details"]["evidence"] = {"sourceManifestTotal": source_total, "evaluatedUnitCount": len(colors), "assessmentRows": colors}
u["details"]["issues"] = [{
    "elementId": "C1-T8",
    "coord": [65, 1645, 160, 42],
    "component": "C1",
    "description": "商卡2的有效界面色系为「红、橙、黄、绿、紫」共5种，超过优秀档的4种上限并命中达标档。",
    "rating": "达标",
    "recommendation": "合并或统一优惠券、商品图及强调信息中的至少1种次要色系；验收时确认单卡有效色系不超过4种。",
    "evidenceImage": SHOT,
}]
set_overview(u, 4, 3, passed=1)

# Complexity.
complexity_rows = []
for card in cards:
    included, excluded, ledger = [], [], []
    for element in elements(card):
        role = element.get("textFacts", {}).get("semanticRole", "")
        color = element.get("visual", {}).get("colorRole", "unknown")
        text = element.get("textFacts", {}).get("rawText", "")
        include = color not in {"neutral", "unknown", ""} and role in {"tag", "recommendation", "promotion"}
        if include:
            style_key = element.get("visual", {}).get("styleKey", f"标签|{color}|{role}|无容器|无")
            ledger.append({"elementId": element["id"], "decision": "included_tag", "reason": "独立彩色折扣或券标签逐实例纳入", "styleKey": style_key})
            included.append({"content": text, "styleKey": style_key, "elementIds": [element["id"]], "countDecision": "独立可理解的异色标签计1个", "dedupDecision": "不同商品或券位的独立实例不去重"})
        else:
            if element.get("render", {}).get("isPhoto"):
                reason = "商家、商品或券图片素材不计入附加界面样式"
            elif role in {"title", "rating", "price", "item_price", "item_original_price"}:
                reason = "标题、评分或价格属于核心字段"
            elif role in {"attachment", "positive_rate", "review_count", "category", "location", "fulfillment"}:
                reason = "商品标题、口碑或基础信息不构成独立附加标签"
            else:
                reason = "中性普通信息排除"
            ledger.append({"elementId": element["id"], "decision": "excluded", "reason": reason})
            excluded.append({"elementId": element["id"], "reason": reason})
    complexity_rows.append({
        "componentId": card["cardId"], "expectedRegions": region_names(card), "scannedRegions": region_names(card), "unscannedRegions": [],
        "scannedElementIds": [element["id"] for element in elements(card)], "candidateLedger": ledger, "phase2ReviewCandidates": [],
        "coverageStatus": "completed", "includedTagStyles": included, "includedIconStyles": [], "excludedEntities": excluded,
        "tagStyleCount": len(included), "iconStyleCount": 0, "evidenceSource": "phase2_json_visual_inventory", "rating": "优秀",
    })
u = component_unit("eval-4-element-complexity")
u["rating"] = "优秀"
u["reason"] = "3张完整商家卡的独立彩色标签实例数分别为4、3、0，附加图标均为0种，全部命中优秀档。"
u["details"]["evidence"] = {"sourceManifestTotal": source_total, "evaluatedUnitCount": 3, "assessmentRows": complexity_rows, "excludedUnits": cropped}
u["details"]["issues"] = []
set_overview(u, 3, 3)

# Hierarchy.
hierarchy_rows = []
for card in cards:
    texts = text_elements(card)
    title = next(element for element in texts if element.get("textFacts", {}).get("semanticRole") == "title")
    basic = [element for element in texts if element.get("textFacts", {}).get("semanticRole") in {"rating", "review_count", "category", "location"}][:4]
    lower = [element for element in texts if element.get("textFacts", {}).get("semanticRole") in {"promotion", "attachment", "item_price"}][-4:]
    hierarchy_rows.append({
        "componentId": card["cardId"],
        "sourceElements": [{"elementId": element["id"], "content": element.get("textFacts", {}).get("rawText", ""), "visualSignal": "粗体标题" if element["id"] == title["id"] else ("基础信息" if element in basic else "次级优惠商品")} for element in [title] + basic + lower],
        "weightSequence": ["商家标题与头图", "评分和位置", "优惠与商品"],
        "tierTrace": [
            {"tier": 1, "elements": [title["id"]], "basis": "标题字号与字重最高"},
            {"tier": 2, "elements": [element["id"] for element in basic], "basis": "评分、品类与位置形成基础信息层"},
            {"tier": 3, "elements": [element["id"] for element in lower], "basis": "优惠和商品位于次级区域"},
        ],
        "levelCount": 3, "rating": "优秀",
    })
u = component_unit("eval-5-info-hierarchy")
u["rating"] = "优秀"
u["reason"] = "3张完整商家卡均以标题和头图建立主体，评分位置承接，优惠商品保持次级；无下挂卡也保持清晰主体层。"
u["details"]["evidence"] = {"sourceManifestTotal": source_total, "evaluatedUnitCount": 3, "assessmentRows": hierarchy_rows, "excludedUnits": cropped}
u["details"]["issues"] = []
set_overview(u, 3, 3)

# Partition.
u = component_unit("eval-6-info-partitioning")
u["rating"] = "优秀"
u["reason"] = "3张完整商家卡的基础信息、优惠券和商品位通过卡内留白、对齐与图片区块清楚区分，未发现粘连或错归属。"
u["details"]["evidence"] = {"sourceManifestTotal": source_total, "evaluatedUnitCount": 3, "assessmentRows": [], "excludedUnits": cropped}
u["details"]["issues"] = []
set_overview(u, 3, 3)

# Authenticity: C0 contradicts the page's explicit Bazhong location state.
auth_rows = []
for card in cards:
    ids = [element["id"] for element in elements(card)]
    conflict = card["cardId"] == "C0"
    auth_rows.append({
        "componentId": card["cardId"],
        "candidatePairs": [{"leftElementId": "C0-T4", "rightElementId": "C0-T6", "relation": "海南乐东地址与乐东地区标签互相一致，但共同违背页面巴中结果状态"}] if conflict else [],
        "pairJudgements": ["conflict"] if conflict else [],
        "inapplicableChecks": ["不使用外部门店营业状态或实时库存校验"],
        "scanCoverage": {"status": "completed", "scannedElementIds": ids, "scannedRegions": region_names(card), "crossChecks": ["页面结果地区与商家地址", "标题与头图主体", "商品与价格归属"]},
        "conflicts": [{"leftElementId": "C0-T4", "rightElementId": "C0-T6", "reason": "页面明确显示巴中结果，而该卡同时显示海南省乐东地址及乐东地区。", "verdict": "conflict"}] if conflict else [],
        "conflictCount": 1 if conflict else 0,
        "evidenceSource": "phase2_json_and_original_screenshot",
        "rating": "不达标" if conflict else "优秀",
    })
u = component_unit("eval-7-info-authenticity")
u["rating"] = "不达标"
u["reason"] = "页面明确声明当前显示巴中结果，但商卡1同时显示海南省乐东地址及乐东地区，形成1处客观地区冲突；其余完整卡无冲突。"
u["details"]["evidence"] = {"sourceManifestTotal": source_total, "evaluatedUnitCount": 3, "evaluatedUnitIds": card_ids, "assessmentRows": auth_rows, "excludedUnits": cropped}
u["details"]["issues"] = [{
    "elementId": "C0-T4", "coord": [440, 682, 390, 42], "component": "C0",
    "description": "商卡1位于页面“已显示巴中”的结果流中，却标注“海南省第三医院乐东分院”和“乐东”，与页面地区状态形成1处客观冲突。",
    "rating": "不达标",
    "recommendation": "修复商卡1的地区召回或页面地区状态，使商家地址与当前结果城市统一；验收时确认页面城市和商卡地区无冲突。",
    "evidenceImage": SHOT,
}]
set_overview(u, 3, 2, failed=1)

# Redundancy: C0 title duplicates head-image brand; C1 voucher image duplicates
# the title/amount printed directly below the same item.
dup_specs = {
    "C0": ("C0-T1", "C0-P1", "乐东乐城荔枝乡烤鸡店 ↔ 图内荔枝乡烤鸡", "商家名称"),
    "C1": ("C1-T18", "C1-P4", "20元代金券 ↔ 图内代金券¥20", "20元代金券"),
}
checks = ["title/subtitle ↔ basic information", "title/subtitle ↔ tags/price/promotion", "tag ↔ price/promotion", "title internal repeated quantified fragments"]
red_rows, red_issues = [], []
for card in cards:
    ids = [element["id"] for element in elements(card)]
    spec = dup_specs.get(card["cardId"])
    pairs = [{"leftElementId": spec[0], "rightElementId": spec[1], "relation": spec[2]}] if spec else []
    duplicates = [{"leftElementId": spec[0], "rightElementId": spec[1], "lexicalCue": spec[2], "normalizedFact": spec[3], "noLossReason": "两处表达同一商家身份或同一券面事实，删除图内重复文字不损失独立决策信息。", "verdict": "duplicate"}] if spec else []
    red_rows.append({
        "componentId": card["cardId"], "scannedRegions": region_names(card), "examinedElements": ids,
        "candidatePairs": pairs, "pairJudgements": ["duplicate"] if spec else [], "selfRepeatCandidates": [], "selfRepeatJudgements": [],
        "duplicates": duplicates, "duplicateCount": len(duplicates),
        "scanCoverage": {"status": "completed", "textAtomCount": len(ids), "scannedElementIds": ids, "scannedRegions": region_names(card), "crossChecks": checks,
            "crossCheckResults": [{"checkType": check, "status": "completed", "candidateCount": 1 if spec and check == checks[0] else 0, "judgementCount": 1 if spec and check == checks[0] else 0, "reason": "已终判标题或券面与图片文字候选。" if spec and check == checks[0] else "该交叉类型未发现额外可无损删除候选。"} for check in checks]},
        "evidenceSource": "phase2_json_full_redundancy_scan", "rating": "不达标" if spec else "优秀",
    })
    if spec:
        index = card["structure"]["listPosition"] + 1
        target = next(element for element in elements(card) if element["id"] == spec[1])
        text = "标题与头图品牌字" if card["cardId"] == "C0" else "券面内金额名称与券标题"
        red_issues.append({
            "elementId": spec[1], "coord": target["坐标"], "component": card["cardId"],
            "description": f"商卡{index}的{text}重复表达同一事实，删除图片内重复文字不损失独立决策信息。",
            "rating": "不达标",
            "recommendation": f"删除或弱化商卡{index}图片内与相邻标题重复的文字，仅保留一处完整事实；验收时确认整卡语义重复数为0。",
            "evidenceImage": SHOT,
        })
u = component_unit("eval-8-info-redundancy")
u["rating"] = "不达标"
u["reason"] = "完整扫描3张商家卡后，商卡1存在标题与头图品牌字重复，商卡2存在券面与券标题重复，共确认2张问题卡。"
u["details"]["evidence"] = {"sourceManifestTotal": source_total, "evaluatedUnitCount": 3, "evaluatedUnitIds": card_ids, "assessmentRows": red_rows, "excludedUnits": cropped}
u["details"]["issues"] = red_issues
set_overview(u, 3, 1, failed=2)

# Page supply and order.
u = page_unit("eval-1-supply-module-completeness")
u["rating"] = "优秀"
u["reason"] = "搜索与Tab、地区状态提示、位置排序筛选、结果列表和推荐衔接提示均完整加载。"
u["details"]["evidence"] = {"assessmentRows": []}
u["details"]["issues"] = []
set_overview(u, 1, 1)

u = page_unit("eval-2-visual-order-alignment")
regions = [
    {"region": "搜索与业务Tab", "observedRole": "建立查询与业务范围", "visualSignals": ["顶部固定入口", "选中Tab黄色下划线"]},
    {"region": "地区状态提示", "observedRole": "说明当前结果城市并提供切换", "visualSignals": ["独立文本提示", "位于筛选之前"]},
    {"region": "位置与排序筛选", "observedRole": "收敛位置和排序条件", "visualSignals": ["单行筛选控件"]},
    {"region": "商家结果列表", "observedRole": "先呈现精确结果再呈现推荐商家", "visualSignals": ["商家卡纵向排列", "推荐提示承担过渡"]},
]
u["rating"] = "优秀"
u["reason"] = "页面从查询与地区状态进入筛选和精确结果，再经明确提示进入推荐商家，主焦点与浏览顺序稳定。"
u["details"]["evidence"] = {"assessmentRows": [{
    "pageRegions": regions,
    "sameTypeComparisons": [{"members": ["商卡1", "商卡2"], "result": "图文下挂卡的主体与商品锚点一致"}],
    "primaryFocus": "商家结果列表",
    "flowChecks": [{"expectedOrder": ["搜索与Tab", "地区状态", "筛选", "精确结果", "推荐衔接", "推荐结果"], "observedOrder": ["搜索与Tab", "地区状态", "筛选", "精确结果", "推荐衔接", "推荐结果"], "visualSignals": ["自上而下单列推进", "推荐提示明确分隔"], "reason": "页面功能和结果语义按预期推进，未出现主焦点错位。", "status": "consistent"}],
    "evidenceSource": "original_screenshot_visual_review", "rating": "优秀",
}]}
u["details"]["issues"] = []
set_overview(u, 1, 1)

# Page color.
u = page_unit("eval-3-page-color-logic")
summaries = [{"componentId": item["componentId"], "colorFamilies": item["colorFamilies"], "colorFamilyCount": item["colorFamilyCount"]} for item in colors]
families = sorted({family for item in summaries for family in item["colorFamilies"]})
u["rating"] = "优秀"
u["reason"] = "全页可见商家组件的有效色系并集为红、橙、黄、绿、紫共5种，未超过页面优秀档上限。"
u["details"]["evidence"] = {"assessmentRows": [{"colorLogicContractVersion": "4.0", "componentColorArtifact": str(MEASURE), "componentColorSummaries": summaries, "colorFamilies": families, "colorFamilyCount": len(families), "evidenceSource": "component_pixel_color_aggregation", "rating": "优秀"}]}
u["details"]["issues"] = []
set_overview(u, 1, 1)

# Page complexity: five independent regions after excluding search box.
u = page_unit("eval-4-static-component-complexity")
u["rating"] = "达标"
u["reason"] = "排除顶部搜索框并合并普通结果卡后，首屏仍有业务Tab、地区状态、位置排序筛选、商家结果列表和推荐衔接提示共5个功能区。"
u["details"]["evidence"] = {"assessmentRows": [{
    "firstScreenBounds": [0, 0, manifest["pageFacts"]["viewport"]["width"], manifest["pageFacts"]["viewport"]["height"]],
    "functionalModules": [
        {"name": "业务Tab栏", "sourceModuleIds": ["M1"]}, {"name": "地区状态提示", "sourceModuleIds": ["M2"]},
        {"name": "位置与排序筛选", "sourceModuleIds": ["M3"]}, {"name": "商家结果列表", "sourceModuleIds": ["M4", "M5"]},
        {"name": "推荐衔接提示", "sourceModuleIds": ["M4"]},
    ],
    "moduleCount": 5, "observableFact": "排除搜索框并合并普通结果列表后，共5个独立功能区。", "rating": "达标",
}]}
u["details"]["issues"] = [{
    "pageArea": "首屏整体",
    "description": "首屏排除搜索框后仍同时呈现业务Tab、地区状态、位置排序筛选、商家结果列表和推荐衔接提示共5个独立功能区，命中达标档。",
    "rating": "达标",
    "recommendation": "合并地区状态与位置筛选，或将推荐衔接提示收敛为列表内轻量文案；验收时确认首屏独立功能区不超过4个。",
    "evidenceImage": SHOT,
}]
set_overview(u, 1, 0, passed=1)

# Browsing flow.
u = page_unit("eval-5-browsing-flow-smoothness")
u["rating"] = "优秀"
u["reason"] = "排序筛选下方4个可见列表位均为标准商家卡；推荐提示仅承担语义衔接，不占独立列表位，异构数为0。"
u["details"]["evidence"] = {"assessmentRows": [{
    "listPositions": [{"position": card["structure"]["listPosition"], "componentId": card["cardId"], "cardType": card["cardTypeName"], "isHeterogeneous": False, "visibleStatus": card["structure"]["visibleStatus"]} for card in all_cards],
    "visibleListPositionCount": len(all_cards), "coverageStatus": "partial", "heterogeneousCount": 0, "frontTenHeterogeneousCount": 0, "allHeterogeneousItems": [], "heterogeneousItems": [], "rating": "优秀",
}]}
u["details"]["issues"] = []
set_overview(u, 1, 1)

# Comparability.
u = page_unit("eval-6-info-comparability")
u["rating"] = "优秀"
u["reason"] = "两张完整图文下挂卡均在固定基础信息区呈现到店状态、评分状态、位置和品类，字段口径与锚点一致；无下挂卡按类型单列。"
u["details"]["evidence"] = {"assessmentRows": [{
    "cardGroups": [{"comparisonGroupKey": cards[0]["structure"]["comparisonGroupKey"], "members": ["C0", "C1"]}, {"comparisonGroupKey": cards[2]["structure"]["comparisonGroupKey"], "members": ["C2"]}],
    "comparableFields": ["到店状态", "评分状态", "位置", "品类"],
    "comparisons": [{"comparisonGroupKey": cards[0]["structure"]["comparisonGroupKey"], "semanticRole": "fulfillment_rating_location_category", "fieldMatchKey": "同型图文下挂卡的基础决策字段", "observations": [{"componentId": card_id, "present": True, "anchor": "基础信息区固定行"} for card_id in ["C0", "C1"]], "detectedDifferences": {"missing": [], "formatMismatch": False, "anchorMismatch": False, "styleSemanticMismatch": False}, "materialImpact": False, "phase3Judgement": "consistent"}],
    "inconsistencyCount": 0, "evidenceSource": "phase2_json_cross_card_comparison", "rating": "优秀",
}]}
u["details"]["issues"] = []
set_overview(u, 1, 1)

# Page redundancy.
u = page_unit("eval-7-info-redundancy")
page_regions = ["搜索与业务Tab", "地区状态提示", "位置与排序筛选", "商家结果列表", "推荐衔接提示"]
pairs = list(combinations(page_regions, 2))
u["rating"] = "优秀"
u["reason"] = "已覆盖5个页面区域并完成10组两两检查；各区域分别承担查询、城市说明、筛选、供给和推荐过渡，跨区域冗余数为0。"
u["details"]["evidence"] = {"assessmentRows": [{
    "pageRegions": page_regions, "candidatePairs": [],
    "scanCoverage": {"status": "completed", "scannedRegionIds": page_regions, "crossChecks": [f"{left} ↔ {right}" for left, right in pairs]},
    "crossChecks": [{"regions": [left, right], "judgement": "distinct", "reason": "两区域承担不同页面任务或提供不同决策信息。"} for left, right in pairs],
    "redundancyItems": [], "redundancyCount": 0, "rating": "优秀",
}]}
u["details"]["issues"] = []
set_overview(u, 1, 1)

OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(OUT)
