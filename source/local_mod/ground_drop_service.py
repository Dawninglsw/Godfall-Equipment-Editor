"""One selected ground item; scan/preview are read-only, apply is explicit."""
from datetime import datetime, timezone
from pathlib import Path
import json
import subprocess
import sys
import uuid

from editor_model import HERE, ROOT, EFFECT_LABELS, source_data
from trait_types import NODE, trait_label, trait_value_text
from settings_service import run_local, game_running
from equipment_names import equipment_name

HISTORY = HERE / 'drop_history'
SUPPORTED_CLASSES = {'Weapon': '武器', 'Ring': '戒指', 'Amulet': '护符', 'Augment': '强化物',
                     'Charm': '符咒', 'Banner': '旗帜', 'Consumable': '生命石'}


def new_session():
    HISTORY.mkdir(exist_ok=True)
    folder = HISTORY / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '_' + uuid.uuid4().hex[:8])
    folder.mkdir()
    return folder


def request(payload):
    result = subprocess.run([str(NODE), str(HERE / 'ground_drop_cli.cjs')],
                            input=json.dumps({**payload, 'clientProtocol': 3}, ensure_ascii=False, allow_nan=False),
                            capture_output=True, encoding='utf-8', errors='replace', timeout=35,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        reply = json.loads(result.stdout)
    except ValueError:
        raise ValueError('词条计算未完成，请重新读取掉落') from None
    if result.returncode or not reply.get('ok'):
        raise ValueError(reply.get('error', '词条计算未完成'))
    return reply['result']


def scan():
    if not game_running():
        raise ValueError('请先启动游戏，停在尚未拾取的装备附近')
    folder = new_session()
    run_local(ROOT / 'analysis/recalibrate_runtime.py', timeout=20)
    run_local(ROOT / 'analysis/read_ground_loot.py', ['--out', folder / 'capture.json'], timeout=30)
    snapshot = json.loads((folder / 'capture.json').read_bytes())
    calibration = json.loads((ROOT / 'analysis/runtime_calibration.json').read_bytes())
    snapshot['process_creation_id'] = calibration['process_creation_id']
    snapshot['session_directory'] = str(folder)
    rows = [equipment_row(record) for record in snapshot['records'] if record['item']['lootClassName'] in SUPPORTED_CLASSES]
    snapshot['rows'] = rows
    snapshot['other_equipment_count'] = sum(r['item']['lootClassName'] not in SUPPORTED_CLASSES for r in snapshot['records'])
    snapshot['editable_equipment_count'] = sum(row['editable'] for row in rows)
    (folder / 'selection.json').write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
    return snapshot


def equipment_row(record):
    """Keep detected items visible even when their affixes cannot be edited."""
    item = record['item']
    localization = source_data().get('localization', {}).get(item['gameplayTag'], {})
    name = equipment_name(item, localization.get('name', item['gameplayTag']))
    row = {'record': record, 'name': name, 'slots': [], 'editable': False,
           'family_label': SUPPORTED_CLASSES.get(item.get('lootClassName'), '装备')}
    if not any(t.get('slotType') in {'Secondary Trait', 'Primary Trait'} for t in item.get('traits', [])):
        return {**row, 'state_label': '没有可替换词条',
                'reason': '已读到这件装备，但没有可替换的主副词条。当前功能不能新增词条。'}
    if item.get('masterworkUpgradeRank', 0) or item.get('mutationNames'):
        return {**row, 'state_label': '特殊属性暂未适配',
                'reason': '已读到这件装备；当前版本暂未开放强化过或带特殊突变装备的词条编辑。'}
    try:
        result = request({'action': 'inspect', 'item': item})
    except (ValueError, KeyError) as e:
        return {**row, 'state_label': '词条资料暂不可用', 'error_detail': str(e),
                'reason': '已读到这件装备，但词条资料暂时无法核对，请重新读取或选择另一件。'}
    editable = any(s['candidates'] for s in result['slots'])
    return {**row, **result, 'editable': editable,
            'state_label': '可编辑' if editable else '现有词条暂未适配',
            'reason': '' if editable else '已读到这件装备，但现有词条暂没有已适配的替换候选。'}


# Preserve the old read-only helper name for archived diagnostics and tests.
weapon_row = equipment_row


def plan(snapshot, row, index, target, display_value=None, quality=None):
    payload = {'action': 'plan', 'item': row['record']['item'], 'index': index, 'targetTraitName': target}
    if display_value is not None:
        payload['displayValue'] = float(display_value)
    elif quality is not None:
        payload['quality'] = float(quality)
    prepared = request(payload)
    prepared.update(capture_pid=snapshot['pid'], capture_process_creation_id=snapshot['process_creation_id'])
    return prepared


def verify_process(plan):
    if not game_running():
        raise ValueError('游戏已关闭；旧读取记录不能继续写入，请启动后重新读取')
    run_local(ROOT / 'analysis/recalibrate_runtime.py', timeout=20)
    calibration = json.loads((ROOT / 'analysis/runtime_calibration.json').read_bytes())
    if (calibration['pid'] != plan['capture_pid'] or
            calibration['process_creation_id'] != plan['capture_process_creation_id']):
        raise ValueError('游戏已经重启，请重新读取地上掉落')


def apply(snapshot, prepared):
    verify_process(prepared)
    folder = Path(snapshot['session_directory']) / ('edit_' + uuid.uuid4().hex[:8])
    folder.mkdir()
    plan_path = folder / 'plan.json'
    plan_path.write_text(json.dumps(prepared, ensure_ascii=False, indent=2), encoding='utf-8')
    receipt = folder / 'applied.json'
    run_trial(['--plan', plan_path, '--out', receipt, '--apply'])
    result = json.loads(receipt.read_bytes())
    if result['status'] != 'applied_and_read_back':
        raise ValueError('未得到完整写入核对结果，请保留记录并重新读取')
    return {'plan': str(plan_path), 'receipt': str(receipt), 'status': result['status'],
            'item_id': prepared['item_id'], 'session': str(folder)}


def restore(last):
    prepared = json.loads(Path(last['plan']).read_bytes())
    verify_process(prepared)
    out = Path(last['session']) / 'restored.json'
    run_trial(['--plan', last['plan'], '--out', out, '--restore', last['receipt']])
    return json.loads(out.read_bytes())


def run_trial(arguments):
    try:
        return run_local(ROOT / 'analysis/ground_trait_trial.py', arguments, timeout=40)
    except RuntimeError as e:
        detail = str(e)
        if any(x in detail for x in ['active ground pickup', 'original ground item or process changed', 'Restore source is no longer']):
            raise ValueError('该装备已被拾取或记录已失效，请重新读取地上装备。已拾取装备不能用旧地址撤回。') from None
        if 'does not fit' in detail or 'buffers overlap' in detail:
            raise ValueError('这件掉落暂不支持写入该类型，请重新读取并选择其他候选。') from None
        raise


def record_observation(last, observation):
    if observation not in {'picked_up', 'restart_retained', 'not_retained'}:
        raise ValueError('验证状态不正确')
    path = Path(last['session']) / 'user_observations.json'
    rows = json.loads(path.read_bytes()) if path.exists() else []
    rows.append({'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'item_id': last['item_id'],
                 'observation': observation, 'source': 'user_report',
                 'limitation': 'Not an automatic ownership, server-response or combat verification.'})
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')


def history():
    result = []
    labels = {'applied_and_read_back': '已写入，待拾取核对', 'restored_before_pickup': '拾取前已撤回',
              'picked_up': '已手动确认拾取', 'restart_retained': '已手动确认重启保留', 'not_retained': '已手动报告未保留',
              'apply_failed': '写入中断，请核对记录'}
    for path in sorted(HISTORY.glob('*/edit_*/applied.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:30]:
        try:
            receipt = json.loads(path.read_bytes())
            if receipt['status'] not in {'applied_and_read_back', 'apply_failed'}:
                continue
            prepared = json.loads((path.parent / 'plan.json').read_bytes())
            loc = source_data().get('localization', {}).get(prepared['gameplayTag'], {})
            name = equipment_name(prepared['gameplayTag'], loc.get('name', prepared['gameplayTag']))
            state = 'restored_before_pickup' if (path.parent / 'restored.json').exists() else receipt['status']
            observations = path.parent / 'user_observations.json'
            if observations.exists():
                rows = json.loads(observations.read_bytes())
                if rows and state != 'restored_before_pickup':
                    state = rows[-1]['observation']
            result.append({'name': name, 'item_id': prepared['item_id'], 'target': trait_label(prepared['target_materialized_trait'])+' '+trait_value_text(prepared['target_materialized_trait']),
                           'state': state, 'state_label': labels.get(state, state), 'plan': str(path.parent / 'plan.json'),
                           'receipt': str(path), 'session': str(path.parent)})
        except (OSError, ValueError, KeyError):
            continue
    return result
