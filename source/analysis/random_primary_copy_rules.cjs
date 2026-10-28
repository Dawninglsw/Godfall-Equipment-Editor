/* Native random primary libraries. No progress, process, or network operations. */
'use strict';
const assert=require('assert/strict'),game=require('./game_trait_sdk.cjs');
const TAG='Weapon.Sword.1H.Player.Conquest';
function check(item,index){
 assert(['Weapon','Ring','Amulet','Charm','Augment','Banner','Consumable'].includes(item.lootClassName),'该物品类型尚未开放随机主词条');
 const rank=item.masterworkUpgradeRank??0;
 assert(Number.isInteger(rank)&&rank>=0&&rank<=5,'随机主词条支持强化0至5级');
 const mutations=item.mutationNames||[];
 assert(!mutations.length||(mutations.length===1&&mutations[0]==='Mutation.Item.Primal'),'随机主词条仅支持普通或单一原始变体');
 assert(Number.isInteger(index)&&item.traits[index]?.slotType==='Primary Trait','请选择随机主词条');
 const template=game.template(item.gameplayTag),slots=game.data.traitSlot.collection.filter(s=>
  s.groupName===template.traitSlotGroups&&s.slotType==='Primary Trait'&&
  item.rarityIdentifier>=s.minRarity&&item.rarityIdentifier<=s.maxRarity);
 // Records omit slotIndex. Accept only equal guaranteed slots;
 // do not infer a fixed/random slot from a union of differing slot libraries.
 assert(slots.length>0,'缺少原生主词条槽位');
 assert.equal(item.traits.filter(t=>t.slotType==='Primary Trait').length,slots.length,'主词条数量与模板不一致');
 assert(slots.every(s=>s.slotChance===1&&s.traitChance===1&&s.traitCategoryGroups===slots[0].traitCategoryGroups),'主词条位置的原生候选库不一致，保持保护');
 assert(Array.isArray(item.selectedTraitTags),'缺少原件实际标签');
 const {api}=game.sdk(),tags=item.selectedTraitTags,allowed=new Set();
 for(const category of api.getValidTraitCategoriesForSlot(item,tags,slots[0],[])){
  if(!(category.weight>0))continue;
  for(const trait of api.getValidTraitsForTraitCategory(item,category))if(trait.weight>0)allowed.add(category.name+'|'+trait.traitName);
 }
 assert(allowed.size>1,'固定主词条不能替换类型');
 assert(item.traits.filter(t=>t.slotType==='Primary Trait').every(t=>allowed.has(t.traitCategoryName+'|'+t.traitName)),'原主词条与本件随机库不符');
 const pool=game.pools(item,index);assert(!pool.primary_fixed&&pool.template_primary_candidate_count>1);
 return {template:item.gameplayTag,slotCount:slots.length,candidateCount:allowed.size,candidateKeys:[...allowed]};
}
module.exports={check,TAG};
