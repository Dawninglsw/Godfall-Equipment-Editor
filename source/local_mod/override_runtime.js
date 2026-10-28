/* Local equipment presentation / UE payload copies. Does not edit account state. */
(function (g) {
  "use strict";
  var config = __GODFALL_EQUIPMENT_CONFIG__;
  function same(a, b) { return typeof a === "number" && Math.abs(a - b) < 0.00001; }
  function copyEffect(effect, rule) {
    if (!effect || effect.lootEffectName !== rule.lootEffectName ||
        (effect.traitName && effect.traitName !== rule.traitName) || !Array.isArray(effect.params)) return effect;
    var changed = false;
    var params = effect.params.map(function (p) {
      if (!p || p.magnitudeName !== rule.magnitudeName ||
          (!same(p.magnitude, rule.baseline) && !same(p.magnitude, rule.value)) || same(p.magnitude, rule.value)) return p;
      changed = true;
      return Object.assign({}, p, { magnitude: rule.value });
    });
    return changed ? Object.assign({}, effect, { params: params }) : effect;
  }
  function copyEffects(list, rule) {
    if (!Array.isArray(list)) return list;
    var changed = false;
    var result = list.map(function (effect) {
      var updated = copyEffect(effect, rule);
      if (updated !== effect) changed = true;
      return updated;
    });
    return changed ? result : list;
  }
  function copyItemEffects(list, item, rule) {
    if (!Array.isArray(list)) return list;
    var labelled = list.filter(function (effect) {
      return effect && effect.traitName === rule.traitName && effect.lootEffectName === rule.lootEffectName;
    });
    if (labelled.length > 1) return list;
    var allowUnlabelled = false;
    if (Array.isArray(item.traits)) {
      var origins = 0;
      item.traits.forEach(function (trait) {
        (trait && Array.isArray(trait.lootEffects) ? trait.lootEffects : []).forEach(function (effect) {
          if (effect && effect.lootEffectName === rule.lootEffectName) origins++;
        });
      });
      var unlabelled = list.filter(function (effect) {
        return effect && !effect.traitName && effect.lootEffectName === rule.lootEffectName;
      });
      allowUnlabelled = labelled.length === 0 && origins === 1 && unlabelled.length === 1 && matchingTraits(item, rule).length === 1;
    }
    var changed = false;
    var result = list.map(function (effect) {
      if (!effect || (!effect.traitName && !allowUnlabelled)) return effect;
      var next = copyEffect(effect, rule);
      if (next !== effect) changed = true;
      return next;
    });
    return changed ? result : list;
  }
  function applyItem(item) {
    if (!config.enabled || !item || typeof item !== "object" || !item.id) return item;
    var result = applyTypeItem(item);
    config.items.forEach(function (rule) {
      if (item.id !== rule.id || item.gameplayTag !== rule.gameplayTag) return;
      if (Array.isArray(item.traits)) {
        var source = matchingTraits(item, rule);
        if (source.length !== 1 || source[0].lootEffects.filter(function (effect) {
          return effect && effect.lootEffectName === rule.lootEffectName;
        }).length !== 1) return;
      }
      var patch = {};
      ["effects", "lootEffects"].forEach(function (key) {
        var updated = copyItemEffects(result[key], result, rule);
        if (updated !== result[key]) patch[key] = updated;
      });
      if (Array.isArray(result.traits)) {
        var traitChanged = false;
        var traits = result.traits.map(function (trait) {
          if (!trait || trait.traitName !== rule.traitName) return trait;
          var updated = copyEffects(trait.lootEffects, rule);
          if (updated === trait.lootEffects) return trait;
          traitChanged = true;
          return Object.assign({}, trait, { lootEffects: updated });
        });
        if (traitChanged) patch.traits = traits;
      }
      if (Object.keys(patch).length) result = Object.assign({}, result, patch);
    });
    return result;
  }
  function stable(value) {
    if (typeof value === "number") return Math.round(value * 1000000000) / 1000000000;
    if (Array.isArray(value)) return value.map(stable);
    if (value && typeof value === "object") {
      var out = {};
      Object.keys(value).sort().forEach(function (key) { if (value[key] !== undefined) out[key] = stable(value[key]); });
      return out;
    }
    return value;
  }
  function key(value) { return JSON.stringify(stable(value)); }
  function effectKey(effect) {
    return key({ traitName: effect.traitName || "", effect: effect.lootEffectName,
      tag: effect.gameplayTag || "", params: (effect.params || []).map(function (p) {
        return { magnitudeName: p.magnitudeName, magnitude: p.magnitude };
      }).sort(function (a, b) {
        return a.magnitudeName < b.magnitudeName ? -1 : a.magnitudeName > b.magnitudeName ? 1 : 0;
      }) });
  }
  function traitKey(trait) {
    return key({ name: trait.traitName, category: trait.traitCategoryName, slot: trait.slotType,
      bonus: trait.masterworkBonusTier || 0, mutations: trait.mutationNames || [],
      conditional: trait.conditionalLootEffects || [], effects: (trait.lootEffects || []).map(function (e) {
        return effectKey(Object.assign({}, e, { traitName: trait.traitName }));
      }).sort() });
  }
  function traitsEqual(a, b) {
    return Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every(function (t, i) { return traitKey(t) === traitKey(b[i]); });
  }
  function affectedEffectKeys(replacements) {
    var keys = {};
    replacements.forEach(function (r) {
      r.sourceEngineEffects.concat(r.targetEngineEffects).forEach(function (e) { keys[effectKey(e)] = true; });
    });
    return keys;
  }
  function effectCounts(list, keys) {
    return (list || []).filter(function (e) { return e && keys[effectKey(e)]; }).map(effectKey).sort();
  }
  function engineCompatible(actual, expected) {
    return effectKey(actual) === effectKey(expected) && key(actual.mutationNames || []) === key(expected.mutationNames || []) &&
      key(actual.ongoingTagRequirements || []) === key(expected.ongoingTagRequirements || []) &&
      key(actual.execProcessors || []) === key(expected.execProcessors || []);
  }
  function replaceEffectGroups(list, before, after, replacements) {
    if (!Array.isArray(list)) return list;
    if (list.some(function (effect) { return !effect || typeof effect !== "object" || !Array.isArray(effect.params); })) return null;
    var affected = affectedEffectKeys(replacements), current = key(effectCounts(list, affected));
    if (current === key(effectCounts(after, affected))) return list;
    if (current !== key(effectCounts(before, affected))) return null;
    var removed = {}, inserts = {};
    for (var ri = 0; ri < replacements.length; ri++) {
      var r = replacements[ri], first = -1;
      for (var ei = 0; ei < r.sourceEngineEffects.length; ei++) {
        for (var mi = 0; mi < list.length; mi++) {
          if (effectKey(list[mi]) === effectKey(r.sourceEngineEffects[ei]) && !engineCompatible(list[mi], r.sourceEngineEffects[ei])) return null;
        }
        var found = -1;
        for (var i = 0; i < list.length; i++) {
          if (!removed[i] && engineCompatible(list[i], r.sourceEngineEffects[ei])) { found = i; break; }
        }
        if (found < 0) return null;
        removed[found] = true;
        if (first < 0 || found < first) first = found;
      }
      if (first < 0) return null;
      inserts[first] = (inserts[first] || []).concat(JSON.parse(JSON.stringify(r.targetEngineEffects)));
    }
    var result = [];
    list.forEach(function (effect, index) {
      if (inserts[index]) result = result.concat(inserts[index]);
      if (!removed[index]) result.push(effect);
    });
    return key(effectCounts(result, affected)) === key(effectCounts(after, affected)) ? result : null;
  }
  function matchesTypeItem(item, group) {
    if (!item || item.id !== group.id || item.gameplayTag !== group.gameplayTag) return false;
    if (item.tierIdentifier !== undefined && item.tierIdentifier !== group.tierIdentifier) return false;
    if (item.rarityIdentifier !== undefined && item.rarityIdentifier !== group.rarityIdentifier) return false;
    if (item.masterworkUpgradeRank !== undefined && item.masterworkUpgradeRank !== group.masterworkUpgradeRank) return false;
    return true;
  }
  function replacedTraits(traits, group) {
    return traits.map(function (trait, index) {
      var replacement = group.replacements.filter(function (r) { return r.index === index; })[0];
      return replacement ? Object.assign({}, trait, JSON.parse(JSON.stringify(replacement.targetTrait))) : trait;
    });
  }
  function traitEffects(traits) {
    var effects = [];
    traits.forEach(function (trait) { effects = effects.concat(trait.lootEffects || []); });
    return effects;
  }
  function replaceDisplayCache(list, group) {
    // The inventory UI also stores a plain concatenation of raw loot effects,
    // without engine trait names or conditions. Accept this shape only after
    // verifying both the complete item traits and the complete cache contents.
    var before = traitEffects(group.sourceTraits), after = traitEffects(group.targetTraits);
    if (list.some(function (effect) { return !effect || effect.traitName; })) return null;
    var current = key(list.map(effectKey).sort());
    if (current !== key(before.map(effectKey).sort()) && current !== key(after.map(effectKey).sort())) return null;
    var replacements = group.replacements.map(function (r) {
      return { sourceEngineEffects: r.sourceTrait.lootEffects, targetEngineEffects: r.targetTrait.lootEffects };
    });
    return replaceEffectGroups(list, before, after, replacements);
  }
  function applyTypeItem(item) {
    var result = item;
    (config.traitTypeRules || []).forEach(function (group) {
      if (!matchesTypeItem(result, group)) return;
      var patch = {};
      if (Array.isArray(result.traits)) {
        if (traitsEqual(result.traits, group.sourceTraits)) patch.traits = replacedTraits(result.traits, group);
        else if (!traitsEqual(result.traits, group.targetTraits)) return;
      }
      var invalid = false;
      ["effects", "lootEffects"].forEach(function (field) {
        if (!Array.isArray(result[field])) return;
        var effects = replaceEffectGroups(result[field], group.sourceEngineEffects, group.targetEngineEffects, group.replacements);
        if (effects === null && field === "lootEffects" && Array.isArray(result.traits)) effects = replaceDisplayCache(result[field], group);
        if (effects === null) invalid = true;
        else if (effects !== result[field]) patch[field] = effects;
      });
      if (!invalid && Object.keys(patch).length) result = Object.assign({}, result, patch);
    });
    return result;
  }
  function rawEffects(gear) {
    var effects = [];
    gear.forEach(function (item) { (item.traits || []).forEach(function (trait) {
      (trait.lootEffects || []).forEach(function (effect) { effects.push(Object.assign({}, effect, { traitName: trait.traitName })); });
    }); });
    return effects;
  }
  function applyAggregatedTypes(character, info) {
    var applicable = [];
    (config.traitTypeRules || []).forEach(function (group) {
      var owned = (info.aggregatedGear || []).filter(function (item) { return matchesTypeItem(item, group); });
      if (owned.length === 1 && (traitsEqual(owned[0].traits, group.sourceTraits) || traitsEqual(owned[0].traits, group.targetTraits))) applicable.push(group);
    });
    if (!applicable.length) return character;
    var replacements = [];
    applicable.forEach(function (g) { replacements = replacements.concat(g.replacements); });
    var afterGear = info.aggregatedGear.map(function (item) {
      var group = applicable.filter(function (g) { return matchesTypeItem(item, g); })[0];
      return group ? Object.assign({}, item, { traits: replacedTraits(item.traits, group) }) : item;
    });
    // Validate the complete affected multiset. Identical effects from two rings
    // remain distinguishable in count: replace exactly one, preserve the other.
    var updated = replaceEffectGroups(character.augments.valorplate.effects, rawEffects(info.aggregatedGear), rawEffects(afterGear), replacements);
    if (!updated || updated === character.augments.valorplate.effects) return character;
    return Object.assign({}, character, { augments: Object.assign({}, character.augments, {
      valorplate: Object.assign({}, character.augments.valorplate, { effects: updated })
    }) });
  }
  function primaryAttributeTrait(item, cached) {
    if (!cached || !item || !Array.isArray(item.traits)) return cached;
    var original = item.traits.filter(function (trait) {
      return trait && trait.slotType === "Primary Attribute" && trait.traitName === cached.traitName;
    });
    if (original.length !== 1) return cached;
    var updated = applyItem(item);
    if (updated === item || !Array.isArray(updated.traits)) return cached;
    var matches = updated.traits.filter(function (trait) {
      return trait && trait.slotType === "Primary Attribute" && trait.traitName === cached.traitName;
    });
    // The game's model caches the raw account trait. Return a presentation copy
    // only when this specific primary attribute changed; keep the cache intact.
    return matches.length === 1 && matches[0] !== original[0] ? matches[0] : cached;
  }
  function entries(value) {
    if (!value || typeof value !== "object") return [];
    return Object.keys(value).map(function (key) { return value[key]; });
  }
  function presetInfo(state) {
    var player = state && state.player;
    var inventory = player && player.inventory;
    var selected = player && player.loadout && player.loadout.selectedValorplateId;
    var plates = inventory && entries(inventory.valorplates);
    if (!selected || !plates) return null;
    var matches = plates.filter(function (plate) { return plate && plate.id === selected; });
    if (matches.length !== 1) return null;
    var plate = matches[0];
    var preset = plate.presets && plate.presets[plate.selectedPresetIndex || 0];
    if (!preset) return null;
    var gear = [], aggregatedGear = [];
    ["weapons", "rings", "amulets", "charms", "augments", "energyShields", "consumables", "banners", "runes"].forEach(function (key) {
      entries(preset[key]).forEach(function (item) {
        if (item && item.id) {
          gear.push(item);
          if (["rings", "amulets", "charms", "augments", "energyShields", "runes"].indexOf(key) >= 0) aggregatedGear.push(item);
        }
      });
    });
    return { plate: plate, preset: preset, gear: gear, aggregatedGear: aggregatedGear };
  }
  function matchingTraits(item, rule) {
    return item && Array.isArray(item.traits) ? item.traits.filter(function (trait) {
      return trait && trait.traitName === rule.traitName && Array.isArray(trait.lootEffects) && trait.lootEffects.some(function (effect) {
        return effect && effect.lootEffectName === rule.lootEffectName;
      });
    }) : [];
  }
  function applyAggregated(character, info) {
    if (!info || !character || typeof character.gameplayTag !== "string" ||
        character.gameplayTag.indexOf("Character.Player.") !== 0 ||
        (character.valorplateBaseGameplayTag || character.gameplayTag) !== info.plate.gameplayTag ||
        !character.weapons || !character.augments || !character.augments.valorplate ||
        !Array.isArray(character.augments.valorplate.effects)) return character;
    var weaponSlots = Object.keys(info.preset.weapons || {});
    if (!weaponSlots.length || !weaponSlots.every(function (slot) {
      var source = info.preset.weapons[slot], target = character.weapons[slot];
      return source && source.id ? target && target.id === source.id : !target;
    })) return character;
    var result = applyAggregatedTypes(character, info);
    config.items.forEach(function (rule) {
      if (rule.aggregation !== "valorplate") return;
      var owned = info.gear.filter(function (item) { return item.id === rule.id && item.gameplayTag === rule.gameplayTag; });
      if (owned.length !== 1 || matchingTraits(owned[0], rule).length !== 1) return;
      // Flattened accessories no longer carry item IDs. Require a unique trait
      // origin in the exact selected preset; never select an effect by value alone.
      var origins = info.gear.filter(function (item) { return matchingTraits(item, rule).length > 0; });
      if (origins.length !== 1) return;
      var sourceEffects = matchingTraits(owned[0], rule)[0].lootEffects;
      if (!sourceEffects.some(function (effect) {
        return effect.lootEffectName === rule.lootEffectName && Array.isArray(effect.params) && effect.params.some(function (p) {
          return p.magnitudeName === rule.magnitudeName && (same(p.magnitude, rule.baseline) || same(p.magnitude, rule.value));
        });
      })) return;
      var effects = result.augments.valorplate.effects;
      var matches = [];
      effects.forEach(function (effect, index) {
        if (effect && effect.traitName === rule.traitName && effect.lootEffectName === rule.lootEffectName &&
            Array.isArray(effect.params) && effect.params.some(function (p) {
              return p.magnitudeName === rule.magnitudeName && (same(p.magnitude, rule.baseline) || same(p.magnitude, rule.value));
            })) matches.push(index);
      });
      if (matches.length !== 1) return;
      var index = matches[0], updated = copyEffect(effects[index], rule);
      if (updated === effects[index]) return;
      var copied = effects.slice(); copied[index] = updated;
      result = Object.assign({}, result, { augments: Object.assign({}, result.augments, {
        valorplate: Object.assign({}, result.augments.valorplate, { effects: copied })
      }) });
    });
    return result;
  }
  function walk(value, depth, info) {
    if (!value || typeof value !== "object" || depth > 32) return value;
    if (Array.isArray(value)) {
      var changed = false;
      var list = value.map(function (child) {
        var next = walk(child, depth + 1, info);
        if (next !== child) changed = true;
        return next;
      });
      return changed ? list : value;
    }
    var result = applyAggregated(applyItem(value), info);
    Object.keys(result).forEach(function (key) {
      var next = walk(result[key], depth + 1, info);
      if (next !== result[key]) {
        if (result === value) result = Object.assign({}, result);
        result[key] = next;
      }
    });
    return result;
  }
  g.__GodfallLocalEquipmentMod = {
    version: 5,
    applyItem: applyItem,
    primaryAttributeTrait: primaryAttributeTrait,
    applyEngineMessage: function (message, state) { return config.enabled ? walk(message, 0, presetInfo(state)) : message; }
  };
  function badge() {
    if (!config.enabled || !g.document || !g.document.body || g.document.getElementById("godfall-local-equipment-marker")) return;
    var node = g.document.createElement("div");
    node.id = "godfall-local-equipment-marker";
    node.textContent = "本地装备设置已加载";
    node.style.cssText = "position:fixed;left:12px;bottom:8px;z-index:2147483647;pointer-events:none;color:#f8d58b;background:rgba(0,0,0,.6);font:14px sans-serif;padding:4px 8px;";
    g.document.body.appendChild(node);
  }
  if (g.document) {
    if (g.document.readyState === "loading") g.document.addEventListener("DOMContentLoaded", badge);
    else badge();
  }
})(window);

