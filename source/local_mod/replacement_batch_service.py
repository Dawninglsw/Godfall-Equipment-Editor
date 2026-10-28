"""Batch independently compiled item plans; stage locally and install only after exit."""
from datetime import datetime, timezone
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import uuid

from editor_model import HERE, write_atomic
from settings_backups import managed_destination, sha
import build_replacement_copy_trial as trial
import replacement_service as single
from equipment_names import equipment_name
from trait_types import trim_item,trait_label,trait_value_text

MAX_ITEMS = 8


def read_preview(entry):
    if entry.get('editable_draft'):
        item=entry['source_item']
        if item['id']!=entry['source_id'] or single.availability(item):
            raise ValueError('本件草稿的原件不完整或尚不支持同款生成。')
        return {'source_materialized':deepcopy(item),
                'expected_materialized':deepcopy(entry.get('draft_target',item))}
    path = Path(entry['preview_path']).resolve()
    if not path.is_relative_to((HERE/'replacement_builds').resolve()) or not path.is_file() or path.stat().st_size>2*1024*1024:
        raise ValueError('请选择本工具制作的单件同款方案。')
    if path.stat().st_size > 2*1024*1024 or sha(path) != entry['preview_sha256']:
        raise ValueError('单件方案文件已变化，请移除后重新加入。')
    preview = json.loads(path.read_bytes())
    if preview.get('source_id') != entry['source_id']:
        raise ValueError('单件方案的原件编号不一致。')
    return preview


def entry_from_item(item):
    source=trim_item(item)
    source['masterworkUpgradeRank']=source.get('masterworkUpgradeRank') or 0
    source['mutationNames']=source.get('mutationNames') or []
    reason=single.availability(source)
    if reason:raise ValueError(equipment_name(source)+'：'+reason)
    if not any(t.get('slotType')=='Secondary Trait' for t in source.get('traits',[])):
        raise ValueError(equipment_name(source)+'：没有可编辑的副词条。')
    return {'source_id':source['id'],'trial_id':'draft-'+hashlib.sha256(source['id'].encode()).hexdigest()[:24],
            'label':equipment_name(source),'family':source['lootClassName'],
            'primal':source['mutationNames']==['Mutation.Item.Primal'],
            'awakened':single.is_awakened_ring(source),'upgrade_rank':source['masterworkUpgradeRank'],
            'preview_path':'','preview_sha256':'','changes':[],
            'editable_draft':True,'source_item':source,'editor_edits':[]}


def edit_request(entry):
    preview=read_preview(entry);source=preview['source_materialized']
    if 'editor_edits' in entry:return deepcopy(source),deepcopy(entry['editor_edits'])
    edits=[]
    for change in entry['changes']:
        index=change['index'];target=preview['expected_materialized']['traits'][index]
        qualities=preview['quality_reconstruction'][index]
        quality=next((p['quality'] for p in qualities if 'quality' in p),.5)
        edits.append({'index':index,'targetTraitName':target['traitName'],
                      'targetCategoryName':target['traitCategoryName'],'quality':quality})
    return deepcopy(source),edits


def edited_entry(source,edits,result):
    entry=entry_from_item(source)
    entry['editor_edits']=deepcopy(edits)
    entry['trial_id']='draft-'+result['trialId']
    entry['draft_target']=deepcopy(result['preview']['expected_materialized'])
    entry['changes']=[{'index':c['index'],'source_trait':trait_label(source['traits'][c['index']]),
                      'source_value':trait_value_text(source['traits'][c['index']]),
                      'target_trait':c['label'],'target_value':trait_value_text(c['targetTrait'])} for c in result['choices']]
    return entry


def entry_from_plan(plan):
    entry = {key: plan[key] for key in ['source_id', 'trial_id', 'label', 'preview_path']}
    path = Path(entry['preview_path']).resolve()
    if not path.is_relative_to((HERE/'replacement_builds').resolve()) or not path.is_file():
        raise ValueError('请选择本工具制作的单件同款方案。')
    entry['preview_sha256'] = sha(path)
    entry['changes'] = deepcopy(plan.get('changes')) or [{'source_trait':plan['source_trait'], 'source_value':plan['source_value'],
                                             'target_trait':plan['target_trait'], 'target_value':plan['target_value']}]
    entry['family'] = plan['family']; entry['upgrade_rank'] = plan.get('upgrade_rank', 0)
    entry['primal'] = bool(plan.get('primal')); entry['awakened'] = bool(plan.get('awakened'))
    read_preview(entry)
    return entry


