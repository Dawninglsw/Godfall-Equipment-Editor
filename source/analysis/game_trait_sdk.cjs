/* Selected original game exports executed offline against original tables. */
'use strict';
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert/strict');
const root=__dirname;
const source=fs.readFileSync(path.join(root,'extracted/main.c05310c4.chunk.js'),'utf8');
const data=JSON.parse(fs.readFileSync(path.join(root,'extracted/source_data.json')));
const clone=x=>JSON.parse(JSON.stringify(x));
function expression(name){
 const needle='a.'+name+'=function',start=source.indexOf(needle);assert(start>=0,name);
 const begin=start+('a.'+name+'=').length;let depth=0,quote=null,escape=false;
 for(let i=begin;i<source.length;i++){const ch=source[i];if(quote){if(escape)escape=false;else if(ch==='\\')escape=true;else if(ch===quote)quote=null;continue;}
  if(ch==='"'||ch==="'"){quote=ch;continue;}if(ch==='{')depth++;else if(ch==='}'&&--depth===0)return source.slice(begin,i+1);}
 throw new Error('Unclosed original function '+name);
}
const values=x=>Array.isArray(x)?x:Object.values(x||{});
const predicate=(row,p)=>typeof p==='function'?p(row):typeof p==='string'?row[p]:Object.entries(p).every(([k,v])=>row[k]===v);
const lodash={cloneDeep:clone,find:(rows,p)=>values(rows).find(row=>predicate(row,p)),
 filter:(rows,p)=>values(rows).filter(row=>predicate(row,p)),
 map:(rows,fn)=>values(rows).map(typeof fn==='string'?row=>row[fn]:fn),
 flatMap:(rows,fn)=>values(rows).flatMap(typeof fn==='string'?row=>row[fn]:fn),
 forEach:(rows,fn)=>values(rows).forEach(fn),compact:rows=>rows.filter(Boolean),
 isEmpty:x=>!x||Object.keys(x).length===0,intersection:(a,b)=>values(a).filter(x=>values(b).includes(x)),
 mapValues:(rows,fn)=>Object.fromEntries(Object.entries(rows||{}).map(([k,v])=>[k,fn(v,k)])),
 isString:x=>typeof x==='string',isNumber:x=>typeof x==='number',isUndefined:x=>x===undefined,
 concat:(array,...more)=>array.concat(...more),assign:Object.assign,
 omit:(obj,keys)=>Object.fromEntries(Object.entries(obj||{}).filter(([k])=>!values(Array.isArray(keys)?keys:[keys]).includes(k))),
 reduce:(rows,fn,initial)=>values(rows).reduce(fn,initial),first:rows=>rows[0],
 times:(n,fn)=>Array.from({length:n},(_,i)=>fn(i))};
const names=['itemMeetsTierAndRarityReqs','getValidTraitCategoriesForSlot','getValidTraitsForTraitCategory',
 'getItemScalingForItem','getTraitByName','getLootEffectSpecByName','roundWithSpecificity','materializeMagnitude',
 'materializeLootEffect','multiplyItemScalingMultiplierRows','getItemScalingMultiplierRowForMutations',
 'masterworkUpgradeTraitTierOffset','masterworkUpgradeAttributeTierOffset','materializeItemTraits',
 'materializeConditionalTriggers','materializeExecProcessors','lootEffectToUE4JSON','lootEffectsToUE4JSON',
 'rollLootEffectsFromSpecs','rollLootEffectsForTrait'];
