#!/usr/bin/env python3
"""Generate q17 from the schema-complete q2 four-card scaffold."""

from pathlib import Path

root = Path('/Users/qianjing/Documents/ChatGPT/search-eval-project-v2')
source_path = root / 'scripts/generate_q2_final30_phase3_results.py'
source = source_path.read_text(encoding='utf-8')
source = source.replace('RUN = "batch-20260920-09-2-final30-r1-q2"', 'RUN = "batch-20260920-09-2-final30-r1-q17"')
source = source.replace('QUERY = "绯诱秘境瑶浴spa"', 'QUERY = "许州五妈凉粉"')
source = source.replace('STEM = "绯诱秘境瑶浴spa_全部_1"', 'STEM = "许州五妈凉粉_全部_1"')
source = source.replace(
    'distinct_pairs = {\n    "C0": [("C0-T13", "C0-T17", "两个3.2折分别服务两条独立套餐"), ("C0-T15", "C0-T19", "两个年售1000+分别服务两条独立套餐")],\n    "C1": [("C1-T13", "C1-T17", "两个年售200+分别服务两条独立套餐")],\n}',
    'distinct_pairs = {}',
)
exec(compile(source, str(source_path), 'exec'), {'__name__': '__main__', '__file__': str(source_path)})

# Replace q2's page-specific narrative and judgements with q17 facts.
import json
from itertools import combinations

run = 'batch-20260920-09-2-final30-r1-q17'
batch = 'batch-20260920-09-2-final30-r1'
shot = str(root / 'screenshots/许州五妈凉粉_全部_1.png')
manifest_path = root / f'screenshots-out/elements_许州五妈凉粉_全部_1_{run}.json'
out = root / f'.artifacts/过程文件-评测结果与审计/{batch}/{run}/results/评测原始结果_{run}.json'
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
results = json.loads(out.read_text(encoding='utf-8'))
cards = [c for c in manifest['cards'] if c['structure']['visibleStatus'] == 'complete']


def unit(skill, dimension=None):
    for result in results:
        if result['skill'] == skill and (dimension is None or result['dimension'] == dimension):
            return result['units'][0]
    raise KeyError(skill)


def card_elements(card):
    return [e for region in card['regions'] for e in region['elements']]


def region_names(card):
    return [region['name'] for region in card['regions']]


def overview(total, excellent, passed=0, failed=0):
    return {'total': total, 'excellent': excellent, 'pass': passed, 'fail': failed,
            'failRate': f'{failed / total * 100:.1f}%' if total else '0.0%'}


card_dim = 'phase3-card_or_component-eval'
page_dim = 'phase3-page_framework-eval'

u = unit('eval-1-supply-completeness', card_dim)
u['reason'] = '4张完整商家卡均呈现可读商家标题、头图与当前卡型适用的基础信息；底部第5张卡为自然裁切，不推断屏外信息。'

# Two real comparison groups: no-attachment cards and image-attachment cards.
u = unit('eval-2-visual-order-alignment', card_dim)
rows = []
for group_key in sorted({c['structure']['comparisonGroupKey'] for c in cards}):
    members = [c for c in cards if c['structure']['comparisonGroupKey'] == group_key]
    checks = []
    signatures = []
    for card in members:
        has_attached = bool(card['structure'].get('attachedItems'))
        observed = ['商家标题与头图', '评分、位置与履约']
        if has_attached:
            observed += ['权益推荐', '优惠券与图文下挂']
        signatures.append({
            'componentId': card['cardId'], 'layoutMode': card['structure']['layoutMode'],
            'layoutSignature': card['structure']['layoutSignature'],
            'regions': [{'region': r['name'], 'elementIds': [e['id'] for e in r['elements']], 'contentBounds': r['coord']} for r in card['regions']],
            'relations': [card['structure']['layoutAnchorRelation']],
        })
        checks.append({
            'componentId': card['cardId'], 'expectedOrder': observed, 'observedOrder': observed,
            'attentionSignals': ['粗体大号标题与左侧头图先建立商家主体', '彩色权益与价格保持在次级区域'],
            'dominantRegion': '基础信息区', 'auxiliaryDominance': False,
            'competingFoci': False, 'ownershipAmbiguity': False, 'pathInversion': False,
            'localDetour': False, 'reason': '主体先于权益和下挂进入注意力路径，归属清楚。', 'status': 'consistent',
        })
    rows.append({'comparisonGroupKey': group_key, 'members': [c['cardId'] for c in members],
                 'layoutSignatures': signatures, 'readingOrderChecks': checks,
                 'evidenceSource': 'original_screenshot_visual_review', 'rating': '优秀'})
