"""Display-only filters over an existing scan; never reads or writes game memory."""
from equipment_names import chinese_names
from trait_types import trait_label

RARITIES = {1: '普通', 2: '罕见', 3: '稀有', 4: '史诗', 5: '传奇'}


def trait_text(value):
    return value.casefold().replace('暴击几率', '暴击率').replace('暴击概率', '暴击率')


def rarity_label(item):
    rarity = item.get('rarityIdentifier')
    return RARITIES.get(rarity, f'未知({rarity})' if rarity is not None else '未知')


def search_index(rows):
    """Cache labels once per scan. Keep original row indices and source records intact."""
    result = []
    for index, row in enumerate(rows):
        item = row['record']['item']
        tag = item.get('gameplayTag', '')
        name = ' '.join([row['name'], chinese_names().get(tag, {}).get('english', ''), tag, item.get('id', '')])
        def text(trait):
            return trait_text(trait_label(trait) + ' ' + trait.get('traitName', ''))
        result.append({'index': index, 'name': name.casefold(), 'family': row.get('family_label', ''),
                       'rarity': rarity_label(item), 'editable': row.get('editable', False),
                       'color': (row.get('augment_profile') or {}).get('color', ''),
                       'existing': [text(s['trait']) for s in row.get('slots', [])],
                       'targets': [text(c['trait']) for s in row.get('slots', [])
                                   for c in s['candidates'] if c.get('available', True)]})
    return result


def matching_indices(index, *, query='', family='全部类型', rarity='全部品质', editable_only=False,
                     trait_mode='不限词条', trait_query='', color='全部颜色'):
    names, traits = query.casefold().split(), trait_text(trait_query).split()
    return [entry['index'] for entry in index
            if all(word in entry['name'] for word in names)
            and (family == '全部类型' or entry['family'] == family)
            and (rarity == '全部品质' or entry['rarity'] == rarity)
            and (not editable_only or entry['editable'])
            and (color == '全部颜色' or entry['color'] == color)
            and (trait_mode == '不限词条' or not traits or
                 any(all(word in text for word in traits)
                     for text in entry['targets' if trait_mode == '可替换为' else 'existing']))]
