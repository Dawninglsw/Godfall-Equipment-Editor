"""Equipment-only snapshot validation and browsing. No game mutation capability."""
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
import json
import math
from pathlib import Path

from equipment_names import equipment_name, chinese_names
from ground_drop_filters import RARITIES, rarity_label, trait_text
from trait_types import trait_label

HERE = Path(__file__).resolve().parent
FAMILIES = {'Weapon': '武器', 'Ring': '戒指', 'Amulet': '护符', 'Charm': '符咒',
            'Augment': '强化物', 'Banner': '旗帜', 'Consumable': '生命石'}
COLLECTIONS = ['weapons', 'rings', 'amulets', 'charms', 'augments', 'banners', 'consumables']
SCOPES = ['当前配装', '当前战甲全部配装', '所有战甲配装', '兵器库全部', '历史记录（未确认）']
SORTS = ['名称', '品质从高到低', '等级从高到低', '强化从高到低', '类型', '原始装备优先', '随机主词条优先']
ITEM_KEYS = {'id', 'gameplayTag', 'lootClassName', 'tierIdentifier', 'rarityIdentifier',
             'masterworkUpgradeRank', 'mutationNames', 'selectedTraitTags', 'traits', 'damageTypes',
             'isFavorite', 'isEquippedInSelectedValorplate', 'equipCount', 'readoutPresetOnly', 'lootAttributes', 'amount', 'objectives'}
HEADER = '{"godfallInventoryReadout":1,"kind":'
MAX_CHARS = 2097152


def valid_text(value, limit=512):
    return isinstance(value, str) and len(value) <= limit


def decode_fragment(text):
    if not text.startswith(HEADER):
        return None
    try:
        obj, end = json.JSONDecoder().raw_decode(text)
        if end > MAX_CHARS or obj.get('godfallInventoryReadout') != 1:
            return None
        if type(obj.get('sequence')) is not int or obj['sequence'] <= 0:
            return None
        if type(obj.get('startedAt')) not in (int, float) or not math.isfinite(obj['startedAt']):
            return None
        if obj.get('kind') == 'page':
            if set(obj) != {'godfallInventoryReadout', 'kind', 'startedAt', 'sequence', 'index', 'items'}:
                return None
            if type(obj['index']) is not int or not 0 <= obj['index'] < 400:
                return None
            if not isinstance(obj['items'], list) or not 1 <= len(obj['items']) <= 32:
                return None
            for item in obj['items']:
                if (not isinstance(item, dict) or set(item) - ITEM_KEYS or not valid_text(item.get('id')) or
                        not item['id'] or not valid_text(item.get('gameplayTag')) or
                        item.get('lootClassName') not in FAMILIES):
                    return None
                if 'traits' in item and (not isinstance(item['traits'], list) or len(item['traits']) > 30 or
                                         not all(isinstance(t, dict) for t in item['traits'])):
                    return None
                if 'lootAttributes' in item:
                    attributes = item['lootAttributes']
                    if (not isinstance(attributes, dict) or set(attributes) - {'attackPower', 'ConsumableHealingPower', 'BannerOvershield'}
                            or any(type(v) not in (int, float) or not math.isfinite(v) for v in attributes.values())):
                        return None
                if 'amount' in item and (type(item['amount']) is not int or not 0 <= item['amount'] <= 1000000):
                    return None
                if 'objectives' in item:
                    objectives = item['objectives']
                    if not isinstance(objectives, list) or len(objectives) > 16:
                        return None
                    for objective in objectives:
                        if (not isinstance(objective, dict) or set(objective) != {
                                'traitName', 'objectiveId', 'progressNumerator', 'progressDenominator'} or
                                not valid_text(objective['traitName']) or not objective['traitName'] or
                                not valid_text(objective['objectiveId']) or not objective['objectiveId']):
                            return None
                        numerator, denominator = objective['progressNumerator'], objective['progressDenominator']
                        if (type(numerator) not in (int, float) or not math.isfinite(numerator) or not 0 <= numerator <= 1e12 or
                                type(denominator) not in (int, float) or not math.isfinite(denominator) or not 0 < denominator <= 1e12):
                            return None
        elif obj.get('kind') == 'manifest':
            if set(obj) != {'godfallInventoryReadout', 'kind', 'startedAt', 'sequence', 'capturedAt',
                            'itemCount', 'pageLengths', 'selectedValorplateId', 'plates', 'collections', 'omitted'}:
                return None
            if (type(obj['capturedAt']) not in (int, float) or not math.isfinite(obj['capturedAt']) or
                    obj['capturedAt'] < obj['startedAt'] or type(obj['omitted']) is not int or obj['omitted'] < 0 or
                    type(obj['itemCount']) is not int or not 0 <= obj['itemCount'] <= 10000 or
                    not valid_text(obj['selectedValorplateId'])):
                return None
            lengths = obj['pageLengths']
            if (not isinstance(lengths, list) or len(lengths) > 400 or
                    any(type(n) is not int or not 0 < n <= MAX_CHARS for n in lengths) or
                    len(lengths) != math.ceil(obj['itemCount'] / 32)):
                return None
            if set(obj['collections']) != set(COLLECTIONS) or any(type(v) is not bool for v in obj['collections'].values()):
                return None
            if not isinstance(obj['plates'], list) or len(obj['plates']) > 64:
                return None
            plate_ids = set()
            for plate in obj['plates']:
                if set(plate) != {'id', 'gameplayTag', 'selectedPresetIndex', 'presets'}:
                    return None
                if (not valid_text(plate['id']) or not plate['id'] or plate['id'] in plate_ids or
                        not valid_text(plate['gameplayTag']) or type(plate['selectedPresetIndex']) is not int or
                        not 0 <= plate['selectedPresetIndex'] <= 2):
                    return None
                plate_ids.add(plate['id'])
                if not isinstance(plate['presets'], list) or len(plate['presets']) > 3:
                    return None
                preset_ids = set()
                for preset in plate['presets']:
                    if set(preset) != {'index', 'bindings'} or type(preset['index']) is not int or not 0 <= preset['index'] <= 2 or preset['index'] in preset_ids:
                        return None
                    preset_ids.add(preset['index'])
                    if not isinstance(preset['bindings'], list) or len(preset['bindings']) > 448:
                        return None
                    for binding in preset['bindings']:
                        if (set(binding) != {'family', 'slot', 'id'} or binding['family'] not in COLLECTIONS or
                                not valid_text(binding['id']) or not valid_text(binding['slot'])):
                            return None
        else:
            return None
        return obj, end
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        return None