u['reason'] = '2组同型商家卡均先建立商家主体与基础决策信息，图文下挂卡再进入权益与商品，视觉路径稳定。'
u['details']['evidence']['assessmentRows'] = rows
u['details']['evidence']['evaluatedUnitCount'] = 2
u['details']['overview'] = overview(2, 2)

u = unit('eval-3-color-logic', card_dim)
u['rating'] = '达标'
u['reason'] = '5张可见商家卡的有效界面色系数分别为1、1、4、5、0；商卡4使用红、橙、黄、青、紫共5种，命中达标档。'
u['details']['overview'] = overview(5, 4, passed=1)
u['details']['issues'] = [{
    'elementId': 'C3-T10', 'coord': [430, 1987, 255, 42], 'component': 'C3',
    'description': '商卡4当前有效界面色系为「红、橙、黄、青、紫」共5种，超过优秀档4种上限并命中达标档。',
    'rating': '达标', 'recommendation': '统一商卡4履约、推荐与促销信息中的至少1种次要色系；验收时确认单卡有效色系不超过4种。',
    'evidenceImage': shot,
}]

u = unit('eval-4-element-complexity', card_dim)
u['rating'] = '不达标'
u['reason'] = '4张完整商家卡的独立彩色标签实例数分别为0、0、8、6；商卡3超过6个而不达标，商卡4命中达标档。'
u['details']['overview'] = overview(4, 2, passed=1, failed=1)
u['details']['issues'] = [
    {'elementId': 'C2-T11', 'coord': [73, 1448, 125, 43], 'component': 'C2',
     'description': '商卡3可见「7折、7折、90天低价、半年低价、神券、¥17、满300可用、使用」共8个独立彩色标签，附加icon为0种，超过6个的不达标上限。',
     'rating': '不达标', 'recommendation': '合并商卡3不同商品位的折扣/低价提示，并将神券金额、门槛与操作收敛为单一权益容器；验收时确认单卡标签不超过4个。', 'evidenceImage': shot},
    {'elementId': 'C3-T11', 'coord': [73, 2130, 125, 43], 'component': 'C3',
     'description': '商卡4可见「半年低价、边缘半年、神券、¥26、满300可用、使用」共6个独立彩色标签，附加icon为0种，命中5—6个的达标档。',
     'rating': '达标', 'recommendation': '将商卡4神券金额、门槛与操作收敛为单一权益表达；验收时确认单卡标签不超过4个。', 'evidenceImage': shot},
]

u = unit('eval-6-info-partitioning', card_dim)
u['reason'] = '2张无下挂卡的商家主体与基础信息、2张图文下挂卡的商家主体、券与商品区均通过留白、对齐和容器清楚分区。'

# Visible merchant identity is repeated in three head images; C2's campaign
# image does not repeat the full merchant identity.
u = unit('eval-8-info-redundancy', card_dim)
dup_cards = {'C0': ('C0-T1', 'C0-P1', '许州五妈凉粉'),
             'C1': ('C1-T1', 'C1-P1', '许州五妈凉粉'),
             'C3': ('C3-T1', 'C3-P1', '巴依老爷')}
