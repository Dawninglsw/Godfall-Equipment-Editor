"""Local settings operations. No gameplay actions or server requests."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from build_local_mod import game_running, install as install_pak
from editor_model import HERE, ROOT, backup_config, encode_config, validate_config, write_atomic
from primal_drop_settings import primal_preferences, with_primal


def installation_state():
    try:
        return json.loads((HERE/'installed_patch.json').read_bytes())
    except (OSError, ValueError):
        return {}


def editor_config(config):
    """Migrate legacy trial preferences into the draft only, without writing files."""
    return with_primal(config, installation_state())


def run_local(script, arguments=(), timeout=90):
    python = Path(sys.executable)
    if python.stem.lower() == 'pythonw' and python.with_name('python.exe').is_file():
        python = python.with_name('python.exe')
    result = subprocess.run([str(python), str(script), *map(str, arguments)],
                            capture_output=True, encoding='utf-8', errors='replace', timeout=timeout,
                            env={**os.environ, 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8'},
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(detail.splitlines()[-1] if detail else '操作未完成')
    return result.stdout


def installed_config():
    try:
        state = json.loads((HERE/'installed_patch.json').read_bytes())
        destination = Path(state['destination'])
        if not destination.exists():
            return None, '本地补丁已停用'
        if hashlib.sha256(destination.read_bytes()).hexdigest() != state['pak_sha256']:
            return None, '安装文件发生变化，请先核对'
        config = state.get('config')
        if config is None:
            snapshot = json.loads((HERE/'installed_config_snapshot.json').read_bytes())
            if snapshot['pak_sha256'] == state['pak_sha256']:
                config = snapshot['config']
        if config is None:
            return None, '本地补丁已安装；尚无完整设置快照'
        result = deepcopy(validate_config(config))
        if 'primalDrop' in result or state.get('primal_drop') or state.get('primal_drop_trial'):
            result = with_primal(result, state)
        return result, '当前本地补丁已安装'
    except (OSError, ValueError, KeyError, TypeError):
        return None, '未找到可核对的安装记录'


def install_draft(config, expected_bytes):
    """Install only after game exit; back up and restore configuration on failure."""
    from settings_backups import install_lock
    if not (HERE/'installed_patch.json').exists() and not game_running():
        from reader_setup import attach_existing_base_reader
        attach_existing_base_reader()
    with install_lock(HERE):
        return _install_draft(config, expected_bytes)


def _install_draft(config, expected_bytes):
    if game_running():
        raise RuntimeError('请先正常退出游戏，再保存并安装')
    config_path = HERE/'overrides.json'
    if config_path.read_bytes() != expected_bytes:
        raise RuntimeError('设置已在别处更新，请关闭旧窗口后重新打开')
    state = installation_state()
    if 'primalDrop' in config or state.get('primal_drop') or state.get('primal_drop_trial'):
        config = with_primal(config, state)
    new_bytes = encode_config(config)
    from settings_backups import capture, rollback_owned, sha
    full_backup = capture(HERE) if (HERE/'installed_patch.json').exists() else None
    backup = backup_config(expected_bytes)
    output = HERE/'unified_builds'/uuid.uuid4().hex
    write_atomic(config_path, new_bytes)
    try:
        run_local(HERE/'build_local_mod.py', ['--install', '--output', output], timeout=60)
        if config_path.read_bytes() != new_bytes:
            raise RuntimeError('安装期间设置在别处更新，请重新打开工具核对')
        if full_backup:
            report = json.loads((output/'build_report.json').read_bytes())
            current = installation_state()
            if (current.get('config') != config or current.get('pak_sha256') != report['pak_sha256'] or
                    sha(current['destination']) != report['pak_sha256']):
                raise RuntimeError('安装后核对未通过')
    except Exception:
        if full_backup:
            old = json.loads(full_backup.read_bytes())
            allowed = [old['pak_sha256'], None]
            report_path = output/'build_report.json'
            if report_path.exists():
                report = json.loads(report_path.read_bytes())
                if report.get('config') == config:
                    allowed.append(report['pak_sha256'])
            concurrent = config_path.read_bytes() if config_path.read_bytes() != new_bytes else None
            rollback_owned(full_backup, HERE, allowed, concurrent)
        # Do not overwrite a concurrent edit from another window.
        if config_path.read_bytes() == new_bytes:
            write_atomic(config_path, expected_bytes)
        raise
    return {'config_bytes': new_bytes, 'config': config, 'config_backup': str(backup),
            'full_backup': str(full_backup) if full_backup else None,
            'message': '装备与原始掉落设置已一起保存并安装。下次启动游戏时生效。'}


def disable_patch():
    if game_running():
        raise RuntimeError('请先正常退出游戏，再停用补丁')
    from settings_backups import capture, install_lock
    with install_lock(HERE):
        full_backup = capture(HERE) if (HERE/'installed_patch.json').exists() else None
        try:
            run_local(HERE/'disable_local_mod.py', timeout=30)
        except Exception:
            if full_backup:
                from settings_backups import rollback_owned
                old = json.loads(full_backup.read_bytes())
                rollback_owned(full_backup, HERE, [old['pak_sha256'], None], (HERE/'overrides.json').read_bytes())
            raise
    return {'full_backup': str(full_backup) if full_backup else None,
            'message': '全部本地补丁已停用。下次启动使用原版装备与掉落；草稿保留。'}


def scan_catalogue():
    if not game_running():
        raise RuntimeError('请先启动游戏，并在兵器库查看想编辑的装备')
    if not (HERE/'installed_patch.json').exists():
        from reader_setup import attach_existing_base_reader
        attach_existing_base_reader()
    current, _ = installed_config()
    if current is None or not installation_state().get('inventory_readout'):
        raise RuntimeError('尚未安装可核对的兵器库读取组件。请正常退出游戏，在主窗口“设置”中点击“安装基础读取组件”，再启动游戏并刷新。')
    run_local(ROOT/'analysis/recalibrate_runtime.py', timeout=15)
    run_local(ROOT/'analysis/read_inventory_snapshot.py', ['--out', HERE/'inventory_snapshot.json'], timeout=60)
    from inventory_snapshot import load_snapshot
    snapshot = load_snapshot()
    if not snapshot:
        raise RuntimeError('读取结果未通过完整性核对，请重试。')
    manifest = snapshot['manifest']
    incomplete = manifest['omitted'] or not all(manifest['collections'].values())
    return {'message': f'已读取 {len(snapshot["items"])} 件装备与强化物、{len(manifest["plates"])} 套战甲的配装。'
            + ('清单有缺项，请按部分清单核对。' if incomplete else '可选择范围、筛选和排序；这是读取时的界面快照。')}


def restore_verified_release(expected_bytes):
    """Restore the latest exact package and configuration verified in the game."""
    from settings_backups import capture, install_lock, rollback_owned
    with install_lock(HERE):
        if game_running():
            raise RuntimeError('请先正常退出游戏，再恢复原始设置')
        if (HERE/'overrides.json').read_bytes() != expected_bytes:
            raise RuntimeError('设置已在别处更新，请重新打开窗口')
        checkpoint = capture(HERE, '恢复原始设置前自动备份') if (HERE/'installed_patch.json').exists() else None
        try:
            result = _restore_verified_release(expected_bytes)
            result['full_backup'] = str(checkpoint) if checkpoint else None
            return result
        except Exception:
            if checkpoint:
                old = json.loads(checkpoint.read_bytes())
                release = json.loads((HERE/'known_good_release.json').read_bytes())
                rollback_owned(checkpoint, HERE, [old['pak_sha256'], release.get('pak_sha256'), None],
                               (HERE/'overrides.json').read_bytes())
            raise


def _restore_verified_release(expected_bytes):
    if game_running():
        raise RuntimeError('请先正常退出游戏，再恢复已验证补丁')
    release = json.loads((HERE/'known_good_release.json').read_bytes())
    if release.get('mode') == 'original_game':
        config_path = HERE/'overrides.json'
        if config_path.read_bytes() != expected_bytes:
            raise RuntimeError('设置已在别处更新，请重新打开窗口')
        config = deepcopy(release['config'])
        if config.get('enabled') is not False or config.get('items') != []:
            raise ValueError('原始设置恢复点不正确')
        from primal_drop_settings import default_primal
        config['primalDrop'] = default_primal()
        payload = encode_config(config)
        backup = backup_config(expected_bytes)
        write_atomic(config_path, payload)
        try:
            run_local(HERE/'disable_local_mod.py', timeout=30)
        except Exception:
            if config_path.read_bytes() == payload:
                write_atomic(config_path, expected_bytes)
            raise
        return {'config_bytes': payload, 'config': config, 'config_backup': str(backup),
                'message': '已恢复原始设置并清空默认修改。下次启动游戏后生效，旧方案仍保留在备份中。'}
    digest = release['pak_sha256']
    if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('已验证补丁的记录不正确')
    pak = HERE/'releases'/(digest+'.pak')
    if hashlib.sha256(pak.read_bytes()).hexdigest() != digest:
        raise RuntimeError('已验证补丁的备份文件不完整')
    config_path = HERE/'overrides.json'
    if config_path.read_bytes() != expected_bytes:
        raise RuntimeError('设置已在别处更新，请重新打开窗口')
    payload = encode_config(release['config'])
    backup = backup_config(expected_bytes)
    write_atomic(config_path, payload)
    try:
        install_pak(pak, {'pak_sha256': digest, 'config': release['config']})
    except Exception:
        if config_path.read_bytes() == payload:
            write_atomic(config_path, expected_bytes)
        raise
    rules = len(release['config']['items'])
    equipment = len({r['id'] for r in release['config']['items']})
    return {'config_bytes': payload, 'config': release['config'], 'config_backup': str(backup),
            'message': f'已恢复验证版本：{equipment}件装备、{rules}条设置。下次启动游戏后生效。'}


def configuration_summary(config):
    types = config.get('traitReplacements', [])
    return {'enabled': config['enabled'], 'rules': len(config['items']) + len(types),
            'equipment': len({r['id'] for r in config['items']} | {r['sourceItem']['id'] for r in types}),
            'primal': primal_preferences(config)}


def full_settings_backups():
    from settings_backups import list_backups
    return list_backups(HERE)


def restore_full_settings(manifest_path, expected_bytes):
    from settings_backups import restore_backup
    return restore_backup(manifest_path, expected_bytes, HERE)
