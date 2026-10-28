"""Read only this installed batch's bounded, equipment-only status rows."""
import argparse
import json
import math
from pathlib import Path

from read_replacement_trace import read_trace, STATUSES as SINGLE_STATUSES

HEADER = '{"godfallReplacementBatch":1,'
STATUSES = SINGLE_STATUSES | {'batch_child_error'}


def parse(text, batch_id, born_ms, now_ms, expected):
    try:
        if not text.startswith(HEADER):
            return None
        value, end = json.JSONDecoder().raw_decode(text)
        if end > 16384 or set(value) != {'godfallReplacementBatch','startedAt','sequence','batchId','items'}:
            return None
        if value['godfallReplacementBatch'] != 1 or value['batchId'] != batch_id:
            return None
        if (type(value['startedAt']) not in (int,float) or not math.isfinite(value['startedAt']) or
                not born_ms <= value['startedAt'] <= now_ms+5000 or type(value['sequence']) is not int or value['sequence']<1):
            return None
        rows = value['items']
        if not isinstance(rows,list) or not 1 <= len(rows)==len(expected) <= 8:
            return None
        allowed = {(r['trial_id'],r['source_id']) for r in expected}; seen = set()
        for r in rows:
            if set(r) != {'trialId','sourceId','status','generatedId','eventTag'}:
                return None
            key = (r['trialId'],r['sourceId'])
            if key not in allowed or key in seen or r['status'] not in STATUSES:
                return None
            seen.add(key)
            if any(not isinstance(r[k],str) or len(r[k])>512 for k in ['generatedId','eventTag']):
                return None
        return value
    except (ValueError,TypeError,KeyError,RecursionError):
        return None


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    state = json.loads((Path(__file__).resolve().parent.parent/'local_mod/installed_patch.json').read_bytes())
    batch = state['replacement_batch_trial']; batch_id = batch['batch_id']
    result = read_trace(source_id=batch_id, header=HEADER, max_chars=16384,
                        parser=lambda text, identity, born, now:parse(text,identity,born,now,batch['items']))
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'pid':result['pid'],'trace':result['trace'],'seconds':result['elapsed_seconds']}))
