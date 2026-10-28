"""Stage sequential native uncursing for one selected item; install after game exit."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid

import build_local_mod as builder
from editor_model import HERE, write_atomic
from equipment_names import equipment_name
from settings_backups import capture, install_lock, managed_destination, rollback_owned, sha
from trait_types import NODE

PLAN = HERE/'uncurse_plan.json'
COMPILER = HERE/'compile_uncurse_trial.cjs'


def availability(item):
    mutations = item.get('mutationNames') or []
    if not 1 <= mutations.count('Mutation.Item.Cursed') <= 3:
        return '请选择剩余1至3层诅咒的物品。'
    if item.get('equipCount') or item.get('isEquippedInSelectedValorplate'):
        return '首轮请选择没有装备或保存到配装的备用物品。'
    if item.get('masterworkUpgradeRank', 0):
        return '首轮仅处理强化等级为0的诅咒物品。'
    if 'objectives' not in item or len(item['objectives']) != 1:
        return '缺少完整的解除诅咒进度，请读取新版兵器库清单。'
    return ''


def prepare(item, *, publish=True):
    reason = availability(item)
    if reason:
        raise ValueError(reason)
    folder = HERE/'uncurse_builds'/uuid.uuid4().hex
    folder.mkdir(parents=True)
    source = folder/'source.json'
    write_atomic(source, json.dumps(item, ensure_ascii=False, indent=2).encode('utf-8'))
    current_bytes = (HERE/'overrides.json').read_bytes()
    current = json.loads(current_bytes)
    if current['enabled'] or current['items'] or current.get('traitReplacements') or current['primalDrop']['enabled']:
        raise ValueError('请先关闭旧装备覆盖及掉落加成，再制作解咒计划。')
    profile = folder/'profile.json'; profile.write_bytes(current_bytes)
    _, base = builder.build(profile, folder/'base')
    config_path, main = folder/'uncurse_config.json', folder/'main.c05310c4.chunk.js'
    code = "const fs=require('fs'),c=require(process.argv[1]);const p=c.compile(JSON.parse(fs.readFileSync(process.argv[2])));fs.writeFileSync(process.argv[3],JSON.stringify(p,null,2));fs.writeFileSync(process.argv[5],c.runtime(p)+'\\n'+c.patch(fs.readFileSync(process.argv[4],'utf8')));"
    run = subprocess.run([str(NODE), '-e', code, str(COMPILER), str(source), str(config_path),
                          str(folder/'base/main.c05310c4.chunk.js'), str(main)], capture_output=True,
                         encoding='utf-8', errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                         env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}, timeout=30)
    if run.returncode:
        raise ValueError('解咒计划核对未通过：' + (run.stderr.strip().splitlines()[-1] if run.stderr.strip() else '原始记录不适用'))
    subprocess.run([str(NODE), '--check', str(main)], check=True, capture_output=True,
                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    data = main.read_bytes(); pak = folder/builder.PAK_NAME
    builder.make_pak(pak, data)
    verification = builder.inspect_pak(pak, extract_to=folder/'verified_extraction')
    if (folder/'verified_extraction/main.c05310c4.chunk.js').read_bytes() != data:
        raise RuntimeError('解咒试验包独立提取核对失败')
    config = json.loads(config_path.read_bytes())
    report = {**base, 'pak': str(pak), 'pak_sha256': sha(pak), 'patched_sha256': hashlib.sha256(data).hexdigest(),
              'verification': verification, 'changed_integration_points': base['changed_integration_points']+4,
              'uncurse_trial': {'version': 1, 'plan_id': config['planId'], 'source_id': item['id'],
                               'before_progress': config['beforeProgress'], 'target_progress': config['targetProgress'],
                               'total_layers': config['totalLayers']},
              'scope': 'Original objective update if needed, original forge awakening, and inventory refresh for one selected item; no loot generation or trait replacement.'}
    write_atomic(folder/'build_report.json', json.dumps(report, ensure_ascii=False, indent=2).encode('utf-8'))
    state_bytes = (HERE/'installed_patch.json').read_bytes(); state = json.loads(state_bytes)
    destination = managed_destination(state)
    if sha(destination) != state['pak_sha256']:
        raise ValueError('当前补丁与安装记录不符，未安装计划。')
    plan = {'version': 1, 'status': 'prepared_not_installed', 'prepared_at_utc': datetime.now(timezone.utc).isoformat(),
            'plan_id': config['planId'], 'source_id': item['id'], 'label': equipment_name(item),
            'tier': item['tierIdentifier'], 'rarity': item['rarityIdentifier'],
            'before_progress': config['beforeProgress'], 'target_progress': config['targetProgress'],
            'start_at_awaken': config['startAtAwaken'],
            'total_layers': config['totalLayers'],
            'report_path': str(folder/'build_report.json'), 'source_path': str(source), 'pak_sha256': report['pak_sha256'],
            'expected_current_pak_sha256': sha(destination), 'expected_config_sha256': hashlib.sha256(current_bytes).hexdigest(),
            'expected_installation_record_sha256': hashlib.sha256(state_bytes).hexdigest()}
    write_atomic(folder/'plan.json', json.dumps(plan, ensure_ascii=False, indent=2).encode('utf-8'))
    if publish:
        write_atomic(PLAN, json.dumps(plan, ensure_ascii=False, indent=2).encode('utf-8'))
    return plan


def load_plan():
    try:
        plan = json.loads(PLAN.read_bytes())
        return plan if plan.get('version') == 1 else None
    except (OSError, ValueError):
        return None


def install(plan):
    if load_plan() != plan:
        raise ValueError('解咒计划已在其他窗口更新，请重新查看。')
    report_path = Path(plan['report_path']).resolve()
    if not report_path.is_relative_to((HERE/'uncurse_builds').resolve()):
        raise ValueError('请选择本工具制作的解咒计划。')
    report = json.loads(report_path.read_bytes())
    if report['pak_sha256'] != plan['pak_sha256'] or sha(report['pak']) != plan['pak_sha256'] or report['uncurse_trial']['plan_id'] != plan['plan_id']:
        raise ValueError('解咒计划与试验包不一致，未安装。')
    profile = report['config']
    if profile['enabled'] or profile['items'] or profile.get('traitReplacements') or profile['primalDrop']['enabled'] or report.get('replacement_copy_trial'):
        raise ValueError('解咒试验包含有其他修改，未安装。')
    with install_lock(HERE):
        if builder.game_running():
            raise ValueError('请正常退出游戏后再安装解咒计划。')
        config_bytes = (HERE/'overrides.json').read_bytes(); state_bytes = (HERE/'installed_patch.json').read_bytes()
        if hashlib.sha256(config_bytes).hexdigest() != plan['expected_config_sha256'] or hashlib.sha256(state_bytes).hexdigest() != plan['expected_installation_record_sha256']:
            raise ValueError('设置或安装状态已变化，请重新制作解咒计划。')
        if sha(managed_destination(json.loads(state_bytes))) != plan['expected_current_pak_sha256']:
            raise ValueError('当前补丁已变化，未安装。')
        checkpoint = capture(HERE, '单件一键解咒试验前')
        try:
            state = builder.install(Path(report['pak']), report)
            state['uncurse_trial'] = report['uncurse_trial']
            state['status'] = 'installed_uncurse_trial_waiting_for_next_start'
            write_atomic(HERE/'installed_patch.json', (json.dumps(state, ensure_ascii=False, indent=2)+'\n').encode('utf-8'))
            if sha(state['destination']) != plan['pak_sha256'] or (HERE/'overrides.json').read_bytes() != config_bytes:
                raise RuntimeError('解咒组件安装后核对失败')
        except Exception:
            concurrent = (HERE/'overrides.json').read_bytes()
            rollback_owned(checkpoint, HERE, [plan['expected_current_pak_sha256'], plan['pak_sha256'], None],
                           concurrent if concurrent != config_bytes else None)
            raise
    return {'config_bytes': config_bytes, 'config': json.loads(config_bytes), 'full_backup': str(checkpoint),
            'message': '单件解咒试验已安装。下次启动逐层完成目标并执行原有觉醒，每层读回核对后继续；需读取结果确认。'}


def read_status(plan):
    from settings_service import installation_state, run_local
    if installation_state().get('uncurse_trial', {}).get('plan_id') != plan['plan_id']:
        raise ValueError('当前没有安装这份解咒计划。')
    output = Path(plan['report_path']).parent/'uncurse_trace.json'
    run_local(HERE.parent/'analysis/recalibrate_runtime.py', timeout=20)
    run_local(HERE.parent/'analysis/read_uncurse_trace.py', ['--out', output], timeout=50)
    result = json.loads(output.read_bytes())
    return status_message(result.get('trace') or {})


def status_message(trace):
    status = trace.get('status')
    message = {'cleansed_after_refresh_verified': '正常保存并重新读取后，已确认选中装备解除诅咒。',
            'already_cleansed_verified': '当前记录已符合已解除诅咒状态，本次未重复提交。',
            'original_request_failed': '游戏原有保存请求失败；尚未确认解除成功，请保留记录供核对。',
            'original_awaken_request_failed': '游戏原有觉醒请求失败；尚未确认解除成功。',
            'awakening_requested': '目标已达标，正在等待原有觉醒操作完成。',
            'waiting_for_awaken_refresh': '正在重新读取觉醒后的装备记录。',
            'next_layer_pending': '上一层已保存并核对，正在处理下一层。',
            'source_changed_before_next_layer': '下一层开始前装备记录发生变化，已停止。',
            'unexpected_layer_state': '读回的诅咒层数或词条记录不符合预期，已停止。',
            'already_requested_previous_run': '此计划已提交过，本次没有重复执行；请读取兵器库核对。',
            'source_changed': '装备或进度已变化，停止执行；请重新读取物品。',
            'equipped_source_not_supported': '物品仍保存在配装中，首轮未执行。',
            'progress_saved_curse_still_present': '计数已到目标，但诅咒仍在；尚未确认解除成功。',
            'waiting_for_refresh': '正在等待游戏重新读取保存结果。',
            'request_started': '已交给游戏原有进度流程，等待结果。'}.get(status, '尚未确认解除结果。请保持兵器库打开后再核对。')
    if 'completedLayers' in trace and 'totalLayers' in trace:
        message += f' 已核对 {trace["completedLayers"]}/{trace["totalLayers"]} 层。'
    return message
