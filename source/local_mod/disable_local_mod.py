"""Disable only this exact installed patch by moving it to the workspace."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
from build_local_mod import game_running,PAKS,PAK_NAME

HERE=Path(__file__).resolve().parent
record=HERE/'installed_patch.json'
state=json.loads(record.read_bytes())
if game_running():
    raise RuntimeError('请先正常退出游戏，再停用本地补丁')
expected=(PAKS/PAK_NAME).resolve()
source=Path(state['destination']).resolve()
if source!=expected:
    raise RuntimeError('Installation path differs from the one exact managed patch')
if source.exists():
    if hashlib.sha256(source.read_bytes()).hexdigest()!=state['pak_sha256']:
        raise RuntimeError('Patch changed independently; refusing to move')
    destination=HERE/'disabled'
    destination.mkdir(exist_ok=True)
    target=destination/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+source.name)
    shutil.move(str(source),str(target))
    state.update(status='disabled_restart_required',disabled_file=str(target))
else:
    state['status']='already_absent'
record.write_text(json.dumps(state,indent=2),encoding='utf-8')
print(json.dumps(state))
