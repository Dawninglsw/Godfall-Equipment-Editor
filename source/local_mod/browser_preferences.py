"""Small UI-only picker preferences, separate from equipment drafts and patches."""
import json
from pathlib import Path

from editor_model import HERE,write_atomic
from inventory_snapshot import FAMILIES,RARITIES,SCOPES,SORTS
from random_primary_catalogue import FILTERS

PREFS_PATH=HERE/'browser_preferences.json'
ENUMS={
    'scope':SCOPES,'family':['全部类型',*FAMILIES.values()], 'rarity':['全部品质',*RARITIES.values()],
    'primal':['全部形态','仅原始装备','非原始装备','仅诅咒装备','已解除诅咒'], 'sort':SORTS,
    'weapon':['全部武器','长剑','双剑','巨剑','长柄武器','战锤'],'color':['全部颜色','红色','绿色','蓝色'],
    'equipped':['全部装备','已保存到配装','未保存到配装'],
    'random_primary': FILTERS,
}


def checked(value):
    if not isinstance(value,dict):return {}
    result={key:value[key] for key,options in ENUMS.items() if value.get(key) in options}
    for key in ['query','traits','plate_id']:
        if isinstance(value.get(key),str) and len(value[key])<=256:result[key]=value[key]
    if type(value.get('favorite')) is bool:result['favorite']=value['favorite']
    low,high=value.get('minimum',''),value.get('maximum','')
    if all(isinstance(v,str) and (not v or v.isdecimal() and len(v)<=3) for v in [low,high]):
        if 0<=int(low or 0)<=int(high or 999)<=999:result.update(minimum=low,maximum=high)
    return result


def load():
    try:
        if PREFS_PATH.stat().st_size>16384:return {}
        value=json.loads(PREFS_PATH.read_bytes())
        return checked(value.get('filters')) if value.get('version')==1 else {}
    except (OSError,ValueError,TypeError,AttributeError):return {}


def save(filters):
    write_atomic(PREFS_PATH,json.dumps({'version':1,'filters':checked(filters)},ensure_ascii=False,indent=2).encode('utf-8'))
