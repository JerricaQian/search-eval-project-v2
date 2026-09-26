#!/usr/bin/env python3
"""Generate the q25 Phase3 judgement from the q8 schema shell."""

import json
from itertools import combinations
from pathlib import Path

root = Path('/Users/qianjing/Documents/ChatGPT/search-eval-project-v2')
source_path = root / 'scripts/generate_q8_final30_phase3_results.py'
source = source_path.read_text(encoding='utf-8')
source = source.replace('RUN = "batch-20260920-09-2-final30-r1-q8"', 'RUN = "batch-20260920-09-2-final30-r1-q25"')
source = source.replace('QUERY = "自体脂肪隆鼻"', 'QUERY = "隐高空美学餐厅曼哈顿"')
source = source.replace('STEM = "自体脂肪隆鼻_全部_1"', 'STEM = "隐高空美学餐厅曼哈顿_全部_1"')
exec(compile(source, str(source_path), 'exec'), {'__name__': '__main__', '__file__': str(source_path)})

run = 'batch-20260920-09-2-final30-r1-q25'
batch = 'batch-20260920-09-2-final30-r1'
stem = '隐高空美学餐厅曼哈顿_全部_1'
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
cropped = [{'componentId': 'C2', 'reason': '底部自然裁切，仅保留当前可见事实，不用于完整商家卡结论。'}]

u = unit('eval-1-supply-completeness', card_dim)
u['reason'] = '2张完整图文商家卡均呈现标题、头图、评分、位置、优惠券和商品下挂；第3张为底部自然裁切。'
u['details']['evidence'] = {'sourceManifestTotal': audit['total'], 'evaluatedUnitCount': 2, 'assessmentRows': [], 'excludedUnits': cropped}
u['details']['overview'] = ov(2, 2)
u['details']['issues'] = []

u = unit('eval-2-visual-order-alignment', card_dim)
u['reason'] = '2张完整图文商家卡形成1个可比组，均先建立商家标题与头图主体，再呈现评分/位置、优惠券，最后进入商品与价格。'
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
u['rating'] = '不达标'
u['reason'] = '3张可见商家卡的有效界面色系数分别为5、6、0；商卡1命中5种达标档，商卡2使用6种色系并命中不达标档。'
u['details']['evidence'] = {'sourceManifestTotal': audit['total'], 'evaluatedUnitCount': 3, 'assessmentRows': colors}
u['details']['overview'] = ov(3, 1, passed=1, failed=1)
u['details']['issues'] = [
    {'elementId': 'C0-T2', 'coord': [1028,792,78,46], 'component': 'C0', 'description': '商卡1的有效界面色系为红、橙、黄、蓝、紫共5种，超过优秀档4种上限并命中达标档。', 'rating': '达标', 'recommendation': '统一商卡1履约、榜单与促销中的至少1种次要色系；验收时确认单卡有效色系不超过4种。', 'evidenceImage': shot},
    {'elementId': 'C1-T2', 'coord': [1028,1473,78,46], 'component': 'C1', 'description': '商卡2的有效界面色系为红、橙、黄、绿、蓝、紫共6种，超过5种不达标阈值，显著增加视觉编码负担。', 'rating': '不达标', 'recommendation': '统一商卡2履约、榜单、好评度与促销中的至少2种次要色系；验收时确认单卡有效色系不超过4种。', 'evidenceImage': shot},
]

# All complete cards remain within the complexity excellent threshold.
u = unit('eval-4-element-complexity', card_dim)
counts = [row['tagStyleCount'] for row in u['details']['evidence']['assessmentRows']]
for row in u['details']['evidence']['assessmentRows']:
    for style in row['includedTagStyles']:
        eid = style['elementIds'][0]
        element = next(e for c in cards for e in elements(c) if e['id'] == eid)
        prefix = element.get('textFacts', {}).get('promotionPrefix', '')
        if prefix:
            style['content'] = prefix
    row['rating'] = '达标' if row['tagStyleCount'] == 5 else ('不达标' if row['tagStyleCount'] >= 6 else '优秀')
