"""One-item native ground-loot experiment; default is read-only preflight.

Only three existing FString contents and optionally one quality scalar may change. No allocation, injection,
engine calls, or network operations. --apply is an explicit separate action.
"""
import argparse
import ctypes as c
from ctypes import wintypes as w
from datetime import datetime, timezone
import json
from pathlib import Path
import struct
import subprocess

from inspect_ue_runtime import ReadOnlyUE, ROOT
from read_ground_loot import NativeGearJSON, capture
from tool_paths import node_executable

NODE = node_executable()


def locate(reader, root, path):
    """Locate one JSON scalar by keys/array indices, without traversing unrelated data."""
    node = None
    for step in path:
        if node is None or reader.unpack('<i', node + 8)[0] == 6:
            obj = root if node is None else reader.unpack('<Q', node + 16)[0]
            matches = [p for p in reader.sparse_slots(obj, 40) if reader.string(p) == step]
            if len(matches) != 1:
                raise ValueError('JSON key is missing or ambiguous')
            node = reader.unpack('<Q', matches[0] + 16)[0]
        elif reader.unpack('<i', node + 8)[0] == 5 and isinstance(step, int):
            data, n, cap = reader.unpack('<Qii', node + 16)
            if not 0 <= step < n <= cap <= 4096:
                raise ValueError('JSON array index is invalid')
            node = reader.unpack('<Q', data + step * 16)[0]
        else:
            raise ValueError('Unexpected JSON path shape')
    return node


