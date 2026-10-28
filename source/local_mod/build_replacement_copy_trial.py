"""Stage/install one bounded ordinary replacement through normal loot generation."""
import hashlib
import json
from pathlib import Path
import subprocess

import build_local_mod as equipment
from editor_model import encode_config, write_atomic
from primal_drop_settings import default_primal
from trait_types import NODE
from equipment_names import equipment_name

HERE = Path(__file__).resolve().parent


def build(preview_path, output=None, *, batch=False):
    output = (Path(output) if output else HERE/'build_replacement_copy_trial').resolve()
    output.mkdir(parents=True, exist_ok=True)
    profile = {'version': 1, 'enabled': False, 'items': [], 'traitReplacements': [], 'primalDrop': default_primal()}
    profile_path = output/'profile.json'; profile_path.write_bytes(encode_config(profile))
    _, base = equipment.build(profile_path, output/'equipment_base')
    compiler = "const fs=require('fs'),m=require(process.argv[1]);const c=m.compile(JSON.parse(fs.readFileSync(process.argv[2])));fs.writeFileSync(process.argv[3],JSON.stringify(c,null,2));fs.writeFileSync(process.argv[5],m.runtime(c)+'\\n'+m.patch(fs.readFileSync(process.argv[4],'utf8')));"
    config_path = output/('batch_config.json' if batch else 'replacement_config.json')
    main = output/'main.c05310c4.chunk.js'
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    subprocess.run([str(NODE), '-e', compiler, str(HERE/('compile_replacement_batch.cjs' if batch else 'compile_replacement_copy.cjs')), str(Path(preview_path).resolve()),
                    str(config_path), str(output/'equipment_base/main.c05310c4.chunk.js'), str(main)],
                   check=True, capture_output=True, encoding='utf-8', creationflags=flags)
    subprocess.run([str(NODE), '--check', str(main)], check=True, capture_output=True, creationflags=flags)
    data = main.read_bytes(); pak = output/equipment.PAK_NAME
    equipment.make_pak(pak, data)
    verification = equipment.inspect_pak(pak, extract_to=output/'verified_extraction')
    if (output/'verified_extraction/main.c05310c4.chunk.js').read_bytes() != data:
        raise RuntimeError('Independent replacement trial extraction differs')
    c = json.loads(config_path.read_bytes())
    if batch:
        metadata = {'version': 1, 'batch_id': c['batchId'], 'max_items': c['maxItems'],
                    'items': [{'trial_id': x['trialId'], 'source_id': x['sourceId'],
                               'label': equipment_name(x['gameplayTag']), 'changed_indexes': x['changedIndexes']}
                              for x in c['configs']]}
    else:
        metadata = single_metadata(c)
    report = {**base, 'pak': str(pak), 'pak_sha256': hashlib.sha256(pak.read_bytes()).hexdigest(),
              'patched_sha256': hashlib.sha256(data).hexdigest(), 'verification': verification,
              'changed_integration_points': base['changed_integration_points']+3,
              ('replacement_batch_trial' if batch else 'replacement_copy_trial'): metadata,
              'scope': 'Reviewed replacements via original factory; old gear overrides and primal chance modifier disabled; no request code changes.',
              'runtime_status': 'staged_not_live_verified'}
    (output/'build_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return pak, report


def single_metadata(c):
    trial = {'version': 1, 'trial_id': c['trialId'], 'source_id': c['sourceId'], 'gameplayTag': c['gameplayTag'],
             'label': equipment_name(c['gameplayTag']), 'scope': 'One replacement on a normal single-player equipment drop; normal pickup required.',
             'persistent_one_generation_guard': True, 'tier': c['tierIdentifier'], 'rarity': c['rarityIdentifier'],
             'upgrade_rank': c.get('masterworkUpgradeRank', 0), 'changed_indexes': c.get('changedIndexes', [])}
    if c.get('mutationNames'):
        trial['mutation_names'] = c['mutationNames']
    if c.get('primaryIndexes'):
        trial['primary_changed_indexes'] = c['primaryIndexes']
    return trial


def install_staged(report_path, expected_config_bytes, expected_current_sha, *, batch=False):
    from settings_backups import capture, install_lock, rollback_owned, sha
    from editor_model import validate_config
    report_path = Path(report_path)
    report = json.loads(report_path.read_bytes()); pak = Path(report['pak'])
    profile = validate_config(report['config'])
    key = 'replacement_batch_trial' if batch else 'replacement_copy_trial'
    if (not report.get(key) or report.get('replacement_copy_trial' if batch else 'replacement_batch_trial') or profile['enabled'] or profile['items'] or
            profile.get('traitReplacements') or profile['primalDrop']['enabled'] or sha(pak) != report['pak_sha256']):
        raise RuntimeError('同款试验包或关闭旧设置的配置未通过核对')
    with install_lock(HERE):
        if equipment.game_running(): raise RuntimeError('请正常退出游戏后再安装同款试验')
        config_path = HERE/'overrides.json'
        if config_path.read_bytes() != expected_config_bytes: raise RuntimeError('设置已变化，保留当前配置')
        state_path = HERE/'installed_patch.json'; old = json.loads(state_path.read_bytes())
        from settings_backups import managed_destination
        current = managed_destination(old)
        actual_sha = sha(current) if current.exists() else None
        if actual_sha != expected_current_sha or (actual_sha is not None and old['pak_sha256'] != actual_sha):
            raise RuntimeError('当前补丁已变化，保留当前状态')
        checkpoint = capture(HERE, '同款替代品生成试验前')
        payload = encode_config(profile)
        try:
            write_atomic(config_path, payload)
            installed = equipment.install(pak, report)
            installed[key] = report[key]
            installed['status'] = 'installed_replacement_batch_waiting_for_drop' if batch else 'installed_replacement_copy_trial_waiting_for_single_drop'
            write_atomic(state_path, (json.dumps(installed, ensure_ascii=False, indent=2)+'\n').encode('utf-8'))
            if config_path.read_bytes() != payload: raise RuntimeError('安装期间配置变化')
            if sha(installed['destination']) != report['pak_sha256']: raise RuntimeError('安装后补丁校验失败')
        except Exception:
            concurrent = config_path.read_bytes() if config_path.read_bytes() != payload else None
            rollback_owned(checkpoint, HERE, [expected_current_sha, report['pak_sha256'], None], concurrent)
            raise
        return {'full_backup': str(checkpoint), 'pak_sha256': report['pak_sha256'], 'trial': report[key]}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    pak, report = build(args.preview, args.output)
    print(json.dumps({'staged': True, 'installed': False, 'pak_sha256': report['pak_sha256'], 'trial': report['replacement_copy_trial']}))
