/* Original-action sequential objective completion for one reviewed unused item. */
'use strict';
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),crypto=require('crypto');
const game=require('../analysis/game_trait_sdk.cjs'),research=require('../analysis/reconstruct_cursed_item.cjs');
function stateSpec(item){
 const remainingCurses=item.mutationNames.filter(m=>m===research.CURSED).length;
 const traits=item.traits.map((t,index)=>{
  const spec=game.data.trait.collection.find(x=>x.traitName===t.traitName),category=game.categoryFor(t);
  const ranges=game.ranges(item,index,{trait:spec,category});
  return {traitName:t.traitName,traitCategoryName:t.traitCategoryName,slotType:t.slotType,
   masterworkBonusTier:t.masterworkBonusTier||0,mutationNames:t.mutationNames||[],priority:t.priority===undefined?null:t.priority,
   effects:(spec.namedLootEffects||[]).map((e,j)=>({name:e.name,tag:t.lootEffects[j].gameplayTag,
    params:ranges.filter(r=>r.effect===e.name).map(r=>({name:r.parameter,min:r.min,max:r.max}))}))};
 });
 const linked=item.traits.find(t=>game.data.trait.collection.find(s=>s.traitName===t.traitName)?.objectiveId);
 let objective=null;
 if(linked){
  const objectiveId=game.data.trait.collection.find(t=>t.traitName===linked.traitName).objectiveId;
  const definition=game.data.objectives.collection.find(o=>o.id===objectiveId),bounds=definition.progressDenominator;
  assert(Number.isFinite(bounds.min)&&Number.isFinite(bounds.max)&&bounds.min>0&&bounds.max<=1e12);
  objective={traitName:linked.traitName,objectiveId,min:bounds.min,max:bounds.max};
 }
 assert.equal(!!objective,remainingCurses>0);
 return {remainingCurses,mutationNames:game.clone(item.mutationNames),traits,objective};
}
function compile(item){
 const index=item.traits.findIndex(t=>t.slotType==='Secondary Trait');research.check(item,index);
 const totalLayers=item.mutationNames.filter(m=>m===research.CURSED).length;
 assert(totalLayers>=1&&totalLayers<=3,'仅支持剩余1至3层诅咒的物品');
 assert(!item.equipCount&&!item.isEquippedInSelectedValorplate,'首轮请选择未装备、未保存到配装的物品');
 assert(item.objectives[0].progressNumerator<=item.objectives[0].progressDenominator,'目标进度超出正常范围');
 const sourceKeys=['id','gameplayTag','lootClassName','tierIdentifier','rarityIdentifier','masterworkUpgradeRank',
  'mutationNames','selectedTraitTags','traits','damageTypes','lootAttributes','amount','objectives'];
 const preservedKeys=['id','gameplayTag','lootClassName','tierIdentifier','rarityIdentifier','masterworkUpgradeRank',
  'selectedTraitTags','damageTypes','lootAttributes','amount'];
 const source=Object.fromEntries(sourceKeys.filter(k=>item[k]!==undefined).map(k=>[k,game.clone(item[k])]));
 const {factory}=require('../analysis/offline_equipment_factory.cjs');
 const native=factory({rollProgressDenominator:o=>o.progressDenominator.min});
 let skeleton=game.clone(source);const states=[stateSpec(skeleton)];
 for(let n=0;n<totalLayers;n++){
  skeleton=native.transform(skeleton,research.CURSED);
  const spec=stateSpec(skeleton);assert.equal(spec.remainingCurses,totalLayers-n-1);states.push(spec);
 }
 const final=states.at(-1);
 const planId=crypto.createHash('sha256').update(JSON.stringify(source)+'|multi-awaken-v3').digest('hex').slice(0,24);
 return {version:1,planId,source,sourceKeys,preservedKeys,collection:research.check(item,index).family.collection,
  beforeProgress:item.objectives[0].progressNumerator,targetProgress:item.objectives[0].progressDenominator,
  autoAwaken:true,startAtAwaken:item.objectives[0].progressNumerator===item.objectives[0].progressDenominator,
  totalLayers,states,finalMutationNames:final.mutationNames,finalTraits:final.traits,
  scope:'One existing unused item,1-3 curse layers, using original objective update/awakening/refresh sequentially. Every next objective uses actual fresh readback. No trait type change or replacement generation.'};
}
const bindAnchor='e.UE_UPDATE_LOADOUT_OBJECTIVE=function(){var e=';
const requestAnchor='Ee.a.request({path:"/inventory/gear/".concat(g,"/objective"),method:"POST",body:{playerId:o,objectiveIndex:u,progressNumerator:d}}).catch((function(e){a({type:y.Oh,payload:t.payload})}))';
const refreshAnchor='return Ee.a.request({path:"/inventory/gear",method:"GET"}).then((function(e){return e}))';
const awakenAnchor='Ee.a.request({path:"/crafting/awaken",method:"POST",body:{playerId:t,gearId:s}})';
function patch(source){
 for(const a of [bindAnchor,requestAnchor,refreshAnchor,awakenAnchor])assert.equal(source.split(a).length-1,1,'Original objective integration missing or ambiguous');
 return source.replace(bindAnchor,'e.UE_UPDATE_LOADOUT_OBJECTIVE=function(){window.__GodfallUncurseTrial.bind(function(){return a.store},function(){return C.Ph},function(){return C.rd},function(){return C.zb});var e=')
  .replace(requestAnchor,'Ee.a.request({path:"/inventory/gear/".concat(g,"/objective"),method:"POST",body:{playerId:o,objectiveIndex:u,progressNumerator:d}}).then((function(__value){window.__GodfallUncurseTrial.ack(g,u,d,!0);return __value})).catch((function(e){window.__GodfallUncurseTrial.ack(g,u,d,!1);a({type:y.Oh,payload:t.payload})}))')
  .replace(refreshAnchor,'return Ee.a.request({path:"/inventory/gear",method:"GET"}).then((function(e){window.__GodfallUncurseTrial.readback(e);return e}))')
  .replace(awakenAnchor,awakenAnchor+'.then((function(__gear){window.__GodfallUncurseTrial.awakenAck(s,!0);return __gear})).catch((function(__error){window.__GodfallUncurseTrial.awakenAck(s,!1);throw __error}))');
}
function runtime(config){return fs.readFileSync(path.join(__dirname,'uncurse_runtime.js'),'utf8').replace('__GODFALL_UNCURSE_CONFIG__',JSON.stringify(config));}
module.exports={compile,patch,runtime};
