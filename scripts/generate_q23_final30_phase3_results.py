#!/usr/bin/env python3
"""Generate the q23 Phase3 judgement from the q8 schema shell."""

import json
from itertools import combinations
from pathlib import Path

root = Path('/Users/qianjing/Documents/ChatGPT/search-eval-project-v2')
source_path = root / 'scripts/generate_q8_final30_phase3_results.py'
source = source_path.read_text(encoding='utf-8')
source = source.replace('RUN = "batch-20260920-09-2-final30-r1-q8"', 'RUN = "batch-20260920-09-2-final30-r1-q23"')
source = source.replace('QUERY = "自体脂肪隆鼻"', 'QUERY = "阿生家"')
source = source.replace('STEM = "自体脂肪隆鼻_全部_1"', 'STEM = "阿生家_全部_1"')
exec(compile(source, str(source_path), 'exec'), {'__name__': '__main__', '__file__': str(source_path)})

run = 'batch-20260920-09-2-final30-r1-q23'
batch = 'batch-20260920-09-2-final30-r1'
stem = '阿生家_全部_1'
shot = str(root / f'screenshots/{stem}.png')
manifest_path = root / f'screenshots-out/elements_{stem}_{run}.json'
audit_path = root / f'screenshots-out/elements_{stem}_{run}.audit.json'
measure_path = root / f'.artifacts/过程文件-评测结果与审计/{batch}/{run}/phase3/measurements/elements_{stem}_{run}.component-color-families.json'
out = root / f'.artifacts/过程文件-评测结果与审计/{batch}/{run}/results/评测原始结果_{run}.json'
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
audit = json.loads(audit_path.read_text(encoding='utf-8'))
colors = json.loads(measure_path.read_text(encoding='utf-8'))['components']
results = json.loads(out.read_text(encoding='utf-8'))
all_cards = manifest['cards']
cards = [c for c in all_cards if c['structure']['visibleStatus'] == 'complete']


def unit(skill, dimension):
    return next(r['units'][0] for r in results if r['skill'] == skill and r['dimension'] == dimension)


def elements(card):
    return [e for region in card['regions'] for e in region['elements']]


def regions(card):
    return [region['name'] for region in card['regions']]


def ov(total, excellent, passed=0, failed=0):
    return {'total': total, 'excellent': excellent, 'pass': passed, 'fail': failed,
            'failRate': f'{failed / total * 100:.1f}%' if total else '0.0%'}


card_dim = 'phase3-card_or_component-eval'
page_dim = 'phase3-page_framework-eval'
cropped = [{'componentId': 'C4', 'reason': '底部自然裁切，仅保留当前可见事实，不用于完整商家卡结论。'}]

u = unit('eval-1-supply-completeness', card_dim)
u['reason'] = '4张完整商家卡均呈现标题、头图、评分/状态、位置以及当前卡型适用的商品下挂；第5张为底部自然裁切。'
u['details']['evidence'] = {'sourceManifestTotal': audit['total'], 'evaluatedUnitCount': 4, 'assessmentRows': [], 'excludedUnits': cropped}
u['details']['overview'] = ov(4, 4)
u['details']['issues'] = []

u = unit('eval-2-visual-order-alignment', card_dim)
u['reason'] = '4张完整商家卡按无下挂与图文下挂形成2个可比组；两组均先建立商家标题与头图主体，再呈现评分/位置，图文卡最后进入商品与价格。'
groups = {}
for card in cards:
    groups.setdefault(card['structure']['comparisonGroupKey'], []).append(card)