function sdk(){
 const a={SOURCE_DATA:data},state={quality:.5,trace:[]};
 const context=vm.createContext({a,c:a,m:data,u:a,l:{default:lodash},n:(x,count)=>x.slice(0,count),
   t:x=>Array.from(x||[]),f:{TraitGroupName:{PrimaryAttribute:'Primary Attribute'}}});
 for(const name of names)a[name]=vm.runInContext('('+expression(name)+')',context);
 const original=a.materializeMagnitude;
 a.materializeMagnitude=function(q,range,decimals){state.trace.push({range:Array.from(range),decimals:decimals||0});return original(q,range,decimals);};
 a.rollRandomMagnitude=()=>state.quality;
 return {api:a,state};
}
function template(tag){for(const key of ['weapons','trinkets','augments','runes','banners','potions']){
 const row=(data[key]?.collection||[]).find(x=>x.gameplayTag===tag);if(row)return row;
 }throw new Error('Unknown item template '+tag);}
function possibleTags(item,definition=template(item.gameplayTag)){
 const groups=item.lootClassName==='Weapon'?definition.traitTagGroups:
   definition.defaultTraitTagGroups?[...definition.defaultTraitTagGroups,...(definition.elementTraitTagGroups||[])]:definition.traitTagGroups;
 const {api}=sdk(),tags=new Set();for(const group of groups||[]){
  const rows=data.traitTags.collection.filter(r=>r.groupName===group&&api.itemMeetsTierAndRarityReqs(item,r)&&r.weight>0);
  if(!rows.length)throw new Error('Missing trait-tag group '+group);
  for(const row of rows)for(const tag of row.addedTraitTags||[])tags.add(tag);
 }return [...tags];
}
function categoryFor(trait){return data.traitCategory.collection.find(c=>c.name===trait.traitCategoryName)||
 data.traitCategory.collection.find(c=>c.traitGroup===trait.traitName&&c.groupName===trait.slotType);}
function pools(item,index){
 const {api}=sdk(),definition=template(item.gameplayTag),old=item.traits[index];
 if(!old)throw new Error('Invalid trait index');
 if(!['Primary Trait','Secondary Trait','Masterwork Trait'].includes(old.slotType))return {candidates:[],reason:'Primary attributes are outside type replacement'};
 const slots=data.traitSlot.collection.filter(s=>s.groupName===definition.traitSlotGroups&&s.slotType===old.slotType&&item.rarityIdentifier>=s.minRarity&&item.rarityIdentifier<=s.maxRarity);
 if(!slots.length)return {candidates:[],reason:'No matching native slot'};
 const all=possibleTags(item,definition);
 const selected=Array.isArray(item.selectedTraitTags)?item.selectedTraitTags:null;
 if(old.slotType!=='Primary Trait'&&!selected)return {candidates:[],reason:'Complete selected trait tags are needed for secondary editing'};
 const tags=old.slotType==='Primary Trait'?all:selected;
 const exclusions=[];
 item.traits.forEach((t,i)=>{if(i===index)return;const cat=categoryFor(t);if(!cat)throw new Error('Unknown existing trait category '+t.traitName);exclusions.push(...(cat.exclusionGroups||[]));});
 const candidates=[],seen=new Set();for(const slot of slots){
  for(const cat of api.getValidTraitCategoriesForSlot(item,tags,slot,exclusions)){
   if(!(cat.weight>0))continue;
   for(const trait of api.getValidTraitsForTraitCategory(item,cat)){
    if(!(trait.weight>0))continue;const key=cat.name+'|'+trait.traitName;if(seen.has(key))continue;seen.add(key);
    candidates.push({category:cat,trait});
   }
  }
 }
 const primaryNames=new Set();
 if(old.slotType==='Primary Trait')for(const slot of slots)for(const cat of api.getValidTraitCategoriesForSlot(item,all,slot,[])){
  if(cat.weight>0)for(const trait of api.getValidTraitsForTraitCategory(item,cat))if(trait.weight>0)primaryNames.add(trait.traitName);
 }
 return {candidates,primary_fixed:old.slotType==='Primary Trait'&&primaryNames.size<=1,
   template_primary_candidate_count:primaryNames.size,
   tags,possible_tags:all,exclusions:[...new Set(exclusions)]};
}
function materialize(item,index,candidate,quality){
 const {api,state}=sdk();state.quality=Math.max(0,Math.min(.999,quality));
 const old=item.traits[index],spec={...clone(candidate.trait),slotType:old.slotType,traitCategoryName:candidate.category.name,priority:old.priority};
 const raw=api.rollLootEffectsForTrait(spec);
 if(old.masterworkBonusTier!==undefined)raw.masterworkBonusTier=old.masterworkBonusTier;
 if(old.mutationNames)raw.mutationNames=clone(old.mutationNames);
 const gear={...clone(item),traits:[raw]};state.trace=[];
 const trait=api.materializeItemTraits(gear)[0];
 const trace=clone(state.trace);const effects=api.lootEffectsToUE4JSON([trait],{tierIdentifier:item.tierIdentifier,rarityIdentifier:item.rarityIdentifier});
 return {trait:clone(trait),engine_effects:clone(effects),trace};
}
function originalCandidate(item,index){const old=item.traits[index],trait=data.trait.collection.find(t=>t.traitName===old.traitName),category=categoryFor(old);
 if(!trait||!category)throw new Error('Original trait definition unavailable');return {trait,category};}
