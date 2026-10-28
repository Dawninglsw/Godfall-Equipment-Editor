"""Attach an existing byte-identical base reader without writing to the game."""
import json
from pathlib import Path
import uuid

import build_local_mod as builder
from editor_model import HERE,write_atomic
from prepare_resources import validate_installation
from runtime_paths import game_directory,node_executable
from settings_backups import install_lock,managed_destination,sha


def attach_existing_base_reader():
    record=HERE/'installed_patch.json'
    if record.exists():return False
    destination=managed_destination()
    if not destination.is_file():return False
    with install_lock(HERE):
        if record.exists():return False
        initial_hash=sha(destination)
        validate_installation(game_directory(),node_executable())
        folder=HERE/'reader_setup'/uuid.uuid4().hex;folder.mkdir(parents=True)
        clean={'version':1,'enabled':False,'items':[],'traitReplacements':[],
               'primalDrop':{'enabled':False,'multiplier':2,'scope':'tower_chest_primal_bonus'}}
        config=folder/'clean_config.json';config.write_text(json.dumps(clean),encoding='utf-8')
        _,report=builder.build(config_path=config,output_dir=folder/'base')
        if (report.get('config')!=clean or not report.get('inventory_readout') or
                initial_hash!=report['pak_sha256'] or sha(destination)!=initial_hash):
            raise RuntimeError('检测到其他本地补丁，不能自动接管。请正常退出游戏，用原工具停用其补丁，再在本工具“设置”中安装基础读取组件。')
        state={'destination':str(destination),'pak_sha256':initial_hash,'config':clean,
               'inventory_readout':report['inventory_readout'],'primal_drop':clean['primalDrop'],
               'original_resources_overwritten':False,'status':'attached_existing_exact_base_reader',
               'verification':'recompiled_clean_base_matches_existing_file','verification_report':str(folder/'base/build_report.json')}
        payload=json.dumps(state,ensure_ascii=False,indent=2).encode('utf-8')
        snapshot=HERE/'installed_config_snapshot.json'
        snapshot_payload=json.dumps({'pak_sha256':initial_hash,'config':clean,'primal_drop':clean['primalDrop']},ensure_ascii=False,indent=2).encode('utf-8')
        previous_snapshot=snapshot.read_bytes() if snapshot.exists() else None
        if previous_snapshot is not None:(folder/'previous_installed_config_snapshot.json').write_bytes(previous_snapshot)
        pending=folder/'installed_patch.pending'
        pending.write_bytes(payload)
        created=False
        try:
            if sha(destination)!=initial_hash:raise RuntimeError('核对期间补丁发生变化，未建立读取记录。')
            pending.rename(record)  # Windows refuses an existing target; never overwrite another record.
            created=True
            write_atomic(snapshot,snapshot_payload)
            if sha(destination)!=initial_hash or record.read_bytes()!=payload:
                raise RuntimeError('建立记录期间补丁或安装记录发生变化，已停止。')
        except Exception:
            if created and record.exists() and record.read_bytes()==payload:record.unlink()
            if created and snapshot.exists() and snapshot.read_bytes()==snapshot_payload:
                if previous_snapshot is None:snapshot.unlink()
                else:write_atomic(snapshot,previous_snapshot)
            raise
        return True
