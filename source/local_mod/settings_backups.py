"""Complete managed-patch checkpoints and verified restore. No live memory access."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import msvcrt
from pathlib import Path
import shutil
import uuid

import build_local_mod as builder
from editor_model import encode_config, validate_config, write_atomic
from primal_drop_settings import with_primal

FILES = ('overrides.json', 'installed_patch.json', 'installed_config_snapshot.json')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@contextmanager
def install_lock(here):
    path = Path(here) / 'settings_install.lock'
    with path.open('a+b') as handle:
        if path.stat().st_size == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise RuntimeError('另一个窗口正在保存或恢复，请等它完成') from None
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def managed_destination(state=None):
    expected = (builder.PAKS / builder.PAK_NAME).resolve()
    if state and Path(state['destination']).resolve() != expected:
        raise RuntimeError('安装记录指向了其他补丁，暂不操作')
    return expected


def capture(here, reason='安装前自动备份'):
    here = Path(here)
    state_path = here / 'installed_patch.json'
    state = json.loads(state_path.read_bytes()) if state_path.exists() else {}
    destination = managed_destination(state)
    active = destination.exists()
    if active and (not state or sha(destination) != state.get('pak_sha256')):
        raise RuntimeError('当前补丁与安装记录不一致，暂不备份或替换')
    config = validate_config(json.loads((here / 'overrides.json').read_bytes()))
    folder = here / 'settings_backups' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'_'+uuid.uuid4().hex[:8])
    folder.mkdir(parents=True)
    hashes = {}
    for name in FILES:
        source = here / name
        if source.exists():
            shutil.copy2(source, folder / name)
            hashes[name] = sha(folder / name)
            if hashes[name] != sha(source):
                raise RuntimeError('备份时设置发生变化，请重新打开工具')
    pak_hash = None
    if active:
        shutil.copy2(destination, folder / 'managed_patch.pak')
        pak_hash = sha(folder / 'managed_patch.pak')
        if pak_hash != state['pak_sha256']:
            raise RuntimeError('补丁备份未通过校验')
    manifest = {'version': 1, 'created_utc': datetime.now(timezone.utc).isoformat(), 'reason': reason,
                'active_package': active, 'destination': str(destination), 'pak_sha256': pak_hash,
                'files': hashes, 'effective_config': with_primal(config, state)}
    write_atomic(folder / 'manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8'))
    return folder / 'manifest.json'


def validate_backup(manifest_path, here):
    manifest_path, here = Path(manifest_path), Path(here)
    if not manifest_path.resolve().is_relative_to((here / 'settings_backups').resolve()):
        raise RuntimeError('请选择本工具的完整备份')
    manifest = json.loads(manifest_path.read_bytes())
    if manifest.get('version') != 1 or type(manifest.get('active_package')) is not bool:
        raise ValueError('完整备份格式不正确')
    if Path(manifest['destination']).resolve() != managed_destination():
        raise ValueError('备份中的补丁位置不一致')
    if 'overrides.json' not in manifest['files']:
        raise ValueError('备份缺少设置')
    for name, digest in manifest['files'].items():
        if name not in FILES or sha(manifest_path.parent / name) != digest:
            raise RuntimeError('备份文件校验失败，未进行恢复')
    if manifest['active_package'] and sha(manifest_path.parent / 'managed_patch.pak') != manifest['pak_sha256']:
        raise RuntimeError('备份补丁校验失败，未进行恢复')
    validate_config(manifest['effective_config'])
    return manifest


def list_backups(here):
    rows = []
    for path in sorted((Path(here) / 'settings_backups').glob('*/manifest.json'), reverse=True):
        try:
            data = json.loads(path.read_bytes())
            if data.get('version') == 1:
                rows.append({**data, 'manifest_path': str(path)})
        except (OSError, ValueError):
            continue
    return rows


def _restore_raw(manifest_path, here, allowed_current=None):
    """Caller holds installation lock and has verified the current package owner."""
    manifest = validate_backup(manifest_path, here)
    folder, here = Path(manifest_path).parent, Path(here)
    destination = managed_destination()
    def check_owner():
        current = sha(destination) if destination.exists() else None
        if allowed_current is not None and current not in set(allowed_current):
            raise RuntimeError('当前补丁在操作期间变化，未覆盖它')
    check_owner()
    if builder.game_running():
        raise RuntimeError('游戏已启动，暂不恢复补丁')
    if manifest['active_package']:
        pending = destination.with_suffix('.pending')
        shutil.copy2(folder / 'managed_patch.pak', pending)
        if sha(pending) != manifest['pak_sha256']:
            raise RuntimeError('恢复文件核对失败')
        if builder.game_running():
            raise RuntimeError('游戏已启动，暂不恢复补丁')
        check_owner()
        pending.replace(destination)
    elif destination.exists():
        disabled = here / 'disabled'
        disabled.mkdir(exist_ok=True)
        target = disabled / (uuid.uuid4().hex + '_' + builder.PAK_NAME)
        if builder.game_running():
            raise RuntimeError('游戏已启动，暂不停用补丁')
        check_owner()
        destination.replace(target)
    for name in FILES:
        target = here / name
        if name in manifest['files']:
            write_atomic(target, (folder / name).read_bytes())
        elif target.exists():
            target.unlink()
    return manifest


def rollback_owned(manifest_path, here, allowed_hashes, preserve_config_bytes=None):
    """Never roll back an unrelated patch or a concurrent configuration edit."""
    if builder.game_running():
        return False
    destination = managed_destination()
    current = sha(destination) if destination.exists() else None
    if current not in set(allowed_hashes):
        return False
    _restore_raw(manifest_path, here, allowed_hashes)
    if preserve_config_bytes is not None:
        write_atomic(Path(here) / 'overrides.json', preserve_config_bytes)
    return True


def restore_backup(manifest_path, expected_bytes, here):
    here = Path(here)
    with install_lock(here):
        if builder.game_running():
            raise RuntimeError('请先正常退出游戏，再恢复完整备份')
        if (here / 'overrides.json').read_bytes() != expected_bytes:
            raise RuntimeError('设置已在别处更新，请重新打开窗口')
        target = validate_backup(manifest_path, here)
        checkpoint = capture(here, '恢复完整备份前自动备份')
        previous = json.loads(checkpoint.read_bytes())
        try:
            _restore_raw(manifest_path, here, [previous['pak_sha256']])
        except Exception:
            current_config = (here / 'overrides.json').read_bytes()
            owned = [expected_bytes, (Path(manifest_path).parent / 'overrides.json').read_bytes()]
            rollback_owned(checkpoint, here, [previous['pak_sha256'], target['pak_sha256'], None],
                           current_config if current_config not in owned else None)
            raise
        payload = (here / 'overrides.json').read_bytes()
        return {'config_bytes': payload, 'config': target['effective_config'], 'full_backup': str(checkpoint),
                'message': '完整备份已恢复，装备与原始掉落设置一起恢复。下次启动游戏时生效。'}