function qualityEstimate(item,index){
 const old=item.traits[index],candidate=originalCandidate(item,index);
 if(old.conditionalLootEffects?.length)throw new Error('Conditional trait conversion needs separate evaluation');
 const probe=materialize(item,index,candidate,.5),params=old.lootEffects.flatMap(e=>e.params),estimates=[];
 if(params.length!==probe.trace.length)throw new Error('Parameter trace is incomplete');
 for(let i=0;i<params.length;i++){
  const observed=params[i].magnitude,[lo,hi]=probe.trace[i].range,d=probe.trace[i].decimals;
  if(Math.abs(hi-lo)<1e-12)continue;
  const half=.5/10**d,ends=[(observed-half-lo)/(hi-lo),(observed+half-lo)/(hi-lo)].sort((a,b)=>a-b);
  const lower=Math.max(0,ends[0]),upper=Math.min(.999,ends[1]);
  if(lower>upper+1e-8)throw new Error('Observed trait lies outside original scaling range');
  estimates.push({parameter:params[i].magnitudeName,lower,upper,midpoint:(lower+upper)/2});
 }
 const quality=estimates.length?estimates.reduce((s,x)=>s+x.midpoint,0)/estimates.length:.5;
 return {quality,estimated:true,parameters:estimates,reason:estimates.length?'Estimated from rounded source values':'Source has no varying parameter; defaults to middle quality'};
}
function ranges(item,index,candidate){
 const low=materialize(item,index,candidate,0),high=materialize(item,index,candidate,.999);
 const rows=[];let offset=0;
 for(let ei=0;ei<low.trait.lootEffects.length;ei++){
  const effect=low.trait.lootEffects[ei],top=high.trait.lootEffects[ei],spec=data.lootEffects.collection.find(e=>e.lootEffectName===effect.lootEffectName);
  for(let pi=0;pi<effect.params.length;pi++){
   const p=effect.params[pi],hp=top.params.find(x=>x.magnitudeName===p.magnitudeName),meta=spec.params.find(x=>x.magnitudeName===p.magnitudeName);
   rows.push({effect:effect.lootEffectName,parameter:p.magnitudeName,min:Math.min(p.magnitude,hp.magnitude),max:Math.max(p.magnitude,hp.magnitude),
    decimals:meta.magnitudeRoundedDecimals||0,multiplier:meta.displayMappingType==='percent'?100:1,
    unit:meta.displayMappingType==='percent'?'%':p.magnitudeName.includes('Seconds')||p.magnitudeName.includes('Duration')?'秒':'数值',
    varying:Math.abs(p.magnitude-hp.magnitude)>1e-12,unrounded:low.trace[offset++]});
  }
 }
 return rows;
}
module.exports={data,source,clone,expression,sdk,template,possibleTags,pools,categoryFor,materialize,qualityEstimate,ranges};
