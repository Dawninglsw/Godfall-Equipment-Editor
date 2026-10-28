/* Offline curse research only. The production compiler deliberately rejects this format. */
'use strict';
const assert=require('assert/strict'),game=require('./game_trait_sdk.cjs');
const core=require('./reconstruct_owned_augment.cjs'),metadata=require('./item_metadata_sdk.cjs');
const {factory}=require('./offline_equipment_factory.cjs');
const CURSED='Mutation.Item.Cursed',AWAKENED='Mutation.Item.Awakened';
const normalize=t=>({...core.normalizeTrait(t),priority:t.priority===undefined?null:t.priority});
function generator(source){
 return factory({rollProgressDenominator:o=>{
  const observed=(source.objectives||[]).find(x=>x.objectiveId===o.id);
  if(observed)return observed.progressDenominator;
  const range=o.progressDenominator;assert(Number.isFinite(range?.min)&&Number.isFinite(range?.max));
  // Only a deterministic offline choice for future objectives; no real progress is changed.
  return range.min;
 }});
}
function check(source,index){
 const family=metadata.families[source.lootClassName];assert(family,'Unsupported family');
 assert.equal(source.masterworkUpgradeRank||0,0,'Upgraded cursed states are a separate study');
 assert(typeof source.id==='string'&&source.id.startsWith(family.prefix+'-'+source.gameplayTag+'.'));
 assert(Array.isArray(source.selectedTraitTags));
 const mutations=source.mutationNames;assert(Array.isArray(mutations)&&mutations.includes(CURSED));
 assert(mutations.every(m=>[CURSED,AWAKENED].includes(m)),'Mixed variants excluded');
 const layers=mutations.filter(m=>m===CURSED).length;
 assert(layers>=1&&layers<=3&&mutations.filter(m=>m===AWAKENED).length<=1);
 assert(Array.isArray(source.traits)&&source.traits.length<=20);
 assert(source.traits[index]?.slotType==='Secondary Trait','Only a secondary is studied');
 assert(source.traits.every(t=>['Primary Trait','Primary Attribute','Secondary Trait','Trait.Objective'].includes(t.slotType)
  &&!(t.conditionalLootEffects||[]).length&&!(t.masterworkBonusTier||0)),'Conditional, upgraded or other slots excluded');
 const linked=source.traits.filter(t=>game.data.trait.collection.find(s=>s.traitName===t.traitName)?.objectiveId);
 assert.equal(linked.length,layers,'Curse layers and objective slots must agree');
 assert(Array.isArray(source.objectives)&&source.objectives.length===1,'Complete observed objective progress is required');
 const objective=source.objectives[0],spec=game.data.trait.collection.find(t=>t.traitName===linked[0].traitName);
 const definition=game.data.objectives.collection.find(o=>o.id===spec.objectiveId);
 assert.equal(objective.traitName,linked[0].traitName);assert.equal(objective.objectiveId,spec.objectiveId);
 assert(Number.isFinite(objective.progressNumerator)&&objective.progressNumerator>=0
  &&Number.isFinite(objective.progressDenominator)&&objective.progressDenominator>0
  &&objective.progressNumerator<=objective.progressDenominator,'Objective counter invalid or already beyond target');
 assert(objective.progressDenominator>=definition.progressDenominator.min&&objective.progressDenominator<=definition.progressDenominator.max);
 const tagged=generator(source).mutate({...game.clone(source),traits:source.traits.map(t=>({...game.clone(t),mutationNames:[]}))});
 assert.deepEqual(tagged.traits.map(t=>t.mutationNames||[]),source.traits.map(t=>t.mutationNames||[]),'Trait mutation layout must match the native mutator');
 return {family,layers,attributes:metadata.reconstruct(source)};
}
function reconstructRaw(source){
 const {family,attributes}=check(source,source.traits.findIndex(t=>t.slotType==='Secondary Trait'));
 const raw=generator(source).generate(source.gameplayTag,source.tierIdentifier,source.rarityIdentifier,source.mutationNames);
 raw.id=family.prefix+'-'+source.gameplayTag+'.OFFLINE_CURSE_RESEARCH_NEVER_SUBMIT';
 raw.masterworkUpgradeRank=0;raw.selectedTraitTags=game.clone(source.selectedTraitTags);
 raw.lootAttributes=game.clone(attributes.raw);raw.damageTypes=game.clone(attributes.damageTypes);raw.amount=attributes.amount;
 raw.traits=source.traits.map((t,n)=>{
  const row=core.rawTrait(source,n,t).raw;
  if(t.priority!==undefined)row.priority=t.priority;
  return row;
 });
 raw.objectives=game.clone(source.objectives);
 assert.deepEqual(game.clone(game.sdk().api.materializeItemTraits(raw)).map(normalize),source.traits.map(normalize));
 return raw;
}
function materialized(raw){return {...game.clone(raw),traits:game.clone(game.sdk().api.materializeItemTraits(raw)),
 lootAttributes:metadata.materialize(raw,raw.lootAttributes)};}
