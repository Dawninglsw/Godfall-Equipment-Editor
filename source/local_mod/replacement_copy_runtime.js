/* One ordinary replacement item through the original loot factory and normal pickup. */
(function (g) {
  'use strict';
  var config = __GODFALL_REPLACEMENT_COPY_CONFIG__, consumed = false;
  var trace = { godfallReplacementCopy: 1, startedAt: Date.now(), sequence: 0,
    status: 'waiting', generatedId: '', eventTag: '', sourceId: config.sourceId };
  function copy(value) { return JSON.parse(JSON.stringify(value)); }
  function stable(value) {
    if (typeof value === 'number') return Math.round(value*1e9)/1e9;
    if (Array.isArray(value)) return value.map(stable);
    if (!value || typeof value !== 'object') return value;
    var result = {}; Object.keys(value).sort().forEach(function (key) {
      if (value[key] !== undefined) result[key] = stable(value[key]);
    }); return result;
  }
  function key(value) { return JSON.stringify(stable(value)); }
  function traitsKey(traits) {
    return key((traits || []).map(function (t) {
      return { name: t.traitName, category: t.traitCategoryName, slot: t.slotType,
        bonus: t.masterworkBonusTier || 0, mutations: t.mutationNames || [], conditional: t.conditionalLootEffects || [],
        effects: (t.lootEffects || []).map(function (e) { return { name: e.lootEffectName, tag: e.gameplayTag,
          params: (e.params || []).map(function (p) { return { name: p.magnitudeName, value: p.magnitude }; })
            .sort(function (a,b) { return a.name < b.name ? -1 : a.name > b.name ? 1 : 0; }) }; }) };
    }));
  }
  function matches(item, traits) {
    return item && item.gameplayTag === config.gameplayTag && item.lootClassName === config.lootClassName &&
      item.tierIdentifier === config.tierIdentifier && item.rarityIdentifier === config.rarityIdentifier &&
      (item.masterworkUpgradeRank || 0) === (config.masterworkUpgradeRank || 0) && key(item.mutationNames || []) === key(config.mutationNames || []) &&
      key(item.lootAttributes || {}) === key(config.sourceLootAttributes || {}) &&
      key(item.damageTypes || null) === key(config.damageTypes || null) &&
      (item.amount === undefined ? 1 : item.amount) === (config.amount || 1) &&
      key(item.selectedTraitTags || []) === key(config.selectedTraitTags) &&
      traitsKey(item.traits) === traitsKey(traits);
  }
  function publish(status, id, event) {
    trace.status = status; trace.sequence++;
    if (id) trace.generatedId = id;
    if (event && event.contextMetaData && typeof event.contextMetaData.gameplayTag === 'string')
      trace.eventTag = event.contextMetaData.gameplayTag.slice(0,200);
    g.__GodfallReplacementCopyTrace = JSON.stringify(trace);
  }
  function run(event, originalResult, state, generate, eligiblePlayers) {
    if (consumed) return originalResult;
    if (!Array.isArray(originalResult) || originalResult.length === 0) { publish('waiting_nonempty_reward', '', event); return originalResult; }
    if (originalResult.length >= 64) { publish('waiting_smaller_reward', '', event); return originalResult; }
    if (eligiblePlayers !== 1) { publish('waiting_single_player', '', event); return originalResult; }
    var classes = ['Weapon','Ring','Amulet','Charm','Augment','Banner','Consumable'];
    if (!originalResult.some(function (item) { return item && !item.autoAcquire && classes.indexOf(item.lootClassName) >= 0; })) {
      publish('waiting_grounded_equipment', '', event); return originalResult;
    }
    var inventory = state && state.player && state.player.inventory && state.player.inventory.gear;
    var family = { Augment: ['augments','AUG'], Ring: ['rings','RNG'], Amulet: ['amulets','AMT'], Charm: ['charms','CHA'],
      Weapon: ['weapons','WPN'], Banner: ['banners','BNR'], Consumable: ['consumables','CNS'] }[config.lootClassName];
    if (!family || (config.collection && config.collection !== family[0]) || (config.prefix && config.prefix !== family[1])) return originalResult;
    var collection = inventory && inventory[family[0]];
    if (!collection || typeof collection !== 'object') { publish('inventory_not_ready', '', event); return originalResult; }
    var owned = Object.keys(collection).map(function (k) { return collection[k]; });
    var source = owned.filter(function (item) { return item && item.id === config.sourceId; });
    if (source.length !== 1 || (source[0].objectives || []).length || !matches(source[0], config.sourceTraits)) { publish('source_changed_or_missing', '', event); return originalResult; }
    var existing = owned.filter(function (item) { return item && item.id !== config.sourceId && matches(item, config.expectedTraits); });
    if (existing.length) { consumed = true; publish('replacement_already_owned', existing[0].id, event); return originalResult; }
    try {
      var storage = g.localStorage, storageKey = 'godfall.replacement-copy.' + config.trialId;
      if (!storage || typeof storage.getItem !== 'function' || typeof storage.setItem !== 'function') throw new Error('storage_unavailable');
      var saved = storage.getItem(storageKey);
      if (saved) {
        var marker = JSON.parse(saved);
        if (marker.sourceId !== config.sourceId || typeof marker.generatedId !== 'string') throw new Error('invalid_trial_marker');
        consumed = true; publish('already_generated_previous_run', marker.generatedId, event); return originalResult;
      }
      var raw = generate(config.gameplayTag, config.tierIdentifier, config.rarityIdentifier, copy(config.mutationNames || []));
      var prefix = family[1] + '-' + config.gameplayTag + '.';
      if (!raw || raw.lootClassName !== config.lootClassName || raw.gameplayTag !== config.gameplayTag ||
          raw.tierIdentifier !== config.tierIdentifier || raw.rarityIdentifier !== config.rarityIdentifier ||
          typeof raw.id !== 'string' || raw.id.indexOf(prefix) !== 0 || /OFFLINE|PREVIEW|NEVER_SUBMIT/.test(raw.id) ||
          raw.id === config.sourceId || owned.some(function (item) { return item && item.id === raw.id; }) ||
          originalResult.some(function (item) { return item && item.id === raw.id; }) || key(raw.mutationNames || []) !== key(config.mutationNames || []) ||
          (raw.objectives || []).length || (raw.masterworkUpgradeRank || 0) !== 0 ||
          (config.lootClassName !== 'Weapon' && raw.damageTypes && Object.keys(raw.damageTypes).length) ||
          Object.keys(raw.lootAttributes || {}).some(function (k) { var v = raw.lootAttributes[k]; return typeof v !== 'number' || !isFinite(v) || v < 0 || v > .999; }) ||
          key(Object.keys(raw.lootAttributes || {}).sort()) !== key(Object.keys(config.rawLootAttributes || {}).sort())) throw new Error('factory_record_rejected');
      var result = Object.assign({}, raw, { traits: copy(config.rawTraits),
        selectedTraitTags: copy(config.selectedTraitTags), lootAttributes: copy(config.rawLootAttributes || {}),
        damageTypes: copy(config.damageTypes || null), masterworkUpgradeRank: config.masterworkUpgradeRank || 0, amount: config.amount || 1, autoAcquire: false });
      // Persist only this trial's generated ID, never account/session data or item attributes.
      var record = { sourceId: config.sourceId, generatedId: result.id };
      storage.setItem(storageKey, JSON.stringify(record));
      var checked = JSON.parse(storage.getItem(storageKey) || 'null');
      if (!checked || checked.generatedId !== result.id || checked.sourceId !== config.sourceId) throw new Error('marker_not_saved');
      consumed = true; publish('generated_waiting_for_pickup', result.id, event);
      return originalResult.concat([result]);
    } catch (_) {
      consumed = true; publish('generation_failed_original_rewards_preserved', '', event); return originalResult;
    }
  }
  g.__GodfallReplacementCopyTrial = { version: 1, run: run };
  publish('waiting', '', null);
})(window);
