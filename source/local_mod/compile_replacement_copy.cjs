'use strict';
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const {normalizeTrait}=require('../analysis/reconstruct_owned_augment.cjs');
const {checkItem}=require('../analysis/reconstruct_owned_item.cjs');
const metadata=require('../analysis/item_metadata_sdk.cjs');
const game=require('../analysis/game_trait_sdk.cjs'),crypto=require('crypto');
function compile(preview){
 assert.equal(preview.status,'offline_preview_only_no_game_or_account_write');
 const s=preview.source_materialized,t=preview.expected_materialized;
 const family=checkItem(s);checkItem(t);const rank=s.masterworkUpgradeRank||0;
 assert.equal((s.objectives||[]).length,0,'Objective augments are not supported');
 assert(s.traits.every(x=>x.slotType!=='Trait.Objective'&&!(x.conditionalLootEffects||[]).length));
 assert.equal(t.gameplayTag,s.gameplayTag);
 assert.equal(t.tierIdentifier,s.tierIdentifier);assert.equal(t.rarityIdentifier,s.rarityIdentifier);
 assert.equal(t.lootClassName,s.lootClassName);assert.equal(t.masterworkUpgradeRank||0,rank);
 assert.equal(preview.raw_preview?.masterworkUpgradeRank||0,rank,'Raw upgrade rank differs from source');
 assert.deepEqual(t.mutationNames||[],s.mutationNames||[]);
 assert.deepEqual(t.selectedTraitTags,s.selectedTraitTags);
 const attributes=metadata.reconstruct(s);
 const rawAttributes=preview.raw_preview?.lootAttributes||{};
 assert.deepEqual(metadata.materialize(s,rawAttributes),attributes.observed,'独立属性未保留');
 assert.deepEqual(t.lootAttributes||{},attributes.observed);
 assert.deepEqual(t.damageTypes||null,attributes.damageTypes);
 assert.equal(t.amount||1,attributes.amount);
 assert.equal(preview.raw_traits.length,s.traits.length);
 assert.equal(preview.source_id,s.id);
 for(const trait of preview.raw_traits){
  assert.equal((trait.conditionalLootEffects||[]).length,0);
  for(const effect of trait.lootEffects||[])for(const p of effect.params||[])
   assert(Number.isFinite(p.magnitude)&&p.magnitude>=0&&p.magnitude<=.999,'Raw roll must be in original range');
 }
 const materialized=game.clone(game.sdk().api.materializeItemTraits({...game.clone(s),traits:game.clone(preview.raw_traits)}));
 assert.deepEqual(materialized.map(normalizeTrait),t.traits.map(normalizeTrait));
 const changed=s.traits.map((trait,index)=>JSON.stringify(normalizeTrait(trait))!==JSON.stringify(normalizeTrait(t.traits[index]))?index:-1).filter(i=>i>=0);
 assert(changed.length>=1&&changed.length<=s.traits.length,'请选择实际修改的词条');
 const primaryIndexes=changed.filter(i=>s.traits[i].slotType==='Primary Trait');
 assert(!primaryIndexes.length||changed.length===1,'随机主词条首轮每份方案仅替换一条主词条');
 for(const index of changed){
  assert(['Primary Trait','Secondary Trait'].includes(s.traits[index].slotType),'固定主属性与精通词条保持原样');
  if(s.traits[index].slotType==='Primary Trait'){
   require('../analysis/random_primary_copy_rules.cjs').check(s,index);
   require('../analysis/random_primary_copy_rules.cjs').check(t,index);
  }
  assert.equal(t.traits[index].slotType,s.traits[index].slotType);
  assert.equal(t.traits[index].masterworkBonusTier||0,s.traits[index].masterworkBonusTier||0,'强化选择位置必须保留');
  assert(game.pools(t,index).candidates.some(c=>c.trait.traitName===t.traits[index].traitName&&c.category.name===t.traits[index].traitCategoryName),'整件方案中的词条不在最终候选库或相互冲突');
 }
 const trialId=crypto.createHash('sha256').update(s.id+JSON.stringify(t.traits.map(normalizeTrait))).digest('hex').slice(0,24);
 return {version:1,trialId,sourceId:preview.source_id,gameplayTag:s.gameplayTag,lootClassName:s.lootClassName,
  collection:family.collection,prefix:family.prefix,changedIndexes:changed,primaryIndexes,
  mutationNames:s.mutationNames||[],
  sourceLootAttributes:attributes.observed,rawLootAttributes:rawAttributes,damageTypes:attributes.damageTypes,amount:attributes.amount,
  tierIdentifier:s.tierIdentifier,rarityIdentifier:s.rarityIdentifier,masterworkUpgradeRank:rank,sourceTraits:s.traits,
  expectedTraits:t.traits,rawTraits:preview.raw_traits,selectedTraitTags:t.selectedTraitTags,
  scope:'One replacement through original factory after a normal single-player equipment drop; normal pickup required.'};
}
const anchor='var a=e.action.payload,r=c.loot.rollLootForEvent(a);return a.responseObject={loot:r},a';
const directStart='e.UE_CREATE_PLAYER_LOOT=function(){var e=';
const directRoll='r=c.loot.rollLootForEvent(a),e.abrupt("return",{loot:r})';
function patch(source){
 for(const point of [anchor,directStart,directRoll])assert.equal(source.split(point).length-1,1,'Original loot integration is missing or ambiguous');
 const changed='var a=e.action.payload,r=c.loot.rollLootForEvent(a);r=window.__GodfallReplacementCopyTrial.run(a,r,e.getState(),function(t,l,q,m){return c.loot.generateLootForGameplayTag(t,l,q,1,!1,m||[])},c.loot.getNumLootEligiblePlayersForEvent(a));return a.responseObject={loot:r},a';
 // The event parameter is also named a. Capture a getter in the outer scope,
 // and resolve the application store at call time because bootstrap assigns it later.
 const directNewStart='e.UE_CREATE_PLAYER_LOOT=function(){var __gfReplacementState=function(){return a.store&&a.store.getState?a.store.getState():null};var e=';
 const directNewRoll='r=c.loot.rollLootForEvent(a),r=window.__GodfallReplacementCopyTrial.run(a,r,__gfReplacementState(),function(t,l,q,m){return c.loot.generateLootForGameplayTag(t,l,q,1,!1,m||[])},c.loot.getNumLootEligiblePlayersForEvent(a)),e.abrupt("return",{loot:r})';
 return source.replace(anchor,changed).replace(directStart,directNewStart).replace(directRoll,directNewRoll);
}
function runtime(config){return fs.readFileSync(path.join(__dirname,'replacement_copy_runtime.js'),'utf8').replace('__GODFALL_REPLACEMENT_COPY_CONFIG__',JSON.stringify(config));}
module.exports={compile,patch,runtime,integrationPoints:3};
