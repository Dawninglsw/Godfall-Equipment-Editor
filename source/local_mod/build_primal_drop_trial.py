"""Stage a combined equipment + primal chance trial. Installation is explicit."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import build_local_mod as equipment
from trait_types import NODE

HERE = Path(__file__).resolve().parent


def build(multiplier=2, output=None):
    output = Path(output) if output else HERE / 'build_primal_drop_trial'
    # Preserve the currently configured equipment rules exactly.
    pak, base = equipment.build(output_dir=output / 'equipment_base', include_primal=False)
    subprocess.run([str(NODE), str(HERE / 'compile_primal_drop_trial.cjs'), str(multiplier), str(output)],
                   check=True, capture_output=True, encoding='utf-8',
                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    compiler = "const fs=require('fs'),m=require(process.argv[1]);const source=fs.readFileSync(process.argv[2],'utf8');fs.writeFileSync(process.argv[3],m.patch(source));"
    source_path = output / 'equipment_base/main.c05310c4.chunk.js'
    patched_path = output / 'drop_integrated_source.js'
    subprocess.run([str(NODE), '-e', compiler, str(HERE / 'compile_primal_drop_trial.cjs'), str(source_path), str(patched_path)],
                   check=True, capture_output=True, encoding='utf-8',
                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    runtime = (output / 'primal_drop_configured.js').read_bytes()
    combined = runtime + b'\n' + patched_path.read_bytes()
    main = output / 'main.c05310c4.chunk.js'
    main.write_bytes(combined)
    subprocess.run([str(NODE), '--check', str(main)], check=True, capture_output=True,
                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    pak = output / equipment.PAK_NAME
    equipment.make_pak(pak, combined)
    verification = equipment.inspect_pak(pak, extract_to=output / 'verified_extraction')
    if (output / 'verified_extraction/main.c05310c4.chunk.js').read_bytes() != combined:
        raise RuntimeError('Independent extraction differs from primal trial source')
    config = json.loads((output / 'primal_drop_config.json').read_bytes())
    report = {**base, 'pak': str(pak), 'pak_sha256': hashlib.sha256(pak.read_bytes()).hexdigest(),
              'patched_sha256': hashlib.sha256(combined).hexdigest(), 'verification': verification,
              'changed_integration_points': base['changed_integration_points'] + 2,
              'primal_drop_config': config,
              'scope': 'Preserved existing equipment rules plus scoped primal reward chance copies. No original tables, inventory request code or item mutation logic changed.',
              'runtime_status': 'built_not_loaded_or_live_verified'}
    (output / 'build_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return pak, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--multiplier', type=int, choices=[2, 3, 5], default=2)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    pak, report = build(args.multiplier, args.output)
    print(json.dumps({'status': 'staged_not_installed', 'pak': str(pak), 'pak_sha256': report['pak_sha256'],
                      'primal_multiplier': report['primal_drop_config']['multiplier'],
                      'approved_rows': len(report['primal_drop_config']['rows'])}))


if __name__ == '__main__':
    main()
