/* Existing augments: original pools/scaling, with objective-linked variants gated. */
'use strict';
const {augmentProfile}=require('./ground_augment_rules.cjs');
function ownedAugmentContext(item){
 if(item.lootClassName!=='Augment')return null;
 const profile=augmentProfile(item),mutations=item.mutationNames||[];
 let reason='',code='';
 if(/Cursed/i.test(profile.trait_slot_group)||(item.objectives||[]).length||
    (item.traits||[]).some(t=>t.slotType==='Trait.Objective')||mutations.some(m=>/Cursed|Awakened/.test(m))){
  reason='诅咒、觉醒或关联目标的强化物尚未适配，先保留原词条';code='owned_augment_objective_pending';
 }else if(mutations.some(m=>m!=='Mutation.Item.Primal')){
  reason='该强化物包含尚未适配的变体';code='owned_augment_mutation_pending';
 }
 return {profile,blocked:!!reason,reason,code};
}
function slotRestriction(item,index,context=ownedAugmentContext(item)){
 if(!context)return null;
 if(context.blocked)return {reason:context.reason,code:context.code};
 const slot=item.traits[index]?.slotType;
 if(slot==='Primary Trait'){
  try{require('./random_primary_copy_rules.cjs').check(item,index);return null;}
  catch(error){return {reason:error.message,code:'owned_augment_primary_pending'};}
 }
 if(!['Secondary Trait','Masterwork Trait'].includes(slot))return {reason:'强化物主属性和目标词条保持原样',code:'owned_augment_fixed_slot'};
 return null;
}
module.exports={ownedAugmentContext,slotRestriction};
