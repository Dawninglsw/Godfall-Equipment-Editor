"""Prepare version-checked resources from the player's own installation, locally."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from runtime_paths import ROOT,HERE,valid_game

EXPECTED_EXE='301f90fc4f6119b64f7ef51971f6083264c4f4878500f5cd52341e4eb673b834'
EXPECTED_UI='64664d49813494ae73886ff6d2154b4672cdd7c89867ddcc5569e68e38c729ae'
EXPECTED_TABLES='20787b0ed6249963dc200c5fa2e99f85f2001ca5fba54278e96723e42a3fbfcb'


def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def validate_installation(game,node):
    game=Path(game).resolve();node=Path(node).resolve()
    if not valid_game(game):raise ValueError('请选择包含 Aperion 文件夹的 Godfall 游戏目录。')
    if not node.is_file():raise ValueError('未找到 Node.js 运行环境，请选择 node.exe。')
    exe=game/'Aperion/Binaries/Win64/Aperion-Win64-Shipping.exe'
    if digest(exe)!=EXPECTED_EXE:raise ValueError('游戏版本尚未验证，已停止准备；未安装任何补丁。')
    result=subprocess.run([str(node),'--version'],check=True,capture_output=True,text=True,timeout=15,
                          creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if not result.stdout.strip().startswith('v'):raise ValueError('Node.js 运行环境无效。')
    return {'game_directory':str(game),'exe_sha256':EXPECTED_EXE,'node_version':result.stdout.strip()}


def prepare(game,node):
    report=validate_installation(game,node)
    extracted=ROOT/'analysis/extracted';extracted.mkdir(parents=True,exist_ok=True)
    original=extracted/'main.c05310c4.chunk.js';tables=extracted/'source_data.json'
    if not original.is_file() or not tables.is_file() or digest(original)!=EXPECTED_UI or (EXPECTED_TABLES and digest(tables)!=EXPECTED_TABLES):
        sys.path.insert(0,str(ROOT/'analysis'))
        from inspect_resources import inspect_pak
        with tempfile.TemporaryDirectory(prefix='prepare_',dir=extracted.parent) as folder:
            result=inspect_pak(Path(game)/'Aperion/Content/Paks/pakchunk0-WindowsNoEditor.pak',extract_to=Path(folder))
            raw=Path(folder)/original.name;data=Path(folder)/tables.name
            if not raw.is_file() or digest(raw)!=EXPECTED_UI or not data.is_file() or (EXPECTED_TABLES and digest(data)!=EXPECTED_TABLES):
                raise ValueError('原版界面资源与已验证版本不一致，未安装补丁。')
            checked=json.loads(data.read_bytes())
            if not all(key in checked for key in ['trait','weapons','augments','valorplates']):raise ValueError('游戏数据表不完整。')
            raw.replace(original);data.replace(tables)
    if not all((HERE/name).is_file() for name in ['chinese_item_names.json','chinese_trait_labels.json','english_trait_labels.json']):
        subprocess.run([str(node),str(ROOT/'analysis/build_chinese_item_names.cjs')],check=True,capture_output=True,timeout=60,
                       creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    report.update(ui_sha256=digest(original),tables_sha256=digest(tables),status='resources_prepared_no_game_writes')
    (HERE/'resource_preparation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report