def assemble(fragments, born_ms, now_ms):
    """Never fill a missing current page from a different generation or older sequence."""
    valid = [pair for pair in fragments if born_ms <= pair[0]['startedAt'] <= now_ms + 5000]
    manifests = [pair for pair in valid if pair[0]['kind'] == 'manifest' and pair[0]['capturedAt'] <= now_ms + 5000]
    if not manifests:
        raise ValueError('尚未找到本次启动的兵器库清单。请确认已安装读取组件，并重新打开兵器库。')
    manifest, _ = max(manifests, key=lambda pair: (pair[0]['startedAt'], pair[0]['sequence']))
    pages = {}
    for obj, length in valid:
        if obj['kind'] == 'page' and (obj['startedAt'], obj['sequence']) == (manifest['startedAt'], manifest['sequence']):
            index = obj['index']
            if index < len(manifest['pageLengths']) and length == manifest['pageLengths'][index]:
                if index in pages and pages[index] != obj['items']:
                    raise ValueError('清单同一页出现不同版本，请重新读取。')
                pages[index] = obj['items']
    if len(pages) != len(manifest['pageLengths']):
        raise ValueError('本次清单尚未完整读出，请保持兵器库打开后重试；不会混入旧记录。')
    items = [item for index in sorted(pages) for item in pages[index]]
    if len(items) != manifest['itemCount'] or len({i['id'] for i in items}) != len(items):
        raise ValueError('清单数量或装备编号核对失败，请重试。')
    return {'manifest': manifest, 'items': items}


