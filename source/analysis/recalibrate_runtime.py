"""Read-only relocation after restart, limited to the exact verified executable."""
import ctypes as c
from ctypes import wintypes as w
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import struct
from inspect_ue_runtime import ReadOnlyUE,ROOT

EXPECTED='301f90fc4f6119b64f7ef51971f6083264c4f4878500f5cd52341e4eb673b834'
POOL_RVA=0x6675650
OBJECT_RVA=0x66b1a90


class ProcessEntry(c.Structure):
    _fields_=[('size',w.DWORD),('usage',w.DWORD),('pid',w.DWORD),('heap',c.c_size_t),
              ('module',w.DWORD),('threads',w.DWORD),('parent',w.DWORD),('priority',w.LONG),
              ('flags',w.DWORD),('exe',w.WCHAR*260)]


class ModuleEntry(c.Structure):
    _fields_=[('size',w.DWORD),('module_id',w.DWORD),('pid',w.DWORD),('global_usage',w.DWORD),
              ('usage',w.DWORD),('base',c.c_void_p),('image_size',w.DWORD),('module',w.HMODULE),
              ('name',w.WCHAR*256),('path',w.WCHAR*260)]


def main():
    k=c.WinDLL('kernel32',use_last_error=True)
    k.CreateToolhelp32Snapshot.argtypes=[w.DWORD,w.DWORD];k.CreateToolhelp32Snapshot.restype=w.HANDLE
    k.CloseHandle.argtypes=[w.HANDLE]
    k.Process32FirstW.argtypes=[w.HANDLE,c.POINTER(ProcessEntry)];k.Process32NextW.argtypes=k.Process32FirstW.argtypes
    snap=k.CreateToolhelp32Snapshot(2,0);entry=ProcessEntry();entry.size=c.sizeof(entry);found=[]
    try:
        ok=k.Process32FirstW(snap,c.byref(entry))
        while ok:
            if entry.exe.lower()=='aperion-win64-shipping.exe':found.append(entry.pid)
            ok=k.Process32NextW(snap,c.byref(entry))
    finally:k.CloseHandle(snap)
    if len(found)!=1:raise RuntimeError('Expected exactly one running Godfall shipping process')
    pid=found[0]
    k.Module32FirstW.argtypes=[w.HANDLE,c.POINTER(ModuleEntry)];k.Module32NextW.argtypes=k.Module32FirstW.argtypes
    snap=k.CreateToolhelp32Snapshot(0x18,pid);module=ModuleEntry();module.size=c.sizeof(module);matches=[]
    try:
        ok=k.Module32FirstW(snap,c.byref(module))
        while ok:
            if module.name.lower()=='aperion-win64-shipping.exe':matches.append((module.base,module.path,module.image_size))
            ok=k.Module32NextW(snap,c.byref(module))
    finally:k.CloseHandle(snap)
    if len(matches)!=1:raise RuntimeError('Executable module is unavailable')
    base,path,size=matches[0]
    with Path(path).open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    if digest!=EXPECTED:raise RuntimeError('Executable build differs; refusing to reuse layout offsets')
    k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE
    h=k.OpenProcess(0x410,False,pid)
    if not h:raise c.WinError(c.get_last_error())
    k.GetProcessTimes.argtypes=[w.HANDLE]+[c.POINTER(c.c_uint64)]*4;k.GetProcessTimes.restype=w.BOOL
    times=[c.c_uint64() for _ in range(4)]
    try:
        if not k.GetProcessTimes(h,*[c.byref(t) for t in times]):raise c.WinError(c.get_last_error())
    finally:k.CloseHandle(h)
    cal={'pid':pid,'process_creation_id':str(times[0].value),'exe_sha256':digest,'exe_path':path,
         'module_base':hex(base),'module_size':size,'fname_blocks':hex(base+POOL_RVA),
         'object_array':hex(base+OBJECT_RVA),'timestamp_utc':datetime.now(timezone.utc).isoformat()}
    ue=ReadOnlyUE(calibration=cal)
    try:
        chunks,_,maximum,n,mc,nc=struct.unpack('<QQiiii',ue.read(ue.array,32))
        if not 1000<n<=maximum<4000000 or not 0<nc<=mc<256:raise RuntimeError('Object array bounds failed')
        first=ue.ptr(ue.ptr(chunks));obj=ue.object(first)
        if not obj or obj['object_index']!=0 or obj['class']!='Package' or obj['name']!='/Script/CoreUObject':
            raise RuntimeError('Object array identity failed')
        cal['verification']={'name_zero':'None','first_object':obj,'objects':n}
    finally:ue.close()
    target=ROOT/'runtime_calibration.json'
    if target.exists():
        backup=ROOT/'calibration_history';backup.mkdir(exist_ok=True)
        (backup/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')).write_bytes(target.read_bytes())
    target.write_text(json.dumps(cal,indent=2),encoding='utf-8')
    print(json.dumps(cal,ensure_ascii=True))


if __name__=='__main__':main()
