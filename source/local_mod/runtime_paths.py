"""User-selectable local paths, with bundled-runtime and Steam discovery."""
import json
import os
from pathlib import Path
import re
import shutil
import uuid

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
SETTINGS=HERE/'application_settings.json'


def load_settings():
    try:
        if SETTINGS.stat().st_size>65536:return {}
        value=json.loads(SETTINGS.read_bytes())
        return value if isinstance(value,dict) and value.get('version')==1 else {}
    except (OSError,ValueError):return {}


def save_settings(changes):
    value={**load_settings(),**changes,'version':1}
    allowed={'version','language','game_directory','node_executable','python_executable'}
    if set(value)-allowed:raise ValueError('Unknown application setting')
    if value.get('language','zh-CN') not in {'zh-CN','en'}:raise ValueError('Unsupported language')
    if any(not isinstance(v,str) or len(v)>4096 for k,v in value.items() if k!='version'):raise ValueError('Invalid application setting')
    pending=SETTINGS.with_name(SETTINGS.name+'.'+uuid.uuid4().hex+'.writing')
    try:
        pending.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');pending.replace(SETTINGS)
    finally:
        if pending.exists():pending.unlink()
    return value


def valid_game(path):
    root=Path(path)
    return (root/'Aperion/Binaries/Win64/Aperion-Win64-Shipping.exe').is_file() and (root/'Aperion/Content/Paks/pakchunk0-WindowsNoEditor.pak').is_file()


def steam_games():
    roots=[]
    try:
        import winreg
        for hive,key,name in [(winreg.HKEY_CURRENT_USER,r'Software\Valve\Steam','SteamPath'),
                              (winreg.HKEY_LOCAL_MACHINE,r'Software\WOW6432Node\Valve\Steam','InstallPath')]:
            try:
                with winreg.OpenKey(hive,key) as handle:roots.append(Path(winreg.QueryValueEx(handle,name)[0]))
            except OSError:pass
    except ImportError:pass
    roots.extend([Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'Steam',Path('D:/Steam')])
    libraries=list(roots)
    for root in roots:
        file=root/'steamapps/libraryfolders.vdf'
        if file.is_file():
            for value in re.findall(r'"path"\s+"([^"\r\n]+)"',file.read_text(encoding='utf-8',errors='replace')):
                libraries.append(Path(value.replace('\\\\','\\')))
    seen=set()
    for library in libraries:
        game=library/'steamapps/common/Godfall'
        if str(game).casefold() not in seen and valid_game(game):
            seen.add(str(game).casefold());yield game


def game_directory():
    configured=os.environ.get('GODFALL_GAME_DIRECTORY') or load_settings().get('game_directory')
    if configured:return Path(configured).expanduser().resolve()
    return next(steam_games(),ROOT/'GAME_NOT_CONFIGURED')


def node_executable():
    bundled=ROOT/'runtime/node/node.exe'
    if bundled.is_file():return bundled
    configured=os.environ.get('GODFALL_NODE_EXECUTABLE') or load_settings().get('node_executable')
    if configured:return Path(configured).expanduser().resolve()
    located=shutil.which('node')
    return Path(located) if located else ROOT/'NODE_NOT_CONFIGURED.exe'