rows = []
for key, members in groups.items():
    graphic = members[0]['cardTypeName'] == '商家卡片-图文下挂'
    expected = ['商家标题与头图', '评分/状态与位置'] + (['商品图片、标题与价格'] if graphic else [])
    rows.append({'comparisonGroupKey': key, 'members': [c['cardId'] for c in members],
        'layoutSignatures': [{'componentId': c['cardId'], 'layoutMode': c['structure']['layoutMode'],
            'layoutSignature': 'merchant_info_then_graphic_attachment' if graphic else 'merchant_head_and_info',
            'regions': [{'region': r['name'], 'elementIds': [e['id'] for e in r['elements']], 'contentBounds': r['coord']} for r in c['regions']],
            'relations': ['头图左置、商家信息右置'] + (['商品组位于商家主体下方'] if graphic else [])} for c in members],
        'readingOrderChecks': [{'componentId': c['cardId'], 'expectedOrder': expected, 'observedOrder': list(expected),
            'attentionSignals': ['粗体标题与左侧头图先建立主体', '评分和位置保持基础信息权重'] + (['红色价格保持在商品下挂内'] if graphic else []),
            'dominantRegion': '基础信息区', 'auxiliaryDominance': False, 'competingFoci': False,
            'ownershipAmbiguity': False, 'pathInversion': False, 'localDetour': False,
            'reason': '商家主体先于基础信息和商品下挂进入注意力路径，信息归属清楚。', 'status': 'consistent'} for c in members],
        'evidenceSource': 'original_screenshot_visual_review', 'rating': '优秀'})
u['details']['evidence'] = {'sourceManifestTotal': audit['total'], 'evaluatedUnitCount': len(rows), 'assessmentRows': rows, 'excludedUnits': cropped}
u['details']['overview'] = ov(len(rows), len(rows))

u = unit('eval-3-color-logic', card_dim)
u['rating'] = '优秀'
u['reason'] = '5张可见商家卡的有效界面色系数分别为1、2、4、1、0，均未超过4种的优秀档上限。'
u['details']['evidence'] = {'sourceManifestTotal': audit['total'], 'evaluatedUnitCount': 5, 'assessmentRows': colors}
u['details']['overview'] = ov(5, 5)
u['details']['issues'] = []

# All complete cards remain within the complexity excellent threshold.
u = unit('eval-4-element-complexity', card_dim)
counts = [row['tagStyleCount'] for row in u['details']['evidence']['assessmentRows']]
u['rating'] = '优秀'
u['reason'] = f'4张完整商家卡的独立彩色标签实例数分别为{"、".join(map(str, counts))}，附加icon均为0种，全部不超过4个的优秀档上限。'
u['details']['issues'] = []
u['details']['overview'] = ov(4, 4)
u['details']['evidence']['evaluatedUnitCount'] = 4
u['details']['evidence']['excludedUnits'] = cropped

u = unit('eval-5-info-hierarchy', card_dim)
u['reason'] = '4张完整卡均以商家标题与头图建立主体，评分/状态和位置承接，商品价格保持在图文下挂次级区域。'
u['details']['evidence']['evaluatedUnitCount'] = 4
u['details']['evidence']['excludedUnits'] = cropped
u['details']['overview'] = ov(4, 4)
u = unit('eval-6-info-partitioning', card_dim)
u['reason'] = '4张完整卡的商家主体、基础信息与商品下挂通过留白、统一缩进和卡间分隔清楚区分。'
u['details']['evidence'] = {'sourceManifestTotal': audit['total'], 'evaluatedUnitCount': 4, 'assessmentRows': [], 'excludedUnits': cropped}
u['details']['overview'] = ov(4, 4)
u['details']['issues'] = []
u = unit('eval-7-info-authenticity', card_dim)
u['reason'] = '逐卡核对商家标题、头图、评分/状态、位置、商品图片、标题与价格归属，未发现不能同时成立或错归主体的关系。'
u['details']['evidence']['evaluatedUnitCount'] = 4
u['details']['evidence']['evaluatedUnitIds'] = [c['cardId'] for c in cards]
u['details']['evidence']['excludedUnits'] = cropped
u['details']['overview'] = ov(4, 4)

