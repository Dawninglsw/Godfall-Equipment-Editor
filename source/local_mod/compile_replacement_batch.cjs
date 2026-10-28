/* Multiple independent reviewed single-item replacements; native loot hooks unchanged. */
'use strict';
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),crypto=require('crypto');
const single=require('./compile_replacement_copy.cjs'),{normalizeTrait}=require('../analysis/reconstruct_owned_augment.cjs');
const MAX_ITEMS=8;
function stable(v){if(Array.isArray(v))return v.map(stable);if(!v||typeof v!=='object')return v;
 return Object.fromEntries(Object.keys(v).sort().map(k=>[k,stable(v[k])]));}
function compile(previews){
 assert(Array.isArray(previews)&&previews.length>=1&&previews.length<=MAX_ITEMS,'批量方案需包含1至8件装备');
 const configs=previews.map(single.compile),sources=new Set(),targets=new Set();
 for(const c of configs){
  assert(c.sourceId.length<=256,'原件编号长度异常，未制作批量方案');
  assert(!sources.has(c.sourceId),'每件原件只能加入一份批量修改');sources.add(c.sourceId);
  const key=JSON.stringify(stable({tag:c.gameplayTag,family:c.lootClassName,tier:c.tierIdentifier,rarity:c.rarityIdentifier,
   rank:c.masterworkUpgradeRank,mutations:c.mutationNames,tags:c.selectedTraitTags,attributes:c.sourceLootAttributes,
   damage:c.damageTypes,amount:c.amount,traits:c.expectedTraits.map(normalizeTrait)}));
  assert(!targets.has(key),'本批次含完全相同的目标同款，请只保留一份');targets.add(key);
 }
 const batchId=crypto.createHash('sha256').update(configs.map(c=>c.trialId).sort().join('|')).digest('hex').slice(0,24);
 return {version:1,batchId,configs,maxItems:MAX_ITEMS};
}
function runtime(config){
 const child=fs.readFileSync(path.join(__dirname,'replacement_copy_runtime.js'),'utf8').replace('__GODFALL_REPLACEMENT_COPY_CONFIG__','__config');
 return fs.readFileSync(path.join(__dirname,'replacement_batch_runtime.js'),'utf8')
  .replace('__GODFALL_REPLACEMENT_BATCH_CONFIG__',JSON.stringify(config)).replace('__SINGLE_ITEM_RUNTIME__',()=>child);
}
module.exports={compile,runtime,patch:single.patch,integrationPoints:single.integrationPoints,MAX_ITEMS};
