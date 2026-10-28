/* Deterministic original-game loot generation for offline validation only. */
'use strict';
const vm=require('vm'),game=require('./game_trait_sdk.cjs');
const values=x=>Array.isArray(x)?x:Object.values(x||{});
const matches=(row,p)=>typeof p==='function'?p(row):typeof p==='string'?row[p]:Object.entries(p).every(([k,v])=>row[k]===v);
function factory(options={}){
 const {api,state}=game.sdk();state.quality=.5;
 // The exported UI module calls the original potion table "consumables".
 api.SOURCE_DATA={...game.data,consumables:game.data.potions};
 const lodash={cloneDeep:game.clone,clone:x=>Array.isArray(x)?x.slice():{...x},
  find:(r,p)=>values(r).find(x=>matches(x,p)),filter:(r,p)=>values(r).filter(x=>matches(x,p)),
  map:(r,p)=>values(r).map(typeof p==='string'?x=>x[p]:p),forEach:(r,fn)=>values(r).forEach(fn),
  reduce:(r,fn,init)=>values(r).reduce(fn,init),isEmpty:x=>!x||Object.keys(x).length===0,isUndefined:x=>x===undefined,
  includes:(r,x)=>values(r).includes(x),startsWith:(s,p)=>String(s).startsWith(p),sumBy:(r,k)=>values(r).reduce((n,x)=>n+x[k],0),
  uniqBy:(r,k)=>r.filter((x,i)=>r.findIndex(y=>y[k]===x[k])===i),
  sortBy:(r,fn)=>r.slice().sort((a,b)=>fn(a)-fn(b)),take:(r,n=1)=>r.slice(0,n),
  findIndex:(r,p)=>r.findIndex(x=>matches(x,p)),times:(n,fn)=>Array.from({length:n},(_,i)=>fn(i))};
 lodash.pullAt=(rows,index)=>rows.splice(index,1);
 const classes=['Amulet','Augment','Consumable','Currency','Powerup','VolatileDreamstone','Ring','Charm','Banner','Weapon','EnergyShield','Rune'];
 const math=Object.create(Math);math.random=()=>.4;let ordinal=0;
 const context=vm.createContext({a:api,l:{default:lodash},f:{ELootClassName:Object.fromEntries(classes.map(x=>[x,x]))},
  m:{default:()=>`OFFLINE_NEVER_SUBMIT_${++ordinal}`},S:{Weapon:'WPN',Ring:'RNG',Amulet:'AMT',Augment:'AUG',Charm:'CHA',Banner:'BNR',Consumable:'CNS'},b:{next:()=>.4},Math:math,
  t:x=>Array.from(x||[]),i:rows=>{const iterator=rows[Symbol.iterator]();return{s(){},n:()=>iterator.next(),e(e){throw e;},f(){}};},
  p:{rollProgressDenominator:options.rollProgressDenominator||function(){throw new Error('Objectives require a separate offline fixture');}}});
 for(const name of ['prefixForLootClassName','lootClassNameForGameplayTag','staticDataCollectionForGearClass',
  'staticDataForGearGameplayTag','generateGearId','generateLootForGameplayTag','identifyLoot','rollWeaponStats',
  'isPotion','rollConsumableStats','rollConsumableCharges',
  'selectTraitTagsFromTraitGroups','selectTraitTagGroup','sampleItemByWeight','getTraitSlotsForGear',
  'rollTraitsForGear','rollTraitForSlot','getObjectivesForGear','mutateGear','transformMutation','rollDamageTypeForWeapon'])
  api[name]=vm.runInContext('('+game.expression(name)+')',context);
 return {generate:(tag,tier=50,rarity=5,mutations=[])=>game.clone(api.generateLootForGameplayTag(tag,tier,rarity,1,false,mutations)),
  mutate:item=>game.clone(api.mutateGear(game.clone(item))),
  transform:(item,mutation)=>game.clone(api.transformMutation(game.clone(item),mutation)),
  setQuality:q=>{if(!Number.isFinite(q)||q<0||q>.999)throw Error('Offline quality outside native range');state.quality=q;}};
}
module.exports={factory};
