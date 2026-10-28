"""Read only this installed uncurse trial's bounded status JSON."""
import argparse
import json
import math
from pathlib import Path

from read_replacement_trace import read_trace

HEADER = '{"godfallUncurseTrial":1,'
STATUSES = {'waiting_for_inventory', 'inventory_timeout', 'source_missing', 'already_cleansed_verified',
            'source_changed', 'equipped_source_not_supported', 'storage_failed', 'already_requested_previous_run',
            'request_started', 'waiting_for_refresh', 'refresh_dispatch_failed', 'cleansed_after_refresh_verified',
            'progress_saved_curse_still_present', 'refresh_timeout', 'request_ack_timeout', 'operation_failed',
            'original_request_failed', 'original_request_acknowledged', 'awaken_pending', 'awakening_requested',
            'source_changed_before_awaken', 'awaken_dispatch_failed', 'original_awaken_request_failed',
            'original_awaken_request_acknowledged', 'waiting_for_awaken_refresh', 'next_layer_pending',
            'source_changed_before_next_layer', 'unexpected_layer_state'}


def parse(text, source_id, born_ms, now_ms, plan_id):
    try:
        if not text.startswith(HEADER):
            return None
        value, end = json.JSONDecoder().raw_decode(text)
        required = {'godfallUncurseTrial', 'startedAt', 'sequence', 'status', 'planId',
                    'sourceId', 'beforeProgress', 'requestedProgress', 'remainingCurses'}
        if end > 4096 or set(value) not in (required, required | {'completedLayers', 'totalLayers'}):
            return None
        if value['godfallUncurseTrial'] != 1 or value['sourceId'] != source_id or value['planId'] != plan_id or value['status'] not in STATUSES:
            return None
        if type(value['sequence']) is not int or value['sequence'] <= 0:
            return None
        if any(type(value[k]) not in (int, float) or not math.isfinite(value[k]) for k in
               ['startedAt', 'beforeProgress', 'requestedProgress', 'remainingCurses']):
            return None
        if not born_ms <= value['startedAt'] <= now_ms+5000:
            return None
        if not 0 <= value['beforeProgress'] <= value['requestedProgress'] <= 1e12 or value['requestedProgress'] <= 0 or value['remainingCurses'] not in (0, 1, 2, 3):
            return None
        if 'totalLayers' in value:
            if (type(value['totalLayers']) is not int or not 1 <= value['totalLayers'] <= 3 or
                    type(value['completedLayers']) is not int or not 0 <= value['completedLayers'] <= value['totalLayers']):
                return None
            if value['status'] in {'cleansed_after_refresh_verified', 'already_cleansed_verified'} and (
                    value['remainingCurses'] != 0 or value['completedLayers'] != value['totalLayers']):
                return None
        return value
    except (ValueError, TypeError, KeyError, RecursionError):
        return None


if __name__ == '__main__':
    args_parser = argparse.ArgumentParser(description=__doc__)
    args_parser.add_argument('--out', type=Path, required=True)
    args = args_parser.parse_args()
    state = json.loads((Path(__file__).resolve().parent.parent/'local_mod/installed_patch.json').read_bytes())
    trial = state['uncurse_trial']
    result = read_trace(source_id=trial['source_id'], header=HEADER,
                        parser=lambda text, source, born, now: parse(text, source, born, now, trial['plan_id']))
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'pid': result['pid'], 'trace': result['trace'], 'seconds': result['elapsed_seconds']}))
