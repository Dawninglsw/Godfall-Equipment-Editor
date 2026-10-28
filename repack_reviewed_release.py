"""Reassemble disclosed sources with exact third-party runtime files; never install."""
from copy import copy
import argparse,hashlib,json
from pathlib import Path
import zipfile
from verify_review import ROOT,verify,sha

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-from-zip',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    audit=verify()
    original=args.runtime_from_zip.resolve();output=args.output.resolve()
    assert original!=output and not output.exists(),'Use a new output ZIP'
    assert sha(original.read_bytes())==audit['distribution_sha256'],'Not the reviewed baseline release'
    reference=(ROOT/'REFERENCE-DISTRIBUTION-MANIFEST.json').read_bytes()
    manifest=json.loads(reference)
    with zipfile.ZipFile(original) as source:
        prefix=audit['distribution_root']+'/'
        assert source.testzip() is None
        with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as dest:
            for info in source.infolist():
                assert info.filename.startswith(prefix)
                relative=info.filename[len(prefix):]
                if relative=='PACKAGE_MANIFEST.json':data=reference
                elif relative.startswith('runtime/'):data=source.read(info.filename)
                else:data=(ROOT/'source'/relative).read_bytes()
                if relative in manifest['files']:
                    record=manifest['files'][relative]
                    assert sha(data)==record['sha256'] and len(data)==record['bytes'],relative
                dest.writestr(copy(info),data)
        with zipfile.ZipFile(output) as rebuilt:
            assert rebuilt.testzip() is None
            assert rebuilt.namelist()==source.namelist()
            for info in source.infolist():
                assert rebuilt.read(info.filename)==source.read(info.filename),info.filename
    digest=sha(output.read_bytes())
    output.with_suffix('.zip.sha256').write_text(digest+'  '+output.name+'\n',encoding='ascii')
    print(json.dumps({'status':'all_payloads_match_reviewed_release','files':len(manifest['files'])+1,'sha256':digest,'byte_identical_zip':digest==audit['distribution_sha256'],'game_access':False},indent=2))
if __name__=='__main__':main()
