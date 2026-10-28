/* Offline plan only. This module never opens the game or makes requests. */
'use strict';
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const game=require('./game_trait_sdk.cjs');
const {dropPool}=require('./ground_primary_rules.cjs');
const {augmentProfile,augmentRestriction}=require('./ground_augment_rules.cjs');
const {LABELS,familyContext,familyRestriction}=require('./ground_additional_rules.cjs');
class PlanError extends Error{constructor(code,message){super(message);this.code=code;}}
function requirePlan(condition,code,message){if(!condition)throw new PlanError(code,message);}

function prepare(raw,index,targetName='WeaponArtDamagePercentSecondary',requestedQuality=null){
 const {api}=game.sdk();
 const original=game.clone(raw);
 requirePlan(['Weapon','Ring','Amulet','Augment',...Object.keys(LABELS)].includes(original.lootClassName),'unsupported_family','该装备类型尚未开放词条写入');
 requirePlan(!(original.masterworkUpgradeRank||0),'upgraded_item','强化过的装备暂未适配');
 requirePlan(!(original.mutationNames||[]).length,'mutated_item','带特殊突变的装备暂未适配');
 const augmentBlocked=augmentRestriction(original);
 requirePlan(!augmentBlocked,augmentBlocked?.code,augmentBlocked?.reason);
 const familyBlocked=familyRestriction(original);
 requirePlan(!familyBlocked,familyBlocked?.code,familyBlocked?.reason);
 const source=original.traits[index];
 requirePlan(['Secondary Trait','Primary Trait'].includes(source?.slotType),'not_editable_trait','主属性及其他位置不开放类型替换');
 const primary=source.slotType==='Primary Trait';
 const materialized={...game.clone(original),traits:api.materializeItemTraits(original)};
 const pool=dropPool(original,index,materialized);
 requirePlan(pool.policy.allowed,pool.policy.reason_code,pool.policy.reason);
 const sourceDefinition=game.data.trait.collection.find(t=>t.traitName===source.traitName);
 requirePlan(!sourceDefinition?.objectiveId,'source_objective','原词条带升级目标，暂不开放替换');
 requirePlan(!(original.objectives||[]).some(o=>o.traitName===source.traitName),'source_objective','原词条仍关联升级目标，暂不开放替换');
 requirePlan(!(source.conditionalLootEffects||[]).length,'source_conditional','原词条含条件效果，暂未适配');
 requirePlan(!(source.mutationNames||[]).length,'source_mutated','这条词条带特殊突变，暂未适配');
 requirePlan(source.lootEffects.length===1,'source_multi_effect','原词条含多个效果，暂未适配');
 const sourceParams=source.lootEffects[0].params,sourceNames=sourceParams.map(p=>p.magnitudeName);
 requirePlan(['Magnitude.X','Magnitude.X|Magnitude.AilmentType'].includes(sourceNames.join('|')),
  'source_parameter_layout','原词条的参数结构暂未适配');
 requirePlan(!primary||sourceNames.join('|')==='Magnitude.X','primary_parameter_layout','随机主词条首批仅开放单个数值、单个效果的兼容组合');
 requirePlan(sourceParams.every(p=>typeof p.magnitude==='number'&&Number.isFinite(p.magnitude)&&p.magnitude>=0&&p.magnitude<1),
  'not_raw_drop','需要尚未拾取装备的原始随机参数');
 const quality=source.lootEffects[0].params[0].magnitude;
 requirePlan(!source.lootEffects[0].gameplayTag,'not_raw_drop','该记录已换算为显示数值，不能用作原始掉落写入');
 const candidates=pool.candidates.filter(c=>c.trait.traitName===targetName);
 requirePlan(candidates.length===1,'not_in_normal_pool','不在这件装备此位置的原游戏候选库中，或与其他词条互斥');
 const candidate=candidates[0];
 requirePlan(!candidate.trait.objectiveId,'target_objective','目标词条带升级目标，暂未适配');
 const targetQuality=requestedQuality===null?quality:requestedQuality;
 assert(typeof targetQuality==='number'&&Number.isFinite(targetQuality)&&targetQuality>=0&&targetQuality<1,'Target quality must stay in the normal range');
 const generator=game.sdk();generator.state.quality=targetQuality;
 const generated=game.clone(generator.api.rollLootEffectsForTrait({...candidate.trait,
  slotType:source.slotType,priority:source.priority,traitCategoryName:candidate.category.name}));
 requirePlan(!(generated.conditionalLootEffects||[]).length,'target_conditional','目标含条件效果，暂未适配');
 requirePlan(generated.lootEffects.length===1,'target_multi_effect','目标含多个效果，暂未适配');
 requirePlan(generated.lootEffects[0].params.map(p=>p.magnitudeName).join('|')===sourceNames.join('|'),
  'parameter_layout_mismatch','原词条和目标的参数结构不同，当前不能互换');
 const ranges=game.ranges(materialized,index,candidate);
 if(sourceParams.length===2){
  const definition=game.data.trait.collection.find(t=>t.traitName===source.traitName);
  const sourceCategory=game.categoryFor(source);
  requirePlan(definition&&sourceCategory,'source_definition_missing','原词条定义暂时无法核对');
  const sourceSelector=definition.namedLootEffects[0]?.magnitudes?.find(p=>p.magnitudeName==='Magnitude.AilmentType');
  const targetSelector=candidate.trait.namedLootEffects[0]?.magnitudes?.find(p=>p.magnitudeName==='Magnitude.AilmentType');
  requirePlan([sourceSelector,targetSelector].every(p=>p?.paramType==='nonScaling'&&Number.isInteger(p.scalar)),
   'variable_selector','作用类型不是固定映射，暂未适配');
  const sourceRanges=game.ranges(materialized,index,{trait:definition,category:sourceCategory});
  requirePlan(sourceRanges.some(r=>r.parameter==='Magnitude.AilmentType'&&!r.varying)&&
   ranges.some(r=>r.parameter==='Magnitude.AilmentType'&&!r.varying),
   'variable_selector','类型参数不是固定映射，暂未适配');
 }
 requirePlan(ranges.some(r=>r.varying),'fixed_target_value','该词条在此装备上的数值固定，当前未开放');
 requirePlan(ranges.filter(r=>r.varying).length===1&&ranges.find(r=>r.varying).parameter==='Magnitude.X',
  'coupled_parameters','目标含多项联动数值，当前未开放');
 // Type strings and optionally this one existing scalar; never replace an item ID.
 const target=game.clone(source);
 target.traitName=generated.traitName;
 target.traitCategoryName=generated.traitCategoryName;
 target.lootEffects[0].lootEffectName=generated.lootEffects[0].lootEffectName;
 target.lootEffects[0].params[0].magnitude=targetQuality;
 const bindings=[
  {path:['traits',index,'traitName'],before:source.traitName,after:target.traitName},
  {path:['traits',index,'traitCategoryName'],before:source.traitCategoryName,after:target.traitCategoryName},
  {path:['traits',index,'lootEffects',0,'lootEffectName'],before:source.lootEffects[0].lootEffectName,after:target.lootEffects[0].lootEffectName}
 ];
 assert(bindings.some(x=>x.before!==x.after),'No type change requested');
 const targetItem=game.clone(original);targetItem.traits[index]=target;
 const profile=augmentProfile(original);
 if(profile)assert.deepEqual(augmentProfile(targetItem),profile,'Augment color, cost and node context changed');
 const context=familyContext(original);
 if(context)assert.deepEqual(familyContext(targetItem),context,'Original family properties changed');
 assert.deepEqual(raw,original,'Offline planner mutated its input');
 return {
  status:'offline_plan_only_not_applied',item_id:original.id,gameplayTag:original.gameplayTag,
  tier:original.tierIdentifier,rarity:original.rarityIdentifier,trait_index:index,
  source_item:original,target_item:targetItem,bindings,
  target_trait_name:targetName,requested_quality:requestedQuality,target_quality:targetQuality,
  numericBindings:targetQuality===quality?[]:[{path:['traits',index,'lootEffects',0,'params',0,'magnitude'],before:quality,after:targetQuality}],
  preserved_original_random_roll:quality,
  source_materialized_trait:materialized.traits[index],
  target_materialized_trait:generator.api.materializeItemTraits(targetItem)[index],
  target_normal_range:ranges,
  parameter_layout:sourceNames,
  slot_type:source.slotType,random_primary:primary,
  augment_profile:profile,
  additional_family_context:context,
  fits_original_string_lengths:bindings.every(x=>x.after.length<=x.before.length),
  required_live_checks:[
   'Fresh same-process capture of this exact still-active ground pickup and item handle.',
   'Original complete raw item must still match; original allowed type pool must contain the target.',
   'Actual native string counts, capacities, non-overlapping allocations and original bytes must be verified.',
   'A reversible local-memory operation would be a separate step; this planner cannot apply anything.',
   'Check current-session display and relevant effects; retention can be checked during a normal user restart.'
  ]
 };
}

if(require.main===module){
 const [capture,output,indexArg='1',targetName='WeaponArtDamagePercentSecondary',qualityArg]=process.argv.slice(2);
 if(!capture||!output)throw new Error('Usage: node prepare_ground_trait_trial.cjs capture.json output.json [index]');
 const snapshot=JSON.parse(fs.readFileSync(capture,'utf8'));
 assert.equal(snapshot.records.length,1,'Select one exact ground item before planning');
 const plan=prepare(snapshot.records[0].item,Number(indexArg),targetName,qualityArg===undefined||qualityArg==='original'?null:Number(qualityArg));
 plan.capture_file=path.resolve(capture);plan.capture_pid=snapshot.pid;
 plan.warning='A saved capture may belong to an earlier process or an already picked item. This file grants no authority and cannot apply changes.';
 fs.writeFileSync(output,JSON.stringify(plan,null,2)+'\n');
 console.log(JSON.stringify({status:plan.status,id:plan.item_id,quality:plan.preserved_original_random_roll,
  target_range:plan.target_normal_range,fits_original_string_lengths:plan.fits_original_string_lengths}));
}
module.exports={prepare,PlanError};
