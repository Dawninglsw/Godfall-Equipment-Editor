"""Read-only scan of the selected Godfall process for equipment JSON candidates.

Opens the game with QUERY_INFORMATION | VM_READ only. It cannot write memory,
inject code, call game functions, or send network requests. Does not dump RAM.
"""
import argparse
import ctypes as c
from ctypes import wintypes as w
from pathlib import Path
import json
import re
import time


class MBI(c.Structure):
    _fields_ = [('BaseAddress', c.c_void_p), ('AllocationBase', c.c_void_p),
                ('AllocationProtect', w.DWORD), ('PartitionId', w.WORD),
                ('RegionSize', c.c_size_t), ('State', w.DWORD),
                ('Protect', w.DWORD), ('Type', w.DWORD)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pid', type=int, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    k = c.WinDLL('kernel32', use_last_error=True)
    k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    k.OpenProcess.restype = w.HANDLE
    k.VirtualQueryEx.argtypes = [w.HANDLE, c.c_void_p, c.POINTER(MBI), c.c_size_t]
    k.VirtualQueryEx.restype = c.c_size_t
    k.ReadProcessMemory.argtypes = [w.HANDLE, c.c_void_p, c.c_void_p, c.c_size_t, c.POINTER(c.c_size_t)]
    k.ReadProcessMemory.restype = w.BOOL
    k.CloseHandle.argtypes = [w.HANDLE]
    h = k.OpenProcess(0x410, False, args.pid)
    if not h:
        raise c.WinError(c.get_last_error())
    started = time.monotonic()
    regions, hits, seen = [], [], set()
    total_read, region_count = 0, 0
    patterns = [(needle.encode(enc), enc) for needle in
                ['masterworkUpgradeRank', '"lootClassName":"Weapon"', '"lootClassName": "Weapon"',
                 'Weapon.Sword.2H.Player.Boar']
                for enc in ['ascii', 'utf-16le']]
    try:
        addr = 0
        mbi = MBI()
        while k.VirtualQueryEx(h, c.c_void_p(addr), c.byref(mbi), c.sizeof(mbi)):
            base = mbi.BaseAddress or 0
            size = mbi.RegionSize
            if not size or base + size <= addr:
                break
            if mbi.State == 0x1000 and mbi.Type == 0x20000 and not mbi.Protect & 0x101 and mbi.Protect & 0xee:
                regions.append((base, size, mbi.Protect))
            addr = base + size
        print(json.dumps({'event':'regions', 'count':len(regions),
                          'private_readable_bytes':sum(x[1] for x in regions)}), flush=True)
        buf = c.create_string_buffer(4 * 1024 * 1024)
        for base, size, prot in regions:
            region_count += 1
            for off in range(0, size, len(buf) - 16384):
                if time.monotonic() - started > 110 or total_read > 8 * 1024**3:
                    break
                n = min(len(buf), size - off)
                got = c.c_size_t()
                ok = k.ReadProcessMemory(h, c.c_void_p(base + off), buf, n, c.byref(got))
                if not got.value:
                    continue
                b = buf.raw[:got.value]
                total_read += got.value
                for needle, enc in patterns:
                    pos = -1
                    while True:
                        pos = b.find(needle, pos + 1)
                        if pos < 0:
                            break
                        address = base + off + pos
                        key = (address, enc)
                        if key in seen:
                            continue
                        seen.add(key)
                        # Decode a bounded context; never output whole responses.
                        lo, hi = max(0, pos - 1000), min(len(b), pos + 2000)
                        if enc == 'utf-16le':
                            lo += (pos - lo) % 2
                            hi -= (hi - lo) % 2
                        context = b[lo:hi].decode(enc, errors='replace')
                        if re.search(r'token|password|authorization|secret|sessionTicket', context, re.I):
                            continue
                        if len(hits) < 300:
                            hits.append({'address':hex(address), 'encoding':enc,
                                         'needle':needle.decode(enc), 'context':context})
            if time.monotonic() - started > 110 or total_read > 8 * 1024**3:
                break
        result = {'pid':args.pid, 'access':'PROCESS_QUERY_INFORMATION | PROCESS_VM_READ',
                  'read_bytes':total_read, 'regions_scanned':region_count,
                  'regions_available':len(regions), 'elapsed_seconds':round(time.monotonic()-started,2),
                  'matches':len(seen), 'saved_contexts':len(hits), 'candidates':hits,
                  'limitation':'Candidate strings may be UI, cached responses, static scripts, or stale copies. No memory writes or gameplay changes.'}
        args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k!='candidates'}), flush=True)
    finally:
        k.CloseHandle(h)


if __name__ == '__main__':
    main()
