"""Read-only Godfall inspection. Writes evidence only under this analysis folder."""
from pathlib import Path
import hashlib
import io
import json
import re
import struct
import zlib
from tool_paths import game_directory

GAME = game_directory()
OUT = Path(__file__).resolve().parent
PAKS = GAME / "Aperion/Content/Paks"


class Reader:
    def __init__(self, data):
        self.f = io.BytesIO(data)

    def read(self, n):
        b = self.f.read(n)
        if len(b) != n:
            raise ValueError("Unexpected end of input")
        return b

    def num(self, fmt="I"):
        return struct.unpack("<" + fmt, self.read(struct.calcsize("<" + fmt)))[0]

    def string(self):
        n = self.num("i")
        if abs(n) > 100000:
            raise ValueError("Invalid string length")
        return self.read(abs(n) * (2 if n < 0 else 1)).decode(
            "utf-16le" if n < 0 else "utf-8"
        ).rstrip("\0")


def inspect_iostore(p):
    b = p.read_bytes()
    if b[:16] != b"-==--==--==--==-" or b[16] != 3:
        raise ValueError("Only the observed Godfall TOC version 3 is supported")
    head, n, nb, bs, nm, ml, block, di = struct.unpack_from("<8I", b, 20)
    flags = b[80]
    if flags & 6:
        raise ValueError("Encrypted or signed container is unsupported")
    start = head + n * 22 + nb * bs + nm * ml
    result = dict(file=p.name, toc_version=3, flags=flags, encrypted=False, chunks=n)
    if not di:
        return result, []
    r = Reader(b[start:start + di])
    mount = r.string()
    dirs = [tuple(r.num() for _ in range(4)) for _ in range(r.num())]
    files = [tuple(r.num() for _ in range(3)) for _ in range(r.num())]
    names = [r.string() for _ in range(r.num())]
    assert r.f.tell() == di, "Directory index length mismatch"
    paths = []
    visited_dirs, visited_files = set(), set()

    def walk(idx, parent):
        while idx != 0xffffffff:
            assert idx not in visited_dirs
            visited_dirs.add(idx)
            name, child, nxt, first = dirs[idx]
            path = parent if name == 0xffffffff else parent + names[name] + "/"
            fi = first
            while fi != 0xffffffff:
                assert fi not in visited_files
                visited_files.add(fi)
                fn, fnext, user = files[fi]
                assert user < n
                paths.append(dict(path=path + names[fn], chunk_index=user))
                fi = fnext
            if child != 0xffffffff:
                walk(child, path)
            idx = nxt

    walk(0, mount)
    assert len(paths) == len(files), "Directory traversal lost files"
    result.update(indexed_files=len(paths), directory_bytes=di, directory_verified=True)
    return result, paths


def inspect_pak(p, extract_to=None):
    with p.open("rb") as f:
        f.seek(-4096, 2)
        footer = f.read()
        magic = footer.rfind(bytes.fromhex("e1126f5a"))
        assert magic >= 17
        ver, offset, size = struct.unpack_from("<Iqq", footer, magic + 4)
        assert ver == 11 and footer[magic - 1] == 0
        f.seek(offset)
        index = f.read(size)
        assert hashlib.sha1(index).digest() == footer[magic + 24:magic + 44]
        r = Reader(index)
        mount, count, seed = r.string(), r.num(), r.num("Q")
        if r.num():
            r.read(36)
        assert r.num() == 1
        doff, dsize, dhash = r.num("Q"), r.num("Q"), r.read(20)
        encoded = r.read(r.num())
        f.seek(doff)
        directory = f.read(dsize)
        assert hashlib.sha1(directory).digest() == dhash
        dr = Reader(directory)
        entries = []
        for _ in range(dr.num()):
            dirname = dr.string()
            for _ in range(dr.num()):
                filename, loc = dr.string(), dr.num("i")
                entries.append((mount + dirname + filename, loc))
        extracted = []
        for path, loc in entries:
            if not re.search(r"source_data\.json$|main\.[^/]+\.js$|/index\.js$", path):
                continue
            assert loc >= 0
            er = Reader(encoded[loc:])
            bits = er.num()
            if bits & 63 == 63:
                er.num()
            data_offset = er.num("I" if bits & (1 << 31) else "Q")
            f.seek(data_offset)
            actual = Reader(f.read(65536))
            unused, compressed, uncompressed = actual.num("Q"), actual.num("Q"), actual.num("Q")
            comp = actual.num()
            digest = actual.read(20)
            blocks = [(actual.num("Q"), actual.num("Q")) for _ in range(actual.num())] if comp else []
            encrypted, block_size = actual.num("B"), actual.num()
            if encrypted or uncompressed >= 64 * 1024 * 1024:
                extracted.append(dict(path=path, size=uncompressed, encrypted=bool(encrypted),
                                      skipped="encrypted or above extraction limit", offset=data_offset))
                continue
            if not comp:
                f.seek(data_offset + actual.f.tell())
                data = f.read(uncompressed)
            else:
                chunks = []
                for start, end in blocks:
                    f.seek(data_offset + start)
                    chunks.append(zlib.decompress(f.read(end - start)))
                data = b"".join(chunks)
            assert len(data) == uncompressed
            assert hashlib.sha1(data).digest() == digest
            dest = (Path(extract_to) if extract_to is not None else OUT / "extracted") / Path(path).name
            dest.parent.mkdir(exist_ok=True)
            dest.write_bytes(data)
            extracted.append(dict(path=path, size=len(data), sha1_verified=True, local=str(dest)))
        return dict(file=p.name, version=ver, files=count, listed_files=len(entries),
                    index_sha1_verified=True, directory_sha1_verified=True,
                    extracted=extracted)


def main():
    OUT.mkdir(exist_ok=True)
    containers, relevant = [], []
    for p in sorted(PAKS.glob("*.utoc")):
        info, paths = inspect_iostore(p)
        containers.append(info)
        for entry in paths:
            if re.search(r"/Items/Loot/|CT_Attributes|CritChance|/LootEffects/", entry["path"], re.I):
                relevant.append(dict(container=p.name, **entry))
    exe = GAME / "Aperion/Binaries/Win64/Aperion-Win64-Shipping.exe"
    data = exe.read_bytes()
    names = set()
    for pattern, enc in [(rb"[\x20-\x7e]{5,240}", "ascii"),
                         (rb"(?:[\x20-\x7e]\x00){5,240}", "utf-16le")]:
        for m in re.finditer(pattern, data):
            s = m.group().decode(enc)
            if re.search(r"Loadout.*Json|PlayerLoot.*Payload|PlayerSession.*Loadout|CriticalHitChance|Server.*Loadout", s):
                names.add(s)
    evidence = dict(game_root=str(GAME), exe_sha256=hashlib.sha256(data).hexdigest(),
                    containers=containers, candidate_assets=relevant,
                    candidate_symbols=sorted(names), pak=inspect_pak(PAKS / "pakchunk0-WindowsNoEditor.pak"),
                    scope="Static inspection only. Symbols are candidates, not verified callable editing APIs. No gameplay or persistence test performed.")
    dest = OUT / "static_evidence.json"
    dest.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(dict(evidence=str(dest), containers=len(containers),
                         indexed_files=sum(c.get("indexed_files", 0) for c in containers),
                         candidate_assets=len(relevant), pak=evidence["pak"]), ensure_ascii=False))


if __name__ == "__main__":
    main()
