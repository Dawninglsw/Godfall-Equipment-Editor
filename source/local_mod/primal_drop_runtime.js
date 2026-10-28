/* Dedicated primal reward opportunities only. No inventory or network access. */
(function (g) {
  "use strict";
  var config = __GODFALL_PRIMAL_DROP_CONFIG__;
  var rules = Object.create(null), stack = [];
  var trace = { version: 1, startedAt: Date.now(), multiplier: config.multiplier, enabled: config.enabled,
    sequence: 0, events: [] };
  function stable(value) {
    if (Array.isArray(value)) return value.map(stable);
    if (!value || typeof value !== "object") return value;
    var result = {};
    Object.keys(value).sort().forEach(function (key) { result[key] = stable(value[key]); });
    return result;
  }
  config.rows.forEach(function (row) {
    rules[row.name] = { row: row, signature: JSON.stringify(stable(row)) };
  });
  function publish() {
    g.__GodfallPrimalDropTraceText = "GF_PRIMAL_TRACE_V1_BEGIN\n" + JSON.stringify(trace) + "\nGF_PRIMAL_TRACE_V1_END";
  }
  function finite(value, fallback) { return typeof value === "number" && isFinite(value) ? value : fallback; }
  function eventTag(value) { return typeof value === "string" && /^[A-Za-z0-9_.-]{1,200}$/.test(value) ? value : ""; }
  function eligible(row, state) {
    if (!state || state.tier < row.minTier || state.tier > row.maxTier ||
        state.threat < row.minThreat || state.threat > row.maxThreat) return false;
    return (row.requiredProgressionFlags || []).every(function (flag) { return state.flags.indexOf(flag) >= 0; });
  }
  function quantityRows(group, rows) {
    if (!config.enabled || typeof group !== "string" || !Array.isArray(rows)) return rows;
    var changed = false, current = stack.length ? stack[stack.length - 1] : null;
    if (!current || config.chestTags.indexOf(current.record.gameplayTag) < 0) return rows;
    var result = rows.map(function (row) {
      var match = row && rules[row.name];
      if (!match || match.row.groupName !== group || JSON.stringify(stable(row)) !== match.signature) return row;
      var chance = Math.min(1, row.chance * config.multiplier);
      if (current && eligible(row, current.state) && current.record.primalOpportunities.length < 48) {
        current.record.primalOpportunities.push({ group: group, row: row.name, before: row.chance, after: chance });
      }
      if (chance === row.chance) return row;
      changed = true;
      return Object.assign({}, row, { chance: chance });
    });
    return changed ? result : rows;
  }
  function runEvent(event, callback) {
    if (!config.enabled) return callback();
    var meta = event && event.contextMetaData || {};
    var state = { tier: finite(meta.tier, 1), threat: finite(meta.threat, 1),
      flags: (Array.isArray(meta.playerProgressionFlags) ? meta.playerProgressionFlags : []).map(function (flag) { return flag && flag.ProgressionFlagId; }) };
    var entry = { state: state, record: { sequence: ++trace.sequence, gameplayTag: eventTag(meta.gameplayTag),
      tier: state.tier, threat: state.threat, eligiblePlayers: finite(meta.numLootEligiblePlayers, 1),
      playerLootBonus: finite(meta.playerLootBonus, 0), targetLootBonus: finite(meta.targetLootBonus, 0),
      primalOpportunities: [], results: [], completed: false } };
    stack.push(entry);
    try {
      var result = callback();
      if (Array.isArray(result)) result.slice(0, 64).forEach(function (item) {
        if (!item || typeof item.gameplayTag !== "string") return;
        entry.record.results.push({ gameplayTag: eventTag(item.gameplayTag), rarity: finite(item.rarityIdentifier, 0),
          mutations: (Array.isArray(item.mutationNames) ? item.mutationNames : []).map(eventTag).filter(Boolean) });
      });
      entry.record.completed = true;
      return result;
    } finally {
      stack.pop();
      // Keep only selected chest events, not unrelated gameplay or account data.
      if (entry.record.primalOpportunities.length || config.chestTags.indexOf(entry.record.gameplayTag) >= 0) {
        trace.events.push(entry.record);
        if (trace.events.length > 16) trace.events.shift();
      }
      publish();
    }
  }
  g.__GodfallPrimalDropRateMod = { version: 1, quantityRows: quantityRows, runEvent: runEvent };
  publish();
})(window);