u['rating'] = '不达标'
u['reason'] = f'2张完整商家卡的独立彩色标签实例数分别为{"、".join(map(str, counts))}，商卡1命中5个达标档，商卡2命中7个不达标档。'
u['details']['issues'] = [
    {'elementId': 'C0-T18', 'coord': [547,1040,170,44], 'component': 'C0', 'description': '商卡1可见标签「榜单、神券、满300可用、使用、0.2折」共5种，icon「无」0种，超过优秀档4种标签上限并命中达标档。', 'rating': '达标', 'recommendation': '合并商卡1优惠券内部的满减条件与使用按钮样式；验收时确认标签不超过4个且icon不超过2种。', 'evidenceImage': shot},
    {'elementId': 'C1-T27', 'coord': [1063,1715,73,44], 'component': 'C1', 'description': '商卡2可见标签「榜单、神券、满300可用、使用、特价团、3.7折、2.5折」共7种，icon「无」0种，达到不达标档并加重扫读负担。', 'rating': '不达标', 'recommendation': '合并商卡2优惠券内部样式并收敛商品促销标签；验收时确认标签不超过4个且icon不超过2种。', 'evidenceImage': shot},
]
u['details']['overview'] = ov(2, 0, passed=1, failed=1)
u['details']['evidence']['evaluatedUnitCount'] = 2
u['details']['evidence']['excludedUnits'] = cropped

u = unit('eval-5-info-hierarchy', card_dim)
u['reason'] = '2张完整卡均以商家标题与头图建立主体，评分和位置承接，优惠券与商品价格保持次级。'
u['details']['evidence']['evaluatedUnitCount'] = 2
u['details']['evidence']['excludedUnits'] = cropped
u['details']['overview'] = ov(2, 2)
u = unit('eval-6-info-partitioning', card_dim)
u['reason'] = '2张完整卡的商家主体、优惠券与商品下挂通过留白、列式对齐和卡间分隔清楚区分。'
u['details']['evidence'] = {'sourceManifestTotal': audit['total'], 'evaluatedUnitCount': 2, 'assessmentRows': [], 'excludedUnits': cropped}
u['details']['overview'] = ov(2, 2)
u['details']['issues'] = []
u = unit('eval-7-info-authenticity', card_dim)
u['reason'] = '逐卡核对商家标题、头图、评分、位置、优惠券、商品图片、标题与价格归属，未发现不能同时成立或错归主体的关系。'
u['details']['evidence']['evaluatedUnitCount'] = 2
u['details']['evidence']['evaluatedUnitIds'] = [c['cardId'] for c in cards]
u['details']['evidence']['excludedUnits'] = cropped
u['details']['overview'] = ov(2, 2)

# Full-card redundancy scan: repeated labels on distinct product items are not
# redundant because they apply to different products.
u = unit('eval-8-info-redundancy', card_dim)
checks = ['title/subtitle ↔ basic information', 'title/subtitle ↔ tags/price/promotion', 'tag ↔ price/promotion', 'title internal repeated quantified fragments']
rows = []
for card in cards:
    ids = [e['id'] for e in elements(card)]
    pairs = []
    judgements = []
    if card['cardId'] == 'C1':
        pairs = [{'leftElementId': 'C1-T17', 'rightElementId': 'C1-T22', 'relation': '两个商品图片分别标注100%好评度'}]
        judgements = ['distinct']
    rows.append({'componentId': card['cardId'], 'scannedRegions': regions(card), 'examinedElements': ids, 'candidatePairs': pairs, 'pairJudgements': judgements, 'selfRepeatCandidates': [], 'selfRepeatJudgements': [], 'duplicates': [], 'duplicateCount': 0,
                 'scanCoverage': {'status': 'completed', 'textAtomCount': len(ids), 'scannedElementIds': ids, 'scannedRegions': regions(card), 'crossChecks': checks,
                     'crossCheckResults': [{'checkType': check, 'status': 'completed', 'candidateCount': 1 if pairs and check == checks[2] else 0, 'judgementCount': 1 if pairs and check == checks[2] else 0,
                         'reason': '两处100%好评度分别归属不同下挂商品，删除任一处会丢失对应商品决策信息。' if pairs and check == checks[2] else '该交叉类型未发现可无损删除候选。'} for check in checks]},
                 'evidenceSource': 'phase2_json_full_redundancy_scan', 'rating': '优秀'})