def validate_entries(entries):
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_ITEMS:
        raise ValueError('每批请选择1至8件装备。')
    if any(not isinstance(e,dict) or not isinstance(e.get('source_id'),str) for e in entries):
        raise ValueError('批量清单中的单件方案不完整。')
    if len({e['source_id'] for e in entries}) != len(entries):
        raise ValueError('每件原件只能加入一份批量修改。')
    return [read_preview(e) for e in entries]


def load_draft():
    try:
        value = json.loads((HERE/'batch_draft.json').read_bytes())
        entries = value['entries']
        if value.get('version') != 1 or not isinstance(entries, list) or len(entries) > MAX_ITEMS:
            return []
        if any(not isinstance(e,dict) or not all(k in e for k in ['source_id','trial_id','label','preview_path','preview_sha256','changes']) for e in entries):
            return []
        if len({e['source_id'] for e in entries}) != len(entries):
            return []
        return entries
    except (OSError, ValueError, KeyError, TypeError):
        return []


def save_draft(entries):
    if not isinstance(entries,list) or len(entries)>MAX_ITEMS:
        raise ValueError('批量清单需为最多8件的列表。')
    if entries:
        validate_entries(entries)
    path = HERE/'batch_draft.json'
    if path.exists():
        folder = HERE/'batch_draft_backups'; folder.mkdir(exist_ok=True)
        write_atomic(folder/(uuid.uuid4().hex+'.json'), path.read_bytes())
    write_atomic(path, json.dumps({'version':1, 'entries':entries}, ensure_ascii=False, indent=2).encode('utf-8'))


def load_plan():
    try:
        plan = json.loads((HERE/'batch_plan.json').read_bytes())
        return plan if plan.get('version') == 1 else None
    except (OSError, ValueError):
        return None


def prepare(entries, *, publish=True):
    validate_entries(entries)
    for entry in entries:
        if entry.get('editable_draft') and not entry.get('editor_edits'):
            raise ValueError(entry['label']+' 尚未设置词条修改，请先编辑或移除。')
    resolved=[]
    for entry in entries:
        if entry.get('editable_draft'):
            source,edits=edit_request(entry)
            if any(source['traits'][e['index']]['slotType']=='Primary Trait' for e in edits):
                if len(edits)!=1:raise ValueError('随机主词条方案一次只改一条，不与副词条混改。')
                edit=edits[0];plan=single.prepare(source,edit['index'],edit,publish=False)
            else:plan=single.prepare_many(source,edits,publish=False)
            compiled=entry_from_plan(plan);compiled['editor_edits']=edits
            resolved.append(compiled)
        else:resolved.append(entry)
    entries=resolved
    previews = validate_entries(entries)
    folder = HERE/'batch_builds'/uuid.uuid4().hex; folder.mkdir(parents=True)
    source = folder/'previews.json'
    write_atomic(source, json.dumps(previews, ensure_ascii=False, indent=2).encode('utf-8'))
    try:
        _, report = trial.build(source, folder/'package', batch=True)
    except subprocess.CalledProcessError as error:
        message = (error.stderr or b'').decode('utf-8', errors='replace') if isinstance(error.stderr, bytes) else error.stderr or ''
        if '完全相同的目标' in message:
            raise ValueError('本批次有完全相同的目标物品，请只保留一份。') from None
        raise ValueError('批量方案未通过重新编译；请核对单件方案，游戏未改变。') from None
    configs = json.loads((folder/'package/batch_config.json').read_bytes())['configs']
    if [(c['sourceId'],c['trialId']) for c in configs] != [(e['source_id'],e['trial_id']) for e in entries]:
        raise ValueError('单件方案与重新计算结果不一致，请重新制作单件方案。')
    config = (HERE/'overrides.json').read_bytes()
    state_bytes = (HERE/'installed_patch.json').read_bytes(); state = json.loads(state_bytes)
    destination = managed_destination(state)
    if sha(destination) != state['pak_sha256']:
        raise ValueError('当前补丁与安装记录不一致，未安装。')
    plan = {'version':1, 'status':'prepared_not_installed', 'prepared_at_utc':datetime.now(timezone.utc).isoformat(),
            'batch_id':report['replacement_batch_trial']['batch_id'], 'entries':deepcopy(entries),
            'report_path':str(folder/'package/build_report.json'), 'config_path':str(folder/'package/batch_config.json'),
            'report_sha256':sha(folder/'package/build_report.json'), 'config_sha256':sha(folder/'package/batch_config.json'),
            'pak_sha256':report['pak_sha256'], 'expected_config_sha256':hashlib.sha256(config).hexdigest(),
            'expected_installation_record_sha256':hashlib.sha256(state_bytes).hexdigest(),
            'expected_current_pak_sha256':sha(destination)}
    write_atomic(folder/'plan.json', json.dumps(plan,ensure_ascii=False,indent=2).encode('utf-8'))
    if publish:
        save_draft(entries)
        write_atomic(HERE/'batch_plan.json', json.dumps(plan,ensure_ascii=False,indent=2).encode('utf-8'))
    return plan


