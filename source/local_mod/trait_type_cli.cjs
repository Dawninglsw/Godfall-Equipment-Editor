/* Type replacement planning. All selection and materialization stay offline. */
'use strict';
const fs=require('fs'),path=require('path'),sdk=require('../analysis/game_trait_sdk.cjs');
const clone=sdk.clone;
const {ownedAugmentContext,slotRestriction}=require('../analysis/owned_augment_rules.cjs');
const traitLabels=JSON.parse(fs.readFileSync(path.join(__dirname,'trait_labels.json'),'utf8'));
const nativeLabelData=JSON.parse(fs.readFileSync(path.join(__dirname,'chinese_trait_labels.json'),'utf8'));
const nativeLabels=nativeLabelData.culture==='zh-CN'?nativeLabelData.labels:{};
const labels={PhysicalDamagePercent:'物理伤害',WeaponArtDamagePercent:'武器技艺伤害',WeakpointDamage:'弱点伤害',
 WeaponArtChargeSpeed:'武器技艺充能速度',AilmentPower:'异常状态加成',AilmentDuration:'减益持续时间',
 CritChance:'暴击率',CritDamage:'暴击伤害',DualBladesDamagePercent:'双剑伤害',GreatswordDamagePercent:'巨剑伤害',
 LongswordDamagePercent:'长剑伤害',PolearmDamagePercent:'长柄武器伤害',WarhammerDamagePercent:'战锤伤害',
 ComboCounterChargeSpeed:'连击充能速度',ComboCounterDamagePercent:'连击伤害',TimingAttackDamagePercent:'时机攻击伤害',
 SoulshatterBuildupPercent:'灵魂破碎积累',PolarityChargeSpeed:'极性充能速度',PolarityDamagePercent:'极性伤害',
 PolarityWeaponBuffDuration:'极性武器增益持续时间',PolarityWeaponBuffPower:'极性武器增益强度',
 FireResistance:'火焰抗性',AllResistance:'全部抗性',DamageToBleeding:'对流血敌人的伤害'};
