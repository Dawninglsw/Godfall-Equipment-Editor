"""Backed-up portable-profile reset. Game saves and acquired items are never opened."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import uuid

import build_local_mod as builder
from editor_model import HERE,ROOT,write_atomic
from prepare_resources import validate_installation
from runtime_paths import game_directory,node_executable
from settings_backups import install_lock,sha

FILES={'application_settings.json','overrides.json','item_labels.json','known_good_release.json',
       'inventory_snapshot.json','equipment_catalogue.json','browser_preferences.json','user_preferences.json',
       'replacement_plan.json','batch_plan.json','batch_draft.json','uncurse_plan.json',
       'installed_patch.json','installed_config_snapshot.json','resource_preparation.json'}
DIRECTORIES={'backups','settings_backups','config_backups','schemes','drop_history','reader_setup',
             'replacement_builds','batch_builds','uncurse_builds','unified_builds','primal_drop_backups',
             'batch_draft_backups','replacement_plan_backups','local_assets','build'}


def clean_config():
    return {'version':1,'enabled':False,'items':[],'traitReplacements':[],
            'primalDrop':{'enabled':False,'multiplier':2,'scope':'tower_chest_primal_bonus'}}


def checked_path(path,parent):
    path=Path(path);parent=Path(parent).resolve()
    if not path.resolve().is_relative_to(parent) or path.resolve()==parent:
        raise RuntimeError('初始化路径超出本工具目录，已停止。')
    if path.exists():
        entries=[path,*path.rglob('*')] if path.is_dir() else [path]
        if any(p.is_symlink() or bool(getattr(p.lstat(),'st_file_attributes',0)&0x400) for p in entries):
            raise RuntimeError('初始化目录含链接或重定向，已停止。')
    return path


def reset_targets():
    targets=[]
    for p in HERE.iterdir():
        if (p.is_file() and (p.name in FILES or p.name.endswith('_error.log') or p.name=='launcher_error.log') or
            p.is_dir() and (p.name in DIRECTORIES or p.name.startswith('build_'))):targets.append(p)
    analysis=ROOT/'analysis'
    for name in ['runtime_calibration.json','calibration_history','equipment_snapshots','live_equipped_weapons.json',
                 'inventory_read_diagnostic.json','last_victory_inventory_records.json','journeyman_ring_records.json',
                 'session_20261025/true_strike_inventory_records.json','session_20261025/betrayer_amulet_after_reequip.json',
                 'session_20261025/conquest_after_equip_inventory.json','session_20261025/equipment_cache_snapshot.json']:
        p=analysis/name
        if p.exists():targets.append(p)
    shortcut=ROOT/'众神陨落-装备编辑器.lnk'
    if shortcut.exists():targets.append(shortcut)
    return [checked_path(p,ROOT) for p in targets]


def initialize_profile(ui_draft=None):
    if not (ROOT/'PACKAGE_MANIFEST.json').is_file() or not (ROOT/'runtime/python/python.exe').is_file():
        raise RuntimeError('初始化仅适用于完整分享包的工具目录。')
    if builder.game_running():raise RuntimeError('请先正常退出游戏，再初始化工具。')
    with install_lock(HERE):
        if builder.game_running():raise RuntimeError('请先正常退出游戏，再初始化工具。')
        targets=reset_targets()
        base=clean_config();destination=builder.PAKS/builder.PAK_NAME
        current_hash=sha(destination) if destination.exists() else None
        state_path=HERE/'installed_patch.json'
        state=json.loads(state_path.read_bytes()) if state_path.exists() else None
        if state and Path(state['destination']).resolve()!=destination.resolve():
            raise RuntimeError('安装记录与游戏目录不一致，未执行初始化。')
        backup_root=checked_path(ROOT/'初始化备份',ROOT);backup_root.mkdir(exist_ok=True)
        backup=backup_root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'_'+uuid.uuid4().hex[:8]);backup.mkdir()
        plan={'version':1,'status':'preparing','game_save_accessed':False,'data_targets':[str(p.relative_to(ROOT)) for p in targets]}
        manifest=backup/'reset_manifest.json'
        def note(status):
            plan['status']=status;manifest.write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
        note('preparing')
        base_pak=report=None
        if current_hash is not None:
            validate_installation(game_directory(),node_executable())
            cfg=backup/'clean_config.json';cfg.write_text(json.dumps(base),encoding='utf-8')
            base_pak,report=builder.build(config_path=cfg,output_dir=backup/'base_reader')
            if report.get('config')!=base or not report.get('inventory_readout'):
                raise RuntimeError('基础读取组件核对未通过，未执行初始化。')
            if current_hash!=report['pak_sha256'] and (not state or state.get('pak_sha256')!=current_hash):
                raise RuntimeError('游戏补丁不属于可核对的本工具状态，未执行初始化。')
            shutil.copy2(destination,backup/'game_patch_before_reset.pak')
            if sha(backup/'game_patch_before_reset.pak')!=current_hash:raise RuntimeError('初始化备份核对未通过。')
        plan.update(game_patch_before=current_hash,base_reader_sha256=report['pak_sha256'] if report else None)
        original={}
        for p in targets:
            if p.is_file():
                relative=p.relative_to(ROOT);saved=backup/'original_files'/relative;saved.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(p,saved);original[relative]=saved
                if sha(p)!=sha(saved):raise RuntimeError('初始化前文件发生变化，已停止。')
        if ui_draft is not None:(backup/'unsaved_main_draft.json').write_text(json.dumps(ui_draft,ensure_ascii=False,indent=2),encoding='utf-8')
        moved=[];written={};installer_files={};defaults={HERE/'overrides.json':base,HERE/'application_settings.json':{'version':1,'language':'en'},
            HERE/'item_labels.json':{},HERE/'known_good_release.json':{'mode':'original_game','config':base}}
        try:
            if current_hash is not None and current_hash!=report['pak_sha256']:
                if sha(destination)!=current_hash:raise RuntimeError('游戏补丁在初始化前发生变化，已停止。')
                builder.install(base_pak,report)
                for name in ['installed_patch.json','installed_config_snapshot.json']:
                    p=HERE/name
                    if p.exists():installer_files[p.relative_to(ROOT)]=p.read_bytes()
            note('archiving')
            # Include the installer's newly created backup/receipt, but retain
            # the original receipts separately for a complete rollback.
            for source in reset_targets():
                target=checked_path(backup/'data'/source.relative_to(ROOT),backup)
                target.parent.mkdir(parents=True,exist_ok=True)
                if builder.game_running():raise RuntimeError('检测到游戏启动，初始化已停止。')
                source.rename(target);moved.append((source,target))
            for path,value in defaults.items():
                payload=json.dumps(value,ensure_ascii=False,indent=2).encode('utf-8')
                write_atomic(path,payload);written[path]=payload
            if current_hash is not None and sha(destination)!=report['pak_sha256']:
                raise RuntimeError('初始化期间游戏补丁发生变化，已停止。')
            plan['archived_entries']=len(moved);note('complete')
        except Exception as error:
            # Never replace a concurrent third-party patch or modify an open game.
            if current_hash is not None and destination.exists() and sha(destination)!=current_hash:
                if not builder.game_running() and sha(destination)==report['pak_sha256']:
                    pending=destination.with_suffix('.reset-rollback');shutil.copy2(backup/'game_patch_before_reset.pak',pending)
                    if sha(pending)!=current_hash:raise RuntimeError('初始化恢复校验失败；请保留初始化备份。')
                    pending.replace(destination)
            for path,payload in written.items():
                if path.exists() and path.read_bytes()==payload:path.unlink()
            for source,target in reversed(moved):
                if not source.exists():target.rename(source)
            for relative,saved in original.items():
                target=ROOT/relative
                if not target.exists():
                    target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(saved,target)
                elif target.is_file() and target.read_bytes()==installer_files.get(relative):shutil.copy2(saved,target)
            if current_hash is not None and destination.exists() and sha(destination)!=current_hash:
                plan['game_patch_restore_pending']=True;note('rollback_requires_game_exit')
            else:note('rolled_back')
            raise RuntimeError('初始化未完成，备份目录：'+str(backup)+'。'+str(error)) from error
        message='初始化完成。已备份并清空工具数据；基础读取组件保留，其他本工具修改已关闭。请重新打开工具完成首次设置。' if current_hash is not None else '初始化完成。已备份并清空工具数据。请重新打开工具完成首次设置，并安装基础读取组件。'
        return {'backup':str(backup),'message':message,
                'game_patch_changed':current_hash is not None and current_hash!=report['pak_sha256']}
