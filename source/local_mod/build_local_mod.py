"""Build an independent V11 pak with an exact-version UI script override.

Pak field layout references: trumank/repak's footer.rs, entry.rs and pak.rs.
Game assets are read from the previously SHA1-verified extraction. Originals
are never overwritten. Default writes only to this workspace; --install adds
the one identified patch file after local verification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys
from editor_model import validate_config
from trait_types import compile_requests
from primal_drop_settings import primal_preferences
from runtime_paths import game_directory

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT/'analysis'))
from inspect_resources import inspect_pak

ORIGINAL = ROOT/'analysis/extracted/main.c05310c4.chunk.js'
EXPECTED = '64664d49813494ae73886ff6d2154b4672cdd7c89867ddcc5569e68e38c729ae'
PAK_NAME = 'pakchunk99-GodfallEquipment_P.pak'
PAKS = game_directory()/'Aperion/Content/Paks'
VIRTUAL = 'Aperion/Content/uiresources/static/js/main.c05310c4.chunk.js'


def string(text):
    data = text.encode('utf-8')+b'\0'
    return struct.pack('<i', len(data))+data


def path_hash(path):
    value = 0xcbf29ce484222325
    for byte in path.lower().encode('utf-16le'):
        value = ((value ^ byte)*0x100000001b3) & 0xffffffffffffffff
    return value


def make_pak(path, data):
    digest = hashlib.sha1(data).digest()
    record = struct.pack('<QQQI20sBI', 0, len(data), len(data), 0, digest, 0, 0)
    assert len(record) == 53
    index_offset = len(record)+len(data)
    encoded = struct.pack('<III', 0xe0000000, 0, len(data))
    phi = struct.pack('<IQII', 1, path_hash(VIRTUAL), 0, 0)
    parts = VIRTUAL.split('/')
    directories = ['/']+['/'.join(parts[:i])+'/' for i in range(1, len(parts))]
    fdi = struct.pack('<I', len(directories))
    for directory in sorted(directories):
        fdi += string(directory)
        leaf = directory == '/'.join(parts[:-1])+'/'
        fdi += struct.pack('<I', int(leaf))
        if leaf:
            fdi += string(parts[-1])+struct.pack('<i', 0)
    def header(phi_offset, fdi_offset):
        return (string('../../../')+struct.pack('<IQIQQ20sIQQ20sI',
                1, 0, 1, phi_offset, len(phi), hashlib.sha1(phi).digest(),
                1, fdi_offset, len(fdi), hashlib.sha1(fdi).digest(), len(encoded))
                +encoded+struct.pack('<I', 0))
    index = header(0, 0)
    index = header(index_offset+len(index), index_offset+len(index)+len(phi))
    footer = (b'\0'*17+struct.pack('<IIQQ20s', 0x5a6f12e1, 11, index_offset, len(index), hashlib.sha1(index).digest())+b'\0'*160)
    assert len(footer) == 221
    path.write_bytes(record+data+index+phi+fdi+footer)


def build(config_path=None, output_dir=None, include_primal=True):
    raw = ORIGINAL.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED:
        raise RuntimeError('Original UI script differs from the verified build')
    config = json.loads((Path(config_path) if config_path is not None else HERE/'overrides.json').read_bytes())
    validate_config(config)
    installed = {}
    if include_primal and config_path is None and (HERE/'installed_patch.json').exists():
        installed = json.loads((HERE/'installed_patch.json').read_bytes())
    profile = primal_preferences(config, installed) if include_primal else None
    if include_primal and ('primalDrop' in config or profile['enabled']):
        config = {**config, 'primalDrop': profile}
    compiled = compile_requests(config)
    runtime_config = dict(config)
    runtime_config['traitTypeRules'] = compiled['groups']
    runtime = (HERE/'override_runtime.js').read_text(encoding='utf-8').replace(
        '__GODFALL_EQUIPMENT_CONFIG__', json.dumps(runtime_config, ensure_ascii=True, separators=(',', ':')))
    source = raw.decode('utf-8')
    replacements = [
        ('g.a.map(this.attributes.traits,(function(a,r){return Object.assign({},a,{tierIdentifier:e.tierIdentifier,rarityIdentifier:e.rarityIdentifier,traitIndex:r})})',
         'g.a.map(window.__GodfallLocalEquipmentMod.applyItem(this.attributes).traits,(function(a,r){return Object.assign({},a,{tierIdentifier:e.tierIdentifier,rarityIdentifier:e.rarityIdentifier,traitIndex:r})})'),
        ('return this._primaryAttributeTrait}},{key:"primaryAttributeValue"',
         'return window.__GodfallLocalEquipmentMod.primaryAttributeTrait(this.attributes,this._primaryAttributeTrait)}},{key:"primaryAttributeValue"'),
        ('a.gearToUE4JSON=function(e){var r=a.mergeStaticDataInto(e);',
         'a.gearToUE4JSON=function(e){e=window.__GodfallLocalEquipmentMod.applyItem(e);var r=a.mergeStaticDataInto(e);'),
        ('o.trigger("UE_DATABRIDGE",C.Ng,JSON.stringify(l))',
         'o.trigger("UE_DATABRIDGE",C.Ng,JSON.stringify(window.__GodfallLocalEquipmentMod.applyEngineMessage(l,(window.__GodfallInventoryReadout.attach(a.store),a.store&&a.store.getState?a.store.getState():null))))'),
        ('m.engine.trigger("UE_DATABRIDGE",C.Yg,JSON.stringify(i))',
         'm.engine.trigger("UE_DATABRIDGE",C.Yg,JSON.stringify(window.__GodfallLocalEquipmentMod.applyEngineMessage(i,(window.__GodfallInventoryReadout.attach(a.store),a.store&&a.store.getState?a.store.getState():null))))')
    ]
    for old, new in replacements:
        if source.count(old) != 1:
            raise RuntimeError('UI integration point is missing or ambiguous')
        source = source.replace(old, new, 1)
    output = Path(output_dir) if output_dir is not None else HERE/'build'
    output.mkdir(parents=True, exist_ok=True)
    (output/'runtime_configured.js').write_text(runtime, encoding='utf-8')
    readout = (HERE/'inventory_readout_runtime.js').read_text(encoding='utf-8')
    combined = readout+'\n'+runtime+'\n'+source
    drop_component = None
    if include_primal and profile['enabled']:
        from primal_drop_build import compose
        combined, drop_component = compose(combined, profile, output)
    patched = combined.encode('utf-8')
    (output/'main.c05310c4.chunk.js').write_bytes(patched)
    if drop_component:
        import subprocess
        from trait_types import NODE
        subprocess.run([str(NODE), '--check', str(output/'main.c05310c4.chunk.js')], check=True,
                       capture_output=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    pak = output/PAK_NAME
    make_pak(pak, patched)
    evidence = inspect_pak(pak, extract_to=output/'verified_extraction')
    extracted = output/'verified_extraction/main.c05310c4.chunk.js'
    if extracted.read_bytes() != patched:
        raise RuntimeError('Independent extraction does not match patched script')
    report = {'original_sha256': EXPECTED, 'patched_sha256': hashlib.sha256(patched).hexdigest(),
              'pak_sha256': hashlib.sha256(pak.read_bytes()).hexdigest(), 'pak': str(pak),
              'changed_integration_points': len(replacements) + (2 if drop_component else 0), 'config': config,
              'compiled_trait_replacements': compiled,
              'verification': evidence, 'runtime_status': 'not_yet_loaded_or_tested_in_game',
              'inventory_readout': {'version': 1, 'access': 'equipment-only UI store snapshot; no requests or game writes'},
              'scope': 'Local display copies and messages to the local UE engine only; server request code is unchanged.'}
    if include_primal:
        report['primal_drop_settings'] = profile
    if drop_component:
        report['primal_drop_config'] = drop_component
        report['scope'] = 'Equipment settings and scoped primal chest opportunities composed together; original tables and request code unchanged.'
    (output/'build_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return pak, report


def install(pak, report):
    destination = PAKS/PAK_NAME
    state_path = HERE/'installed_patch.json'
    if destination.exists():
        if not state_path.exists():
            raise RuntimeError('Destination exists without this tool installation record')
        previous = json.loads(state_path.read_bytes())
        if hashlib.sha256(destination.read_bytes()).hexdigest() != previous['pak_sha256']:
            raise RuntimeError('Installed patch was changed independently')
        if previous['pak_sha256']==report['pak_sha256']:
            return previous
        if game_running():
            raise RuntimeError('请先正常退出游戏，再安装更新后的本地补丁')
        backup = HERE/'backups'
        backup.mkdir(exist_ok=True)
        shutil.copy2(destination, backup/(previous['pak_sha256']+'.pak'))
    if game_running():
        raise RuntimeError('请先正常退出游戏，再安装本地补丁')
    pending=destination.with_suffix('.pending')
    shutil.copy2(pak, pending)
    if hashlib.sha256(pending.read_bytes()).hexdigest() != report['pak_sha256']:
        raise RuntimeError('Installed file verification failed')
    if game_running():
        raise RuntimeError('检测到游戏已启动；已保留当前补丁，待游戏退出后再安装')
    pending.replace(destination)
    state = {'destination': str(destination), 'pak_sha256': report['pak_sha256'],
             'config': report['config'],
             'original_resources_overwritten': False, 'status': 'installed_awaiting_game_restart'}
    if 'inventory_readout' in report:
        state['inventory_readout'] = report['inventory_readout']
    if 'primal_drop_settings' in report:
        state['primal_drop'] = report['primal_drop_settings']
    pending_state=state_path.with_suffix('.tmp')
    pending_state.write_text(json.dumps(state, indent=2), encoding='utf-8')
    pending_state.replace(state_path)
    snapshot = HERE/'installed_config_snapshot.json'
    pending_snapshot = snapshot.with_suffix('.tmp')
    pending_snapshot.write_text(json.dumps({'pak_sha256': report['pak_sha256'], 'config': report['config'],
                                           'primal_drop': report.get('primal_drop_settings')}, ensure_ascii=False, indent=2), encoding='utf-8')
    pending_snapshot.replace(snapshot)
    return state


def game_running():
    import ctypes as c
    from ctypes import wintypes as w
    from recalibrate_runtime import ProcessEntry
    k=c.WinDLL('kernel32',use_last_error=True)
    k.CreateToolhelp32Snapshot.argtypes=[w.DWORD,w.DWORD];k.CreateToolhelp32Snapshot.restype=w.HANDLE
    k.Process32FirstW.argtypes=[w.HANDLE,c.POINTER(ProcessEntry)];k.Process32NextW.argtypes=k.Process32FirstW.argtypes
    k.CloseHandle.argtypes=[w.HANDLE]
    snap=k.CreateToolhelp32Snapshot(2,0)
    if snap==c.c_void_p(-1).value:raise c.WinError(c.get_last_error())
    entry=ProcessEntry();entry.size=c.sizeof(entry)
    try:
        ok=k.Process32FirstW(snap,c.byref(entry))
        while ok:
            if entry.exe.lower()=='aperion-win64-shipping.exe':return True
            ok=k.Process32NextW(snap,c.byref(entry))
        return False
    finally:k.CloseHandle(snap)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--install', action='store_true')
    ap.add_argument('--config', type=Path)
    ap.add_argument('--output', type=Path)
    args = ap.parse_args()
    pak, report = build(args.config, args.output)
    result = {'status': 'built_and_independently_extracted', 'pak': str(pak), 'integration_points': report['changed_integration_points']}
    if args.install:
        result['installation'] = install(pak, report)
    print(json.dumps(result, ensure_ascii=True))


if __name__ == '__main__':
    main()
