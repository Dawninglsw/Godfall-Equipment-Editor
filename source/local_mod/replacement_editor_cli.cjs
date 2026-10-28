/* Offline bridge: use the original pool/range planner, then reconstruct one copy. */
'use strict';
const fs=require('fs'),assert=require('assert/strict');
const planner=require('./trait_type_cli.cjs');
const {reconstruct,checkItem,reconstructMany}=require('../analysis/reconstruct_owned_item.cjs');
const game=require('../analysis/game_trait_sdk.cjs');
const compiler=require('./compile_replacement_copy.cjs');
function prepare(request){
 if(request.edits!==undefined)return prepareMany(request);
 const s=request.item;
 checkItem(s);
 const slot=s.traits&&s.traits[request.index]?.slotType;
 assert(['Primary Trait','Secondary Trait'].includes(slot),'只开放副词条与已适配的随机主词条');
 if(slot==='Primary Trait')require('../analysis/random_primary_copy_rules.cjs').check(s,request.index);
 const choice=planner.preview(request),preview=reconstruct(s,request.index,choice.targetTrait);
 const config=compiler.compile(preview);
 return {preview,choice,choices:[{...choice,index:request.index}],trialId:config.trialId};
}
function editsFor(item,edits){
 checkItem(item);assert(Array.isArray(edits)&&edits.length>0&&edits.length<=item.traits.length,'整件方案需包含1条或以上副词条修改');
 const seen=new Set();return edits.map(edit=>{
  assert(edit&&Number.isInteger(edit.index)&&item.traits[edit.index]?.slotType==='Secondary Trait','仅支持本件装备的副词条');
  assert(!seen.has(edit.index),'同一副词条不能重复设置');seen.add(edit.index);
  assert(typeof edit.targetTraitName==='string','请选择目标词条');
  return {...edit};
 }).sort((a,b)=>a.index-b.index);
}
function project(item,edits,omitIndex){
 const working=game.clone(item);
 for(const edit of edits){
  if(edit.index===omitIndex)continue;
  const trait=game.data.trait.collection.find(t=>t.traitName===edit.targetTraitName);
  assert(trait,'目标词条不存在');
  const old=item.traits[edit.index],category=edit.targetCategoryName?game.data.traitCategory.collection.find(c=>c.name===edit.targetCategoryName):game.categoryFor({...old,traitName:trait.traitName,traitCategoryName:trait.traitName});
  assert(category,'目标词条类别不存在');
  working.traits[edit.index]={...game.clone(old),traitName:trait.traitName,traitCategoryName:category.name};
 }
 return working;
}
function inspectMany(request){
 checkItem(request.item);
 const edits=request.edits?.length?editsFor(request.item,request.edits):[];
 assert(Number.isInteger(request.index)&&request.item.traits[request.index]?.slotType==='Secondary Trait','请选择副词条');
 return planner.inspect({item:project(request.item,edits,request.index),index:request.index});
}
function prepareMany(request){
 const source=request.item,edits=editsFor(source,request.edits),choices=[];
 // Validate each slot against the final other types. This also permits a legal
 // A/B swap without order-dependent intermediate exclusions; quality always
 // comes from the original slot rather than another edited slot's values.
 for(const edit of edits){
  const working=project(source,edits,edit.index),choice=planner.preview({...edit,item:working});
  choices.push({...choice,index:edit.index});
 }
 const preview=reconstructMany(source,choices.map(c=>({index:c.index,targetTrait:c.targetTrait}))),config=compiler.compile(preview);
 return {preview,choice:choices[0],choices,trialId:config.trialId};
}
function primarySupport(item){
 try{
  const index=item.traits.findIndex(t=>t.slotType==='Primary Trait');
  const allowed=require('../analysis/random_primary_copy_rules.cjs').check(item,index);
  checkItem(item);
  return {supported:true,...allowed};
 }catch(error){return {supported:false,reason:error.message};}
}
function run(request){
 if(request.action==='primary_support')return primarySupport(request.item);
 return request.action==='inspect_many'?inspectMany(request):prepare(request);
}
if(require.main===module){
 try{process.stdout.write(JSON.stringify({ok:true,result:run(JSON.parse(fs.readFileSync(0,'utf8')))}));}
 catch(error){process.stdout.write(JSON.stringify({ok:false,error:error.message}));process.exitCode=1;}
}
module.exports={prepare,prepareMany,inspectMany,primarySupport,run};
