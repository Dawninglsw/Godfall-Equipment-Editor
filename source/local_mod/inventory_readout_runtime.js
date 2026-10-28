/* Equipment-only readout of the original UI store. No requests or game writes. */
(function (g) {
  'use strict';
  var families = ['weapons', 'rings', 'amulets', 'charms', 'augments', 'banners', 'consumables'];
  var classes = ['Weapon', 'Ring', 'Amulet', 'Charm', 'Augment', 'Banner', 'Consumable'];
  var itemKeys = ['id', 'gameplayTag', 'lootClassName', 'tierIdentifier', 'rarityIdentifier',
    'masterworkUpgradeRank', 'mutationNames', 'selectedTraitTags', 'traits', 'damageTypes',
    'isFavorite', 'isEquippedInSelectedValorplate', 'equipCount', 'amount'];
  var startedAt = Date.now(), sequence = 0, attached = null, timer = null;
  var lastGear = null, lastPlates = null, lastSelected = null, fingerprint = null;
  function values(value) {
    return value && typeof value === 'object' ? Object.keys(value).map(function (key) { return value[key]; }) : [];
  }
  function text(value) { return typeof value === 'string' && value.length <= 512 ? value : ''; }
  // Only gear fields are traversed. Unknown root, account and session fields are never copied.
  function gear(item) {
    if (!item || typeof item !== 'object' || !text(item.id) || !text(item.gameplayTag) ||
        classes.indexOf(item.lootClassName) < 0) return null;
    var out = {};
    itemKeys.forEach(function (key) { if (Object.prototype.hasOwnProperty.call(item, key)) out[key] = item[key]; });
    if (item.objectives !== undefined) {
      if (!Array.isArray(item.objectives) || item.objectives.length > 16) return null;
      var objectives = [], invalidObjective = false;
      item.objectives.forEach(function (objective) {
        if (!objective || typeof objective !== 'object' || Array.isArray(objective) ||
            !text(objective.traitName) || !text(objective.objectiveId)) { invalidObjective = true; return; }
        var numerator = objective.progressNumerator, denominator = objective.progressDenominator;
        if (typeof numerator !== 'number' || !isFinite(numerator) || numerator < 0 || numerator > 1e12 ||
            typeof denominator !== 'number' || !isFinite(denominator) || denominator <= 0 || denominator > 1e12) {
          invalidObjective = true; return;
        }
        // Export only the gear's bounded objective fields, never surrounding quest/account state.
        objectives.push({ traitName: objective.traitName, objectiveId: objective.objectiveId,
          progressNumerator: numerator, progressDenominator: denominator });
      });
      if (invalidObjective) return null;
      out.objectives = objectives;
    }
    if (item.lootAttributes !== undefined) {
      if (!item.lootAttributes || typeof item.lootAttributes !== 'object' || Array.isArray(item.lootAttributes)) return null;
      var attributes = {}, invalid = false;
      Object.keys(item.lootAttributes).forEach(function (key) {
        var value = item.lootAttributes[key];
        if (['attackPower','ConsumableHealingPower','BannerOvershield'].indexOf(key) < 0 ||
            typeof value !== 'number' || !isFinite(value)) { invalid = true; return; }
        attributes[key] = value;
      });
      if (invalid) return null;
      out.lootAttributes = attributes;
    }
    if (out.amount !== undefined && (typeof out.amount !== 'number' || out.amount < 0 || out.amount > 1000000 || Math.floor(out.amount) !== out.amount)) return null;
    return JSON.parse(JSON.stringify(out));
  }
  function capture(state) {
    var player = state && state.player, inventory = player && player.inventory;
    if (!inventory || !inventory.gear || !inventory.valorplates) return false;
    var selected = text(player.loadout && player.loadout.selectedValorplateId);
    // Redux dispatches unrelated events while the game runs. Keep the published
    // pages stable until inventory/preset content changes so a bounded read can finish.
    if (lastGear === inventory.gear && lastPlates === inventory.valorplates && lastSelected === selected) return true;
    var rows = [], seen = Object.create(null), omitted = 0, collections = {};
    families.forEach(function (family) {
      var collection = inventory.gear[family];
      collections[family] = !!collection && typeof collection === 'object';
      values(collection).forEach(function (item) {
        if (!item || !item.id || seen[item.id]) return;
        var copy = gear(item);
        if (!copy || rows.length >= 10000) { omitted++; return; }
        seen[copy.id] = true; rows.push(copy);
      });
    });
    var plates = [];
    values(inventory.valorplates).slice(0, 64).forEach(function (plate) {
      if (!plate || !text(plate.id) || !text(plate.gameplayTag)) return;
      var presets = [];
      Object.keys(plate.presets || {}).slice(0, 3).forEach(function (key) {
        var bindings = [], preset = plate.presets[key];
        families.forEach(function (family) {
          Object.keys(preset && preset[family] || {}).slice(0, 64).forEach(function (slot) {
            var item = preset[family][slot];
            if (!item || !text(item.id)) return;
            bindings.push({ family: family, slot: text(String(slot)), id: item.id });
            // Presets can reference items missing from the inventory collection. Keep provenance separate.
            if (!seen[item.id]) {
              var copy = gear(item);
              if (copy && rows.length < 10000) { seen[copy.id] = true; copy.readoutPresetOnly = true; rows.push(copy); }
              else omitted++;
            }
          });
        });
        presets.push({ index: Number(key), bindings: bindings });
      });
      plates.push({ id: plate.id, gameplayTag: plate.gameplayTag,
        selectedPresetIndex: Number(plate.selectedPresetIndex || 0), presets: presets });
    });
    var nextFingerprint = JSON.stringify({ selectedValorplateId: selected, plates: plates,
      collections: collections, omitted: omitted, items: rows });
    if (nextFingerprint === fingerprint) {
      lastGear = inventory.gear; lastPlates = inventory.valorplates; lastSelected = selected;
      return true;
    }
    var seq = sequence + 1, stamp = Date.now(), pages = [], lengths = [], failed = false;
    for (var i = 0; i < rows.length; i += 32) {
      var page = JSON.stringify({ godfallInventoryReadout: 1, kind: 'page', startedAt: startedAt,
        sequence: seq, index: pages.length, items: rows.slice(i, i + 32) });
      if (page.length > 2097152) { failed = true; break; }
      pages.push(page); lengths.push(page.length);
    }
    if (failed || pages.length > 400) return false;
    var manifest = JSON.stringify({ godfallInventoryReadout: 1, kind: 'manifest', startedAt: startedAt,
      sequence: seq, capturedAt: stamp, itemCount: rows.length, pageLengths: lengths,
      selectedValorplateId: selected, plates: plates, collections: collections, omitted: omitted });
    if (manifest.length > 2097152) return false;
    // Keep independent flat JSON strings alive; the external reader also validates every page.
    g.__GodfallInventoryReadoutPages = pages;
    g.__GodfallInventoryReadoutManifest = manifest;
    sequence = seq;
    fingerprint = nextFingerprint; lastGear = inventory.gear;
    lastPlates = inventory.valorplates; lastSelected = selected;
    return true;
  }
  function attach(store) {
    if (!store || typeof store.getState !== 'function' || attached === store) return;
    attached = store;
    function update() {
      if (timer !== null) return;
      timer = g.setTimeout(function () {
        timer = null;
        try { capture(store.getState()); } catch (_) { /* Diagnostics cannot disrupt game messages. */ }
      }, 500);
    }
    try { capture(store.getState()); if (typeof store.subscribe === 'function') store.subscribe(update); } catch (_) {}
  }
  g.__GodfallInventoryReadout = { version: 1, capture: capture, attach: attach };
})(window);
