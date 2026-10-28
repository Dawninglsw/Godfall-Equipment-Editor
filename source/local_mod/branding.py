"""Bundled application artwork supplied by the user. No game-portrait access."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from runtime_paths import HERE,ROOT

APP_NAME='众神陨落-装备编辑器'
APP_ID='GaussTheorem.GodfallEquipmentEditor'
ICON_SHA256='8e30d14b6ab37705c34f4aca55491a066e98588427b34fa3c77bb6e79850ffed'
ICO_SHA256='1a9c56a3bd9182bf7adf029846a109991f6a38ee61e89274d4e5336215c5f02f'
ASSETS=HERE/'assets'
PNG=ASSETS/'app_icon.png'
ICO=ASSETS/'app_icon.ico'


def valid_portrait(path=PNG):
    try:
        data=Path(path).read_bytes()
        return (len(data)<1024*1024 and hashlib.sha256(data).hexdigest()==ICON_SHA256 and
                data[:8]==b'\x89PNG\r\n\x1a\n' and struct.unpack('>II',data[16:24])==(400,400))
    except (OSError,struct.error):return False


def ensure_app_branding():
    """Validate included icons and create a local shortcut. Never open game files."""
    try:
        if not valid_portrait() or hashlib.sha256(ICO.read_bytes()).hexdigest()!=ICO_SHA256:
            raise ValueError('Bundled application icon is missing or damaged')
        shortcut=ROOT/(APP_NAME+'.lnk')
        state=HERE/'local_assets';state.mkdir(exist_ok=True)
        receipt=state/'branding.json'
        expected={'version':2,'source':'bundled_user_image','portrait_sha256':ICON_SHA256,'root':str(ROOT)}
        previous=json.loads(receipt.read_bytes()) if receipt.exists() else None
        if not shortcut.is_file() or previous!=expected:
            import os
            powershell=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
            launcher=ROOT/'Launch.cmd' if (ROOT/'Launch.cmd').is_file() else HERE/'Launch.cmd'
            subprocess.run([str(powershell),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(HERE/'prepare_shortcut.ps1'),
                            '-IconPath',str(ICO),'-ShortcutPath',str(shortcut),'-Launcher',str(launcher)],
                           check=True,capture_output=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            receipt.write_text(json.dumps(expected,ensure_ascii=False,indent=2),encoding='utf-8')
        return {'status':'ready','source':'bundled_user_image','portrait_sha256':ICON_SHA256}
    except Exception:
        import traceback
        try:(HERE/'branding_error.log').write_text(traceback.format_exc(),encoding='utf-8')
        except OSError:pass
        return {'status':'unavailable','log':'branding_error.log'}


def set_process_identity():
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except (AttributeError,OSError):pass


def apply_icon(window):
    try:
        if ICO.is_file():window.iconbitmap(default=str(ICO))
        elif valid_portrait():
            import tkinter
            window._app_icon=tkinter.PhotoImage(master=window,file=str(PNG))
            window.iconphoto(True,window._app_icon)
    except Exception:pass


def header_portrait(window):
    if not valid_portrait():return None
    import tkinter
    return tkinter.PhotoImage(master=window,file=str(PNG)).subsample(12,12)
