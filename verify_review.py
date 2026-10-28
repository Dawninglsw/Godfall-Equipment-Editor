"""Check disclosed source against the preserved distribution manifest; no game access."""
import hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
def sha(data):return hashlib.sha256(data).hexdigest()
def verify():
    audit=json.loads((ROOT/'REVIEW-MANIFEST.json').read_bytes())
    reference=json.loads((ROOT/'REFERENCE-DISTRIBUTION-MANIFEST.json').read_bytes())
    for name,record in audit['source_files'].items():
        path=ROOT/'source'/name
        data=path.read_bytes()
        assert len(data)==record['bytes'] and sha(data)==record['sha256'],name
        assert record==reference['files'][name],name
    expected={n for n in reference['files'] if not n.startswith('runtime/')}
    actual={str(p.relative_to(ROOT/'source')).replace('\\','/') for p in (ROOT/'source').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    assert expected==actual,'Source file list differs'
    assert json.loads((ROOT/'source/local_mod/application_settings.json').read_bytes())=={'version':1,'language':'en'}
    assert not any(Path(n).suffix.lower() in {'.exe','.dll','.pyd','.pak','.zip','.7z','.rar'} for n in actual)
    assert (ROOT/'source/local_mod/launch_portable.ps1').read_bytes().startswith(b'\xef\xbb\xbf')
    return audit
if __name__=='__main__':
    audit=verify()
    print(json.dumps({'status':'verified','source_files':len(audit['source_files']),'distribution_sha256':audit['distribution_sha256'],'game_access':False},indent=2))
