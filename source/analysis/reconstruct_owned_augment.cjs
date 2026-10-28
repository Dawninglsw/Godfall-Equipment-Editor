/* Offline reconstruction preview. Placeholder IDs must never be submitted. */
'use strict';
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const game=require('./game_trait_sdk.cjs'),{factory}=require('./offline_equipment_factory.cjs');
const {augmentProfile}=require('./ground_augment_rules.cjs');
function normalizeTrait(t){
 return {name:t.traitName,category:t.traitCategoryName,slot:t.slotType,bonus:t.masterworkBonusTier||0,
  mutations:t.mutationNames||[],conditional:t.conditionalLootEffects||[],
  effects:(t.lootEffects||[]).map(e=>({name:e.lootEffectName,tag:e.gameplayTag,
   params:e.params.map(p=>({name:p.magnitudeName,value:p.magnitude})).sort((a,b)=>a.name.localeCompare(b.name))}))};
}
function equal(a,b){return JSON.stringify(a)===JSON.stringify(b);}
function rawTrait(item,index,desired){
 assert(!(desired.conditionalLootEffects||[]).length,'Conditional reconstruction deferred');
 const spec=game.data.trait.collection.find(t=>t.traitName===desired.traitName);assert(spec,'Unknown trait');
 const category=game.categoryFor(desired);assert(category,'Unknown category');
 const probe=game.materialize(item,index,{trait:spec,category},.5),{api}=game.sdk();
 const raw=game.clone(api.rollLootEffectsForTrait({...game.clone(spec),slotType:desired.slotType,traitCategoryName:desired.traitCategoryName}));
 if(desired.mutationNames)raw.mutationNames=game.clone(desired.mutationNames);
 if(desired.masterworkBonusTier!==undefined)raw.masterworkBonusTier=desired.masterworkBonusTier;
 const target=desired.lootEffects.flatMap(e=>e.params),params=raw.lootEffects.flatMap(e=>e.params);
 assert.equal(target.length,probe.trace.length);assert.equal(params.length,target.length);
 const quality=[];
 for(let i=0;i<params.length;i++){
  assert.equal(params[i].magnitudeName,target[i].magnitudeName);
  const value=target[i].magnitude,{range:[lo,hi],decimals}=probe.trace[i];let q=.5;
  if(Math.abs(hi-lo)>1e-12){
   const half=.5/10**decimals,bounds=[(value-half-lo)/(hi-lo),(value+half-lo)/(hi-lo)].sort((a,b)=>a-b);
   const min=Math.max(0,bounds[0]),max=Math.min(.999,bounds[1]);assert(min<=max,'Value outside native range');q=(min+max)/2;
  }
  params[i].magnitude=q;quality.push({parameter:params[i].magnitudeName,observed:value,quality:q});
 }
 const checked=game.clone(api.materializeItemTraits({...game.clone(item),traits:[raw]})[0]);
 assert(equal(normalizeTrait(checked),normalizeTrait(desired)),'Reconstruction did not round-trip exactly');
 return {raw,checked,quality};
}
function reconstruct(source,index,targetTrait){
 assert.equal(source.lootClassName,'Augment');assert.equal(source.masterworkUpgradeRank||0,0,'First trial uses unupgraded gear');
 assert.equal((source.mutationNames||[]).length,0,'First trial uses an ordinary augment');
 assert(!source.traits.some(t=>t.slotType==='Trait.Objective'));
 const raw=factory().generate(source.gameplayTag,source.tierIdentifier,source.rarityIdentifier);
 raw.id='AUG-'+source.gameplayTag+'.OFFLINE_RECONSTRUCTION_PREVIEW_ONLY';
 raw.selectedTraitTags=game.clone(source.selectedTraitTags);raw.masterworkUpgradeRank=0;
 const expected=game.clone(source);expected.traits[index]=game.clone(targetTrait);
 const rows=expected.traits.map((t,n)=>rawTrait(expected,n,t));raw.traits=rows.map(r=>r.raw);
 const materialized={...game.clone(raw),traits:game.clone(game.sdk().api.materializeItemTraits(raw))};
 assert(equal(materialized.traits.map(normalizeTrait),expected.traits.map(normalizeTrait)));
 assert.deepEqual(augmentProfile(materialized),augmentProfile(source));
 return {status:'offline_preview_only_no_game_or_account_write',source_id:source.id,raw_preview:raw,
  expected_materialized:materialized,source_materialized:game.clone(source),
  raw_traits:raw.traits,expected_traits:materialized.traits,quality_reconstruction:rows.map(r=>r.quality),
  profile:augmentProfile(source),checks:{all_traits_roundtrip_exactly:true,color_and_cost_preserved:true,
   new_identifier_required:true,original_item_preserved:true},
  limits:['Placeholder ID is deliberately unusable in the game; a real trial must obtain a fresh ID from the original game factory.',
   'Whole-item reconstruction and pickup persistence have not been tested in the game.']};
}
if(require.main===module){
 if(!process.argv[2]||!process.argv[3])throw new Error('Usage: node reconstruct_owned_augment.cjs input.json output.json');
 const proposal=JSON.parse(fs.readFileSync(process.argv[2]));
 const result=reconstruct(proposal.item,proposal.sourceIndex,proposal.targetTrait);
 const out=path.resolve(process.argv[3]);
 fs.writeFileSync(out,JSON.stringify(result,null,2));console.log(JSON.stringify({offline_roundtrip:result.checks,
  primary:result.expected_traits[0].lootEffects,attribute:result.expected_traits[1].lootEffects,
  secondary:result.expected_traits[2].lootEffects,profile:result.profile,game_writes:0}));
}
module.exports={reconstruct,normalizeTrait,rawTrait};
