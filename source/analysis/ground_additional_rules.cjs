/* Context for newly adapted secondary-only families, from original templates. */
'use strict';
const game=require('./game_trait_sdk.cjs');
const LABELS={Charm:'符咒',Banner:'旗帜',Consumable:'生命石'};
function familyContext(item){
 const label=LABELS[item.lootClassName];if(!label)return null;
 const definition=game.template(item.gameplayTag);
 const keys={Charm:['className','elementalAffinityIdentifier'],
  Banner:['overshieldScalar','radiusScalar','durationScalar','cooldownScalar'],
  Consumable:['healScalar','chargesScalar','healDurationScalar','secondaryTraitDurationScalar','gearSlot']}[item.lootClassName];
 return {family:item.lootClassName,label,trait_slot_group:definition.traitSlotGroups,
  preserved_template_properties:Object.fromEntries(keys.filter(k=>definition[k]!==undefined).map(k=>[k,definition[k]]))};
}
function familyRestriction(item){
 if(!LABELS[item.lootClassName])return null;
 if(/Cursed/i.test(game.template(item.gameplayTag).traitSlotGroups)||(item.objectives||[]).length)
  return {code:'new_family_objective_pending',reason:'此类型带诅咒或关联目标的装备暂未适配'};
 return null;
}
module.exports={LABELS,familyContext,familyRestriction};