def load_snapshot(path=None):
    try:
        result = json.loads((path or HERE/'inventory_snapshot.json').read_bytes())
        manifest = result['manifest']
        fragments = [decode_fragment(json.dumps(manifest, separators=(',', ':'), ensure_ascii=True))]
        for index in range(len(manifest['pageLengths'])):
            obj = {'godfallInventoryReadout': 1, 'kind': 'page', 'startedAt': manifest['startedAt'],
                   'sequence': manifest['sequence'], 'index': index, 'items': result['items'][index*32:(index+1)*32]}
            text = json.dumps(obj, separators=(',', ':'), ensure_ascii=False)
            decoded = decode_fragment(text)
            # JS length counts UTF-16 code units.
            # The persisted file has been re-encoded by Python; number formatting
            # can differ from JavaScript. Exact source lengths are checked during RAM reading.
            fragments.append((decoded[0], manifest['pageLengths'][index]) if decoded else None)
        if not all(fragments):
            return None
        checked = assemble(fragments, 0, datetime.now(timezone.utc).timestamp()*1000)
        return {**result, **checked, 'live_process': same_process(result)}
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None


def same_process(snapshot):
    """A prior launch's disk snapshot must never be presented as a fresh current loadout."""
    try:
        import ctypes as c
        from ctypes import wintypes as w
        k = c.WinDLL('kernel32', use_last_error=True)
        k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]; k.OpenProcess.restype = w.HANDLE
        k.CloseHandle.argtypes = [w.HANDLE]
        k.GetProcessTimes.argtypes = [w.HANDLE] + [c.POINTER(c.c_uint64)]*4
        k.GetExitCodeProcess.argtypes = [w.HANDLE, c.POINTER(w.DWORD)]
        handle = k.OpenProcess(0x1000, False, snapshot['pid'])
        if not handle: return False
        try:
            times, status = [c.c_uint64() for _ in range(4)], w.DWORD()
            return (bool(k.GetProcessTimes(handle, *[c.byref(t) for t in times])) and
                    str(times[0].value) == snapshot['process_creation_id'] and
                    bool(k.GetExitCodeProcess(handle, c.byref(status))) and status.value == 259)
        finally:
            k.CloseHandle(handle)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def rows_from_snapshot(snapshot):
    if not snapshot:
        return []
    manifest, rows = snapshot['manifest'], []
    bindings = {}
    for plate in manifest['plates']:
        for preset in plate['presets']:
            for binding in preset['bindings']:
                bindings.setdefault(binding['id'], []).append({'plate': plate['id'], 'tag': plate['gameplayTag'],
                    'preset': preset['index'], 'slot': binding['slot'],
                    'currentPlate': plate['id'] == manifest['selectedValorplateId'],
                    'current': plate['id'] == manifest['selectedValorplateId'] and preset['index'] == plate['selectedPresetIndex']})
    for item in snapshot['items']:
        rows.append(make_row(item, bindings.get(item['id'], []), 'snapshot'))
    return rows


def make_row(item, bindings=None, origin='history', label=None):
    from random_primary_catalogue import item_has_random_primary
    from owned_augment_model import availability
    from replacement_service import is_awakened_ring
    tag = item.get('gameplayTag', '')
    traits = item.get('traits') or []
    from equipment_names import trait_labels_for
    zh,en=trait_labels_for('zh-CN'),trait_labels_for('en')
    searchable = trait_text(' '.join(' '.join([trait_label(t),str(t.get('traitName','')),
        zh.get(t.get('traitName'),{}).get('label',''),en.get(t.get('traitName'),{}).get('label','')]) for t in traits))
    name = label or equipment_name(item)
    augment = availability(item)
    mutations = item.get('mutationNames') or []
    cursed = 'Mutation.Item.Cursed' in mutations
    awakened = 'Mutation.Item.Awakened' in mutations and not cursed
    objective_linked = cursed or awakened or bool(item.get('objectives')) or any(t.get('slotType') == 'Trait.Objective' for t in traits)
    copy_only = is_awakened_ring(item)
    return {'item': deepcopy(item), 'label': name, 'bindings': bindings or [], 'origin': origin,
            'family': FAMILIES.get(item.get('lootClassName'), '未知'), 'rarity': rarity_label(item),
            'primal': any('Primal' in x for x in item.get('mutationNames') or []),
            'cursed': cursed, 'awakened': awakened, 'random_primary': item_has_random_primary(item),
            'search': ' '.join([name, tag, item.get('id', ''), chinese_names().get(tag, {}).get('name', ''), chinese_names().get(tag, {}).get('english', ''), searchable]).casefold(),
            'traitSearch': searchable, 'color': augment_colors().get(tag, ''),
            'copy_only': copy_only,
            'editable': True if copy_only else False if objective_linked else augment['editable'] if augment else item.get('lootClassName') in {'Weapon', 'Ring', 'Amulet', 'Charm', 'Banner', 'Consumable'} and bool(traits),
            'edit_reason': '已解咒戒指可制作副词条同款替代品；本轮不加入本地覆盖草稿。' if copy_only else '诅咒目标和解除后的变体关联尚在研究，当前只读。' if objective_linked else augment['reason'] if augment else ''}