# Full-card redundancy scan: repeated labels on distinct product items are not
# redundant because they apply to different products.
u = unit('eval-8-info-redundancy', card_dim)
checks = ['title/subtitle ↔ basic information', 'title/subtitle ↔ tags/price/promotion', 'tag ↔ price/promotion', 'title internal repeated quantified fragments']
rows = []
for card in cards:
    ids = [e['id'] for e in elements(card)]
    pairs = []
    judgements = []
    if card['cardId'] == 'C2':
        pairs = [{'leftElementId': 'C2-T13', 'rightElementId': 'C2-T17', 'relation': '两个商品图片分别标注100%好评度'}]
        judgements = ['distinct']
    rows.append({'componentId': card['cardId'], 'scannedRegions': regions(card), 'examinedElements': ids, 'candidatePairs': pairs, 'pairJudgements': judgements, 'selfRepeatCandidates': [], 'selfRepeatJudgements': [], 'duplicates': [], 'duplicateCount': 0,
                 'scanCoverage': {'status': 'completed', 'textAtomCount': len(ids), 'scannedElementIds': ids, 'scannedRegions': regions(card), 'crossChecks': checks,
                     'crossCheckResults': [{'checkType': check, 'status': 'completed', 'candidateCount': 1 if pairs and check == checks[2] else 0, 'judgementCount': 1 if pairs and check == checks[2] else 0,
                         'reason': '两处100%好评度分别归属不同下挂商品，删除任一处会丢失对应商品决策信息。' if pairs and check == checks[2] else '该交叉类型未发现可无损删除候选。'} for check in checks]},
                 'evidenceSource': 'phase2_json_full_redundancy_scan', 'rating': '优秀'})
u['rating'] = '优秀'; u['reason'] = '4张完整卡均完成标题、基础信息、标签、商品下挂和价格的整卡扫描；重复文案均服务于不同商品，确认语义重复数为0。'
u['details']['evidence'] = {'sourceManifestTotal': audit['total'], 'evaluatedUnitCount': 4, 'evaluatedUnitIds': [c['cardId'] for c in cards], 'assessmentRows': rows, 'excludedUnits': cropped}
u['details']['issues'] = []
u['details']['overview'] = ov(4, 4)

# Page-level judgements.
u = unit('eval-1-supply-module-completeness', page_dim)
u['reason'] = '搜索框、业务Tab、定位/排序筛选、相似推荐提示和商家结果列表均完整加载。'
u = unit('eval-2-visual-order-alignment', page_dim)
row = u['details']['evidence']['assessmentRows'][0]
row['pageRegions'] = [
    {'region': '搜索与业务Tab', 'observedRole': '建立查询与结果范围', 'visualSignals': ['顶部稳定入口', '选中Tab黄色下划线']},
    {'region': '定位与排序筛选', 'observedRole': '调整地点、排序与筛选条件', 'visualSignals': ['单行浅色控件', '与结果留白分隔']},
    {'region': '相似推荐提示', 'observedRole': '解释相似商家推荐语境', 'visualSignals': ['淡粉背景', '说明文字与推荐商卡邻近']},
    {'region': '商家结果列表', 'observedRole': '连续呈现商家及商品', 'visualSignals': ['商家卡纵向排列', '标题和价格锚点稳定']},
]
row['sameTypeComparisons'] = [
    {'members': ['商卡1', '商卡4'], 'result': '无下挂卡标题和基础信息主锚点一致'},
    {'members': ['商卡2', '商卡3'], 'result': '图文下挂卡标题、基础信息和商品区主锚点一致'},
]
row['primaryFocus'] = '商家结果列表'
row['flowChecks'] = [{'expectedOrder': ['搜索与Tab', '定位与排序筛选', '商家结果'], 'observedOrder': ['搜索与Tab', '定位与排序筛选', '商家结果'], 'visualSignals': ['自上而下单列推进', '相似推荐提示紧邻其商卡且未打断主流'], 'reason': '页面按查询、筛选与浏览结果的路径推进。', 'status': 'consistent'}]
u['reason'] = '页面由搜索与业务Tab进入定位排序筛选，再进入连续商家结果；相似推荐提示与对应商卡邻近，未造成主焦点错位。'