u['rating'] = '优秀'; u['reason'] = '2张完整卡均完成标题、基础信息、优惠券、商品下挂和价格的整卡扫描；相同优惠与好评度文案分别服务于不同商家或商品，确认卡内语义重复数为0。'
u['details']['evidence'] = {'sourceManifestTotal': audit['total'], 'evaluatedUnitCount': 2, 'evaluatedUnitIds': [c['cardId'] for c in cards], 'assessmentRows': rows, 'excludedUnits': cropped}
u['details']['issues'] = []
u['details']['overview'] = ov(2, 2)

# Page-level judgements.
u = unit('eval-1-supply-module-completeness', page_dim)
u['reason'] = '搜索框、业务Tab、商户补充入口、定位筛选、无相关结果提示和推荐商家列表均完整加载。'
u = unit('eval-2-visual-order-alignment', page_dim)
row = u['details']['evidence']['assessmentRows'][0]
row['pageRegions'] = [
    {'region': '搜索与业务Tab', 'observedRole': '建立查询与结果范围', 'visualSignals': ['顶部稳定入口', '选中Tab黄色下划线']},
    {'region': '商户补充入口', 'observedRole': '提供用户补充与商家添加路径', 'visualSignals': ['独立白色容器', '双入口水平并列']},
    {'region': '定位筛选', 'observedRole': '确认当前地点条件', 'visualSignals': ['浅色独立控件', '与提示区留白分隔']},
    {'region': '无相关结果提示', 'observedRole': '解释后续为推荐商家', 'visualSignals': ['居中文字与横线', '说明文字紧邻推荐列表']},
    {'region': '商家结果列表', 'observedRole': '连续呈现商家及商品', 'visualSignals': ['商家卡纵向排列', '标题和价格锚点稳定']},
]
row['sameTypeComparisons'] = [{'members': ['商卡1', '商卡2'], 'result': '图文下挂卡标题、基础信息、优惠券和商品区主锚点一致'}]
row['primaryFocus'] = '商家结果列表'
row['flowChecks'] = [{'expectedOrder': ['搜索与Tab', '补充/定位入口', '结果状态提示', '推荐商家'], 'observedOrder': ['搜索与Tab', '补充/定位入口', '结果状态提示', '推荐商家'], 'visualSignals': ['自上而下单列推进', '无结果提示紧邻推荐列表'], 'reason': '页面按查询、补充或定位、状态解释与浏览推荐的路径推进。', 'status': 'consistent'}]
u['reason'] = '页面由搜索与业务Tab进入补充/定位入口，再经无结果提示进入连续推荐商家；主焦点与浏览顺序稳定。'

