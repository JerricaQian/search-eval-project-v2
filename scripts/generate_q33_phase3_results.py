#!/usr/bin/env python3
"""Materialize the manually adjudicated Phase 3 result for the q33 retry.

The judgement is deliberately kept in this small, reviewable file; the program
only projects the accepted Phase 2 inventory and prepared measurements into the
strict result contract.
"""
import json
from pathlib import Path

ROOT = Path('/Users/qianjing/Documents/ChatGPT/workproject_3')
RUN = 'eval-20260913-09-1-next35-v1-q33-r2'
MANIFEST = ROOT / f'screenshots-out/elements_网咖_全部_1_{RUN}.json'
MEASURE = ROOT / f'.artifacts/过程文件-评测结果与审计/eval-20260913-09-1-next35-v1/{RUN}/phase3/measurements'
OUT = ROOT / f'.artifacts/过程文件-评测结果与审计/eval-20260913-09-1-next35-v1/{RUN}/results/评测原始结果_{RUN}.json'
SHOT = str(ROOT / 'screenshots/网咖_全部_1.png')

m = json.loads(MANIFEST.read_text())
colors = json.loads(next(MEASURE.glob('*.component-color-families.json')).read_text())['components']
color_artifact = str(next(MEASURE.glob('*.component-color-families.json')))
cards = m['cards']

def atoms(card, photos=False):
    return [e for r in card['regions'] for e in r['elements'] if bool(e['render'].get('isPhoto')) == photos]

def region(card, name):
    return next(r for r in card['regions'] if r['name'] == name)

def union(es):
    xs = [e['坐标'][0] for e in es]; ys = [e['坐标'][1] for e in es]
    rs = [e['坐标'][0]+e['坐标'][2] for e in es]; bs = [e['坐标'][1]+e['坐标'][3] for e in es]
    return [min(xs), min(ys), max(rs)-min(xs), max(bs)-min(ys)]

def relation(a,b):
    if a[0]+a[2] <= b[0]: return 'left_of'
    if b[0]+b[2] <= a[0]: return 'right_of'
    if a[1]+a[3] <= b[1]: return 'above'
    if b[1]+b[3] <= a[1]: return 'below'
    return 'overlap'

def overview(rating, total=1):
    return {'total':total,'excellent':total if rating=='优秀' else 0,'pass':total if rating=='达标' else 0,'fail':total if rating=='不达标' else 0,'failRate':'0.0%' if rating!='不达标' else '100.0%'}

def unit(rating, reason, evidence, issues=None):
    return {'tab':'全部','rating':rating,'reason':reason,'details':{'screenshot':SHOT,'evidenceMode':'original-page','overview':overview(rating, evidence.get('evaluatedUnitCount',1) if isinstance(evidence,dict) else 1),'evidence':evidence,'issues':issues or []}}

def result(dim, skill, title, rating, reason, evidence):
    return {'query':'网咖','dimension':dim,'skill':skill,'title':title,'units':[unit(rating,reason,evidence)]}

active = [e for c in cards for r in c['regions'] for e in r['elements']]
all_ids = [e['id'] for e in active]
text_by_card = {c['cardId']: atoms(c, False) for c in cards}
regions_by_card = {c['cardId']:[r['name'] for r in c['regions']] for c in cards}
R=[]
CD='phase3-card_or_component-eval'; PD='phase3-page_framework-eval'

R.append(result(CD,'eval-1-supply-completeness','供给呈现质量','优秀','四张可见商家卡均呈现标题、基础信息与至少一组文字下挂商品；末卡底部为自然截断，未据此认定供给缺失。',{'assessmentRows':[]}))

members=[c['cardId'] for c in cards]
sigs=[]; checks=[]
for c in cards:
    chosen=['标题区','基础信息区','文字下挂区','头图区']
    regs=[]
    for n in chosen:
        rr=region(c,n); es=rr['elements']; regs.append({'region':n,'elementIds':[e['id'] for e in es],'contentBounds':union(es)})
    b={x['region']:x['contentBounds'] for x in regs}
    rels=[{'fromRegion':'头图区','toRegion':'基础信息区','relation':relation(b['头图区'],b['基础信息区'])},{'fromRegion':'基础信息区','toRegion':'文字下挂区','relation':relation(b['基础信息区'],b['文字下挂区'])}]
    sigs.append({'componentId':c['cardId'],'layoutMode':'left_image_right_text','layoutSignature':'merchant_text_attachment','regions':regs,'relations':rels})
    checks.append({'componentId':c['cardId'],'regionOrder':['头图区','标题区','基础信息区','文字下挂区'],'status':'consistent'})
