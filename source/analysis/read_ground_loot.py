"""Read-only capture of actual ground equipment through the native loot manager.

No writes, injected calls, network requests, or account payloads. Requires the
exact executable and process-generation calibration enforced by ReadOnlyUE.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import struct

from inspect_ue_runtime import ReadOnlyUE, ROOT


class NativeGearJSON:
    def __init__(self, ue):
        self.ue = ue
        self.visits = 0
        calibration = json.loads((ROOT / 'runtime_calibration.json').read_bytes())
        if calibration['pid'] != ue.pid:
            raise ValueError('Calibration process mismatch')
        # Non-reflected custom data type, observed on this exact executable.
        self.item_handle_vtable = int(calibration['module_base'], 16) + 0x5010430

    def unpack(self, fmt, address):
        size = struct.calcsize(fmt)
        raw = self.ue.read(address, size)
        if len(raw) != size:
            raise ValueError('Unreadable gear data')
        return struct.unpack(fmt, raw)

    def string(self, address):
        pointer, count, capacity = self.unpack('<Qii', address)
        if count == 0:
            return ''
        if not 1 <= count <= capacity <= 32768:
            raise ValueError('Invalid equipment string')
        raw = self.ue.read(pointer, count * 2)
        if len(raw) != count * 2 or raw[-2:] != b'\0\0':
            raise ValueError('Incomplete equipment string')
        return raw[:-2].decode('utf-16le')

    def sparse_slots(self, address, stride):
        pointer, count, capacity = self.unpack('<Qii', address)
        bits, maxbits = self.unpack('<ii', address + 40)
        if not 0 <= count <= capacity <= 4096 or bits != count or not bits <= maxbits <= 65536:
            raise ValueError('Invalid sparse equipment map')
        flag_pointer = address + 16 if maxbits <= 128 else self.unpack('<Q', address + 32)[0]
        flags = self.ue.read(flag_pointer, (count + 7) // 8)
        if len(flags) != (count + 7) // 8:
            raise ValueError('Unreadable allocation flags')
        for i in range(count):
            if flags[i // 8] & (1 << (i % 8)):
                yield pointer + i * stride

    def object(self, address, depth=0, gear_root=False):
        if depth > 20:
            raise ValueError('Equipment JSON nesting limit')
        entries = [(self.string(p), p) for p in self.sparse_slots(address, 40)]
        if gear_root:
            keys = {key for key, _ in entries}
            if not {'id', 'gameplayTag', 'lootClassName', 'traits'}.issubset(keys):
                raise ValueError('Not a complete equipment root')
        return {key: self.value(self.unpack('<Q', p + 16)[0], depth + 1) for key, p in entries}

    def value(self, address, depth):
        self.visits += 1
        if depth > 20 or self.visits > 20000:
            raise ValueError('Equipment JSON traversal limit')
        kind = self.unpack('<i', address + 8)[0]
        if kind == 1:
            return None
        if kind == 2:
            return self.string(address + 16)
        if kind == 3:
            return self.unpack('<d', address + 16)[0]
        if kind == 4:
            return bool(self.unpack('<B', address + 16)[0])
        if kind == 5:
            pointer, count, capacity = self.unpack('<Qii', address + 16)
            if not 0 <= count <= capacity <= 4096:
                raise ValueError('Invalid equipment JSON array')
            return [self.value(self.unpack('<Q', pointer + i * 16)[0], depth + 1) for i in range(count)]
        if kind == 6:
            return self.object(self.unpack('<Q', address + 16)[0], depth + 1)
        raise ValueError('Unsupported equipment JSON value')


def objects(ue):
    chunks, _, maximum, count, maxchunks, nchunks = struct.unpack('<QQiiii', ue.read(ue.array, 32))
    chunkptrs = ue.read(chunks, nchunks * 8)
    for ci in range(nchunks):
        ptr = struct.unpack_from('<Q', chunkptrs, ci * 8)[0]
        size = min(65536, count - ci * 65536)
        rows = ue.read(ptr, size * 24)
        for j in range(len(rows) // 24):
            address = struct.unpack_from('<Q', rows, j * 24)[0]
            if address:
                obj = ue.object(address)
                if obj and (obj['class'] == 'APLootManagerComponent' or obj['class'].startswith('BP_Pickup_PlayerLoot_Gear')):
                    if not int(obj['flags'], 16) & (0x10 | 0x20):
                        yield obj


def fields(ue, obj):
    return {p['property']: p for p in ue.properties(int(obj['class_address'], 16))}


def capture(ue):
    reader = NativeGearJSON(ue)
    found = list(objects(ue))
    pending, errors, excluded_handles, excluded_pickups = {}, [], {}, []
    for obj in found:
        if obj['class'] != 'APLootManagerComponent':
            continue
        f = fields(ue, obj)['PendingPlayerLootItemData']
        meta = int(f['metadata_address'], 16)
        value_offset, _, _, stride, alignment = reader.unpack('<5i', meta + 0x88)
        if (value_offset, stride, alignment) != (8, 104, 8):
            raise ValueError('Unknown native loot map layout')
        for p in reader.sparse_slots(int(obj['address'], 16) + f['offset'], stride):
            handle = reader.unpack('<i', p)[0]
            # Exact-build AssembleAssetPayload: JSON shared pointer at offset 32.
            json_pointer = reader.unpack('<Q', p + value_offset + 32)[0]
            try:
                item = reader.object(json_pointer, gear_root=True)
                if item['lootClassName'] not in {'Weapon', 'Ring', 'Amulet', 'Charm', 'Augment', 'Banner', 'Consumable', 'EnergyShield', 'Rune'}:
                    excluded_handles[handle] = item['lootClassName']
                    continue
                if not isinstance(item['traits'], list) or not item['id'].startswith(('WPN-', 'RNG-', 'AMT-', 'CHA-', 'AUG-', 'BNR-', 'CNS-', 'ESD-', 'RUN-')):
                    raise ValueError('Invalid equipment identity')
                pending.setdefault(handle, []).append({'item': item, 'manager_address': obj['address'],
                                                       'native_json_address': hex(json_pointer)})
            except (ValueError, UnicodeError, KeyError, struct.error):
                # Currency/powerups and unknown payloads are intentionally omitted.
                continue
    ground = []
    for obj in found:
        if not obj['class'].startswith('BP_Pickup_PlayerLoot_Gear'):
            continue
        excluded_kind = None
        f = fields(ue, obj)
        address = int(obj['address'], 16)
        state = f['activeState']
        state_schema = ue.ptr(int(state['metadata_address'], 16) + 0x78)
        active_field = next(x for x in ue.properties(state_schema) if x['property'] == 'bIsActive')
        if not reader.unpack('<B', address + state['offset'] + active_field['offset'])[0]:
            continue
        container = f['RepItemsContainer']
        schema = ue.ptr(int(container['metadata_address'], 16) + 0x78)
        arr = next(x for x in ue.properties(schema) if x['property'] == 'Items')
        inner = ue.ptr(int(arr['metadata_address'], 16) + 0x78)
        size = reader.unpack('<i', inner + 0x3c)[0]
        if size != 72:
            raise ValueError('Unknown native pickup item stride')
        p, n, cap = reader.unpack('<Qii', address + container['offset'] + arr['offset'])
        if not 0 <= n <= cap <= 64:
            raise ValueError('Invalid pickup item count')
        for i in range(n):
            hp, hn, hc = reader.unpack('<Qii', p + i * size + 32)
            if not 0 <= hn <= hc <= 16:
                continue
            for hi in range(hn):
                custom, cn, cc = reader.unpack('<Qii', hp + hi * 16)
                if not 0 <= cn <= cc <= 16:
                    continue
                for j in range(cn):
                    cp = reader.unpack('<Q', custom + j * 16)[0]
                    # Exact-build non-replicated PlayerLootItemHandle custom data.
                    vtable, = reader.unpack('<Q', cp)
                    if vtable != reader.item_handle_vtable:
                        continue
                    replicated = reader.unpack('<B', cp + 8)[0]
                    handle = reader.unpack('<i', cp + 16)[0]
                    if not replicated and handle in excluded_handles:
                        excluded_kind = excluded_handles[handle]
                    if replicated or handle not in pending:
                        continue
                    for entry in pending[handle]:
                        distance = reader.unpack('<f', address + f['DistanceLocalPlayer']['offset'])[0]
                        ground.append({'pickup': obj, 'loot_item_handle': handle, 'distance_game_units': distance, **entry})
        if not any(g['pickup']['address'] == obj['address'] for g in ground):
            if excluded_kind:
                excluded_pickups.append({'pickup': obj['name'], 'lootClassName': excluded_kind})
            else:
                errors.append({'pickup': obj['name'], 'reason': 'No complete equipment payload linked'})
    return {'pid': ue.pid, 'timestamp_utc': datetime.now(timezone.utc).isoformat(),
            'access': 'QUERY_INFORMATION | VM_READ only', 'records': ground, 'unresolved': errors,
            'ignored_non_equipment': excluded_pickups,
            'limitation': 'Current ground pickup to pending native payload association only. No backend acceptance or ownership claim. No writes or network requests.'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    ue = ReadOnlyUE()
    try:
        result = capture(ue)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'out': str(args.out), 'records': [
            {'id': r['item']['id'], 'gameplayTag': r['item']['gameplayTag'], 'handle': r['loot_item_handle'],
             'distance': r['distance_game_units'], 'traits': len(r['item']['traits'])} for r in result['records']],
            'unresolved': result['unresolved']}))
    finally:
        ue.close()


if __name__ == '__main__':
    main()
