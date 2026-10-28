"""Read only the bounded replacement-trial diagnostic JSON from the current game."""
import argparse
import ctypes as c
from ctypes import wintypes as w
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import time

from inspect_ue_runtime import ReadOnlyUE
from read_live_equipment import MBI

HEADER = '{"godfallReplacementCopy":1,'
STATUSES = {'waiting', 'inventory_not_ready', 'source_changed_or_missing', 'replacement_already_owned',
            'already_generated_previous_run', 'generated_waiting_for_pickup', 'generation_failed_original_rewards_preserved',
            'waiting_nonempty_reward', 'waiting_smaller_reward', 'waiting_single_player', 'waiting_grounded_equipment'}


def parse(text, source_id, born_ms, now_ms):
    if not text.startswith(HEADER): return None
    try:
        value, end = json.JSONDecoder().raw_decode(text)
        if end > 4096 or set(value) != {'godfallReplacementCopy','startedAt','sequence','status','generatedId','eventTag','sourceId'}:
            return None
        if value['godfallReplacementCopy'] != 1 or value['sourceId'] != source_id or value['status'] not in STATUSES:
            return None
        if (type(value['startedAt']) not in (float, int) or not math.isfinite(value['startedAt']) or
                not born_ms <= value['startedAt'] <= now_ms + 5000 or type(value['sequence']) is not int or value['sequence'] < 1):
            return None
        if any(not isinstance(value[k], str) or len(value[k]) > 512 for k in ['generatedId','eventTag']):
            return None
        return value
    except (ValueError, TypeError, KeyError, RecursionError):
        return None


def read_trace(seconds=35, max_gib=8, *, source_id=None, header=HEADER, parser=None, max_chars=4096):
    if type(max_chars) is not int or not 4096 <= max_chars <= 16384:
        raise ValueError('Unsupported bounded trace size')
    root = Path(__file__).resolve().parent
    if source_id is None:
        state = json.loads((root.parent/'local_mod/installed_patch.json').read_bytes())
        source_id = state['replacement_copy_trial']['source_id']
    parser = parser or parse
    calibration = json.loads((root/'runtime_calibration.json').read_bytes())
    born_ms = int(calibration['process_creation_id'])/10000 - 11644473600000
    ue = ReadOnlyUE(); started = time.monotonic(); address = total = 0; found = {}; seen = set()
    try:
        ue.k.VirtualQueryEx.argtypes = [w.HANDLE, c.c_void_p, c.POINTER(MBI), c.c_size_t]
        ue.k.VirtualQueryEx.restype = c.c_size_t; mbi = MBI()
        while time.monotonic()-started < seconds and total < max_gib*1024**3:
            if not ue.k.VirtualQueryEx(ue.h,c.c_void_p(address),c.byref(mbi),c.sizeof(mbi)): break
            base,size = mbi.BaseAddress or 0,mbi.RegionSize
            if not size or base+size <= address: break
            address = base+size
            if mbi.State != 0x1000 or mbi.Type != 0x20000 or mbi.Protect & 0x101 or not mbi.Protect & 0xee: continue
            for offset in range(0,size,4*1024**2-128):
                if time.monotonic()-started >= seconds or total >= max_gib*1024**3: break
                raw=ue.read(base+offset,min(4*1024**2,size-offset)); total+=len(raw)
                for encoding in ('ascii','utf-16le'):
                    for match in re.finditer(re.escape(header.encode(encoding)),raw):
                        ptr=base+offset+match.start()
                        if (ptr,encoding) in seen: continue
                        seen.add((ptr,encoding))
                        data=ue.read(ptr,min(max_chars*2+8,base+size-ptr))
                        if encoding=='utf-16le': data=data[:len(data)//2*2]
                        value=parser(data.decode(encoding,errors='replace'),source_id,born_ms,time.time()*1000)
                        if value: found[(value['startedAt'],value['sequence'])]=value
        return {'pid':ue.pid,'timestamp_utc':datetime.now(timezone.utc).isoformat(),
                'trace':found[max(found)] if found else None,'distinct_versions':len(found),
                'access':'QUERY_INFORMATION | VM_READ only','read_bytes':total,'elapsed_seconds':round(time.monotonic()-started,2)}
    finally: ue.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    result=read_trace();args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'pid':result['pid'],'trace':result['trace'],'seconds':result['elapsed_seconds']}))