function itemCheck(item,index){
 if(!item||typeof item.id!=='string'||typeof item.gameplayTag!=='string'||!item.id.includes('-'+item.gameplayTag+'.'))throw new Error('装备编号或类型不正确');
 if(!Array.isArray(item.traits)||!Number.isInteger(index)||index<0||index>=item.traits.length)throw new Error('词条位置不正确');
 if(!Number.isFinite(item.tierIdentifier)||!Number.isFinite(item.rarityIdentifier))throw new Error('缺少装备等级或稀有度');
 if(!['Weapon','Ring','Amulet','Charm','Augment','Banner','Consumable'].includes(item.lootClassName))throw new Error('该装备类型尚未开放词条编辑');
}
function supported(old,candidate){
 if(old.conditionalLootEffects?.length||candidate.trait.conditionalLootEffects?.length)return '条件词条需要额外处理，暂不替换';
 if(!candidate.trait.namedLootEffects?.length)return '没有可生成的效果';
 return '';
}
function primaryCopyPool(item,index,pool){
 if(item.traits[index].slotType==='Primary Trait'){
  const rules=require('../analysis/random_primary_copy_rules.cjs');let allowed;
  try{allowed=rules.check(item,index);}catch(error){
   return {...pool,candidates:[],reason:error.message,primary_fixed:pool.primary_fixed};
  }
  return {...pool,candidates:pool.candidates.filter(c=>allowed.candidateKeys.includes(c.category.name+'|'+c.trait.traitName)),
   template_primary_candidate_count:allowed.candidateCount};
 }
 return pool;
}
function candidateInfo(item,index,candidate,context){
 const old=item.traits[index],restriction=slotRestriction(item,index,context),reason=restriction?.reason||supported(old,candidate);
 let ranges=[];
 if(!reason)try{ranges=sdk.ranges(item,index,candidate);}catch(error){return {category:candidate.category.name,traitName:candidate.trait.traitName,supported:false,reason:error.message};}
 const effects=candidate.trait.namedLootEffects.map(e=>labels[e.name]||e.name);
 const native=nativeLabels[candidate.trait.traitName];
 return {category:candidate.category.name,traitName:candidate.trait.traitName,
  label:native?.label||traitLabels[candidate.trait.traitName]||effects.join('、'),description:native?.description||(candidate.trait.description||'').replace(/^"|"$/g,''),
  supported:!reason,reason,ranges};
}
function inspect(request){
 const {item,index}=request;itemCheck(item,index);const context=ownedAugmentContext(item);
 const pool=context?.blocked?{candidates:[],reason:context.reason}:primaryCopyPool(item,index,sdk.pools(item,index));
 let quality;try{quality=sdk.qualityEstimate(item,index);}catch(error){quality={quality:.5,estimated:true,reason:error.message,unavailable:true};}
 return {item_id:item.id,source_index:index,source_trait:clone(item.traits[index]),quality,
  primary_fixed:!!pool.primary_fixed,template_primary_candidate_count:pool.template_primary_candidate_count||0,
  reason:context?.reason||slotRestriction(item,index,context)?.reason||pool.reason||'',
  augment_profile:context?.profile||null,augment_restriction:slotRestriction(item,index,context),
  candidates:pool.candidates.map(c=>candidateInfo(item,index,c,context)),
  source_is_conditional:!!item.traits[index].conditionalLootEffects?.length};
}
function preview(request){
 const {item,index,targetTraitName,targetCategoryName}=request;itemCheck(item,index);
 const context=ownedAugmentContext(item),restriction=slotRestriction(item,index,context);
 if(restriction)throw new Error(restriction.reason);
 const pool=primaryCopyPool(item,index,sdk.pools(item,index));
 if(pool.primary_fixed)throw new Error('这件装备的主词条固定，不开放更换类型');
 if(item.traits[index].traitName===targetTraitName)throw new Error('请选择不同的词条类型');
 const candidate=pool.candidates.find(c=>c.trait.traitName===targetTraitName&&(!targetCategoryName||c.category.name===targetCategoryName));
 if(!candidate)throw new Error('目标词条不在该装备当前槽位的正常候选库中，或与其他词条互斥');
 const reason=supported(item.traits[index],candidate);if(reason)throw new Error(reason);
 let estimate;try{estimate=sdk.qualityEstimate(item,index);}catch(error){estimate={quality:.5,estimated:true,unavailable:true,reason:error.message};}
 let quality=request.quality===undefined?estimate.quality:request.quality;
 if(typeof quality!=='number'||!Number.isFinite(quality)||quality<0||quality>.999)throw new Error('词条档次必须处于正常范围');
 const ranges=sdk.ranges(item,index,candidate),variable=ranges.find(r=>r.varying);
 if(request.desiredValue!==undefined){
  if(!variable)throw new Error('该类型的数值固定，不能单独调整');
  const v=request.desiredValue,d=variable.decimals;
  if(typeof v!=='number'||!Number.isFinite(v)||v<variable.min-1e-9||v>variable.max+1e-9||Math.abs(Math.round(v*10**d)/10**d-v)>1e-8)throw new Error('所选数值超出正常范围或不符合游戏精度');
  const [lo,hi]=variable.unrounded.range,half=.5/10**d;
  const bounds=[(v-half-lo)/(hi-lo),(v+half-lo)/(hi-lo)].sort((a,b)=>a-b);
  const lower=Math.max(0,bounds[0]),upper=Math.min(.999,bounds[1]);if(lower>upper)throw new Error('无法生成该数值');
  quality=(lower+upper)/2;
 }
 const target=sdk.materialize(item,index,candidate,quality);
 if(request.desiredValue!==undefined){const effect=target.trait.lootEffects.find(e=>e.lootEffectName===variable.effect);
  if(Math.abs(effect.params.find(p=>p.magnitudeName===variable.parameter).magnitude-request.desiredValue)>1e-8)throw new Error('生成数值与选择不一致');}
 // Original engine effects must use observed materialized values, not re-rolled
 // values. The SDK supplies only their condition/processor annotations here.
 const {api}=sdk.sdk();const oldEffects=api.lootEffectsToUE4JSON([item.traits[index]],{tierIdentifier:item.tierIdentifier,rarityIdentifier:item.rarityIdentifier});
 return {item_id:item.id,index,category:candidate.category.name,targetTraitName,quality,quality_estimate:estimate,
  ranges,label:candidateInfo(item,index,candidate).label,description:candidate.trait.description||'',
  sourceTrait:clone(item.traits[index]),targetTrait:target.trait,augment_profile:context?.profile||null,
  sourceEngineEffects:clone(oldEffects),targetEngineEffects:target.engine_effects};
}
function compile(request){
 const edits=request.edits||[];if(!Array.isArray(edits)||edits.length>100)throw new Error('类型修改最多100条');
 const groups=new Map(),seen=new Set(),previews=[];
 for(const edit of edits){const item=edit.sourceItem,index=edit.sourceIndex;itemCheck(item,index);
  const key=item.id+'|'+index;if(seen.has(key))throw new Error('同一词条不能重复替换');seen.add(key);
  let group=groups.get(item.id);if(!group){group={id:item.id,gameplayTag:item.gameplayTag,sourceItem:clone(item),working:clone(item),replacements:[]};groups.set(item.id,group);}
  if(JSON.stringify(group.sourceItem)!==JSON.stringify(item))throw new Error('同一装备的来源快照不一致');
  const result=preview({item:group.working,index,targetTraitName:edit.targetTraitName,targetCategoryName:edit.targetCategoryName,quality:edit.quality});
  group.working.traits[index]=clone(result.targetTrait);group.replacements.push(result);previews.push(result);
 }
 const compiled=[];for(const group of groups.values()){
  const {api}=sdk.sdk();compiled.push({id:group.id,gameplayTag:group.gameplayTag,
   tierIdentifier:group.sourceItem.tierIdentifier,rarityIdentifier:group.sourceItem.rarityIdentifier,
   masterworkUpgradeRank:group.sourceItem.masterworkUpgradeRank||0,
   sourceTraits:group.sourceItem.traits,targetTraits:group.working.traits,
   sourceEngineEffects:clone(api.lootEffectsToUE4JSON(group.sourceItem.traits,{tierIdentifier:group.sourceItem.tierIdentifier,rarityIdentifier:group.sourceItem.rarityIdentifier})),
   targetEngineEffects:clone(api.lootEffectsToUE4JSON(group.working.traits,{tierIdentifier:group.sourceItem.tierIdentifier,rarityIdentifier:group.sourceItem.rarityIdentifier})),
   replacements:group.replacements.map(p=>({index:p.index,sourceTrait:p.sourceTrait,targetTrait:p.targetTrait,
    sourceEngineEffects:p.sourceEngineEffects,targetEngineEffects:p.targetEngineEffects}))});
 }
 return {groups:compiled,previews};
}
function run(request){if(request.action==='inspect')return inspect(request);if(request.action==='preview')return preview(request);if(request.action==='compile')return compile(request);throw new Error('Unknown offline request');}
if(require.main===module){try{const request=JSON.parse(fs.readFileSync(0,'utf8'));process.stdout.write(JSON.stringify({ok:true,result:run(request)}));}
 catch(error){process.stdout.write(JSON.stringify({ok:false,error:error.message}));process.exitCode=1;}}
module.exports={inspect,preview,compile,run};