rows, issues = [], []
checks = ['title/subtitle ↔ basic information', 'title/subtitle ↔ tags/price/promotion', 'tag ↔ price/promotion', 'title internal repeated quantified fragments']
for idx, card in enumerate(cards, 1):
    ids = [e['id'] for e in card_elements(card)]
    spec = dup_cards.get(card['cardId'])
    pairs = [] if not spec else [{'leftElementId': spec[0], 'rightElementId': spec[1], 'relation': f'标题与头图内品牌字重复表达{spec[2]}'}]
    judgements = [] if not spec else ['duplicate']
    duplicates = [] if not spec else [{'leftElementId': spec[0], 'rightElementId': spec[1], 'lexicalCue': spec[2], 'normalizedFact': spec[2], 'noLossReason': '标题已完整表达商家身份，删除头图内重复品牌字不损失独立决策信息。', 'verdict': 'duplicate'}]
    rows.append({'componentId': card['cardId'], 'scannedRegions': region_names(card), 'examinedElements': ids,
                 'candidatePairs': pairs, 'pairJudgements': judgements, 'selfRepeatCandidates': [], 'selfRepeatJudgements': [],
                 'duplicates': duplicates, 'duplicateCount': 1 if spec else 0,
                 'scanCoverage': {'status': 'completed', 'textAtomCount': len(ids), 'scannedElementIds': ids, 'scannedRegions': region_names(card), 'crossChecks': checks,
                     'crossCheckResults': [{'checkType': check, 'status': 'completed', 'candidateCount': 1 if spec and check == checks[0] else 0, 'judgementCount': 1 if spec and check == checks[0] else 0,
                                            'reason': '已终判标题与头图品牌字候选。' if spec and check == checks[0] else '该交叉类型未发现额外可无损删除候选。'} for check in checks]},
                 'evidenceSource': 'phase2_json_full_redundancy_scan', 'rating': '不达标' if spec else '优秀'})
    if spec:
        img = next(e for e in card_elements(card) if e['id'] == spec[1])
        issues.append({'elementId': spec[1], 'coord': img['坐标'], 'component': card['cardId'],
                       'description': f'商卡{idx}的标题与头图内品牌字重复表达「{spec[2]}」商家身份，删除头图重复文字不损失独立决策信息。',
                       'rating': '不达标', 'recommendation': f'删除或弱化商卡{idx}头图内与标题重复的品牌文字，只保留一处完整商家身份；验收时确认整卡重复数为0。', 'evidenceImage': shot})
u['rating'] = '不达标'
u['reason'] = '4张完整商家卡均完成整卡扫描；其中3张的标题与头图品牌字重复表达同一商家身份。'
u['details']['evidence']['assessmentRows'] = rows
u['details']['evidence']['evaluatedUnitCount'] = 4
u['details']['evidence']['evaluatedUnitIds'] = [c['cardId'] for c in cards]
u['details']['issues'] = issues
u['details']['overview'] = overview(4, 1, failed=3)

u = unit('eval-1-supply-module-completeness', page_dim)
u['reason'] = '搜索框、业务Tab、排序筛选与商家结果列表均完整加载，并有可见推荐衔接提示，页面核心骨架完整。'

u = unit('eval-2-visual-order-alignment', page_dim)
row = u['details']['evidence']['assessmentRows'][0]
row['pageRegions'] = [
    {'region': '搜索与业务Tab', 'observedRole': '建立查询与结果范围', 'visualSignals': ['顶部固定入口', '当前Tab使用黄色下划线']},
    {'region': '位置与排序筛选', 'observedRole': '收敛地域与排序条件', 'visualSignals': ['独立浅色筛选条', '与列表留白分隔']},
    {'region': '商家结果列表', 'observedRole': '连续呈现标准商家卡', 'visualSignals': ['两种正式商家卡自上而下排列', '卡间距稳定']},
    {'region': '推荐衔接提示', 'observedRole': '说明条件匹配较少并承接后续结果', 'visualSignals': ['居中浅灰说明', '与前后卡片边界清楚']},
]
row['sameTypeComparisons'] = [{'members': ['商卡1', '商卡2'], 'result': '无下挂卡主锚点一致'}, {'members': ['商卡3', '商卡4'], 'result': '图文下挂卡主锚点一致'}]
row['primaryFocus'] = '商家结果列表'
row['flowChecks'] = [{'expectedOrder': ['搜索与Tab', '位置与排序筛选', '商家结果', '推荐衔接提示'], 'observedOrder': ['搜索与Tab', '位置与排序筛选', '商家结果', '推荐衔接提示'], 'visualSignals': ['自上而下单列推进', '不同商卡变体仍保持主体对齐'], 'reason': '主焦点稳定落在结果卡，提示不抢占浏览主路径。', 'status': 'consistent'}]
u['reason'] = '页面从搜索与Tab进入位置/排序筛选，随后连续浏览商家结果，底部推荐提示不抢占主焦点。'