@lru_cache(maxsize=1)
def augment_colors():
    from editor_model import source_data
    return {r['gameplayTag']: {1: '红色', 2: '绿色', 3: '蓝色'}.get(r.get('affinityIdentifier'), '')
            for r in source_data()['augments']['collection']}


def filter_rows(rows, *, scope='兵器库全部', query='', family='全部类型', rarity='全部品质', random_primary='不限主词条',
                primal='全部形态', favorite=False, trait_query='', sort='名称', subtype='全部武器',
                equipped='全部装备', minimum_level=0, maximum_level=999, color='全部颜色', plate_id=''):
    if family not in {'全部类型','武器'}:subtype='全部武器'
    if family not in {'全部类型','强化物'}:color='全部颜色'
    found = []
    for row in rows:
        item, bindings = row['item'], row['bindings']
        if scope == '历史记录（未确认）':
            if row['origin'] != 'history': continue
        elif row['origin'] != 'snapshot': continue
        elif scope == '当前配装' and not any(b['current'] for b in bindings): continue
        elif scope == '当前战甲全部配装' and not any(b['currentPlate'] for b in bindings): continue
        elif scope == '所有战甲配装' and not bindings: continue
        elif scope == '兵器库全部' and item.get('readoutPresetOnly'): continue
        if plate_id and not any(b['plate'] == plate_id for b in bindings): continue
        if family != '全部类型' and row['family'] != family: continue
        if rarity != '全部品质' and row['rarity'] != rarity: continue
        if random_primary == '有随机主词条' and row.get('random_primary') is not True: continue
        if random_primary == '无随机主词条' and row.get('random_primary') is not False: continue
        if primal == '仅原始装备' and not row['primal']: continue
        if primal == '非原始装备' and row['primal']: continue
        if primal == '仅诅咒装备' and not row.get('cursed'): continue
        if primal == '已解除诅咒' and not row.get('awakened'): continue
        if favorite and item.get('isFavorite') is not True: continue
        if equipped == '已保存到配装' and not bindings: continue
        if equipped == '未保存到配装' and bindings: continue
        if not all(word in row['search'] for word in trait_text(query).split()): continue
        if not all(word in row['traitSearch'] for word in trait_text(trait_query).split()): continue
        tier = item.get('tierIdentifier')
        if type(tier) not in (float, int) or not minimum_level <= tier <= maximum_level: continue
        tag = item.get('gameplayTag', '')
        weapon_types = {'长剑': 'Weapon.Sword.1H.', '双剑': 'Weapon.DualBlades.', '巨剑': 'Weapon.Sword.2H.',
                        '长柄武器': 'Weapon.Polearm.', '战锤': 'Weapon.Hammer.2H.'}
        if subtype != '全部武器' and not tag.startswith(weapon_types.get(subtype, '\x00')): continue
        if color != '全部颜色' and row.get('color') != color: continue
        found.append(row)
    def number(row, key):
        value = row['item'].get(key, 0)
        return value if type(value) in (int, float) and math.isfinite(value) else 0
    def key(row):
        base = (row['label'].casefold(), row['item']['id'])
        if sort == '品质从高到低': return (-number(row, 'rarityIdentifier'), *base)
        if sort == '等级从高到低': return (-number(row, 'tierIdentifier'), *base)
        if sort == '强化从高到低': return (-number(row, 'masterworkUpgradeRank'), *base)
        if sort == '类型': return (row['family'], *base)
        if sort == '原始装备优先': return (not row['primal'], *base)
        if sort == '随机主词条优先': return (0 if row.get('random_primary') is True else 1 if row.get('random_primary') is False else 2, *base)
        return base
    return sorted(found, key=key)


def load_rows(snapshot=None):
    from trait_types import source_items
    rows = rows_from_snapshot(snapshot)
    rows.extend(make_row(r['item'], origin='history', label=r['label']) for r in source_items())
    return rows
