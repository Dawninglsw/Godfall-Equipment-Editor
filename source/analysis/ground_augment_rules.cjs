/* Immutable augment context from the original template and scaling tables. */
'use strict';
const game=require('./game_trait_sdk.cjs');
function augmentProfile(item){
 if(item.lootClassName!=='Augment')return null;
 const definition=game.template(item.gameplayTag),scaling=game.sdk().api.getItemScalingForItem(item);
 if(!scaling||typeof scaling.powerDrain!=='number'||typeof definition.powerDrainMultiplier!=='number')
  throw new Error('强化物耗能资料暂时无法核对');
 return {affinity_identifier:definition.affinityIdentifier,
  color:{0:'中性',1:'红色',2:'绿色',3:'蓝色'}[definition.affinityIdentifier]||'未知颜色',
  tier_power_cost:Math.round(scaling.powerDrain*definition.powerDrainMultiplier),
  power_drain_multiplier:definition.powerDrainMultiplier,
  trait_slot_group:definition.traitSlotGroups,
  node_rules_preserved:true};
}
function augmentRestriction(item){
 if(item.lootClassName!=='Augment')return null;
 const definition=game.template(item.gameplayTag);
 if(/Cursed/i.test(definition.traitSlotGroups)||(item.objectives||[]).length)
  return {code:'augment_objective_pending',reason:'诅咒或仍有关联目标的强化物暂未适配'};
 return null;
}
module.exports={augmentProfile,augmentRestriction};
