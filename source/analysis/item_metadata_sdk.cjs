/* Original item-attribute scaling and exact inverse at the game's display precision. */
'use strict';
const assert=require('assert/strict'),vm=require('vm'),game=require('./game_trait_sdk.cjs');
const families={Augment:{collection:'augments',prefix:'AUG',attributes:[]},
 Ring:{collection:'rings',prefix:'RNG',attributes:[]},Amulet:{collection:'amulets',prefix:'AMT',attributes:[]},
 Charm:{collection:'charms',prefix:'CHA',attributes:[]},Weapon:{collection:'weapons',prefix:'WPN',attributes:['attackPower']},
 Banner:{collection:'banners',prefix:'BNR',attributes:['BannerOvershield']},
 Consumable:{collection:'consumables',prefix:'CNS',attributes:['ConsumableHealingPower']}};
function api(){
 const {api}=game.sdk();
 const lodash={find:(rows,p)=>rows.find(r=>Object.entries(p).every(([k,v])=>r[k]===v)),
  mapValues:(rows,fn)=>Object.fromEntries(Object.entries(rows).map(([k,v])=>[k,fn(v,k)]))};
 const context=vm.createContext({a:api,c:api,m:game.data,l:{default:lodash}});
 for(const name of ['getLootStatsStaticData','getWeaponLootAttributesStaticData','getConsumableLootAttributesStaticData','materializedAttributes'])
  api[name]=vm.runInContext('('+game.expression(name)+')',context);
 return api;
}
function sameKeys(a,b){return JSON.stringify(Object.keys(a).sort())===JSON.stringify(Object.keys(b).sort());}
function ranges(item){
 const a=api(),definition=game.template(item.gameplayTag);let result={};
 if(item.lootClassName==='Weapon')result=game.clone(a.getWeaponLootAttributesStaticData(item,definition));
 if(['Banner','Consumable'].includes(item.lootClassName))result=game.clone(a.getConsumableLootAttributesStaticData(item,definition));
 for(const pair of Object.values(result))assert(Array.isArray(pair)&&pair.length===2&&pair.every(Number.isFinite),'属性缩放范围不完整');
 return result;
}
function damageTypes(item){
 if(item.lootClassName!=='Weapon'){
  assert(!item.damageTypes||Object.keys(item.damageTypes).length===0,'该类型不应含独立伤害属性');return null;
 }
 const row=game.data.lootDamageTypes.collection.find(r=>(item.selectedTraitTags||[]).includes(r.traitTag));
 const expected=row?{[row.gameplayTag]:row.percentOfDamage}:{};
 assert.deepEqual(item.damageTypes,expected,'武器伤害类型与原始元素标签不一致');
 return game.clone(expected);
}
function amount(item){
 const expected=item.lootClassName==='Consumable'?Math.max(1,Math.round(game.data.globalParameters.potionBaseCharges*game.template(item.gameplayTag).chargesScalar)):1;
 assert(Number.isInteger(expected)&&expected>0&&expected<=1000000,'无法确定原始充能次数');
 if(item.lootClassName==='Consumable')assert.equal(item.amount,expected,'缺少完整充能数据，或当前充能数量不符合模板');
 else assert(item.amount===undefined||item.amount===1,'该物品数量不符合原始模板');
 return expected;
}
function materialize(item,raw){
 const r=ranges(item);
 assert(raw&&typeof raw==='object'&&!Array.isArray(raw)&&sameKeys(raw,r),'随机属性字段不完整');
 for(const q of Object.values(raw))assert(Number.isFinite(q)&&q>=0&&q<=.999,'随机属性档次超出正常范围');
 return game.clone(api().materializedAttributes(raw,{lootAttributes:r}));
}
function reconstruct(item){
 const family=families[item.lootClassName];assert(family,'未知物品类型');
 const r=ranges(item),observed=item.lootAttributes||{};
 assert(typeof observed==='object'&&!Array.isArray(observed)&&sameKeys(observed,r),'缺少完整的攻击力、回复量或护盾属性，请读取新版完整记录');
 assert.deepEqual(Object.keys(r).sort(),family.attributes.slice().sort(),'该模板的独立属性尚未适配');
 const raw={},details=[];
 for(const [key,[lo,hi]] of Object.entries(r)){
  const value=observed[key];assert(Number.isFinite(value),'独立属性数值无效');let quality=.5;
  if(Math.abs(hi-lo)>1e-12){
   const ends=[(value-.005-lo)/(hi-lo),(value+.005-lo)/(hi-lo)].sort((a,b)=>a-b);
   const lower=Math.max(0,ends[0]),upper=Math.min(.999,ends[1]);
   assert(lower<=upper,'独立属性超出原游戏范围');quality=(lower+upper)/2;
  }
  raw[key]=quality;details.push({key,value,range:[lo,hi],quality});
 }
 assert.deepEqual(materialize(item,raw),observed,'独立属性没有精确还原');
 return {raw,observed:game.clone(observed),damageTypes:damageTypes(item),amount:amount(item),details};
}
module.exports={families,ranges,materialize,reconstruct,damageTypes,amount};