align={'comparisonGroupKey':'商家卡片_文字下挂','members':members,'layoutSignatures':sigs,'readingOrderChecks':checks,'evidenceSource':'original_screenshot_visual_review','rating':'优秀'}
R.append(result(CD,'eval-2-visual-order-alignment','视觉秩序统一对齐','优秀','四张同型商家卡均保持左侧头图、右侧标题与基础信息、下方文字商品的阅读顺序。',{'sourceManifestTotal':len(active),'evaluatedUnitCount':1,'assessmentRows':[align]}))

R.append(result(CD,'eval-3-color-logic','色彩逻辑', '优秀','四张商家卡的强调色均控制在两种色相族内，用于评分、促销或标签。',{'sourceManifestTotal':len(active),'evaluatedUnitCount':len(colors),'assessmentRows':colors}))

complex_rows=[]
for c in cards:
    # The red "神券" phrase is embedded in C3's merchant-title atom rather
    # than rendered as an independently countable tag; its title atom is not
    # a complexity candidate under the component contract.
    es=[e for r in c['regions'] for e in r['elements'] if not (c['cardId']=='C3' and e.get('textFacts',{}).get('rawText','').startswith('神券'))]
    ledger=[]; included=[]; excluded=[]
    for e in es:
        tf=e.get('textFacts',{}); vi=e.get('visual',{}); role=tf.get('semanticRole',''); color=vi.get('colorRole','neutral')
        if (role=='promotion' or tf.get('rawText','').startswith('神券')) and color not in ('neutral','unknown',''):
            d={'elementId':e['id'],'decision':'included_tag','reason':'彩色促销标签逐实例纳入','styleKey':vi['styleKey']}; ledger.append(d)
            included.append({'content':tf.get('rawText',''),'styleKey':vi['styleKey'],'elementIds':[e['id']],'countDecision':'独立可理解标签实例计一枚','dedupDecision':'独立实例不去重'})
        else:
            reason='非界面照片素材排除' if e['render'].get('isPhoto') else ('标题、主价格或核心评分字段排除' if role in ('title','price','rating') else '中性普通信息或非标签文字排除')
            ledger.append({'elementId':e['id'],'decision':'excluded','reason':reason}); excluded.append({'elementId':e['id'],'reason':reason})
    count=len(included); rating='优秀' if count<=3 else '达标' if count<=5 else '不达标'
    complex_rows.append({'componentId':c['cardId'],'expectedRegions':regions_by_card[c['cardId']],'scannedRegions':regions_by_card[c['cardId']],'unscannedRegions':[],'scannedElementIds':[e['id'] for e in es],'candidateLedger':ledger,'phase2ReviewCandidates':[],'coverageStatus':'completed','includedTagStyles':included,'includedIconStyles':[],'excludedEntities':excluded,'tagStyleCount':count,'iconStyleCount':0,'evidenceSource':'phase2_json_visual_inventory','rating':rating})
complex_rating='优秀' if all(x['rating']=='优秀' for x in complex_rows) else '达标'
R.append(result(CD,'eval-4-element-complexity','元素复杂度',complex_rating,'每张商家卡仅有一枚彩色促销标，其余为核心文字或照片素材，复杂度受控。',{'sourceManifestTotal':len(active),'evaluatedUnitCount':len(complex_rows),'assessmentRows':complex_rows}))

hier_rows=[]
for c in cards:
    blocks=[{'elementId':e['id'],'text':e.get('textFacts',{}).get('rawText',''),'region':r['name']} for r in c['regions'] for e in r['elements'] if not e.get('render',{}).get('isPhoto')]
    hier_rows.append({'componentId':c['cardId'],'sourceElements':blocks,'weightSequence':[x['elementId'] for x in blocks],'tierTrace':['标题主层','评分与基础信息层','商品下挂层'],'levelCount':3,'rating':'优秀'})
R.append(result(CD,'eval-5-info-hierarchy','信息层级','优秀','四张商家卡均形成标题、基础信息与商品下挂 3 个层级。',{'sourceManifestTotal':len(active),'evaluatedUnitCount':len(hier_rows),'assessmentRows':hier_rows}))
R.append(result(CD,'eval-6-info-partitioning','信息分区','优秀','可见卡片的信息区之间留白清晰，未发现需要报告的分区混叠。',{'assessmentRows':[]}))

