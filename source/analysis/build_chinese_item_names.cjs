/* Extract the original UI's simplified-Chinese dictionary; no game writes. */
'use strict';
const fs=require('fs'),path=require('path'),vm=require('vm'),crypto=require('crypto'),assert=require('assert/strict');
const root=path.join(__dirname,'..'),sourcePath=path.join(__dirname,'extracted/main.c05310c4.chunk.js');
const bytes=fs.readFileSync(sourcePath),sha=crypto.createHash('sha256').update(bytes).digest('hex');
assert.equal(sha,'64664d49813494ae73886ff6d2154b4672cdd7c89867ddcc5569e68e38c729ae');
const source=bytes.toString('utf8');
function dictionaryAt(anchor){
 const position=source.indexOf(anchor);assert(position>=0,'Original localization anchor missing');
 const start=source.lastIndexOf('JSON.parse(',position)+'JSON.parse('.length;
 assert(start>=11&&["'",'"'].includes(source[start]));
 const quote=source[start];let escaped=false,end=-1;
 for(let i=start+1;i<source.length;i++){
  const c=source[i];if(escaped){escaped=false;continue;}if(c==='\\'){escaped=true;continue;}
  if(c===quote){end=i+1;break;}
 }
 assert(end>position&&source[end]===')');
 // Execute only one bounded, lexed string literal, never the webpack bundle.
 const json=vm.runInNewContext(source.slice(start,end),Object.create(null),{timeout:1000});
 return {dictionary:JSON.parse(json),source_offset:start};
}
const zh=dictionaryAt('"Weapon.Hammer.2H.Player.Harbinger.name":"\\u9707\\u9524"');
const en=dictionaryAt('"Weapon.Hammer.2H.Player.Harbinger.name":"The Gavel"');
assert.equal(zh.dictionary['Weapon.Hammer.2H.Player.Harbinger.name'],'震锤');
assert.equal(zh.dictionary['Weapon.DualBlades.1H.Player.Brimtide.name'],'布里米特的屠刀');
const names={};
const prefixes=['Weapon.','Ring.','Amulet.','Charm.','Augment.','Banner.','Consumable.','EnergyShield.','Rune.','Character.Player.'];
for(const [key,name] of Object.entries(zh.dictionary)){
 if(!key.endsWith('.name')||!prefixes.some(p=>key.startsWith(p)))continue;
 const tag=key.slice(0,-5);if(typeof name!=='string'||!name.trim())continue;
 names[tag]={name:name.trim(),english:en.dictionary[key]||'',source_key:key};
}
const output=path.join(root,'local_mod','chinese_item_names.json');
fs.writeFileSync(output,JSON.stringify({version:1,culture:'zh-CN',source_sha256:sha,
 source:'Original bundled UI simplified-Chinese dictionary',names},null,2)+'\n');
const data=JSON.parse(fs.readFileSync(path.join(__dirname,'extracted/source_data.json'))),labels={};
const primaryNames={
 'Trigger.NoModularTrigger.Payoff.NorthernTechDamage.Rank.4':'北斗技艺伤害',
 'Trigger.NoModularTrigger.Payoff.ForbiddenTechDamage.Rank.4':'南斗技艺伤害',
 'Trigger.NoModularTrigger.Payoff.ForbiddenTechDamageToFullHealth.Rank.5':'南斗技艺对满血敌人的伤害',
 'Trigger.NoModularTrigger.Payoff.WeaponDamageWhileAtFullHealth.Rank.5':'满血时武器伤害'
};
for(const t of data.trait.collection){
 const primary=t.traitName.startsWith('Trigger.');
 if(!t.traitName.endsWith('Secondary')&&!primary)continue;
 const description=zh.dictionary[t.traitName+'.description'];
 if(typeof description!=='string')continue;
 let label=description.replace(/^\s*[+\-]?\s*%\([^)]+\)[a-z]%%?\s*/,'').trim();
 if(primary){
  label=primaryNames[t.traitName]||description.replace(/%\([^)]+\)[a-z](?:%%)?/g,'…').replace(/<[^>]+>/g,'').trim();
  if(label.length>160)label=label.slice(0,157)+'…';
 }
 if((primary||label!==description.trim())&&!label.includes('%(')&&label&&label.length<=160)
  labels[t.traitName]={label,description,kind:primary?'primary':'secondary'};
}
fs.writeFileSync(path.join(root,'local_mod','chinese_trait_labels.json'),JSON.stringify({version:1,culture:'zh-CN',source_sha256:sha,labels},null,2)+'\n');
const englishLabels={};
for(const t of data.trait.collection){
 const description=en.dictionary[t.traitName+'.description'];if(typeof description!=='string')continue;
 const primary=t.traitName.startsWith('Trigger.');
 let label=description.replace(/^\s*[+\-]?\s*%\([^)]+\)[a-z]%%?\s*/,'').replace(/<[^>]+>/g,'').trim();
 if(primary)label=description.replace(/%\([^)]+\)[a-z](?:%%)?/g,'…').replace(/<[^>]+>/g,'').trim();
 if(label.length>160)label=label.slice(0,157)+'…';
 if(label&&!label.includes('%('))englishLabels[t.traitName]={label,description,kind:primary?'primary':t.traitName.endsWith('Masterwork')?'masterwork':'secondary'};
}
fs.writeFileSync(path.join(root,'local_mod','english_trait_labels.json'),JSON.stringify({version:1,culture:'en',source_sha256:sha,labels:englishLabels},null,2)+'\n');
const counts={};for(const tag of Object.keys(names)){const family=tag.split('.')[0];counts[family]=(counts[family]||0)+1;}
const report={output,source_sha256:sha,chinese_module_literal_offset:zh.source_offset,
 english_module_literal_offset:en.source_offset,total:Object.keys(names).length,counts,
 simple_trait_labels:Object.values(labels).filter(r=>r.kind==='secondary').length,
 primary_trait_labels:Object.values(labels).filter(r=>r.kind==='primary').length,
 samples:Object.fromEntries(['Weapon.Hammer.2H.Player.Harbinger','Weapon.DualBlades.1H.Player.Brimtide','Weapon.Sword.1H.Player.ArgentBlade','Weapon.Sword.1H.Player.Conquest'].map(t=>[t,names[t]]))};
fs.writeFileSync(path.join(__dirname,'chinese_item_names_audit.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report));
