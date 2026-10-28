"""Bounded read-only reader for equipment-only UI snapshots; never dumps surrounding memory."""
import argparse
import ctypes as c
from ctypes import wintypes as w
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'local_mod'))
from inventory_snapshot import HEADER, MAX_CHARS, assemble, decode_fragment
from inspect_ue_runtime import ReadOnlyUE
from read_live_equipment import MBI


def read_snapshot(seconds=40, max_gib=8):
    ue = ReadOnlyUE()
    started, address, read_bytes = time.monotonic(), 0, 0
    fragments, seen, newest = {}, set(), (0, 0)
    calibration = json.loads((Path(__file__).parent/'runtime_calibration.json').read_bytes())
    born_ms = int(calibration['process_creation_id']) / 10000 - 11644473600000
    try:
        ue.k.VirtualQueryEx.argtypes = [w.HANDLE, c.c_void_p, c.POINTER(MBI), c.c_size_t]
        ue.k.VirtualQueryEx.restype = c.c_size_t
        mbi = MBI()
        while time.monotonic() - started < seconds and read_bytes < max_gib*1024**3:
            if not ue.k.VirtualQueryEx(ue.h, c.c_void_p(address), c.byref(mbi), c.sizeof(mbi)): break
            base, size = mbi.BaseAddress or 0, mbi.RegionSize
            if not size or base + size <= address: break
            address = base + size
            if mbi.State != 0x1000 or mbi.Type != 0x20000 or mbi.Protect & 0x101 or not mbi.Protect & 0xee: continue
            for offset in range(0, size, 4*1024**2 - 256):
                if time.monotonic() - started >= seconds or read_bytes >= max_gib*1024**3: break
                raw = ue.read(base + offset, min(4*1024**2, size - offset))
                read_bytes += len(raw)
                for encoding in ('ascii', 'utf-16le'):
                    for match in re.finditer(re.escape(HEADER.encode(encoding)), raw):
                        ptr = base + offset + match.start()
                        if (ptr, encoding) in seen: continue
                        seen.add((ptr, encoding))
                        candidate = raw[match.start():]
                        def decode(data):
                            if encoding == 'utf-16le': data = data[:len(data)//2*2]
                            return decode_fragment(data.decode(encoding, errors='replace'))
                        decoded = decode(candidate)
                        if not decoded and len(candidate) < MAX_CHARS*(2 if encoding == 'utf-16le' else 1):
                            candidate = ue.read(ptr, min(MAX_CHARS*2 + 16, base + size - ptr))
                            read_bytes += len(candidate)
                            decoded = decode(candidate)
                        if not decoded: continue
                        obj, end = decoded
                        if not born_ms <= obj['startedAt'] <= time.time()*1000 + 5000: continue
                        seq = (obj['startedAt'], obj['sequence'])
                        newest = max(newest, seq)
                        if seq[0] != newest[0] or seq[1] < newest[1] - 6: continue
                        key = (*seq, obj['kind'], obj.get('index', -1))
                        # Python indexes code points; JS lengths count UTF-16 code units.
                        text = candidate[:len(candidate)//2*2].decode('utf-16le', errors='replace') if encoding == 'utf-16le' else candidate.decode('ascii', errors='replace')
                        js_length = len(text[:end].encode('utf-16le'))//2
                        fragments[key] = (obj, js_length)
                        fragments = {k: v for k, v in fragments.items() if k[0] == newest[0] and k[1] >= newest[1] - 6}
        try:
            result = assemble(list(fragments.values()), born_ms, time.time()*1000)
        except ValueError:
            diagnostic = {'pid': ue.pid, 'read_bytes': read_bytes,
                          'elapsed_seconds': round(time.monotonic()-started, 2), 'marker_matches': len(seen),
                          'versions': []}
            generations = sorted({(k[0], k[1]) for k in fragments})
            for generation in generations:
                parts = [v for k, v in fragments.items() if k[:2] == generation]
                manifest = next((v[0] for v in parts if v[0]['kind'] == 'manifest'), None)
                diagnostic['versions'].append({'startedAt': generation[0], 'sequence': generation[1],
                    'manifest_found': bool(manifest), 'expected_pages': len(manifest['pageLengths']) if manifest else None,
                    'found_pages': sorted(v[0]['index'] for v in parts if v[0]['kind'] == 'page'),
                    'capturedAt': manifest['capturedAt'] if manifest else None})
            path = Path(__file__).parent/'inventory_read_diagnostic.json'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(diagnostic, indent=2), encoding='utf-8')
            raise
        return {**result, 'pid': ue.pid, 'process_creation_id': calibration['process_creation_id'],
                'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'read_bytes': read_bytes,
                'elapsed_seconds': round(time.monotonic() - started, 2),
                'access': 'QUERY_INFORMATION | VM_READ only',
                'scope': 'Original UI inventory gear and saved valorplate preset bindings only; point-in-time snapshot.'}
    finally:
        ue.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    result = read_snapshot()
    pending = args.out.with_suffix('.pending')
    pending.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    pending.replace(args.out)
    print(json.dumps({'item_count': len(result['items']), 'plates': len(result['manifest']['plates']),
                      'omitted': result['manifest']['omitted'], 'seconds': result['elapsed_seconds']}))


if __name__ == '__main__':
    main()