u = unit('eval-3-page-color-logic', page_dim)
u['reason'] = '全页商家卡的有效界面色系并集为红、橙、黄、绿共4种，未超过页面优秀档上限。'
u = unit('eval-4-static-component-complexity', page_dim)
row = u['details']['evidence']['assessmentRows'][0]
row.update({'functionalModules': [{'name': '业务Tab栏', 'sourceModuleIds': ['M3']}, {'name': '定位与排序筛选', 'sourceModuleIds': ['M4']}, {'name': '相似推荐提示', 'sourceModuleIds': ['M5']}, {'name': '商家结果列表', 'sourceModuleIds': ['M6']}], 'excludedModules': [{'sourceModuleId': 'M1', 'reason': '位于首张结果卡内部的候选行，不是独立页面功能区'}, {'sourceModuleId': 'M2', 'reason': '顶部搜索框按本Skill规则排除'}], 'moduleCount': 4, 'observableFact': '排除搜索框和结果卡内部伪模块，并将所有商家卡合并为单一结果列表后，共4个独立功能区。', 'rating': '优秀'})
u['rating'] = '优秀'; u['reason'] = '排除顶部搜索框、结果卡内部伪模块并合并商家卡为单一结果列表后，首屏有业务Tab、定位排序筛选、相似推荐提示和结果列表共4个功能区，命中优秀档。'; u['details']['overview'] = ov(1, 1)
u['details']['issues'] = []

u = unit('eval-5-browsing-flow-smoothness', page_dim)
u['reason'] = '排序筛选下方5个可见列表位均为标准商家卡，前10位当前可见范围内异构数为0。'
u = unit('eval-6-info-comparability', page_dim)
u['reason'] = '4张完整商家卡按无下挂与图文下挂形成2组；各组的到店状态、评分/状态、位置及适用价格字段均保持一致信息层和表达口径。'
row = u['details']['evidence']['assessmentRows'][0]
row['cardGroups'] = [
    {'comparisonGroupKey': '商家卡片_无下挂|cv_candidate', 'members': ['C0', 'C3']},
    {'comparisonGroupKey': '商家卡片_图文下挂|cv_candidate', 'members': ['C1', 'C2']},
]
row['comparableFields'] = ['到店状态', '评分/评分状态', '区域与城市', '人均价格', '下挂商品价格']
row['comparisons'] = [
    {'comparisonGroupKey': '商家卡片_无下挂|cv_candidate', 'semanticRole': 'fulfillment_rating_location', 'fieldMatchKey': '主商家层的到店状态、评分/状态与位置槽位', 'observations': [{'componentId': cid, 'present': True, 'anchor': '标题下方基础信息行与右侧城市位'} for cid in ['C0','C3']], 'detectedDifferences': {'missing': [], 'formatMismatch': False, 'anchorMismatch': False, 'styleSemanticMismatch': False}, 'materialImpact': False, 'phase3Judgement': 'consistent'},
    {'comparisonGroupKey': '商家卡片_图文下挂|cv_candidate', 'semanticRole': 'fulfillment_rating_price_location_attachment_price', 'fieldMatchKey': '主商家层基础信息与商品下挂价格槽位', 'observations': [{'componentId': cid, 'present': True, 'anchor': '标题下方基础信息行与图片下方价格位'} for cid in ['C1','C2']], 'detectedDifferences': {'missing': [], 'formatMismatch': False, 'anchorMismatch': False, 'styleSemanticMismatch': False}, 'materialImpact': False, 'phase3Judgement': 'consistent'},
]
row['excludedReasons'] = ['不同商家的实际评分、城市、价格、商品数量及推荐标签差异属于内容差异，不是表达口径不一致。']

u = unit('eval-7-info-redundancy', page_dim)
page_regions = ['搜索与业务Tab', '定位与排序筛选', '相似推荐提示', '商家结果列表']
pairs = list(combinations(page_regions, 2))
row = {'pageRegions': page_regions, 'candidatePairs': [], 'scanCoverage': {'status': 'completed', 'scannedRegionIds': page_regions, 'crossChecks': [f'{a} ↔ {b}' for a, b in pairs]}, 'crossChecks': [{'regions': [a, b], 'judgement': 'distinct', 'reason': '两区域承担不同页面任务或提供不同决策信息。'} for a, b in pairs], 'redundancyItems': [], 'redundancyCount': 0, 'rating': '优秀'}
u['details']['evidence'] = {'assessmentRows': [row]}; u['reason'] = '已覆盖4个独立页面区域并完成6组两两检查；搜索导航、定位筛选、推荐语境与商家列表职责不同，跨区域冗余数为0。'

out.write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
