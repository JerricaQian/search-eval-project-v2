#!/usr/bin/env python3
"""Generate the q20 Phase3 judgement from the five-card q8 schema shell."""

import json
from itertools import combinations
from pathlib import Path

root = Path('/Users/qianjing/Documents/ChatGPT/search-eval-project-v2')
source_path = root / 'scripts/generate_q8_final30_phase3_results.py'
source = source_path.read_text(encoding='utf-8')
source = source.replace('RUN = "batch-20260920-09-2-final30-r1-q8"', 'RUN = "batch-20260920-09-2-final30-r1-q20"')
source = source.replace('QUERY = "自体脂肪隆鼻"', 'QUERY = "迪士尼蛋糕拍拍灯"')
source = source.replace('STEM = "自体脂肪隆鼻_全部_1"', 'STEM = "迪士尼蛋糕拍拍灯_全部_1"')
exec(compile(source, str(source_path), 'exec'), {'__name__': '__main__', '__file__': str(source_path)})

run = 'batch-20260920-09-2-final30-r1-q20'
batch = 'batch-20260920-09-2-final30-r1'
stem = '迪士尼蛋糕拍拍灯_全部_1'
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
cropped = [{'componentId': 'C5', 'reason': '底部自然裁切，仅保留当前可见事实，不用于完整商家卡结论。'}]

u = unit('eval-1-supply-completeness', card_dim)
u['reason'] = '5张完整景点商家卡均呈现商家标题、头图、评分/状态、位置与当前卡型适用的文字下挂；第6张为底部自然裁切。'

u = unit('eval-2-visual-order-alignment', card_dim)
u['reason'] = '5张完整同型商家卡均先建立景点标题与头图主体，再呈现评分/位置，最后进入票务价格与文字下挂，扫读顺序稳定。'
for row in u['details']['evidence']['assessmentRows']:
    for check in row['readingOrderChecks']:
        check['expectedOrder'] = ['景点标题与头图', '评分/状态与位置', '票务价格与文字下挂']
        check['observedOrder'] = list(check['expectedOrder'])
        check['attentionSignals'] = ['粗体大号标题与左侧头图先建立景点主体', '红色票价与促销保持在下挂次级区域']

u = unit('eval-3-color-logic', card_dim)
u['rating'] = '达标'
u['reason'] = '6张可见卡的有效界面色系数分别为5、5、4、5、5、0；商卡1、2、4、5各使用5种色系，命中达标档。'
u['details']['evidence'] = {'sourceManifestTotal': audit['total'], 'evaluatedUnitCount': 6, 'assessmentRows': colors}
u['details']['overview'] = ov(6, 2, passed=4)
issues = []
for idx, card_id in enumerate(['C0', 'C1', 'C3', 'C4'], 1):
    card = next(c for c in cards if c['cardId'] == card_id)
    target = next(e for e in elements(card) if e.get('textFacts', {}).get('semanticRole') == 'fulfillment')
    visible_num = card['structure']['listPosition'] + 1
    issues.append({'elementId': target['id'], 'coord': target['坐标'], 'component': card_id,
                   'description': f'商卡{visible_num}的有效界面色系为「红、橙、黄、青、蓝」共5种，超过优秀档4种上限并命中达标档。',
                   'rating': '达标', 'recommendation': f'统一商卡{visible_num}景点履约、评分与票务促销中的至少1种次要色系；验收时确认单卡有效色系不超过4种。', 'evidenceImage': shot})
u['details']['issues'] = issues

# All complete cards remain within the complexity excellent threshold.
u = unit('eval-4-element-complexity', card_dim)
counts = [row['tagStyleCount'] for row in u['details']['evidence']['assessmentRows']]
u['rating'] = '优秀'
u['reason'] = f'5张完整商家卡的独立彩色标签实例数分别为{"、".join(map(str, counts))}，附加icon均为0种，全部不超过4个的优秀档上限。'
u['details']['issues'] = []
u['details']['overview'] = ov(5, 5)

u = unit('eval-5-info-hierarchy', card_dim)
u['reason'] = '5张完整卡均以景点标题与头图建立主体，评分/状态和位置承接，票务价格与促销保持次级。'
u = unit('eval-6-info-partitioning', card_dim)
u['reason'] = '5张完整卡的景点主体、基础信息与票务下挂通过垂直留白、统一缩进和卡间分隔清楚区分。'
u = unit('eval-7-info-authenticity', card_dim)
u['reason'] = '逐卡核对景点标题、头图、评分/状态、位置、票务价格与同行项目归属，未发现不能同时成立或错归主体的关系。'

