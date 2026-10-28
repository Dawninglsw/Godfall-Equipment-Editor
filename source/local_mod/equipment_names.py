"""Display names from the exact game's original simplified-Chinese UI dictionary."""
from functools import lru_cache
import json
from pathlib import Path
from localization import language

HERE = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def chinese_names():
    try:
        data = json.loads((HERE / 'chinese_item_names.json').read_bytes())
        if data.get('culture') != 'zh-CN' or data.get('version') != 1:
            return {}
        return data['names']
    except (OSError, ValueError, KeyError):
        return {}


def equipment_name(item, fallback=None):
    tag = item.get('gameplayTag', '') if isinstance(item, dict) else str(item)
    row=chinese_names().get(tag,{})
    original = row.get('english') if language()=='en' else row.get('name')
    if isinstance(original, str) and original.strip():
        return original.strip()
    return str(fallback if fallback is not None else tag).strip('"')


def chinese_trait_labels():
    return trait_labels_for(language())


@lru_cache(maxsize=2)
def trait_labels_for(culture):
    try:
        name='english_trait_labels.json' if culture=='en' else 'chinese_trait_labels.json'
        data = json.loads((HERE / name).read_bytes())
        if data.get('culture') != culture or data.get('version') != 1:
            return {}
        return data['labels']
    except (OSError, ValueError, KeyError):
        return {}