def install(plan):
    if load_plan() != plan:
        raise ValueError('批量方案已被其他窗口更新，请重新查看。')
    report_path = Path(plan['report_path']).resolve()
    if not report_path.is_relative_to((HERE/'batch_builds').resolve()):
        raise ValueError('请选择本工具制作的批量方案。')
    if Path(plan['config_path']).resolve() != report_path.parent/'batch_config.json':
        raise ValueError('批量配置位置不一致。')
    report = json.loads(report_path.read_bytes())
    if (sha(report_path) != plan['report_sha256'] or sha(plan['config_path']) != plan['config_sha256'] or
            report['replacement_batch_trial']['batch_id'] != plan['batch_id'] or report['pak_sha256'] != plan['pak_sha256']
            or sha(report['pak']) != plan['pak_sha256']):
        raise ValueError('批量方案与生成包不一致，未安装。')
    if [(i['source_id'],i['trial_id']) for i in report['replacement_batch_trial']['items']] != [(e['source_id'],e['trial_id']) for e in plan['entries']]:
        raise ValueError('批量清单与生成包中的物品不一致。')
    config = (HERE/'overrides.json').read_bytes(); state_bytes = (HERE/'installed_patch.json').read_bytes()
    if (hashlib.sha256(config).hexdigest() != plan['expected_config_sha256'] or
            hashlib.sha256(state_bytes).hexdigest() != plan['expected_installation_record_sha256']):
        raise ValueError('当前设置或安装状态已变化，请重新制作批量方案。')
    result = trial.install_staged(report_path, config, plan['expected_current_pak_sha256'], batch=True)
    payload = (HERE/'overrides.json').read_bytes()
    return {**result, 'config_bytes':payload, 'config':json.loads(payload),
            'message':'批量生成已安装并备份。下次单人正常掉落时逐件生成；每件独立防重复，需正常拾取。'}


def read_status(plan):
    from settings_service import installation_state, run_local
    if installation_state().get('replacement_batch_trial',{}).get('batch_id') != plan['batch_id']:
        raise ValueError('当前没有安装这份批量方案。')
    report_path=Path(plan['report_path']).resolve()
    if not report_path.is_relative_to((HERE/'batch_builds').resolve()):
        raise ValueError('请选择本工具制作的批量方案。')
    output = report_path.parent/'batch_trace.json'
    run_local(HERE.parent/'analysis/recalibrate_runtime.py', timeout=20)
    run_local(HERE.parent/'analysis/read_replacement_batch_trace.py', ['--out',output], timeout=55)
    return json.loads(output.read_bytes()).get('trace')


def matches_in_snapshot(plan, snapshot):
    if not snapshot or not snapshot.get('live_process'):
        return {}
    config = json.loads(Path(plan['config_path']).read_bytes())
    def traits(rows):
        return [{'name':t['traitName'],'category':t['traitCategoryName'],'slot':t['slotType'],
                 'bonus':t.get('masterworkBonusTier',0),'flags':t.get('mutationNames',[]),
                 'effects':t.get('lootEffects',[]),'conditional':t.get('conditionalLootEffects',[])} for t in rows]
    found = {}
    for c in config['configs']:
        target = {'gameplayTag':c['gameplayTag'],'lootClassName':c['lootClassName'],'tierIdentifier':c['tierIdentifier'],
                  'rarityIdentifier':c['rarityIdentifier'],'masterworkUpgradeRank':c['masterworkUpgradeRank'],
                  'mutationNames':c['mutationNames'],'selectedTraitTags':c['selectedTraitTags'],
                  'lootAttributes':c['sourceLootAttributes'],'damageTypes':c['damageTypes'],'amount':c['amount']}
        def attribute(item,key):
            if key=='masterworkUpgradeRank':return item.get(key) or 0
            if key=='mutationNames':return item.get(key) or []
            return item.get(key,1 if key=='amount' else None)
        matches = [i['id'] for i in snapshot['items'] if i['id'] != c['sourceId'] and not i.get('objectives')
                   and all(attribute(i,k)==v for k,v in target.items())
                   and traits(i.get('traits',[]))==traits(c['expectedTraits'])]
        found[c['trialId']] = matches
    return found
