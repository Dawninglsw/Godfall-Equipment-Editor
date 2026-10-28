/* Research-only upgraded copy preview; no game process or account operations. */
'use strict';
const assert=require('assert/strict'),game=require('./game_trait_sdk.cjs');
const core=require('./reconstruct_owned_augment.cjs'),metadata=require('./item_metadata_sdk.cjs');
const {factory}=require('./offline_equipment_factory.cjs'),planner=require('../local_mod/trait_type_cli.cjs');
function upgradeContext(item){
 const rank=item.masterworkUpgradeRank;
 assert(Number.isInteger(rank)&&rank>=1&&rank<=5,'研究对象必须是强化1至5级的物品');
 const row=game.data.craftingUpgrade.collection.find(r=>r.rank===rank
  &&r.whitelistItemClasses.includes(item.lootClassName)&&item.tierIdentifier>=r.minTier
  &&item.tierIdentifier<=r.maxTier&&item.rarityIdentifier>=r.minRarityIdentifier);
 assert(row,'强化等级不符合原游戏等级、品质或物品类型要求');
 const secondary=item.traits.filter(t=>t.slotType==='Secondary Trait');
 const boosted=item.traits.filter(t=>(t.masterworkBonusTier||0)!==0);
 const masterwork=item.traits.filter(t=>t.slotType==='Masterwork Trait');
 assert(boosted.every(t=>t.slotType==='Secondary Trait'&&t.masterworkBonusTier===1),'强化选择标记不符合原游戏规则');
 assert.equal(boosted.length,rank>=3&&secondary.length?1:0,'缺少或多出强化所选副词条');
 assert.equal(masterwork.length,rank===5?1:0,'精通词条数量与强化等级不符');
 return {rank,row:game.clone(row),boosted_index:boosted.length?item.traits.indexOf(boosted[0]):-1,
  masterwork_index:masterwork.length?item.traits.indexOf(masterwork[0]):-1};
}
function check(item,index){
 const family=metadata.families[item.lootClassName];assert(family,'物品类型尚未适配');
 assert(typeof item.id==='string'&&item.id.startsWith(family.prefix+'-'+item.gameplayTag+'.'),'物品编号与模板不符');
 assert(Number.isInteger(item.tierIdentifier)&&item.tierIdentifier>0&&Number.isInteger(item.rarityIdentifier),'等级或品质不完整');
 assert.deepEqual((item.mutationNames||[]).filter(m=>m!=='Mutation.Item.Primal'),[],'诅咒、觉醒或其他混合变体保持只读');
 assert((item.mutationNames||[]).length<=1,'原始标记重复');
 assert(!(item.objectives||[]).length,'目标状态尚未适配');
 assert(Array.isArray(item.selectedTraitTags),'缺少词条标签');
 assert(Array.isArray(item.traits)&&item.traits.length>0&&item.traits.length<=20,'词条记录不完整');
 assert(item.traits.every(t=>['Primary Trait','Primary Attribute','Secondary Trait','Masterwork Trait'].includes(t.slotType)
  &&!(t.conditionalLootEffects||[]).length
  &&(t.mutationNames||[]).every(m=>(item.mutationNames||[]).includes(m))),'条件、目标或其他词条变体尚未适配');
 assert(item.traits[index]?.slotType==='Secondary Trait','本轮只研究副词条替换');
 const upgrade=upgradeContext(item),attributes=metadata.reconstruct(item);
 const primal=factory().mutate({...game.clone(item),traits:item.traits.map(t=>({...game.clone(t),mutationNames:[]}))});
 assert.deepEqual(primal.traits.map(t=>t.mutationNames||[]),item.traits.map(t=>t.mutationNames||[]),'原始主词条增强标记不符');
 return {family,upgrade,attributes};
}
function reconstruct(source,index,targetTraitName,targetCategoryName,desiredValue){
 const {family,upgrade,attributes}=check(source,index);
 const choice=planner.preview({item:source,index,targetTraitName,targetCategoryName,desiredValue});
 const expected=game.clone(source);expected.traits[index]=game.clone(choice.targetTrait);
 assert.equal(expected.traits[index].masterworkBonusTier||0,source.traits[index].masterworkBonusTier||0,'强化所选位置未保留');
 const raw=factory().generate(source.gameplayTag,source.tierIdentifier,source.rarityIdentifier,source.mutationNames||[]);
 assert(!(raw.objectives||[]).length);
 raw.id=family.prefix+'-'+source.gameplayTag+'.OFFLINE_UPGRADED_PREVIEW_ONLY';
 raw.selectedTraitTags=game.clone(source.selectedTraitTags);raw.masterworkUpgradeRank=source.masterworkUpgradeRank;
 raw.lootAttributes=game.clone(attributes.raw);raw.damageTypes=game.clone(attributes.damageTypes);raw.amount=attributes.amount;
 const rows=expected.traits.map((t,n)=>core.rawTrait(expected,n,t));raw.traits=rows.map(r=>r.raw);
 const materialized={...game.clone(raw),traits:game.clone(game.sdk().api.materializeItemTraits(raw)),
  lootAttributes:metadata.materialize(raw,raw.lootAttributes)};
 assert.deepEqual(materialized.traits.map(core.normalizeTrait),expected.traits.map(core.normalizeTrait));
 assert.deepEqual(materialized.lootAttributes,source.lootAttributes||{});
 assert.deepEqual(upgradeContext(materialized),upgrade);
 return {status:'offline_upgraded_research_preview_not_deployable',source_id:source.id,
  source_materialized:game.clone(source),expected_materialized:materialized,raw_preview:raw,
  raw_traits:raw.traits,expected_traits:materialized.traits,choice,upgrade,attribute_reconstruction:attributes,
  checks:{all_traits_roundtrip_exactly:true,upgrade_rank_preserved:true,selected_secondary_bonus_preserved:true,
   masterwork_trait_preserved:true,primal_markers_preserved:true,independent_attributes_preserved:true,
   original_retained:true,new_id_required:true},
  limits:['Research preview only, rejected by the production compiler; no installation, generation or save acceptance tested.',
   'Conditional effects, objectives, cursed/awakened and mixed variants remain excluded.',
   'Inverse qualities reproduce observed rounded values; unknown original rolls and future upgrade rounding are not claimed identical.']};
}
module.exports={upgradeContext,check,reconstruct};
