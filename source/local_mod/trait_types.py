"""Public trait-type requests and the offline original-game calculation bridge."""
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import subprocess
from equipment_names import equipment_name, chinese_trait_labels
from runtime_paths import node_executable

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
NODE = node_executable()


def trim_item(item):
    keys = ('id', 'gameplayTag', 'lootClassName', 'tierIdentifier', 'rarityIdentifier',
            'masterworkUpgradeRank', 'mutationNames', 'selectedTraitTags', 'traits', 'damageTypes', 'lootAttributes', 'amount', 'objectives')
    result = {key: deepcopy(item[key]) for key in keys if key in item}
    result.setdefault('lootClassName', str(item.get('gameplayTag', '')).split('.')[0])
    return result


def validate_requests(config):
    if 'traitTypeRules' in config:
        raise ValueError('类型效果由工具生成，不能直接导入内部效果字段')
    edits = config.get('traitReplacements', [])
    if not isinstance(edits, list) or len(edits) > 100:
        raise ValueError('类型修改最多100条')
    if edits and config['items']:
        raise ValueError('类型方案与旧数值测试方案请分别使用，避免混用')
    seen = set()
    for edit in edits:
        if not isinstance(edit, dict) or not isinstance(edit.get('sourceItem'), dict):
            raise ValueError('类型修改缺少原始装备记录')
        item, index = edit['sourceItem'], edit.get('sourceIndex')
        if type(index) is not int or not isinstance(item.get('traits'), list) or not 0 <= index < len(item['traits']) <= 20:
            raise ValueError('原词条位置无效')
        if not isinstance(item.get('id'), str) or not isinstance(item.get('gameplayTag'), str):
            raise ValueError('原装备编号无效')
        for field in ('targetTraitName', 'targetCategoryName'):
            if not isinstance(edit.get(field), str) or not 1 <= len(edit[field]) <= 300:
                raise ValueError('缺少目标词条类型')
        q = edit.get('quality')
        if isinstance(q, bool) or not isinstance(q, (float, int)) or not math.isfinite(q) or not 0 <= q <= .999:
            raise ValueError('词条档次必须处于正常范围')
        if item['traits'][index].get('slotType') not in {'Primary Trait', 'Secondary Trait', 'Masterwork Trait'}:
            raise ValueError('主属性不属于本轮类型替换范围')
        key = (item['id'], index)
        if key in seen:
            raise ValueError('同一词条不能重复替换')
        seen.add(key)
    return edits


def request(payload):
    raw = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    result = subprocess.run([str(NODE), str(HERE/'trait_type_cli.cjs')], input=raw,
                            capture_output=True, encoding='utf-8', errors='replace', timeout=30,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                            env={**os.environ, 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8'})
    try:
        response = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise ValueError('原始词条计算未完成：' + (result.stderr.strip().splitlines()[-1] if result.stderr.strip() else '没有返回有效数据')) from None
    if result.returncode or not response.get('ok'):
        raise ValueError(response.get('error', '词条计算未完成'))
    return response['result']


def compile_requests(config):
    edits = validate_requests(config)
    return request({'action': 'compile', 'edits': edits}) if edits else {'groups': [], 'previews': []}


def source_items():
    from editor_model import source_records, source_data
    labels = {}
    try:
        labels = json.loads((HERE/'item_labels.json').read_bytes())
    except (OSError, ValueError):
        pass
    items = {}
    for original, evidence in source_records():
        item = trim_item(original)
        if item.get('lootClassName') not in {'Weapon', 'Ring', 'Amulet', 'Charm'} or not item.get('traits'):
            continue
        if not isinstance(item.get('tierIdentifier'), (int, float)) or not isinstance(item.get('rarityIdentifier'), (int, float)):
            continue
        score = 100 * bool(item.get('selectedTraitTags')) + len(item['traits'])
        if item['id'] in items and items[item['id']]['score'] >= score:
            continue
        loc = source_data()['localization'].get(item['gameplayTag'], {})
        label = equipment_name(item, labels.get(item['id'], loc.get('name', item['gameplayTag'])))
        items[item['id']] = {'item': item, 'label': label, 'evidence': evidence, 'score': score}
    return sorted(items.values(), key=lambda row: (row['label'], row['item']['id']))


def trait_label(trait):
    from editor_model import EFFECT_LABELS
    native = chinese_trait_labels().get(trait.get('traitName'), {}).get('label')
    if native:
        return native
    labels = json.loads((HERE/'trait_labels.json').read_bytes())
    if trait.get('traitName') in labels:
        return labels[trait['traitName']]
    names = [EFFECT_LABELS.get(e.get('lootEffectName'), e.get('lootEffectName', '效果')) for e in trait.get('lootEffects', [])]
    return '、'.join(dict.fromkeys(names)) or trait.get('traitName', '未知词条')


def trait_value_text(trait):
    from editor_model import source_data
    specs = {r['lootEffectName']: r for r in source_data()['lootEffects']['collection']}
    texts = []
    for effect in trait.get('lootEffects', []):
        for param in effect.get('params', []):
            if param.get('magnitudeName') not in {'Magnitude.X', 'Magnitude.Duration', 'Magnitude.Seconds.A'}:
                continue
            spec = next((p for p in specs.get(effect.get('lootEffectName'), {}).get('params', []) if p['magnitudeName'] == param['magnitudeName']), {})
            percent = spec.get('displayMappingType') == 'percent'
            value = param['magnitude'] * (100 if percent else 1)
            unit = '%' if percent else '秒' if param['magnitudeName'] != 'Magnitude.X' else ''
            texts.append(f'{value:g}{unit}')
    return ' / '.join(texts)


def number_for_quality(row, quality):
    lo, hi = row['unrounded']['range']
    scale = 10 ** row['decimals']
    value = math.floor((lo + (hi-lo)*quality)*scale+.5)/scale
    return value


def prepare_slot(config, source, index):
    """Preview exclusions after the other staged slots, retaining the raw source."""
    working = deepcopy(source)
    edits = [edit for edit in config.get('traitReplacements', [])
             if edit['sourceItem']['id'] == source['id'] and edit['sourceIndex'] != index]
    if edits:
        result = request({'action': 'compile', 'edits': edits})
        working['traits'] = result['groups'][0]['targetTraits']
    return working


def stage_replacement(config, source, index, preview, label):
    candidate = deepcopy(config)
    if candidate['items']:
        raise ValueError('请先载入原始设置或空白方案，再编辑词条类型；旧数值方案仍可导出保留')
    edit = {'sourceItem': trim_item(source), 'sourceIndex': index,
            'targetTraitName': preview['targetTraitName'], 'targetCategoryName': preview['category'],
            'quality': preview['quality'], 'label': label, 'targetLabel': preview['label'],
            'targetValueText': trait_value_text(preview['targetTrait'])}
    edits = candidate.setdefault('traitReplacements', [])
    for i, old in enumerate(edits):
        if (old['sourceItem']['id'], old['sourceIndex']) == (source['id'], index):
            edits[i] = edit
            break
    else:
        edits.append(edit)
    candidate['enabled'] = True
    compile_requests(candidate)
    return candidate
