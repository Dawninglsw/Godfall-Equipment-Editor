/* Ordinary items without separately rolled attributes; all work is offline. */
'use strict';
const assert=require('assert/strict'),game=require('./game_trait_sdk.cjs');
const core=require('./reconstruct_owned_augment.cjs'),{factory}=require('./offline_equipment_factory.cjs');
const metadata=require('./item_metadata_sdk.cjs'),{families}=metadata;
const {upgradeContext}=require('./reconstruct_upgraded_item.cjs');
function checkItem(item){
 const family=families[item?.lootClassName];assert(family,'该物品类型尚未开放同款生成');
 assert(typeof item.gameplayTag==='string'&&item.gameplayTag.startsWith(item.lootClassName+'.'),'物品类型与模板不一致');
 assert(typeof item.id==='string'&&item.id.startsWith(family.prefix+'-'+item.gameplayTag+'.'),'物品编号与类型不一致');
 assert(Number.isInteger(item.tierIdentifier)&&item.tierIdentifier>0&&Number.isInteger(item.rarityIdentifier)&&item.rarityIdentifier>0,'物品等级或品质不完整');
 game.template(item.gameplayTag);
 const rank=item.masterworkUpgradeRank||0;
 assert(Number.isInteger(rank)&&rank>=0&&rank<=5,'强化等级必须处于0至5级');
 const mutations=item.mutationNames||[],primal=mutations.length===1&&mutations[0]==='Mutation.Item.Primal';
 const awakened=mutations.length===1&&mutations[0]==='Mutation.Item.Awakened';
 assert(!mutations.length||primal||awakened,'尚未解除的诅咒及混合变体保持只读');
 if(awakened){
  assert(item.lootClassName==='Ring'&&rank===0,'已解咒同款试验先限定强化0的戒指');
  assert(Array.isArray(item.objectives)&&item.objectives.length===0,'请读取完整的解咒后任务状态');
 }
 assert.equal((item.objectives||[]).length,0,'关联目标的物品尚未开放');
 assert(Array.isArray(item.selectedTraitTags)&&item.selectedTraitTags.every(t=>typeof t==='string'),'缺少完整词条标签');
 assert(Array.isArray(item.traits)&&item.traits.length>0&&item.traits.length<=20,'物品词条记录不完整');
 assert(item.traits.every(t=>['Primary Trait','Primary Attribute','Secondary Trait',...(rank?['Masterwork Trait']:[])].includes(t.slotType)
  &&!(t.conditionalLootEffects||[]).length&&(rank||!(t.masterworkBonusTier||0))
  &&(t.mutationNames||[]).every(m=>(primal&&m==='Mutation.Item.Primal')||(awakened&&m==='Mutation.Item.Awakened'))),
  '该物品含尚未适配的条件、目标或强化效果');
 if(rank)upgradeContext(item);
 metadata.reconstruct(item);
 if(primal||awakened){
  const native=factory().mutate({...game.clone(item),traits:item.traits.map(t=>({...game.clone(t),mutationNames:[]}))});
  assert.deepEqual(native.traits.map(t=>t.mutationNames||[]),item.traits.map(t=>t.mutationNames||[]),'变体标记与原版主词条增强位置不一致');
 }
 return family;
}
function reconstruct(source,index,targetTrait){
 checkItem(source);
 assert(Number.isInteger(index)&&['Primary Trait','Secondary Trait'].includes(source.traits[index]?.slotType),'请选择副词条或已开放的随机主词条');
 assert.equal(targetTrait.slotType,source.traits[index].slotType);
 if(source.traits[index].slotType==='Primary Trait')require('./random_primary_copy_rules.cjs').check(source,index);
 if(source.lootClassName==='Augment'&&source.traits[index].slotType==='Secondary Trait'&&!(source.mutationNames||[]).length&&!source.masterworkUpgradeRank)return core.reconstruct(source,index,targetTrait);
 return reconstructMany(source,[{index,targetTrait}]);
}
function reconstructMany(source,changes){
 const family=checkItem(source),seen=new Set();
 assert(Array.isArray(changes)&&changes.length>0&&changes.length<=source.traits.length,'请选择本件装备需要修改的副词条');
 const expected=game.clone(source);
 const primary=changes.filter(c=>source.traits[c.index]?.slotType==='Primary Trait');
 assert(!primary.length||changes.length===1,'随机主词条试验每份方案只替换一条主词条');
 for(const {index,targetTrait} of changes){
  assert(Number.isInteger(index)&&['Primary Trait','Secondary Trait'].includes(source.traits[index]?.slotType),'只开放副词条与已适配的随机主词条');
  if(source.traits[index].slotType==='Primary Trait')require('./random_primary_copy_rules.cjs').check(source,index);
  assert(!seen.has(index),'同一副词条不能重复设置');seen.add(index);
  assert.equal(targetTrait.slotType,source.traits[index].slotType);
  expected.traits[index]=game.clone(targetTrait);
 }
 checkItem(expected);
 const attributes=metadata.reconstruct(source);
 const raw=factory().generate(source.gameplayTag,source.tierIdentifier,source.rarityIdentifier,source.mutationNames||[]);
 assert.equal(raw.lootClassName,source.lootClassName);assert.equal((raw.objectives||[]).length,0);
 assert.deepEqual(raw.mutationNames||[],source.mutationNames||[]);
 raw.id=family.prefix+'-'+source.gameplayTag+'.OFFLINE_RECONSTRUCTION_PREVIEW_ONLY';
 raw.selectedTraitTags=game.clone(source.selectedTraitTags);raw.masterworkUpgradeRank=source.masterworkUpgradeRank||0;
 raw.lootAttributes=game.clone(attributes.raw);raw.damageTypes=game.clone(attributes.damageTypes);raw.amount=attributes.amount;
 const rows=expected.traits.map((t,n)=>{const row=core.rawTrait(expected,n,t);
  if(t.priority!==undefined)row.raw.priority=t.priority;
  return row;});raw.traits=rows.map(r=>r.raw);
 const materialized={...game.clone(raw),traits:game.clone(game.sdk().api.materializeItemTraits(raw)),
  lootAttributes:metadata.materialize(raw,raw.lootAttributes)};
 assert.deepEqual(materialized.traits.map(core.normalizeTrait),expected.traits.map(core.normalizeTrait));
 return {status:'offline_preview_only_no_game_or_account_write',source_id:source.id,
  raw_preview:raw,source_materialized:game.clone(source),expected_materialized:materialized,
  raw_traits:raw.traits,expected_traits:materialized.traits,quality_reconstruction:rows.map(r=>r.quality),
  attribute_reconstruction:attributes,
  profile:{family:source.lootClassName,extra_attributes:Object.keys(attributes.raw)},
  checks:{all_traits_roundtrip_exactly:true,...(primary.length?{other_primary_and_attribute_traits_preserved:true}:{primary_and_attribute_traits_preserved:true}),
   upgrade_rank_and_choices_preserved:true,extra_attributes_roundtrip_exactly:true,damage_type_and_charges_preserved:true,new_identifier_required:true,original_item_preserved:true},
  limits:['Offline preview only; new-ID generation and actual save acceptance need a live trial.',
   'Copies support ordinary/single-Primal rank0-5 and fully-Awakened rank0 Rings for secondaries. Single random-primary editing requires matching guaranteed native slot libraries and actual selected tags. Conditional, objective and other variants remain excluded.',
   'Current rounded values are reproduced; unknown original random rolls and future upgrade rounding are not asserted identical.']};
}
module.exports={families,checkItem,reconstruct,reconstructMany};
