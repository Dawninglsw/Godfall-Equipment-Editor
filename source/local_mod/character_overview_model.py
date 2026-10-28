"""Read-only preset projection; missing records never fall back to another preset."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from functools import lru_cache

from editor_model import source_data
from equipment_names import equipment_name
from ground_drop_filters import rarity_label
from replacement_batch_details import DAMAGE,trait_description,SLOTS

EQUIPMENT=[('weapons','0','武器 1'),('weapons','1','武器 2'),
           ('consumables','0','生命石'),('banners','0','旗帜'),
           ('rings','0','戒指 1'),('rings','1','戒指 2'),
           ('amulets','0','护符'),('charms','0','符咒')]
RARITY_COLORS={1:'#9BA6B7',2:'#86BF94',3:'#83AFE9',4:'#C19BE8',5:'#DCB66D'}
AFFINITIES={0:('通用','#A6B0C0'),1:('红色','#D88C8C'),2:('绿色','#8BBE94'),3:('蓝色','#8EAFE0')}


@lru_cache(maxsize=12)
def nodes_for(tag):
    return sorted([r for r in source_data()['augmentGraphs']['collection'] if r['valorplateGameplayTag']==tag],key=lambda r:r['nodeId'])


def preset_view(snapshot,plate_id,preset_index):
    if not snapshot:return {'plate':None,'preset_known':False,'equipment':[],'augments':[]}
    plate=next((p for p in snapshot['manifest']['plates'] if p['id']==plate_id),None)
    if not plate:return {'plate':None,'preset_known':False,'equipment':[],'augments':[]}
    preset=next((p for p in plate['presets'] if p['index']==preset_index),None)
    available=isinstance(preset,dict) and isinstance(preset.get('bindings'),list)
    grouped={}
    for binding in preset['bindings'] if available else []:
        grouped.setdefault((binding['family'],binding['slot']),[]).append(binding['id'])
    inventory={i['id']:i for i in snapshot['items']}
    def slot(family,index,label,node=None):
        references=grouped.get((family,index),[]);item=None
        if not available:state='preset_unread'
        elif len(references)>1:state='conflict'
        elif not references:state='empty'
        elif references[0] not in inventory:state='item_unread'
        else:
            candidate=inventory[references[0]]
            expected={'weapons':'Weapon','rings':'Ring','amulets':'Amulet','charms':'Charm','augments':'Augment','banners':'Banner','consumables':'Consumable'}
            if candidate.get('lootClassName')!=expected[family]:state='conflict'
            else:state='equipped';item=deepcopy(candidate)
        return {'key':family+':'+index,'family':family,'slot':index,'label':label,'state':state,
                'item':item,'reference_id':references[0] if len(references)==1 else None,'node':node}
    equipment=[slot(family,index,label) for family,index,label in EQUIPMENT]
    definitions={str(row['nodeId']):row for row in nodes_for(plate['gameplayTag'])}
    for family,index in grouped:
        if family=='augments' and index not in definitions:definitions[index]=None
    augments=[slot('augments',index,'节点 '+index,definitions[index]) for index in sorted(definitions,key=lambda x:(not x.isdecimal(),int(x) if x.isdecimal() else x))]
    return {'plate':deepcopy(plate),'preset_known':available,'equipment':equipment,'augments':augments,
            'recorded_active':plate_id==snapshot['manifest']['selectedValorplateId'] and preset_index==plate['selectedPresetIndex']}


def snapshot_caption(snapshot):
    if not snapshot:return '尚未读取角色配装；请点击“刷新角色配装”。'
    stamp=datetime.fromtimestamp(snapshot['manifest']['capturedAt']/1000,timezone(timedelta(hours=8))).strftime('%m-%d %H:%M')
    context='本次游戏读取' if snapshot.get('live_process') else '上次游戏记录'
    complete=not snapshot['manifest']['omitted'] and all(snapshot['manifest']['collections'].values())
    return f'{context} · {stamp} · {len(snapshot["manifest"]["plates"])} 套战甲'+(' · 清单有缺项' if not complete else '')


def item_details(item):
    flags=item.get('mutationNames') or []
    form=[]
    if 'Mutation.Item.Primal' in flags:form.append('原始')
    if 'Mutation.Item.Cursed' in flags:form.append('诅咒')
    elif 'Mutation.Item.Awakened' in flags:form.append('已解咒')
    meta=' · '.join([rarity_label(item),*form,f'等级 {item.get("tierIdentifier","未读取")}',f'强化 {item.get("masterworkUpgradeRank") or 0}'])
    attributes=item.get('lootAttributes') or {};stat=''
    if 'attackPower' in attributes:
        element='、'.join(DAMAGE.get(tag,'未知') for tag in item.get('damageTypes') or {})
        stat=f'攻击力 {attributes["attackPower"]:g}'+(' · '+element if element else '')
    elif 'BannerOvershield' in attributes:stat=f'护盾量 {attributes["BannerOvershield"]:g}'
    elif 'ConsumableHealingPower' in attributes:stat=f'回复量 {attributes["ConsumableHealingPower"]:g}'
    else:
        stat=' · '.join(trait_description(t) for t in item.get('traits',[]) if t.get('slotType')=='Primary Attribute')
    groups=[]
    for slot in ['Primary Trait','Secondary Trait','Masterwork Trait','Trait.Objective']:
        selected=[t for t in item.get('traits',[]) if t.get('slotType')==slot]
        if selected:groups.append((SLOTS[slot],[trait_description(t) for t in selected]))
    for objective in item.get('objectives',[]):
        groups.append(('解咒进度',[f'{objective["progressNumerator"]:g} / {objective["progressDenominator"]:g}']))
    return {'name':equipment_name(item),'meta':meta,'stat':stat,'groups':groups,
            'color':RARITY_COLORS.get(item.get('rarityIdentifier'),'#A6B0C0')}