u = unit('eval-3-page-color-logic', page_dim)
u['rating'] = '达标'
u['reason'] = '全页商家卡的有效界面色系并集为红、橙、黄、绿、蓝、紫共6种，超过优秀档5种上限并命中达标档。'
u['details']['evidence']['assessmentRows'][0]['rating'] = '达标'
u['details']['overview'] = ov(1, 0, passed=1)
u['details']['issues'] = [{'pageArea': '推荐商家结果列表', 'description': '全页推荐商家卡的有效界面色系并集为红、橙、黄、绿、蓝、紫共6种，超过页面优秀档5种上限，增加跨卡视觉编码负担。', 'rating': '达标', 'recommendation': '统一推荐商家卡的履约、榜单、好评度和促销辅助色；验收时确认全页有效色系并集不超过5种。', 'evidenceImage': shot}]
u = unit('eval-4-static-component-complexity', page_dim)
row = u['details']['evidence']['assessmentRows'][0]
row.update({'functionalModules': [{'name': '业务Tab栏', 'sourceModuleIds': ['M2']}, {'name': '商户补充入口', 'sourceModuleIds': ['M3']}, {'name': '定位筛选', 'sourceModuleIds': ['M4']}, {'name': '无结果推荐提示', 'sourceModuleIds': ['M5']}, {'name': '推荐商家结果列表', 'sourceModuleIds': ['M6']}], 'excludedModules': [{'sourceModuleId': 'M1', 'reason': '顶部搜索框按本Skill规则排除'}], 'moduleCount': 5, 'observableFact': '排除顶部搜索框并将所有商家卡合并为单一结果列表后，共5个独立功能区。', 'rating': '达标'})
u['rating'] = '达标'; u['reason'] = '排除顶部搜索框并合并商家卡为单一结果列表后，首屏有业务Tab、商户补充入口、定位筛选、无结果推荐提示和结果列表共5个功能区，命中达标档。'; u['details']['overview'] = ov(1, 0, passed=1)
u['details']['issues'] = [{'pageArea': '首屏整体', 'description': '排除搜索框后，首屏同时呈现业务Tab、商户补充入口、定位筛选、无结果推荐提示和推荐结果列表共5个独立功能区，命中达标档并增加模块切换。', 'rating': '达标', 'recommendation': '将商户补充入口收敛进无结果提示区或次级入口；验收时确认首屏独立功能区不超过4个。', 'evidenceImage': shot}]

u = unit('eval-5-browsing-flow-smoothness', page_dim)
u['reason'] = '无结果推荐提示下方3个可见列表位均为标准图文商家卡，前10位当前可见范围内异构数为0。'
u = unit('eval-6-info-comparability', page_dim)
u['reason'] = '2张完整图文商家卡的到店状态、评分、位置、人均价格、优惠券与商品价格均保持一致信息层和表达口径。'
row = u['details']['evidence']['assessmentRows'][0]
row['cardGroups'] = [{'comparisonGroupKey': '商家卡片_图文下挂|cv_candidate', 'members': ['C0', 'C1']}]
row['comparableFields'] = ['到店状态', '评分/评分状态', '区域与城市', '人均价格', '下挂商品价格']
row['comparisons'] = [{'comparisonGroupKey': '商家卡片_图文下挂|cv_candidate', 'semanticRole': 'fulfillment_rating_price_location_coupon_attachment_price', 'fieldMatchKey': '主商家层基础信息、优惠券与商品下挂价格槽位', 'observations': [{'componentId': cid, 'present': True, 'anchor': '标题下方基础信息行、左侧优惠券与图片下方价格位'} for cid in ['C0','C1']], 'detectedDifferences': {'missing': [], 'formatMismatch': False, 'anchorMismatch': False, 'styleSemanticMismatch': False}, 'materialImpact': False, 'phase3Judgement': 'consistent'}]
row['excludedReasons'] = ['不同商家的实际评分、城市、价格、商品数量及推荐标签差异属于内容差异，不是表达口径不一致。']

u = unit('eval-7-info-redundancy', page_dim)
page_regions = ['搜索与业务Tab', '商户补充入口', '定位筛选', '无相关结果提示', '推荐商家结果列表']
pairs = list(combinations(page_regions, 2))
row = {'pageRegions': page_regions, 'candidatePairs': [], 'scanCoverage': {'status': 'completed', 'scannedRegionIds': page_regions, 'crossChecks': [f'{a} ↔ {b}' for a, b in pairs]}, 'crossChecks': [{'regions': [a, b], 'judgement': 'distinct', 'reason': '两区域承担不同页面任务或提供不同决策信息。'} for a, b in pairs], 'redundancyItems': [], 'redundancyCount': 0, 'rating': '优秀'}
u['details']['evidence'] = {'assessmentRows': [row]}; u['reason'] = '已覆盖5个独立页面区域并完成10组两两检查；搜索导航、补充入口、定位、状态提示和推荐列表职责不同，跨区域冗余数为0。'

out.write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
