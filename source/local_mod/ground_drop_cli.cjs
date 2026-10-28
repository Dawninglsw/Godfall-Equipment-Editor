/* Original-game pool and range calculations for one unpicked item. Offline only. */
'use strict';
const fs=require('fs'),game=require('../analysis/game_trait_sdk.cjs');
const {prepare,PlanError}=require('../analysis/prepare_ground_trait_trial.cjs');
const {dropPool}=require('../analysis/ground_primary_rules.cjs');
const {augmentProfile}=require('../analysis/ground_augment_rules.cjs');
const {familyContext}=require('../analysis/ground_additional_rules.cjs');
function candidateDetail(raw,index,c,materialized){
 let plan=null,error=null;
 try{plan=prepare(raw,index,c.trait.traitName);}catch(e){error=e;}
 let trait=plan?.target_materialized_trait,ranges=plan?.target_normal_range;
 if(!trait){
  try{trait=game.materialize(materialized,index,c,raw.traits[index].lootEffects[0]?.params[0]?.magnitude??.5).trait;}
  catch(e){trait={traitName:c.trait.traitName,lootEffects:(c.trait.namedLootEffects||[]).map(e=>({lootEffectName:e.name,params:[]}))};}
 }
 if(!ranges){try{ranges=game.ranges(materialized,index,c);}catch(e){ranges=[];}}
 let code=error?.code||'available',reason=error?.message||'';
 if(error&&!(error instanceof PlanError)){code='calculation_error';reason='候选资料暂时无法完整核对';}
 if(plan&&!plan.fits_original_string_lengths){code='storage_layout_limit';reason='该类型暂不适配这件装备现有的记录空间';}
 const new_parameter_support=Boolean(plan?.parameter_layout.length===2);
 const new_primary_support=Boolean(plan?.random_primary);
 const new_augment_support=Boolean(plan?.augment_profile);
 const new_family_support=Boolean(plan?.additional_family_context);
 if(code==='available'&&new_parameter_support)reason='同结构双参数转换已通过离线检查，尚待游戏内核对';
 if(code==='available'&&new_primary_support)reason='随机主词条兼容转换已通过离线检查，尚待游戏内核对';
 if(code==='available'&&new_augment_support)reason='强化物副词条已通过离线检查，颜色与耗能保留，尚待游戏内核对';
 if(code==='available'&&new_family_support)reason=plan.additional_family_context.label+'副词条已通过离线检查，尚待游戏内核对';
 return {traitName:c.trait.traitName,trait,available:code==='available',reason_code:code,reason,
  ranges:ranges||[],default_quality:plan?.target_quality??null,new_parameter_support,new_primary_support,new_augment_support,new_family_support};
}
function inspectItem(raw){
 const materialized={...game.clone(raw),traits:game.clone(game.sdk().api.materializeItemTraits(raw))};
 const slots=[];
 for(let index=0;index<raw.traits.length;index++){
  if(!['Secondary Trait','Primary Trait'].includes(raw.traits[index].slotType))continue;
  const candidates=[],all_candidates=[];
  const pool=dropPool(raw,index,materialized);
  for(const c of pool.candidates){
   if(c.trait.traitName===raw.traits[index].traitName)continue;
   const detail=candidateDetail(raw,index,c,materialized);all_candidates.push(detail);
   if(detail.available)candidates.push(detail);
  }
  slots.push({index,trait:materialized.traits[index],candidates,all_candidates,
   normal_candidate_count:all_candidates.length,slot_type:raw.traits[index].slotType,
   primary_policy:pool.primary?pool.policy:null});
 }
 return {materialized,slots,augment_profile:augmentProfile(raw),additional_family_context:familyContext(raw)};
}
function qualityForValue(range,displayValue){
 if(!Number.isFinite(displayValue))throw new Error('数值必须为有限数字');
 const value=displayValue/range.multiplier;
 if(value<range.min-1e-10||value>range.max+1e-10)throw new Error('请选择列出的正常范围内数值');
 const [lo,hi]=range.unrounded.range,half=.5/10**range.decimals;
 if(!(hi>lo))throw new Error('该参数没有可调整的范围');
 const lower=Math.max(0,(value-half-lo)/(hi-lo)),upper=Math.min(.999,(value+half-lo)/(hi-lo));
 if(lower>upper)throw new Error('该数值不在游戏可显示的档位中');
 const q=(lower+upper)/2,rounded=Math.floor((lo+(hi-lo)*q)*10**range.decimals+.5)/10**range.decimals;
 if(Math.abs(rounded-value)>1e-9)throw new Error('该数值不在游戏可显示的档位中');
 return q;
}
function run(input){
 if(input.action==='inspect')return inspectItem(input.item);
 if(input.action==='explain'){
  const info=inspectItem(input.item),slot=info.slots.find(s=>s.index===input.index);
  if(!slot)throw new Error('请选择一条主词条或副词条');
  if(slot.primary_policy&&!slot.primary_policy.allowed)return {traitName:input.targetTraitName,available:false,
   reason_code:slot.primary_policy.reason_code,reason:slot.primary_policy.reason};
  if(input.item.traits[input.index].traitName===input.targetTraitName)
   return {traitName:input.targetTraitName,available:false,reason_code:'current_type',reason:'这是当前词条，无需替换'};
  return slot.all_candidates.find(c=>c.traitName===input.targetTraitName)||{
   traitName:input.targetTraitName,available:false,reason_code:'not_in_normal_pool',
   reason:'不在这件装备此位置的原游戏候选库中，或与其他词条互斥'};
 }
 if(input.action==='plan'){
  let quality=input.quality??null;
  if(input.displayValue!==undefined){
   const base=prepare(input.item,input.index,input.targetTraitName);
   const ranges=base.target_normal_range.filter(r=>r.varying);
   if(ranges.length!==1)throw new Error('本轮仅开放单个数值的简单副词条');
   quality=qualityForValue(ranges[0],input.displayValue);
  }
  const plan=prepare(input.item,input.index,input.targetTraitName,quality);
  if(!plan.fits_original_string_lengths)throw new Error('该类型尚未适配这件掉落，请选择其他候选');
  return plan;
 }
 throw new Error('不支持的掉落编辑操作');
}
function rpc(input){
 // An already-open old Python window must not silently expose a new write mode.
 if(![2,3].includes(input.clientProtocol)&&input.action==='plan'&&input.item?.traits?.[input.index]?.lootEffects?.[0]?.params?.length===2)
  throw new Error('请关闭并重新打开修改工具，以使用新增词条适配');
 if(input.action==='plan'&&input.item?.traits?.[input.index]?.slotType==='Primary Trait'&&input.clientProtocol!==3)
  throw new Error('请关闭并重新打开修改工具，以使用随机主词条编辑');
 const result=run(input);
 if(![2,3].includes(input.clientProtocol)&&input.action==='inspect')for(const slot of result.slots){
  slot.candidates=slot.candidates.filter(c=>!c.new_parameter_support);
  slot.all_candidates=slot.all_candidates.map(c=>c.new_parameter_support?{...c,available:false,
   reason_code:'old_interface',reason:'请重新打开工具以使用新增适配'}:c);
 }
 if(input.clientProtocol!==3&&input.action==='inspect')result.slots=result.slots.filter(s=>s.slot_type!=='Primary Trait');
 return result;
}
if(require.main===module){
 try{process.stdout.write(JSON.stringify({ok:true,result:rpc(JSON.parse(fs.readFileSync(0,'utf8')))}));}
 catch(e){process.stdout.write(JSON.stringify({ok:false,error:e.message}));process.exitCode=1;}
}
module.exports={inspectItem,qualityForValue,run,rpc};
