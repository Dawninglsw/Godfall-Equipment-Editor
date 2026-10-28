"""Equipment catalogue and configuration validation; no game-process access."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from equipment_names import equipment_name

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA_PATH = ROOT/'analysis/extracted/source_data.json'

# Passive effects use Magnitude.X. The named DivineIntervention duration is a
# separate experimental path; cooldown/type parameters remain read-only.
EFFECT_LABELS = {
    'AilmentDuration': '减益状态持续时间', 'AilmentPower': '异常状态强度', 'WeaponArtDamagePercent': '武器技艺伤害',
    'PhysicalDamagePercent': '物理伤害', 'CritChance': '暴击率', 'CritDamage': '暴击伤害',
    'WeakpointDamage': '弱点伤害', 'WeaponArtChargeSpeed': '武器技艺充能速度',
    'MightFlat': '威力', 'SpiritFlat': '灵气', 'VitalityFlat': '活力',
    'MightPercent': '威力加成', 'SpiritPercent': '灵气加成', 'VitalityPercent': '活力加成',
    'FireDamagePercent': '火焰伤害', 'WaterDamagePercent': '寒冰伤害',
    'AirDamagePercent': '雷电伤害', 'EarthDamagePercent': '毒素伤害', 'VoidDamagePercent': '虚空伤害',
    'AllDamagePercent': '全部伤害', 'WeaponDamage': '武器伤害',
    'LongswordDamagePercent': '长剑伤害', 'PolearmDamagePercent': '长柄武器伤害',
    'GreatswordDamagePercent': '巨剑伤害', 'WarhammerDamagePercent': '战锤伤害',
    'DualBladesDamagePercent': '双剑伤害', 'ShieldDamagePercent': '盾牌伤害',
    'BreachDamage': '破防伤害', 'BreachDuration': '破防持续时间',
    'HeavyDamage': '重击伤害', 'TimingAttackDamagePercent': '时机攻击伤害',
    'ComboCounterChargeSpeed': '连击充能速度', 'ComboCounterDamagePercent': '连击伤害',
    'ComboCounterExpiryDelay': '连击保持时间', 'SoulshatterBuildupPercent': '灵魂破碎积累',
    'PolarityDamagePercent': '极性攻击伤害', 'PolarityChargeSpeed': '极性充能速度',
    'ArchonDuration': '执政官狂怒持续时间', 'ArchonDamagePercent': '执政官狂怒伤害',
    'TakedownDamagePercent': '处决伤害', 'BannerOvershieldPercent': '旗帜超量护盾',
    'BannerDuration': '旗帜持续时间', 'DamageReduction': '伤害减免',
    'DivineIntervention': '保命效果'
}
SPECIAL_PARAMETER_LABELS = {
    ('DivineIntervention', 'Magnitude.Duration'): '保命无敌持续时间',
    ('DivineIntervention', 'Magnitude.Seconds.A'): '保命效果冷却（秒）'
}
SLOT_LABELS = {'Primary Trait': '主词条', 'Primary Attribute': '主属性',
               'Secondary Trait': '副词条', 'Masterwork Trait': '大师强化词条'}
FAMILIES = {'Weapon': '武器', 'Ring': '戒指', 'Amulet': '护符', 'Charm': '饰物',
            'Augment': '增幅物', 'EnergyShield': '盾牌'}
_data = None


def source_data():
    global _data
    if _data is None:
        _data = json.loads(DATA_PATH.read_bytes())
    return _data


def effect_metadata(name, magnitude_name='Magnitude.X'):
    if name not in EFFECT_LABELS:
        raise ValueError('该效果尚未开放编辑：' + str(name))
    effect = next((e for e in source_data()['lootEffects']['collection'] if e['lootEffectName'] == name), None)
    params = effect.get('params', []) if effect else []
    if name == 'DivineIntervention':
        if magnitude_name == 'Magnitude.Seconds.A':
            raise ValueError('冷却说明文字固定为10分钟，目前只读取此参数，不开放修改')
        if magnitude_name != 'Magnitude.Duration' or {p.get('magnitudeName') for p in params} != {'Magnitude.Duration', 'Magnitude.Seconds.A'}:
            raise ValueError('保命效果目前只开放无敌持续时间参数')
        return {'unit': '秒', 'multiplier': 1, 'decimals': 1, 'minimum': .1, 'maximum': 60,
                'label': SPECIAL_PARAMETER_LABELS[(name, magnitude_name)], 'experimental': True}
    if magnitude_name != 'Magnitude.X':
        raise ValueError('该效果不开放此参数，效果类型等参数保持原样')
    xs = [p for p in params if p.get('magnitudeName') == 'Magnitude.X']
    other = {p.get('magnitudeName') for p in params if p.get('magnitudeName') != 'Magnitude.X'}
    allowed_other = {'Magnitude.AilmentType'} if name in {'AilmentDuration', 'AilmentPower'} else set()
    if len(xs) != 1 or not other.issubset(allowed_other):
        raise ValueError('该效果的参数结构尚未支持')
    param = xs[0]
    percent = param.get('displayMappingType') == 'percent'
    return {'unit': '%' if percent else '数值', 'multiplier': 100 if percent else 1,
            'decimals': param.get('magnitudeRoundedDecimals', 0),
            'minimum': 0, 'maximum': 1 if name == 'CritChance' else 10 if percent else 1000000,
            'label': EFFECT_LABELS[name]}


def rule_key(rule):
    return tuple(rule.get(k) for k in ('id', 'traitName', 'lootEffectName', 'magnitudeName'))


def finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_config(config):
    if not isinstance(config, dict) or type(config.get('version')) is not int or config['version'] != 1:
        raise ValueError('配置格式或版本不正确')
    if type(config.get('enabled')) is not bool:
        raise ValueError('配置的启用状态不正确')
    if 'primalDrop' in config:
        from primal_drop_settings import validate_primal
        validate_primal(config['primalDrop'])
    rules = config.get('items')
    if not isinstance(rules, list) or len(rules) > 200:
        raise ValueError('配置最多包含200条设置')
    seen = set()
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError('词条设置格式不正确')
        for field in ('id', 'gameplayTag', 'traitName', 'lootEffectName', 'magnitudeName'):
            if not isinstance(rule.get(field), str) or not 1 <= len(rule[field]) <= 300:
                raise ValueError('词条设置缺少有效的装备或效果名称')
        tag, identity = rule['gameplayTag'], rule['id']
        family = tag.split('.')[0]
        if family not in FAMILIES or not re.fullmatch(r'[A-Z]{2,5}-' + re.escape(tag) + r'\.[A-Za-z0-9_-]{10,100}', identity):
            raise ValueError('装备编号与装备类型不匹配')
        if family == 'Weapon' and not identity.startswith('WPN-'):
            raise ValueError('武器编号不正确')
        if family == 'Ring' and not identity.startswith('RNG-'):
            raise ValueError('戒指编号不正确')
        if family != 'Weapon' and rule.get('aggregation') != 'valorplate':
            raise ValueError('该装备需要按当前配装匹配合并效果')
        meta = effect_metadata(rule['lootEffectName'], rule['magnitudeName'])
        trait = next((t for t in source_data()['trait']['collection'] if t.get('traitName') == rule['traitName']), None)
        named = trait.get('namedLootEffects', []) if trait else []
        triggered = rule['traitName'].startswith('Trigger.') and not rule['traitName'].startswith('Trigger.NoModularTrigger.')
        if (trait is None or triggered or trait.get('conditionalLootEffects') or trait.get('ongoingTagRequirements') or len(named) != 1 or
                named[0].get('name') != rule['lootEffectName']):
            raise ValueError('该词条属于尚未开放的复杂效果')
        for field in ('baseline', 'value'):
            value = rule.get(field)
            if not finite_number(value) or not meta['minimum'] <= value <= meta['maximum']:
                raise ValueError('词条数值无效或超出当前编辑范围')
        for field in ('label', 'traitLabel'):
            if field in rule and (not isinstance(rule[field], str) or not 1 <= len(rule[field]) <= 200):
                raise ValueError('装备或词条的显示名称不正确')
        key = rule_key(rule)
        if key in seen:
            raise ValueError('同一件装备的同一词条有重复设置')
        seen.add(key)
    if 'traitReplacements' in config or 'traitTypeRules' in config:
        from trait_types import validate_requests
        validate_requests(config)
    return config


def display_number(value, effect_name, magnitude_name='Magnitude.X'):
    meta = effect_metadata(effect_name, magnitude_name)
    return f'{value * meta["multiplier"]:.8f}'.rstrip('0').rstrip('.')


def parse_display_value(text, effect_name, magnitude_name='Magnitude.X'):
    meta = effect_metadata(effect_name, magnitude_name)
    entry = str(text).strip()
    if entry.endswith('%') and meta['unit'] != '%':
        raise ValueError('该词条使用' + meta['unit'] + '，请输入对应数值')
    if meta['unit'] == '秒':
        entry = entry.removesuffix('秒').strip()
    try:
        value = float(entry.removesuffix('%').strip()) / meta['multiplier']
    except (ValueError, TypeError, OverflowError):
        raise ValueError('请输入有效数字') from None
    if not finite_number(value) or not meta['minimum'] <= value <= meta['maximum']:
        lower = display_number(meta['minimum'], effect_name, magnitude_name)
        upper = display_number(meta['maximum'], effect_name, magnitude_name)
        suffix = meta['unit'] if meta['unit'] in {'%', '秒'} else ''
        raise ValueError(f'请输入{lower}至{upper}{suffix}之间的数值')
    return value


def encode_config(config):
    validate_config(config)
    return json.dumps(config, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')


def load_config(path):
    data = Path(path).read_bytes()
    if len(data) > 2 * 1024**2:
        raise ValueError('配置文件过大')
    return validate_config(json.loads(data))


def write_atomic(path, data):
    path = Path(path)
    pending = path.with_name(path.name + '.writing')
    pending.write_bytes(data)
    pending.replace(path)


def export_config(path, config):
    write_atomic(path, encode_config(config))


def source_records():
    paths = [ROOT/'analysis/last_victory_inventory_records.json',
             ROOT/'analysis/journeyman_ring_records.json',
             ROOT/'analysis/session_20261025/true_strike_inventory_records.json',
             ROOT/'analysis/session_20261025/betrayer_amulet_after_reequip.json',
             ROOT/'analysis/session_20261025/conquest_after_equip_inventory.json',
             ROOT/'analysis/session_20261025/equipment_cache_snapshot.json']
    paths.extend(sorted((ROOT/'analysis/equipment_snapshots').glob('*.json'))[-20:])
    records = []
    for path in paths:
        if not path.exists():
            continue
        report = json.loads(path.read_bytes())
        for record in report.get('records', []):
            item = record.get('item')
            if isinstance(item, dict) and isinstance(item.get('traits'), list):
                records.append((item, str(path.relative_to(ROOT))))
    weapons = ROOT/'analysis/live_equipped_weapons.json'
    if weapons.exists():
        for record in json.loads(weapons.read_bytes()).get('weapons', []):
            item = deepcopy(record['weapon'])
            # Converted weapon payloads retain labelled effects, not traits.
            if not item.get('traits'):
                grouped = {}
                for effect in item.get('effects', []):
                    name = effect.get('traitName')
                    if not name:
                        continue
                    slot = 'Primary Trait' if name.startswith('Trigger.') else 'Masterwork Trait' if 'Masterwork' in name else 'Secondary Trait'
                    trait = grouped.setdefault(name, {'traitName': name, 'slotType': slot, 'lootEffects': []})
                    trait['lootEffects'].append(effect)
                item['traits'] = list(grouped.values())
            records.append((item, str(weapons.relative_to(ROOT))))
    return records


def build_catalogue(config):
    validate_config(config)
    configured = {rule_key(r): r for r in config['items']}
    try:
        known_names = json.loads((HERE/'item_labels.json').read_bytes())
    except (OSError, ValueError):
        known_names = {}
    known_names.update({r['id']: r.get('label', r['gameplayTag']) for r in config['items']})
    entries = {}
    for item, evidence in source_records():
        identity, tag = item.get('id'), item.get('gameplayTag')
        if not isinstance(identity, str) or not isinstance(tag, str) or tag.split('.')[0] not in FAMILIES:
            continue
        localization = source_data()['localization'].get(tag, {})
        label = equipment_name(item, known_names.get(identity, localization.get('name', tag)))
        for trait in item.get('traits', []):
            for effect in trait.get('lootEffects', []):
                for param in effect.get('params', []):
                    magnitude_name = param.get('magnitudeName')
                    special = effect.get('lootEffectName') == 'DivineIntervention' and magnitude_name in {'Magnitude.Duration', 'Magnitude.Seconds.A'}
                    if (magnitude_name != 'Magnitude.X' and not special) or not finite_number(param.get('magnitude')):
                        continue
                    key = (identity, trait.get('traitName'), effect.get('lootEffectName'), magnitude_name)
                    original = configured.get(key)
                    value = param['magnitude']
                    if original and any(abs(value - original[k]) < 1e-6 for k in ('baseline', 'value')):
                        value = original['baseline']
                    slot = SLOT_LABELS.get(trait.get('slotType'), '词条')
                    name = effect.get('lootEffectName')
                    candidate = {'id': identity, 'gameplayTag': tag, 'label': label,
                                 'traitLabel': slot + '·' + SPECIAL_PARAMETER_LABELS.get((name, magnitude_name), EFFECT_LABELS.get(name, '复杂效果')),
                                 'traitName': trait.get('traitName'), 'lootEffectName': name,
                                 'magnitudeName': magnitude_name, 'baseline': value, 'value': value}
                    if not tag.startswith('Weapon.'):
                        candidate['aggregation'] = 'valorplate'
                    reason = ''
                    try:
                        validate_config({'version': 1, 'enabled': True, 'items': [candidate]})
                        if trait.get('conditionalLootEffects') or len(trait.get('lootEffects', [])) != 1:
                            raise ValueError('包含触发或条件效果，暂不开放编辑')
                    except ValueError as error:
                        reason = str(error)
                    row = entries.setdefault(key, {'rule': candidate, 'values': [], 'evidence': [],
                                                   'supported': not reason, 'reason': reason,
                                                   'family': FAMILIES[tag.split('.')[0]],
                                                   'upgrade_rank': item.get('masterworkUpgradeRank'),
                                                   'source_status': '曾读取的装备记录，使用前核对游戏显示'})
                    if special and magnitude_name == 'Magnitude.Duration':
                        row['source_status'] = '实验性参数，尚未验证实际触发持续时间'
                    if value not in row['values']:
                        row['values'].append(value)
                    if evidence not in row['evidence']:
                        row['evidence'].append(evidence)
    for key, row in entries.items():
        if len(row['values']) != 1:
            row.update(supported=False, reason='读到多个数值版本，需重新核对')
        if key in configured:
            row['source_status'] = '已有修改设置'
    report = {'version': 1, 'created_utc': datetime.now(timezone.utc).isoformat(),
              'completeness': 'partial_cached_equipment_records',
              'items': sorted(entries.values(), key=lambda r: (r['rule']['label'], r['rule']['id'], r['rule']['traitLabel']))}
    return report


def save_catalogue(config):
    report = build_catalogue(config)
    write_atomic(HERE/'equipment_catalogue.json', json.dumps(report, ensure_ascii=False, indent=2).encode('utf-8'))
    return report


def backup_config(config_bytes):
    folder = HERE/'config_backups'
    folder.mkdir(exist_ok=True)
    digest = hashlib.sha256(config_bytes).hexdigest()
    path = folder/(digest + '.json')
    if not path.exists():
        write_atomic(path, config_bytes)
    return path


if __name__ == '__main__':
    catalogue = save_catalogue(load_config(HERE/'overrides.json'))
    print(json.dumps({'equipment': len({r['rule']['id'] for r in catalogue['items']}),
                      'trait_entries': len(catalogue['items']),
                      'editable_entries': sum(r['supported'] for r in catalogue['items'])}))