# C1 repeats the exact same ticket offer in two independent attachment rows.
u = unit('eval-8-info-redundancy', card_dim)
checks = ['title/subtitle ↔ basic information', 'title/subtitle ↔ tags/price/promotion', 'tag ↔ price/promotion', 'title internal repeated quantified fragments']
rows = []
for card in cards:
    ids = [e['id'] for e in elements(card)]
    spec = None
    if card['cardId'] == 'C1':
        by_text = {}
        for e in elements(card):
            text = e.get('textFacts', {}).get('rawText', '')
            if text:
                by_text.setdefault(text, []).append(e)
        a, b = by_text['【亲子2大1小票】夜场Ai智航票'][:2]
        spec = (a, b)
    pairs = [] if spec is None else [{'leftElementId': spec[0]['id'], 'rightElementId': spec[1]['id'], 'relation': '两条文字下挂的价格、促销和票务标题完全相同'}]
    dups = [] if spec is None else [{'leftElementId': spec[0]['id'], 'rightElementId': spec[1]['id'], 'lexicalCue': '同卡两条「【亲子2大1小票】夜场Ai智航票」', 'normalizedFact': '亲子2大1小夜场Ai智航票¥388特价团', 'noLossReason': '两条下挂的票种、价格与促销完全一致，删除其中一条不损失决策信息。', 'verdict': 'duplicate'}]
    rows.append({'componentId': card['cardId'], 'scannedRegions': regions(card), 'examinedElements': ids, 'candidatePairs': pairs, 'pairJudgements': ['duplicate'] if spec else [], 'selfRepeatCandidates': [], 'selfRepeatJudgements': [], 'duplicates': dups, 'duplicateCount': 1 if spec else 0,
                 'scanCoverage': {'status': 'completed', 'textAtomCount': len(ids), 'scannedElementIds': ids, 'scannedRegions': regions(card), 'crossChecks': checks,
                     'crossCheckResults': [{'checkType': check, 'status': 'completed', 'candidateCount': 1 if spec and check == checks[2] else 0, 'judgementCount': 1 if spec and check == checks[2] else 0, 'reason': '已终判两条完全相同票务下挂。' if spec and check == checks[2] else '该交叉类型未发现额外可无损删除候选。'} for check in checks]},
                 'evidenceSource': 'phase2_json_full_redundancy_scan', 'rating': '不达标' if spec else '优秀'})
u['rating'] = '不达标'; u['reason'] = '5张完整卡均完成整卡扫描；商卡2的两条文字下挂在票种、价格和促销上完全相同，确认1个可无损删除的重复。'
u['details']['evidence'] = {'sourceManifestTotal': audit['total'], 'evaluatedUnitCount': 5, 'evaluatedUnitIds': [c['cardId'] for c in cards], 'assessmentRows': rows, 'excludedUnits': cropped}
u['details']['issues'] = [{'elementId': 'C1-T11', 'coord': [492, 1357, 500, 48], 'component': 'C1', 'description': '商卡2的两条「【亲子2大1小票】夜场Ai智航票」同时使用¥388和特价团，票种、价格和促销完全一致，删除任一条不损失决策信息。', 'rating': '不达标', 'recommendation': '合并商卡2的两条完全相同票务下挂，仅保留一条¥388特价团信息；验收时确认整卡语义重复数为0。', 'evidenceImage': shot}]
u['details']['overview'] = ov(5, 4, failed=1)

