"""Compose the verified scoped drop runtime with a normal equipment build."""
import json
from pathlib import Path
import subprocess

from primal_drop_settings import validate_primal
from trait_types import NODE

HERE = Path(__file__).resolve().parent


def compose(source, profile, output):
    profile = validate_primal(profile)
    if not profile['enabled']:
        return source, None
    component = Path(output) / 'primal_component'
    component.mkdir(parents=True, exist_ok=True)
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    subprocess.run([str(NODE), str(HERE / 'compile_primal_drop_trial.cjs'), str(profile['multiplier']), str(component)],
                   check=True, capture_output=True, encoding='utf-8', creationflags=flags)
    before, after = component / 'equipment_source.js', component / 'integrated_source.js'
    before.write_text(source, encoding='utf-8')
    command = "const fs=require('fs'),m=require(process.argv[1]);fs.writeFileSync(process.argv[3],m.patch(fs.readFileSync(process.argv[2],'utf8')));"
    subprocess.run([str(NODE), '-e', command, str(HERE / 'compile_primal_drop_trial.cjs'), str(before), str(after)],
                   check=True, capture_output=True, encoding='utf-8', creationflags=flags)
    runtime = (component / 'primal_drop_configured.js').read_text(encoding='utf-8')
    return runtime + '\n' + after.read_text(encoding='utf-8'), json.loads((component / 'primal_drop_config.json').read_bytes())