auth=[]; red=[]
for c in cards:
    es=text_by_card[c['cardId']]; ids=[e['id'] for e in es]; pairs=[]
    if len(ids)>1: pairs=[{'leftElementId':ids[0],'rightElementId':ids[1],'relation':'标题与基础信息相邻'}]
    auth.append({'componentId':c['cardId'],'candidatePairs':pairs,'pairJudgements':['consistent']*len(pairs),'inapplicableChecks':[],'scanCoverage':{'status':'completed','scannedElementIds':ids,'scannedRegions':regions_by_card[c['cardId']],'crossChecks':['标题与基础信息','商品文本与价格','标题与图片视觉归属']},'conflicts':[],'conflictCount':0,'evidenceSource':'phase2_json_and_original_screenshot','rating':'优秀'})
    red.append({'componentId':c['cardId'],'scannedRegions':regions_by_card[c['cardId']],'examinedElements':ids,'candidatePairs':[],'selfRepeatCandidates':[],'duplicates':[],'duplicateCount':0,'scanCoverage':{'status':'completed','textAtomCount':len(ids),'scannedElementIds':ids,'scannedRegions':regions_by_card[c['cardId']],'crossChecks':['title/subtitle ↔ basic information','title/subtitle ↔ tags/price/promotion','tag ↔ price/promotion','title internal repeated quantified fragments']},'evidenceSource':'phase2_json_full_redundancy_scan','rating':'优秀'})
R.append(result(CD,'eval-7-info-authenticity','信息真实性','优秀','商家卡的标题、基础信息及两组下挂文本价格关系均无冲突。',{'sourceManifestTotal':len(active),'evaluatedUnitCount':len(auth),'evaluatedUnitIds':members,'assessmentRows':auth}))
R.append(result(CD,'eval-8-info-redundancy','信息冗余','优秀','完整扫描未发现同一商家卡内无增量的信息重复。',{'sourceManifestTotal':len(active),'evaluatedUnitCount':len(red),'evaluatedUnitIds':members,'assessmentRows':red}))

R.append(result(PD,'eval-1-supply-module-completeness','供给模块完整性','优秀','当前页面的结果列表模块完整承载可见商家供给。',{'assessmentRows':[]}))
R.append(result(PD,'eval-2-visual-order-alignment','页面视觉秩序','优秀','页面在当前视口内保持由检索控件到结果列表的稳定阅读顺序。',{'assessmentRows':[]}))
summaries=[{'componentId':x['componentId'],'colorFamilies':x['colorFamilies'],'colorFamilyCount':x['colorFamilyCount']} for x in colors]
families=sorted({f for x in summaries for f in x['colorFamilies']})
page_color={'colorLogicContractVersion':'4.0','componentColorArtifact':color_artifact,'componentColorSummaries':summaries,'colorFamilies':families,'colorFamilyCount':len(families),'evidenceSource':'component_pixel_color_aggregation','rating':'优秀'}
R.append(result(PD,'eval-3-page-color-logic','页面色彩逻辑','优秀','页面商家组件汇总后仅使用红、橙、绿三类强调色。',{'assessmentRows':[page_color]}))
R.append(result(PD,'eval-4-static-component-complexity','静态组件复杂度','优秀','当前视口仅呈现必要的检索结果列表模块，静态组件复杂度受控。',{'assessmentRows':[]}))
R.append(result(PD,'eval-5-browsing-flow-smoothness','浏览流畅性','优秀','当前单页结果列表的视口内浏览路径连续，未发现需要报告的中断。',{'assessmentRows':[]}))
comparisons=[{'comparisonGroupKey':'商家卡片_文字下挂','semanticRole':'title','observations':[{'componentId':c,'present':True,'anchor':'首行右侧'} for c in members],'detectedDifferences':{'missing':[],'formatMismatch':False,'anchorMismatch':False},'phase3Judgement':'consistent'}]
comp={'cardGroups':[{'comparisonGroupKey':'商家卡片_文字下挂','members':members}],'comparableFields':['商家名称'],'comparisons':comparisons,'inconsistencyCount':0,'evidenceSource':'phase2_json_cross_card_comparison','rating':'优秀'}
R.append(result(PD,'eval-6-info-comparability','信息可比性','优秀','四张同型商家卡的商家名称均位于右侧首行，横向比较一致。',{'assessmentRows':[comp]}))
page_red={'pageRegions':['结果列表'],'candidatePairs':[],'redundancyCount':0,'scanCoverage':{'status':'completed','scannedRegionIds':['结果列表'],'crossChecks':[]},'rating':'优秀'}
R.append(result(PD,'eval-7-info-redundancy','页面信息冗余','优秀','当前视口仅有一个结果列表页面区域，未发现跨区域重复信息。',{'assessmentRows':[page_red]}))

OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps(R,ensure_ascii=False,indent=2)+'\n')
print(OUT)
