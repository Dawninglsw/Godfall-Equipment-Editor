/* Confirmed random-primary templates from original loot definitions. */
'use strict';
const game=require('./game_trait_sdk.cjs');
const CONFIRMED=new Set([
 'Weapon.Sword.1H.Player.HinterclawPrime','Weapon.Sword.1H.Player.Conquest',
 'Weapon.Polearm.2H.Player.Destiny','Weapon.Polearm.2H.Player.Constellation',
 'Weapon.Sword.2H.Player.Scarab','Weapon.Sword.2H.Player.Writhe',
 'Weapon.Hammer.2H.Player.Hinterclaw','Weapon.Hammer.2H.Player.Monarch',
 'Weapon.DualBlades.1H.Player.Flameberge','Weapon.DualBlades.1H.Player.Silverthorn','Amulet.16'
]);
function dropPool(raw,index,materialized){
 const source=raw.traits[index],pool=game.pools(materialized,index),primary=source.slotType==='Primary Trait';
 let policy={allowed:true,reason_code:'allowed',reason:''},candidates=pool.candidates;
 if(primary){
  if(raw.lootClassName==='Augment')policy={allowed:false,reason_code:'augment_primary_pending',reason:'强化物主词条及节点联动首版只读，当前仅开放兼容副词条'};
  else if(['Charm','Banner','Consumable'].includes(raw.lootClassName))policy={allowed:false,reason_code:'new_family_primary_pending',reason:'此类型首版只开放兼容副词条，主词条当前只读'};
  else if(pool.primary_fixed)policy={allowed:false,reason_code:'fixed_primary',reason:'这件装备的主词条类型固定，不开放替换'};
  else if(!CONFIRMED.has(raw.gameplayTag))policy={allowed:false,reason_code:'unconfirmed_primary_template',reason:'该装备的随机主词条模板尚未确认，暂不开放'};
  else if(!Array.isArray(raw.selectedTraitTags)||!raw.selectedTraitTags.length)
   policy={allowed:false,reason_code:'missing_selected_tags',reason:'缺少这件掉落的完整元素与类型标记，请重新读取'};
  const tags=new Set(raw.selectedTraitTags||[]);
  candidates=candidates.filter(c=>(c.category.allowedTraitTags||[]).some(tag=>tags.has(tag)));
 }
 return {...pool,candidates,primary,policy};
}
module.exports={dropPool,CONFIRMED};
