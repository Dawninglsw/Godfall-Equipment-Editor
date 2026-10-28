/* Compile an exact-source allowlist, not a global loot or mutation multiplier. */
'use strict';
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const game=require('../analysis/game_trait_sdk.cjs');
function compile(multiplier=2,enabled=true){
 assert([2,3,5].includes(multiplier),'Unsupported primal chance multiplier');
 assert.equal(typeof enabled,'boolean');
 const categories=game.data.lootCategory.collection;
 const rows=game.data.lootQuantity.collection.filter(row=>{
  if(!row.groupName.startsWith('Chest - ToT -')||!Number.isFinite(row.chance)||row.chance<=0||row.chance>1)return false;
  const pool=categories.filter(c=>c.groupName===row.lootCategoryGroupName&&c.weight>0);
  return pool.length>0&&pool.every(c=>c.type==='Gear'&&(c.lootMutationWhitelistTags||[]).includes('Mutation.Item.Primal'));
 });
 assert(rows.length>0);
 assert.equal(new Set(rows.map(r=>r.name)).size,rows.length,'Ambiguous primal opportunity names');
 const groups=new Set(rows.map(r=>r.groupName));
 const chestTags=[...new Set(game.data.gameplayEvents.collection.filter(e=>(e.lootQuantityGroups||[]).some(g=>groups.has(g))).map(e=>e.gameplayTag).filter(Boolean))];
 return {version:1,enabled,multiplier,scope:'Original dedicated primal rewards in Chest - ToT - groups; chance capped at 1',
  rows:game.clone(rows),chestTags};
}
function runtime(config){
 return fs.readFileSync(path.join(__dirname,'primal_drop_runtime.js'),'utf8').replace('__GODFALL_PRIMAL_DROP_CONFIG__',JSON.stringify(config));
}
function patch(source){
 const quantity='a.getValidLootQuantityGroupsByGroupName='+game.expression('getValidLootQuantityGroupsByGroupName');
 const event='a.rollLootItemsForEvent='+game.expression('rollLootItemsForEvent');
 for(const anchor of [quantity,event])assert.equal(source.split(anchor).length-1,1,'Missing or ambiguous drop integration point');
 const quantityNew='a.getValidLootQuantityGroupsByGroupName=function(e){var r=a.SOURCE_DATA.lootQuantity;return window.__GodfallPrimalDropRateMod.quantityRows(e,l.default.filter(r.collection,{groupName:e}))}';
 const eventNew='a.__GodfallOriginalRollLootItemsForEvent='+game.expression('rollLootItemsForEvent')+
  ';a.rollLootItemsForEvent=function(e){return window.__GodfallPrimalDropRateMod.runEvent(e,function(){return a.__GodfallOriginalRollLootItemsForEvent(e)})}';
 return source.replace(quantity,quantityNew).replace(event,eventNew);
}
if(require.main===module){
 const [multiplier='2',destination]=process.argv.slice(2);assert(destination,'Output folder required');
 fs.mkdirSync(destination,{recursive:true});const config=compile(Number(multiplier));
 fs.writeFileSync(path.join(destination,'primal_drop_config.json'),JSON.stringify(config,null,2)+'\n');
 fs.writeFileSync(path.join(destination,'primal_drop_configured.js'),runtime(config));
 console.log(JSON.stringify({rows:config.rows.length,groups:new Set(config.rows.map(r=>r.groupName)).size,multiplier:config.multiplier}));
}
module.exports={compile,runtime,patch};