function reconstruct(source,index,targetTraitName,targetCategoryName,quality){
 const before=game.clone(source),{family,layers}=check(source,index);
 const candidate=game.pools(source,index).candidates.find(c=>c.trait.traitName===targetTraitName&&c.category.name===targetCategoryName);
 assert(candidate&&candidate.trait.traitName!==source.traits[index].traitName,'Target must be a different native pool option');
 assert(!(candidate.trait.conditionalLootEffects||[]).length&&candidate.trait.namedLootEffects?.length);
 const estimate=game.qualityEstimate(source,index),q=quality===undefined?estimate.quality:quality;
 assert(Number.isFinite(q)&&q>=0&&q<=.999);
 const target=game.materialize(source,index,candidate,q).trait;
 if(source.traits[index].priority!==undefined)target.priority=source.traits[index].priority;
 const expected=game.clone(source);expected.traits[index]=target;
 const originalRaw=reconstructRaw(source),raw=reconstructRaw(expected);
 raw.id=family.prefix+'-'+source.gameplayTag+'.OFFLINE_CURSE_REPLACEMENT_NEVER_SUBMIT';
 const result=materialized(raw);
 assert.deepEqual(result.traits.map(normalize),expected.traits.map(normalize));
 assert.deepEqual(result.objectives,source.objectives);
 const tagged=generator(source).mutate({...game.clone(raw),traits:raw.traits.map(t=>({...game.clone(t),mutationNames:[]}))});
 assert.deepEqual(tagged.traits.map(t=>t.mutationNames||[]),raw.traits.map(t=>t.mutationNames||[]));
 const targetOrdinal=source.traits.slice(0,index).filter(t=>t.slotType!=='Trait.Objective').length;
 let control=game.clone(originalRaw),changed=game.clone(raw);const steps=[];
 for(let step=0;step<=layers;step++){
  const cm=materialized(control),nm=materialized(changed);
  const ct=cm.traits.filter(t=>t.slotType!=='Trait.Objective'),nt=nm.traits.filter(t=>t.slotType!=='Trait.Objective');
  assert.equal(ct.length,nt.length);
  assert.deepEqual(cm.mutationNames,nm.mutationNames);assert.deepEqual(cm.objectives,nm.objectives);
  ct.forEach((t,n)=>{if(n!==targetOrdinal)assert.deepEqual(normalize(t),normalize(nt[n]));});
  steps.push({removed_layers:step,remaining_curses:nm.mutationNames.filter(m=>m===CURSED).length,
   objectives:game.clone(nm.objectives),target_trait:game.clone(nt[targetOrdinal]),other_traits_match_reconstructed_control:true});
  if(step<layers){
   // Synthetic completion is confined to offline objects to exercise the original transform helper.
   for(const item of [control,changed])item.objectives[0].progressNumerator=item.objectives[0].progressDenominator;
   control=generator(source).transform(control,CURSED);changed=generator(source).transform(changed,CURSED);
  }
 }
 assert.equal(changed.mutationNames.filter(m=>m===CURSED).length,0);assert.equal(changed.objectives.length,0);
 assert.deepEqual(source,before);
 return {status:'offline_cursed_research_preview_not_deployable',source_id:source.id,index,
  source_materialized:before,raw_preview:raw,expected_materialized:result,raw_traits:raw.traits,expected_traits:result.traits,
  target_trait_name:targetTraitName,target_category_name:targetCategoryName,quality_estimate:estimate,quality:q,
  cursed_ranges:game.ranges(source,index,candidate),native_unwind_replay:steps,
  checks:{all_current_traits_exact:true,priority_and_array_order_preserved:true,curse_layers_and_native_flags_preserved:true,
   observed_objective_progress_preserved:true,native_unwind_matches_reconstructed_control:true,
   source_unchanged:true,offline_ids_only:true},
  limits:['Research-only format; production compilation, deployment and cursed-copy save acceptance are not enabled or tested.',
   'Replay of the original transform helper does not prove live completion or server validation.',
   'Qualities are inferred from rounded values. Future uncursing values of unchanged traits are compared to an inferred reconstruction, not the unknown original raw rolls.',
   'Future objective denominator selection is deterministic only for offline comparison; normal gameplay rules remain authoritative.']};
}
module.exports={check,reconstruct,reconstructRaw,normalize,CURSED,AWAKENED};
