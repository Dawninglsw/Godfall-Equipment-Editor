"""Public drop preferences shared by editor, builder and backups."""
from copy import deepcopy

SCOPE = 'tower_chest_primal_bonus'
MULTIPLIERS = (2, 3, 5)


def default_primal():
    return {'enabled': False, 'multiplier': 2, 'scope': SCOPE}


def validate_primal(value):
    if not isinstance(value, dict) or set(value) != {'enabled', 'multiplier', 'scope'}:
        raise ValueError('原始掉落设置格式不正确')
    if type(value['enabled']) is not bool or type(value['multiplier']) is not int or value['multiplier'] not in MULTIPLIERS:
        raise ValueError('原始掉落倍率仅支持2、3或5倍')
    if value['scope'] != SCOPE:
        raise ValueError('当前仅支持试炼之塔常规装备主题宝箱的原始额外奖励')
    return deepcopy(value)


def primal_preferences(config, state=None):
    if 'primalDrop' in config:
        return validate_primal(config['primalDrop'])
    state = state or {}
    if 'primalDrop' in state.get('config', {}):
        return validate_primal(state['config']['primalDrop'])
    if state.get('primal_drop'):
        return validate_primal(state['primal_drop'])
    trial = state.get('primal_drop_trial')
    if trial:
        return validate_primal({'enabled': True, 'multiplier': trial['multiplier'], 'scope': SCOPE})
    return default_primal()


def with_primal(config, state=None):
    result = deepcopy(config)
    result['primalDrop'] = primal_preferences(config, state)
    return result


def primal_label(profile):
    profile = validate_primal(profile)
    return f"原始额外奖励 ×{profile['multiplier']}" if profile['enabled'] else '原始掉落修改关闭'