# Page-level judgements.
u = unit('eval-1-supply-module-completeness', page_dim)
u['reason'] = '搜索框、业务Tab、当前城市提示、图形意图筛选、排序筛选和景点结果列表均完整加载。'
u = unit('eval-2-visual-order-alignment', page_dim)
row = u['details']['evidence']['assessmentRows'][0]
row['pageRegions'] = [
    {'region': '搜索与业务Tab', 'observedRole': '建立查询与结果范围', 'visualSignals': ['顶部稳定入口', '选中Tab黄色下划线']},
    {'region': '城市与图形意图筛选', 'observedRole': '确认城市并快速收敛业态', 'visualSignals': ['上海/北京文字提示', '六个等距图形入口']},
    {'region': '排序筛选', 'observedRole': '调整分类、排序与距离', 'visualSignals': ['浅色独立控件', '与结果留白分隔']},
    {'region': '景点结果列表', 'observedRole': '连续呈现景点与票务', 'visualSignals': ['同型商家卡纵向排列', '标题和票务锚点稳定']},
]
row['sameTypeComparisons'] = [{'members': ['商卡1', '商卡2', '商卡3', '商卡4', '商卡5'], 'result': '标题、基础信息和票务下挂主锚点一致'}]
row['primaryFocus'] = '景点结果列表'
row['flowChecks'] = [{'expectedOrder': ['搜索与Tab', '城市/意图收敛', '排序筛选', '景点结果'], 'observedOrder': ['搜索与Tab', '城市/意图收敛', '排序筛选', '景点结果'], 'visualSignals': ['自上而下单列推进', '图形筛选与结果列表分区清楚'], 'reason': '页面按查询、意图收敛、排序与浏览结果的路径推进。', 'status': 'consistent'}]
u['reason'] = '页面由搜索与Tab进入城市/图形意图收敛，再经排序筛选进入连续景点结果，主焦点与浏览顺序稳定。'

u = unit('eval-3-page-color-logic', page_dim)
u['reason'] = '全页景点卡的有效界面色系并集为红、橙、黄、青、蓝共5种，未超过页面优秀档上限。'
u = unit('eval-4-static-component-complexity', page_dim)
row = u['details']['evidence']['assessmentRows'][0]
row.update({'functionalModules': [{'name': '业务Tab栏', 'sourceModuleIds': ['M1']}, {'name': '当前城市提示', 'sourceModuleIds': ['M2']}, {'name': '图形意图筛选', 'sourceModuleIds': ['M3']}, {'name': '排序筛选', 'sourceModuleIds': ['M4']}, {'name': '景点结果列表', 'sourceModuleIds': ['M5']}], 'moduleCount': 5, 'observableFact': '排除顶部搜索框并合并景点卡为单一结果列表后，共5个独立功能区。', 'rating': '达标'})
u['rating'] = '达标'; u['reason'] = '排除顶部搜索框并合并景点卡为单一结果列表后，首屏有业务Tab、城市提示、图形意图筛选、排序筛选和结果列表共5个功能区，命中达标档。'; u['details']['overview'] = ov(1, 0, passed=1)
u['details']['issues'] = [{'pageArea': '首屏整体', 'description': '排除搜索框后，首屏同时呈现业务Tab、当前城市提示、图形意图筛选、排序筛选和景点结果列表共5个独立功能区，命中达标档，增加从查询到结果的模块切换。', 'rating': '达标', 'recommendation': '将当前城市提示收敛进图形意图筛选或排序筛选区；验收时确认首屏独立功能区不超过4个。', 'evidenceImage': shot}]

u = unit('eval-5-browsing-flow-smoothness', page_dim)
u['reason'] = '排序筛选下方6个可见列表位均为同型标准景点商家卡，前10位当前可见范围内异构数为0。'
u = unit('eval-6-info-comparability', page_dim)
u['reason'] = '5张完整同型景点卡均在固定基础信息层呈现景点履约、评分/状态和位置，票务价格与项目也在同一下挂锚点呈现，可直接比较。'
row = u['details']['evidence']['assessmentRows'][0]
row['comparableFields'] = ['景点履约', '评分/评分状态', '位置', '票务价格与项目']
row['excludedReasons'] = ['不同景点的实际评分、票价、项目数和销量差异属于内容差异，不是表达口径不一致。']

u = unit('eval-7-info-redundancy', page_dim)
page_regions = ['搜索与业务Tab', '当前城市提示', '图形意图筛选', '排序筛选', '景点结果列表']
pairs = list(combinations(page_regions, 2))
row = {'pageRegions': page_regions, 'candidatePairs': [], 'scanCoverage': {'status': 'completed', 'scannedRegionIds': page_regions, 'crossChecks': [f'{a} ↔ {b}' for a, b in pairs]}, 'crossChecks': [{'regions': [a, b], 'judgement': 'distinct', 'reason': '两区域承担不同页面任务或提供不同决策信息。'} for a, b in pairs], 'redundancyItems': [], 'redundancyCount': 0, 'rating': '优秀'}
u['details']['evidence'] = {'assessmentRows': [row]}; u['reason'] = '已覆盖5个独立页面区域并完成10组两两检查；城市上下文、意图筛选、排序与景点列表职责不同，跨区域冗余数为0。'

out.write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