def string_patches(reader, root, bindings):
    patches, allocations = [], []
    if len(bindings) != 3:
        raise ValueError('This experiment requires exactly three string fields')
    for binding in bindings:
        node = locate(reader, root, binding['path'])
        if reader.unpack('<i', node + 8)[0] != 2:
            raise ValueError('Expected native JSON string value')
        header = node + 16
        pointer, count, capacity = reader.unpack('<Qii', header)
        if reader.string(header) != binding['before']:
            raise ValueError('Original string changed')
        after = binding['after'].encode('utf-16le') + b'\0\0'
        if len(after) > count * 2 or not count <= capacity <= 32768:
            raise ValueError('Replacement does not fit the existing native string')
        # No resizing, freed allocations, or allocator calls. Keep the buffer tail zeroed.
        after = after.ljust(count * 2, b'\0')
        before = reader.ue.read(pointer, count * 2)
        if len(before) != count * 2:
            raise ValueError('Incomplete original string buffer')
        interval = (pointer, pointer + capacity * 2)
        if any(interval[0] < hi and lo < interval[1] for lo, hi in allocations):
            raise ValueError('String buffers overlap; independent edits cannot be guaranteed')
        allocations.append(interval)
        patches.extend([
            {'kind': 'existing_utf16_buffer', 'path': binding['path'], 'address': hex(pointer),
             'before_hex': before.hex(), 'after_hex': after.hex()},
            {'kind': 'fstring_length', 'path': binding['path'], 'address': hex(header + 8),
             'before_hex': struct.pack('<i', count).hex(),
             'after_hex': struct.pack('<i', len(binding['after'].encode('utf-16le')) // 2 + 1).hex()}
        ])
    return patches


def check_bytes(ue, patches, key):
    for patch in patches:
        expected = bytes.fromhex(patch[key])
        if ue.read(int(patch['address'], 16), len(expected)) != expected:
            raise ValueError('Native bytes differ from the checked trial state')


def number_patches(reader, root, bindings):
    if len(bindings) > 1:
        raise ValueError('Only one existing quality scalar may change')
    result = []
    for binding in bindings:
        node = locate(reader, root, binding['path'])
        if reader.unpack('<i', node + 8)[0] != 3:
            raise ValueError('Expected native JSON number')
        if reader.unpack('<d', node + 16)[0] != binding['before'] or not 0 <= binding['after'] < 1:
            raise ValueError('Original quality changed or target is outside normal range')
        result.append({'kind': 'existing_quality_scalar', 'path': binding['path'], 'address': hex(node + 16),
                       'before_hex': struct.pack('<d', binding['before']).hex(),
                       'after_hex': struct.pack('<d', binding['after']).hex()})
    return result


def write_all(ue, patches, key):
    """Open only VM read/write/operation and query rights; no other process capability."""
    k = ue.k
    k.WriteProcessMemory.argtypes = [w.HANDLE, c.c_void_p, c.c_void_p, c.c_size_t, c.POINTER(c.c_size_t)]
    k.WriteProcessMemory.restype = w.BOOL
    handle = k.OpenProcess(0x438, False, ue.pid)
    if not handle:
        raise c.WinError(c.get_last_error())
    try:
        for patch in patches:
            data = bytes.fromhex(patch[key])
            buffer = c.create_string_buffer(data)
            written = c.c_size_t()
            ok = k.WriteProcessMemory(handle, c.c_void_p(int(patch['address'], 16)), buffer, len(data), c.byref(written))
            if not ok or written.value != len(data):
                raise RuntimeError('Native string write was incomplete')
    finally:
        k.CloseHandle(handle)


def restore_patches(reader, root, intent, receipt):
    """Rebuild every restore address and byte from the live JSON and checked plan."""
    result = []
    for binding in intent['bindings']:
        node = locate(reader, root, binding['path'])
        if reader.unpack('<i', node + 8)[0] != 2 or reader.string(node + 16) != binding['after']:
            raise ValueError('Restore string type changed')
        pointer, count, capacity = reader.unpack('<Qii', node + 16)
        original = binding['before'].encode('utf-16le') + b'\0\0'
        target = binding['after'].encode('utf-16le') + b'\0\0'
        if count != len(target) // 2 or not len(target) <= len(original) <= capacity * 2:
            raise ValueError('Restore string capacity changed')
        result.extend([
            {'kind': 'existing_utf16_buffer', 'path': binding['path'], 'address': hex(pointer),
             'before_hex': original.hex(), 'after_hex': target.ljust(len(original), b'\0').hex()},
            {'kind': 'fstring_length', 'path': binding['path'], 'address': hex(node + 24),
             'before_hex': struct.pack('<i', len(original) // 2).hex(),
             'after_hex': struct.pack('<i', len(target) // 2).hex()}
        ])
    reversed_numbers = number_patches(reader, root, [
        {'path': b['path'], 'before': b['after'], 'after': b['before']} for b in intent.get('numericBindings', [])])
    for row in reversed_numbers:
        result.append({**row, 'before_hex': row['after_hex'], 'after_hex': row['before_hex']})
    if result != receipt['patches']:
        raise ValueError('Restore receipt differs from reconstructed original bytes or addresses')
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--plan', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    group = ap.add_mutually_exclusive_group()
    group.add_argument('--apply', action='store_true')
    group.add_argument('--restore', type=Path, metavar='APPLIED_RECEIPT')
    args = ap.parse_args()
    intent = json.loads(args.plan.read_bytes())
    calibration = json.loads((ROOT / 'runtime_calibration.json').read_bytes())
    ue = ReadOnlyUE(calibration=calibration)
    try:
        fresh = capture(ue)
        matches = [r for r in fresh['records'] if r['item']['id'] == intent['item_id']]
        if len(matches) != 1:
            raise ValueError('Exact item is no longer uniquely linked to an active ground pickup')
        rec = matches[0]
        root = int(rec['native_json_address'], 16)
        reader = NativeGearJSON(ue)
        if args.restore:
            receipt = json.loads(args.restore.read_bytes())
            if receipt['status'] != 'applied_and_read_back' or receipt['process_creation_id'] != calibration['process_creation_id']:
                raise ValueError('Restore receipt is not for this active process generation')
            if receipt['native_json_address'] != rec['native_json_address'] or receipt['item_id'] != intent['item_id']:
                raise ValueError('Restore object identity changed')
            if rec['item'] != intent['target_item']:
                raise ValueError('Restore source is no longer the exact trial target')
            patches = restore_patches(reader, root, intent, receipt)
            check_bytes(ue, patches, 'after_hex')
            write_all(ue, list(reversed(patches)), 'before_hex')
            if reader.object(root, gear_root=True) != intent['source_item']:
                raise RuntimeError('Restored item read-back failed')
            result = {'status': 'restored_before_pickup', 'item_id': intent['item_id']}
        else:
            if rec['item'] != intent['source_item'] or fresh['pid'] != intent['capture_pid']:
                raise ValueError('The original ground item or process changed')
            # Independently regenerate legality and quality using the original game tables.
            fresh_input = args.out.with_suffix('.fresh_input.json')
            fresh_plan = args.out.with_suffix('.fresh_plan.json')
            fresh_input.write_text(json.dumps({**fresh, 'records': [rec]}), encoding='utf-8')
            target_name = intent.get('target_trait_name', intent['target_item']['traits'][intent['trait_index']]['traitName'])
            requested = intent.get('requested_quality')
            subprocess.run([str(NODE), str(ROOT / 'prepare_ground_trait_trial.cjs'), str(fresh_input), str(fresh_plan), str(intent['trait_index']), target_name,
                            'original' if requested is None else str(requested)],
                           check=True, capture_output=True)
            checked = json.loads(fresh_plan.read_bytes())
            if checked['source_item'] != intent['source_item'] or checked['target_item'] != intent['target_item'] or checked['bindings'] != intent['bindings'] or checked.get('numericBindings', []) != intent.get('numericBindings', []):
                raise ValueError('Independent original-game legality check differs')
            patches = string_patches(reader, root, checked['bindings'])
            patches.extend(number_patches(reader, root, checked.get('numericBindings', [])))
            check_bytes(ue, patches, 'before_hex')
            result = {'status': 'read_only_preflight_passed', 'item_id': intent['item_id'],
                      'pid': ue.pid, 'process_creation_id': calibration['process_creation_id'],
                      'native_json_address': rec['native_json_address'], 'pickup': rec['pickup'],
                      'loot_item_handle': rec['loot_item_handle'], 'patches': patches,
                      'normal_range': checked['target_normal_range'],
                      'target_materialized_trait': checked['target_materialized_trait'],
                      'writes_performed': False}
            if args.apply:
                # Persist the complete original bytes before acquiring any write capability.
                backup = args.out.with_suffix('.before_apply.json')
                backup.write_text(json.dumps(result, indent=2), encoding='utf-8')
                if reader.object(root, gear_root=True) != intent['source_item']:
                    raise ValueError('Item changed immediately before applying')
                attempted_write = False
                try:
                    check_bytes(ue, patches, 'before_hex')
                    attempted_write = True
                    write_all(ue, patches, 'after_hex')
                    check_bytes(ue, patches, 'after_hex')
                    if reader.object(root, gear_root=True) != intent['target_item']:
                        raise RuntimeError('Complete modified item read-back differs')
                except Exception as error:
                    # Restore only if each byte is still original or from this attempt,
                    # and the same item ID is still readable at the same JSON root.
                    rollback = '未能确认恢复；请保留本次记录'
                    try:
                        linked = [r for r in capture(ue)['records'] if r['item']['id'] == intent['item_id'] and
                                  r['native_json_address'] == rec['native_json_address'] and
                                  r['loot_item_handle'] == rec['loot_item_handle'] and r['pickup'] == rec['pickup']]
                        if len(linked) == 1 and reader.value(locate(reader, root, ['id']), 0) == intent['item_id']:
                            safe = all(len(current := ue.read(int(p['address'], 16), len(bytes.fromhex(p['before_hex'])))) == len(bytes.fromhex(p['before_hex'])) and
                                       all(v in (a, b) for v, a, b in zip(current, bytes.fromhex(p['before_hex']), bytes.fromhex(p['after_hex']))) for p in patches)
                            if safe and attempted_write:
                                write_all(ue, list(reversed(patches)), 'before_hex')
                            if reader.object(root, gear_root=True) == intent['source_item']:
                                rollback = '原始掉落数据已核对恢复'
                    except Exception:
                        pass
                    failed = {**result, 'status': 'apply_failed', 'writes_attempted': attempted_write,
                              'rollback': rollback, 'error': str(error)}
                    args.out.write_text(json.dumps(failed, ensure_ascii=False, indent=2), encoding='utf-8')
                    raise RuntimeError('写入中断；' + rollback) from error
                result.update(status='applied_and_read_back', writes_performed=True)
        result['timestamp_utc'] = datetime.now(timezone.utc).isoformat()
        result['scope'] = 'One active unpicked equipment payload. No requests, allocation, injection, or installed patch changes. Server acceptance unknown.'
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({k: v for k, v in result.items() if k not in {'patches', 'pickup', 'target_materialized_trait'}}))
    finally:
        ue.close()


if __name__ == '__main__':
    main()
