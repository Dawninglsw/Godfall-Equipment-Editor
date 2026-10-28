"""Prepare one replacement independently of local override drafts; install on demand."""
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid

from editor_model import HERE, write_atomic
from equipment_names import equipment_name
from trait_types import NODE, trait_label, trait_value_text
import build_replacement_copy_trial as trial
from settings_backups import managed_destination, sha

PLAN = HERE / 'replacement_plan.json'
CLI = HERE / 'replacement_editor_cli.cjs'


def is_awakened_ring(item):
    return (item.get('lootClassName') == 'Ring' and item.get('masterworkUpgradeRank', 0) == 0
            and item.get('mutationNames') == ['Mutation.Item.Awakened']
            and isinstance(item.get('objectives'), list) and not item['objectives']
            and not any(t.get('slotType') == 'Trait.Objective' for t in item.get('traits', [])))


@lru_cache(maxsize=128)
def _primary_support(serialized_item):
    return _request({'action': 'primary_support', 'item': json.loads(serialized_item)})


def random_primary_support(item):
    return _primary_support(json.dumps(item, sort_keys=True, ensure_ascii=False, allow_nan=False))


def availability(item, index=None):
    if item.get('lootClassName') not in {'Augment', 'Ring', 'Amulet', 'Charm', 'Weapon', 'Banner', 'Consumable'}:
        return '该物品类型尚未开放同款生成。'
    rank = item.get('masterworkUpgradeRank', 0)
    if type(rank) is not int or not 0 <= rank <= 5:
        return '强化等级必须处于 0 至 5 级。'
    if (item.get('mutationNames') or []) not in [[], ['Mutation.Item.Primal']] and not is_awakened_ring(item):
        return '未解完的诅咒和混合变体保持只读；已解咒试验先限定强化0且完整读取的戒指。'
    if item.get('objectives') or any(t.get('slotType') == 'Trait.Objective' or t.get('conditionalLootEffects')
                                     for t in item.get('traits', [])):
        return '这件物品含尚未适配的目标或条件效果。'
    attributes = {'Weapon': 'attackPower', 'Banner': 'BannerOvershield', 'Consumable': 'ConsumableHealingPower'}
    field = attributes.get(item.get('lootClassName'))
    if field and field not in (item.get('lootAttributes') or {}):
        return '这份记录缺少攻击力、护盾量或回复量；请用新版完整清单重新读取后再制作同款方案。'
    if index is not None:
        if type(index) is not int or not 0 <= index < len(item.get('traits', [])):
            return '词条位置不正确。'
        slot = item['traits'][index].get('slotType')
        if slot == 'Primary Trait':
            support = random_primary_support(item)
            if not support['supported']:
                return '本件主词条不可编辑：' + support['reason']
        elif slot != 'Secondary Trait':
            return '固定主属性与精通词条保持原样。'
    return ''


def prepare(item, index, payload, *, publish=True):
    reason = availability(item, index)
    if reason:
        raise ValueError(reason)
    return _prepare({**payload, 'item': item, 'index': index}, publish=publish)


def prepare_many(item, edits, *, publish=True):
    reason = availability(item)
    if reason:
        raise ValueError(reason)
    if not isinstance(edits, list) or not edits:
        raise ValueError('请至少设置一条副词条。')
    for edit in edits:
        if not isinstance(edit, dict) or type(edit.get('index')) is not int:
            raise ValueError('每条修改都需要有效的词条位置。')
        reason = availability(item, edit.get('index'))
        if reason:
            raise ValueError(reason)
        if item['traits'][edit['index']].get('slotType') != 'Secondary Trait':
            raise ValueError('整件多条编辑目前只支持副词条；随机主词条请使用单条同款模式。')
    return _prepare({'item': item, 'edits': edits}, publish=publish)


def calculate_many(item, edits, *, index=None):
    """Inspect a slot or validate a whole draft without building or selecting a plan."""
    reason = availability(item, index)
    if reason:
        raise ValueError(reason)
    request = {'item': item, 'edits': edits}
    if index is not None:
        request.update(action='inspect_many', index=index)
    return _request(request)


