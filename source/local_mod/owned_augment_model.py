"""Display policy for existing augments; original JS planner authorizes all edits."""
from functools import lru_cache


@lru_cache(maxsize=1)
def definitions():
    from editor_model import source_data
    return {r['gameplayTag']: r for r in source_data()['augments']['collection']}


def availability(item):
    if item.get('lootClassName') != 'Augment':
        return None
    definition = definitions().get(item.get('gameplayTag'))
    if not definition:
        return {'editable': False, 'reason': '该强化物模板尚未识别'}
    mutations = item.get('mutationNames') or []
    if ('Cursed' in definition.get('traitSlotGroups', '') or item.get('objectives') or
            any(t.get('slotType') == 'Trait.Objective' for t in item.get('traits', [])) or
            any('Cursed' in m or 'Awakened' in m for m in mutations)):
        return {'editable': False, 'reason': '诅咒、觉醒或关联目标的强化物尚未适配，先保留原词条'}
    if any(m != 'Mutation.Item.Primal' for m in mutations):
        return {'editable': False, 'reason': '该强化物包含尚未适配的变体'}
    editable = any(t.get('slotType') in {'Secondary Trait', 'Masterwork Trait'} and not t.get('conditionalLootEffects')
                   for t in item.get('traits', []))
    return {'editable': editable, 'reason': '可编辑副词条与精通词条；保留颜色、耗能和主词条' if editable else '这颗强化物没有本轮可编辑的副词条'}