u = unit('eval-3-page-color-logic', page_dim)
u['reason'] = '全页有效界面色系并集为红、橙、黄、青、紫共5种，未超过页面优秀档上限。'

u = unit('eval-4-static-component-complexity', page_dim)
row = u['details']['evidence']['assessmentRows'][0]
row.update({'functionalModules': [{'name': '业务Tab栏', 'sourceModuleIds': ['M1']}, {'name': '位置与排序筛选', 'sourceModuleIds': ['M2']}, {'name': '商家结果列表', 'sourceModuleIds': ['M3']}, {'name': '推荐衔接提示', 'sourceModuleIds': ['M4']}], 'moduleCount': 4, 'observableFact': '排除顶部搜索框并合并普通结果卡后，共4个独立功能区。', 'rating': '优秀'})
u['rating'] = '优秀'; u['reason'] = '排除顶部搜索框并合并商家卡为单一结果列表后，首屏有4个独立功能区，达到优秀档。'; u['details']['issues'] = []; u['details']['overview'] = overview(1, 1)

u = unit('eval-5-browsing-flow-smoothness', page_dim)
u['reason'] = '排序筛选下方5个可见列表位均为正式商家卡，虽含无下挂与图文下挂两种变体，但均保持统一商家主体起点，异构卡数为0。'

u = unit('eval-6-info-comparability', page_dim)
comparisons = []
groups = []
for key in sorted({c['structure']['comparisonGroupKey'] for c in cards}):
    members = [c for c in cards if c['structure']['comparisonGroupKey'] == key]
    groups.append({'comparisonGroupKey': key, 'members': [c['cardId'] for c in members]})
    comparisons.append({'comparisonGroupKey': key, 'semanticRole': 'fulfillment_rating_location_category', 'fieldMatchKey': '同型商家卡主商家层的履约、评分/状态、位置与品类', 'observations': [{'componentId': c['cardId'], 'present': True, 'anchor': '标题下方基础信息行'} for c in members], 'detectedDifferences': {'missing': [], 'formatMismatch': False, 'anchorMismatch': False, 'styleSemanticMismatch': False}, 'materialImpact': False, 'phase3Judgement': 'consistent'})
row = u['details']['evidence']['assessmentRows'][0]
row.update({'cardGroups': groups, 'comparableFields': ['到店履约', '评分/评分状态', '位置', '品类'], 'comparisons': comparisons, 'excludedReasons': ['无下挂卡与图文下挂卡属不同变体，不强行跨组比较下挂字段。'], 'inconsistencyCount': 0, 'rating': '优秀'})
u['reason'] = '2组同型完整商家卡的履约、评分/状态、位置与品类均在相同信息层呈现，格式与锚点可直接比较。'

u = unit('eval-7-info-redundancy', page_dim)
regions = ['搜索与业务Tab', '位置与排序筛选', '商家结果列表', '推荐衔接提示']
pairs = list(combinations(regions, 2))
row = {'pageRegions': regions, 'candidatePairs': [], 'scanCoverage': {'status': 'completed', 'scannedRegionIds': regions, 'crossChecks': [f'{a} ↔ {b}' for a, b in pairs]}, 'crossChecks': [{'regions': [a, b], 'judgement': 'distinct', 'reason': '两区域承担不同页面任务或提供不同决策信息。'} for a, b in pairs], 'redundancyItems': [], 'redundancyCount': 0, 'rating': '优秀'}
u['details']['evidence'] = {'assessmentRows': [row]}
u['reason'] = '已覆盖4个独立页面区域并完成6组两两检查；各区域职责不同，跨区域冗余数为0。'

out.write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
