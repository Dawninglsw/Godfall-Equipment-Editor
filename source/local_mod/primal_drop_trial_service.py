"""Explicit installation/rollback for the staged trial, with exact baseline pins."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import uuid

import build_local_mod as equipment

HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic(path, raw):
    pending = path.with_suffix(path.suffix + '.pending')
    pending.write_bytes(raw)
    pending.replace(path)


def prepare(output=None):
    output = Path(output) if output else HERE / 'build_primal_drop_trial'
    report_path = output / 'build_report.json'
    report = json.loads(report_path.read_bytes())
    state_path = HERE / 'installed_patch.json'
    state = json.loads(state_path.read_bytes())
    destination = Path(state['destination'])
    if destination.resolve() != (equipment.PAKS / equipment.PAK_NAME).resolve():
        raise RuntimeError('Unexpected managed patch destination')
    if state.get('primal_drop_trial'):
        raise RuntimeError('已有掉率测试补丁，请先恢复上一版再准备新版本')
    if digest(destination) != state['pak_sha256'] or digest(report['pak']) != report['pak_sha256']:
        raise RuntimeError('补丁校验不一致，请保留现有文件')
    config = json.loads((HERE / 'overrides.json').read_bytes())
    if config != state.get('config') or config != report['config']:
        raise RuntimeError('装备设置存在尚未安装的变更，请先核对')
    base = json.loads((output / 'equipment_base/build_report.json').read_bytes())
    if base['pak_sha256'] != state['pak_sha256']:
        raise RuntimeError('装备基线无法逐字节复现，暂不安装掉率试验')
    folder = HERE / 'primal_drop_backups' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'_'+uuid.uuid4().hex[:8])
    folder.mkdir(parents=True)
    shutil.copy2(destination, folder / 'original_managed_patch.pak')
    files = {}
    for name in ['installed_patch.json', 'installed_config_snapshot.json', 'overrides.json']:
        source = HERE / name
        if source.exists():
            shutil.copy2(source, folder / name)
            files[name] = digest(source)
    manifest = {'version': 1, 'status': 'prepared_not_installed', 'destination': str(destination),
                'baseline_sha256': state['pak_sha256'], 'trial_sha256': report['pak_sha256'],
                'report_path': str(report_path), 'report_sha256': digest(report_path), 'files': files,
                'multiplier': report['primal_drop_config']['multiplier'], 'backup_directory': str(folder)}
    (folder / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return folder / 'manifest.json'


def checked(manifest_path):
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_bytes())
    if equipment.game_running():
        raise RuntimeError('请先正常退出游戏，补丁在下次启动时加载')
    destination = Path(manifest['destination'])
    if destination.resolve() != (equipment.PAKS / equipment.PAK_NAME).resolve():
        raise RuntimeError('Unexpected managed patch destination')
    backup = Path(manifest['backup_directory'])
    if backup.resolve() != manifest_path.parent.resolve():
        raise RuntimeError('Backup manifest location mismatch')
    if digest(backup / 'original_managed_patch.pak') != manifest['baseline_sha256']:
        raise RuntimeError('原补丁备份校验失败')
    for name, expected in manifest['files'].items():
        if name not in {'installed_patch.json', 'installed_config_snapshot.json', 'overrides.json'} or digest(backup / name) != expected:
            raise RuntimeError('配置备份校验失败')
    if digest(HERE / 'overrides.json') != manifest['files']['overrides.json']:
        raise RuntimeError('装备设置已更新，请先核对，暂不替换补丁')
    return manifest, destination, backup


def install(manifest_path):
    manifest, destination, backup = checked(manifest_path)
    if digest(destination) != manifest['baseline_sha256']:
        raise RuntimeError('当前补丁已变化，暂不安装')
    if digest(manifest['report_path']) != manifest['report_sha256']:
        raise RuntimeError('试验说明已变化，请重新准备')
    report = json.loads(Path(manifest['report_path']).read_bytes())
    if digest(report['pak']) != manifest['trial_sha256'] or report['pak_sha256'] != manifest['trial_sha256']:
        raise RuntimeError('试验补丁校验失败')
    try:
        state = equipment.install(Path(report['pak']), report)
        state['primal_drop_trial'] = {'version': 1, 'multiplier': manifest['multiplier'],
                                      'manifest': str(manifest_path), 'scope': report['primal_drop_config']['scope']}
        atomic(HERE / 'installed_patch.json', json.dumps(state, ensure_ascii=False, indent=2).encode('utf-8'))
        manifest['status'] = 'installed_awaiting_game_restart'
        atomic(Path(manifest_path), json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8'))
        return state
    except Exception:
        # Roll back only this known baseline/trial while the game is still closed.
        if not equipment.game_running() and destination.exists() and digest(destination) in {manifest['baseline_sha256'], manifest['trial_sha256']}:
            pending = destination.with_suffix('.pending')
            shutil.copy2(backup / 'original_managed_patch.pak', pending)
            pending.replace(destination)
            for name in manifest['files']:
                if name != 'overrides.json':
                    atomic(HERE / name, (backup / name).read_bytes())
        raise


def restore(manifest_path):
    manifest, destination, backup = checked(manifest_path)
    if digest(destination) != manifest['trial_sha256']:
        raise RuntimeError('当前不是这次试验补丁，请先核对')
    old_state = json.loads((backup / 'installed_patch.json').read_bytes())
    equipment.install(backup / 'original_managed_patch.pak', {'pak_sha256': manifest['baseline_sha256'], 'config': old_state['config']})
    for name in manifest['files']:
        if name != 'overrides.json':
            atomic(HERE / name, (backup / name).read_bytes())
    manifest['status'] = 'restored_original_managed_patch'
    atomic(Path(manifest_path), json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8'))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'install', 'restore'])
    parser.add_argument('--manifest', type=Path)
    args = parser.parse_args()
    if args.action == 'prepare':
        print(json.dumps({'manifest': str(prepare()), 'status': 'prepared_not_installed'}))
    elif not args.manifest:
        raise RuntimeError('Manifest required')
    else:
        result = install(args.manifest) if args.action == 'install' else restore(args.manifest)
        print(json.dumps({'status': result.get('status'), 'multiplier': result.get('primal_drop_trial', {}).get('multiplier')}))


if __name__ == '__main__':
    main()
