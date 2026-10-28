"""Read-only native primary libraries; randomness is separate from edit support."""
from collections import defaultdict
from functools import lru_cache
from itertools import product

from editor_model import source_data

FILTERS = ['不限主词条', '有随机主词条', '无随机主词条']
TABLES = ['weapons', 'trinkets', 'augments', 'banners', 'potions']


def eligible(row, tier, rarity):
    return (row.get('minTier', 1) <= tier <= row.get('maxTier', 100)
            and row.get('minRarity', 1) <= rarity <= row.get('maxRarity', 5))


@lru_cache(maxsize=1)
def native_index():
    data = source_data()
    templates = {r['gameplayTag']: r for key in TABLES for r in data[key]['collection']}
    slots, categories, traits, tags = (defaultdict(list) for _ in range(4))
    for r in data['traitSlot']['collection']:
        if r['slotType'] == 'Primary Trait': slots[r['groupName']].append(r)
    for r in data['traitCategory']['collection']:
        if r.get('weight', 0) > 0: categories[r['groupName']].append(r)
    for r in data['trait']['collection']:
        if r.get('weight', 0) > 0: traits[r['groupName']].append(r)
    for r in data['traitTags']['collection']:
        if r.get('weight', 0) > 0: tags[r['groupName']].append(r)
    return templates, slots, categories, traits, tags


@lru_cache(maxsize=4096)
def native_pool(group, tier, rarity, selected_tags):
    _, _, categories, traits, _ = native_index()
    selected = set(selected_tags)
    return frozenset(t['traitName'] for c in categories.get(group, [])
                     if eligible(c, tier, rarity) and selected.intersection(c.get('allowedTraitTags', []))
                     for t in traits.get(c['traitGroup'], []) if eligible(t, tier, rarity))


def primary_slots(template, rarity):
    _, slots, _, _, _ = native_index()
    return [s for s in slots.get(template['traitSlotGroups'], [])
            if s['minRarity'] <= rarity <= s['maxRarity'] and s.get('traitChance', 0) > 0]


def item_has_random_primary(item):
    """None means incomplete/unknown, not fixed. No process reads or Node calls."""
    if not isinstance(item.get('traits'), list): return None
    if not any(t.get('slotType') == 'Primary Trait' for t in item['traits']): return False
    template = native_index()[0].get(item.get('gameplayTag'))
    tier, rarity, tags = item.get('tierIdentifier'), item.get('rarityIdentifier'), item.get('selectedTraitTags')
    if (not template or type(tier) is not int or type(rarity) is not int or not isinstance(tags, list)
            or not all(isinstance(t, str) for t in tags)): return None
    return any(len(native_pool(s['traitCategoryGroups'], tier, rarity, tuple(sorted(set(tags))))) > 1
               for s in primary_slots(template, rarity))


def tag_contexts(template, tier, rarity):
    tags = native_index()[4]
    groups = (list(template['defaultTraitTagGroups']) + list(template.get('elementTraitTagGroups', []))
              if template.get('defaultTraitTagGroups') else template.get('traitTagGroups', []))
    options = [list({tuple(sorted(r['addedTraitTags'])) for r in tags.get(group, [])
                     if eligible(r, tier, rarity)}) for group in groups]
    if not options or any(not x for x in options): return []
    return {tuple(sorted({tag for row in choice for tag in row})) for choice in product(*options)}


def list_random_templates():
    """Every equipment template, across native level/rarity boundaries, not inventory."""
    data = source_data()
    levels = {1, 50, 100}
    for key in ['traitTags', 'traitCategory', 'trait']:
        for row in data[key]['collection']:
            levels.update(n for n in [row.get('minTier', 1), row.get('maxTier', 100) + 1] if 1 <= n <= 100)
    rarity_names = {'Common': 1, 'Uncommon': 2, 'Rare': 3, 'Epic': 4, 'Legendary': 5}
    result = []
    for tag, template in native_index()[0].items():
        native_rarity = template.get('rarityIdentifier')
        rarity = rarity_names.get(native_rarity, native_rarity)
        rarities = [rarity] if type(rarity) is int else range(1, 6)
        examples = []
        for rarity in rarities:
            slots = primary_slots(template, rarity)
            if not slots: continue
            for tier in sorted(levels):
                contexts = tag_contexts(template, tier, rarity)
                matching = [s for s in slots if any(len(native_pool(s['traitCategoryGroups'], tier, rarity, tags)) > 1
                                                  for tags in contexts)]
                if matching:
                    examples.append({'rarity': rarity, 'example_level': tier, 'random_slots': len(matching),
                                     'total_primary_slots': len(slots)})
                    break
        if examples:
            result.append({'gameplayTag': tag, 'family': tag.split('.')[0], 'english_name': template.get('name', tag).strip('"'),
                           'examples': examples})
    return sorted(result, key=lambda row: (row['family'], row['gameplayTag']))