def calculate_primary(item, edits, *, index=None):
    if index is None:
        if len(edits)!=1:raise ValueError('随机主词条方案一次只改一条。')
        index=edits[0]['index']
    if type(index) is not int or not 0<=index<len(item.get('traits',[])) or item['traits'][index]['slotType']!='Primary Trait':
        raise ValueError('请选择已适配的随机主词条。')
    reason=availability(item,index)
    if reason:raise ValueError(reason)
    if not edits:
        from trait_types import request
        return request({'action':'inspect','item':item,'index':index})
    return _request({**edits[0],'item':item})


def _request(request):
    run = subprocess.run([str(NODE), str(CLI)],
                         input=json.dumps(request, ensure_ascii=False, allow_nan=False),
                         capture_output=True, encoding='utf-8', errors='replace', timeout=40,
                         env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        result = json.loads(run.stdout)
    except ValueError:
        raise ValueError('同款物品计算没有完成；原件未改变。') from None
    if run.returncode or not result.get('ok'):
        raise ValueError(result.get('error', '同款物品计算未完成'))
    return result['result']


def _prepare(request, *, publish):
    item = request['item']
    data = _request(request)
    folder = HERE/'replacement_builds'/uuid.uuid4().hex
    folder.mkdir(parents=True)
    preview = folder/'preview.json'
    write_atomic(preview, json.dumps(data['preview'], ensure_ascii=False, indent=2).encode('utf-8'))
    _, report = trial.build(preview, folder/'package')
    config = (HERE/'overrides.json').read_bytes()
    state_path = HERE/'installed_patch.json'
    state = json.loads(state_path.read_bytes()) if state_path.exists() else None
    destination = managed_destination(state)
    current_sha = sha(destination) if destination.exists() else None
    if current_sha and (not state or state.get('pak_sha256') != current_sha):
        raise ValueError('当前补丁与安装记录不符；方案已保留，未安装。')
    choices = data['choices']
    changes = [{'index': choice['index'], 'source_trait': trait_label(item['traits'][choice['index']]),
                'source_value': trait_value_text(item['traits'][choice['index']]),
                'target_trait': choice['label'], 'target_value': trait_value_text(choice['targetTrait'])}
               for choice in choices]
    first = changes[0]
    preserved = {'lootAttributes': data['preview']['expected_materialized'].get('lootAttributes', {}),
                 'damageTypes': data['preview']['expected_materialized'].get('damageTypes'),
                 'amount': data['preview']['expected_materialized'].get('amount', 1)}
    plan = {'version': 1, 'status': 'prepared_not_installed',
            'prepared_at_utc': datetime.now(timezone.utc).isoformat(),
            'trial_id': data['trialId'], 'source_id': item['id'], 'label': equipment_name(item), 'family': item['lootClassName'],
            'primal': item.get('mutationNames') == ['Mutation.Item.Primal'],
            'awakened': is_awakened_ring(item),
            'primary_trial': any(item['traits'][c['index']]['slotType'] == 'Primary Trait' for c in changes),
            'source_trait': first['source_trait'], 'source_value': first['source_value'],
            'target_trait': first['target_trait'], 'target_value': first['target_value'], 'changes': changes,
            'tier': item['tierIdentifier'], 'rarity': item['rarityIdentifier'],
            'upgrade_rank': item.get('masterworkUpgradeRank', 0),
            'preserved_upgrade': {'boosted_indexes': [n for n, t in enumerate(item['traits']) if t.get('masterworkBonusTier')],
                                  'masterwork_traits': [trait_label(t) + ' ' + trait_value_text(t)
                                                       for t in item['traits'] if t.get('slotType') == 'Masterwork Trait']},
            'preserved_metadata': preserved,
            'source_index': first['index'], 'report_path': str(folder/'package/build_report.json'),
            'preview_path': str(preview), 'pak_sha256': report['pak_sha256'],
            'expected_config_sha256': hashlib.sha256(config).hexdigest(),
            'expected_current_pak_sha256': current_sha,
            'expected_installation_record_sha256': hashlib.sha256(state_path.read_bytes()).hexdigest() if state_path.exists() else None}
    # Each prepared plan is retained even when a later plan becomes the UI selection.
    write_atomic(folder/'plan.json', json.dumps(plan, ensure_ascii=False, indent=2).encode('utf-8'))
    if publish:
        write_atomic(PLAN, json.dumps(plan, ensure_ascii=False, indent=2).encode('utf-8'))
    return plan


def load_plan():
    try:
        plan = json.loads(PLAN.read_bytes())
        if plan.get('version') != 1:
            return None
        return plan
    except (OSError, ValueError):
        return None


def install(plan):
    if load_plan() != plan:
        raise ValueError('同款方案已在其他窗口更新，请重新查看。')
    config = (HERE/'overrides.json').read_bytes()
    if hashlib.sha256(config).hexdigest() != plan['expected_config_sha256']:
        raise ValueError('装备设置已变化，请重新制作同款方案。')
    state = HERE/'installed_patch.json'
    state_sha = hashlib.sha256(state.read_bytes()).hexdigest() if state.exists() else None
    if state_sha != plan['expected_installation_record_sha256']:
        raise ValueError('安装状态已变化，请重新制作同款方案。')
    report_path = Path(plan['report_path']).resolve()
    if not report_path.is_relative_to((HERE/'replacement_builds').resolve()):
        raise ValueError('请选择本工具制作的同款方案。')
    report = json.loads(report_path.read_bytes())
    if report['pak_sha256'] != plan['pak_sha256'] or report['replacement_copy_trial']['trial_id'] != plan['trial_id']:
        raise ValueError('同款方案与生成包不一致，未安装。')
    result = trial.install_staged(report_path, config, plan['expected_current_pak_sha256'])
    return {**result, 'config_bytes': (HERE/'overrides.json').read_bytes(),
            'config': json.loads((HERE/'overrides.json').read_bytes()),
            'message': '同款生成已安装并备份。下次启动后单人正常打怪或开箱，正常拾取即可；每个方案只生成一次。'}


def generation_status(plan):
    from settings_service import installed_config, installation_state, run_local
    current, _ = installed_config()
    if current is None or installation_state().get('replacement_copy_trial', {}).get('trial_id') != plan['trial_id']:
        raise ValueError('当前没有启用这份同款方案。')
    run_local(HERE.parent/'analysis/recalibrate_runtime.py', timeout=20)
    output = Path(plan['report_path']).parent/'generation_trace.json'
    run_local(HERE.parent/'analysis/read_replacement_trace.py', ['--out', output], timeout=50)
    result = json.loads(output.read_bytes())
    trace = result.get('trace')
    if not trace:
        return '本次尚未读到生成记录。请确认已进入单人关卡并发生装备掉落，再检查一次。'
    messages = {
        'waiting': '等待单人关卡中的正常装备掉落。',
        'inventory_not_ready': '兵器库尚未载入；进入关卡后再正常打怪或开箱。',
        'source_changed_or_missing': '原件与方案记录不一致，已停止生成。请重新读取物品并制作方案。',
        'replacement_already_owned': '背包中已有符合此方案的同款物品，本次没有重复生成。',
        'already_generated_previous_run': '这份方案此前已生成过，不会再次生成；请先查看背包。',
        'generated_waiting_for_pickup': '新物品已生成。若已拾取，请读取兵器库核对；此记录本身不代表已拾取保存。',
        'generation_failed_original_rewards_preserved': '本次没有成功生成同款物品，原掉落保留。请保留方案供检查。',
        'waiting_nonempty_reward': '等待下一轮正常装备掉落。',
        'waiting_smaller_reward': '本轮掉落过多，等待下一轮装备掉落。',
        'waiting_single_player': '当前掉落不是单人奖励，等待单人玩法中的装备掉落。',
        'waiting_grounded_equipment': '本轮只有自动到账奖励，等待正常落地的装备奖励。',
    }
    text = messages.get(trace['status'], '生成状态暂未识别。')
    return text + (' 新编号末尾：' + trace['generatedId'][-12:] if trace.get('generatedId') else '')
