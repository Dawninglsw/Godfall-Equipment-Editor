"""Read-only, full before/after presentation from each hashed plan preview."""
from collections import Counter
from functools import lru_cache
import re

from editor_model import source_data
from equipment_names import chinese_trait_labels
from ground_drop_filters import rarity_label
from inventory_snapshot import FAMILIES, augment_colors
from trait_types import trait_label, trait_value_text

SLOTS = {'Primary Trait':'主词条','Primary Attribute':'主属性','Secondary Trait':'副词条',
         'Masterwork Trait':'精通词条','Trait.Objective':'诅咒目标'}
DAMAGE = {'Damage.Primary.Physical':'物理','Damage.Primary.Elemental.Air':'气系',
          'Damage.Primary.Elemental.Cold':'冰系','Damage.Primary.Elemental.Fire':'火系',
          'Damage.Primary.Elemental.Shadow':'虚空','Damage.Primary.Elemental.Earth':'土系'}
PLACEHOLDER = re.compile(r'%\(([^)]+)\)(?:\.\d+)?[dfs]')


@lru_cache(maxsize=1)
def effect_specs():
    return {r['lootEffectName']:r for r in source_data()['lootEffects']['collection']}


def trait_description(trait):
    """Resolve original Chinese placeholders without losing secondary parameters."""
    description = chinese_trait_labels().get(trait.get('traitName'),{}).get('description','')
    values = {}; by_parameter = {}
    for effect in trait.get('lootEffects',[]):
        name = effect.get('lootEffectName','')
        specs = {p['magnitudeName']:p for p in effect_specs().get(name,{}).get('params',[])}
        for param in effect.get('params',[]):
            key = param.get('magnitudeName','').removeprefix('Magnitude.')
            magnitude = param.get('magnitude')
            if not isinstance(magnitude,(int,float)):continue
            percent = specs.get(param.get('magnitudeName'),{}).get('displayMappingType')=='percent'
            text = f'{magnitude*(100 if percent else 1):g}'
            values[name+'.'+key] = text
            by_parameter.setdefault(key,set()).add(text)
    if description:
        unresolved = []
        def replace(match):
            key = match[1]
            if key in values:return values[key]
            options = by_parameter.get(key.split('.',1)[-1],set())
            if len(options)==1:return next(iter(options))
            unresolved.append(key);return '…'
        text = PLACEHOLDER.sub(replace,description).replace('%%','%').replace('+-','−')
        if not unresolved and '%(' not in text:return text
    label = trait_label(trait); value = trait_value_text(trait)
    return label+(' '+value if value else '')


def details_from_preview(entry, preview):
    source = preview['source_materialized']; target = preview['expected_materialized']
    flags = source.get('mutationNames',[])
    form = '原始' if flags==['Mutation.Item.Primal'] else '已解除诅咒' if flags==['Mutation.Item.Awakened'] else '普通'
    summary = [f'{entry["label"]} · {FAMILIES.get(source["lootClassName"],"装备")} · {rarity_label(source)} · {form}',
               f'等级 {source["tierIdentifier"]} · 强化 {source.get("masterworkUpgradeRank") or 0}']
    attributes = source.get('lootAttributes',{})
    extras = []
    for key,label in [('attackPower','攻击力'),('BannerOvershield','护盾量'),('ConsumableHealingPower','回复量')]:
        if key in attributes:extras.append(f'{label} {attributes[key]:g}')
    damage = source.get('damageTypes') or {}
    if damage:extras.append('伤害类型：'+'、'.join(DAMAGE.get(k,'未识别类型') for k in damage))
    if source['lootClassName']=='Consumable':extras.append(f'充能 {source.get("amount",1)} 次')
    if source['lootClassName']=='Augment':
        color = augment_colors().get(source['gameplayTag'])
        if color:extras.append(color)
    primary = [trait_description(t) for t in source['traits'] if t['slotType']=='Primary Attribute']
    if primary:extras.extend(primary)
    if extras:summary.append(' · '.join(extras))
    rows=[];counts=Counter()
    for old,new in zip(source['traits'],target['traits']):
        slot=old['slotType'];counts[slot]+=1
        title=SLOTS.get(slot,'属性词条')+str(counts[slot])
        if old.get('masterworkBonusTier'):title+='（已强化）'
        rows.append({'title':title,'before':trait_description(old),'after':trait_description(new),
                     'changed':old!=new})
    return {'summary':'\n'.join(summary),'rows':rows,'source_id':entry['source_id'],'trial_id':entry['trial_id']}
