/* One selected unused item; each native awakening is verified before the next layer. */
(function(g){
 'use strict';
 var config=__GODFALL_UNCURSE_CONFIG__,getStore=null,getUpdate=null,getRefresh=null,getAwaken=null,store=null;
 var started=false,finished=false,timer=null,deadline=0,waitTicks=0,progressReadBack=false;
 var step=0,total=config.totalLayers,stageSource=config.source;
 var trace={godfallUncurseTrial:1,startedAt:Date.now(),sequence:0,status:'waiting_for_inventory',
  planId:config.planId,sourceId:config.source.id,beforeProgress:config.beforeProgress,
  requestedProgress:config.targetProgress,remainingCurses:total,completedLayers:0,totalLayers:total};
 function clone(x){return JSON.parse(JSON.stringify(x));}
 function stable(x){if(typeof x==='number')return Math.round(x*1e9)/1e9;
  if(Array.isArray(x))return x.map(stable);if(!x||typeof x!=='object')return x;
  var r={};Object.keys(x).sort().forEach(function(k){if(x[k]!==undefined)r[k]=stable(x[k]);});return r;}
 function same(a,b){return JSON.stringify(stable(a))===JSON.stringify(stable(b));}
 function values(x){return x&&typeof x==='object'?Object.keys(x).map(function(k){return x[k];}):[];}
 function count(i){return (i.mutationNames||[]).filter(function(m){return m==='Mutation.Item.Cursed';}).length;}
 function publish(status,item){trace.status=status;trace.sequence++;if(item)trace.remainingCurses=count(item);
  trace.completedLayers=step;g.__GodfallUncurseTrace=JSON.stringify(trace);}
 function find(state){var p=state&&state.player,inv=p&&p.inventory;
  if(!inv||!inv.gear||!p.loadout||!p.loadout.selectedValorplateId||!values(inv.valorplates).length)return null;
  var rows=values(inv.gear[config.collection]).filter(function(i){return i&&i.id===config.source.id;});
  return rows.length===1?rows[0]:null;}
 function fingerprint(i){var r={};config.sourceKeys.forEach(function(k){if(i[k]!==undefined)r[k]=i[k];});return r;}
 function equipped(state){return values(state.player.inventory.valorplates).some(function(p){
  return values(p.presets).some(function(preset){return Object.keys(preset||{}).some(function(family){
   return values(preset[family]).some(function(i){return i&&i.id===config.source.id;});});});});}
 function validState(i,spec){
  if(!i||!spec||!config.preservedKeys.every(function(k){return same(i[k],config.source[k]);})||
   count(i)!==spec.remainingCurses||!same(i.mutationNames||[],spec.mutationNames)||
   !Array.isArray(i.traits)||i.traits.length!==spec.traits.length)return false;
  if(spec.objective){
   if(!Array.isArray(i.objectives)||i.objectives.length!==1)return false;
   var objective=i.objectives[0],n=objective.progressNumerator,d=objective.progressDenominator;
   if(objective.traitName!==spec.objective.traitName||objective.objectiveId!==spec.objective.objectiveId||
    typeof n!=='number'||!isFinite(n)||typeof d!=='number'||!isFinite(d)||n<0||n>d||d<spec.objective.min||d>spec.objective.max)return false;
  }else if((i.objectives||[]).length)return false;
  return spec.traits.every(function(t,n){var a=i.traits[n];
   if(!a||a.traitName!==t.traitName||a.traitCategoryName!==t.traitCategoryName||a.slotType!==t.slotType||
    (a.masterworkBonusTier||0)!==(t.masterworkBonusTier||0)||(a.priority===undefined?null:a.priority)!==t.priority||
    !same(a.mutationNames||[],t.mutationNames||[])||!same(a.conditionalLootEffects||[],[])||
    !Array.isArray(a.lootEffects)||a.lootEffects.length!==t.effects.length)return false;
   return t.effects.every(function(e,j){var ae=a.lootEffects[j];return ae&&ae.lootEffectName===e.name&&ae.gameplayTag===e.tag&&
    Array.isArray(ae.params)&&ae.params.length===e.params.length&&e.params.every(function(p){var ap=ae.params.find(function(x){return x&&x.magnitudeName===p.name;});
     return ap&&typeof ap.magnitude==='number'&&isFinite(ap.magnitude)&&ap.magnitude>=p.min-1e-8&&ap.magnitude<=p.max+1e-8;});});
  });
 }
 function stop(status,item){finished=true;if(timer!==null){g.clearInterval(timer);timer=null;}publish(status,item);}
 function requestRefresh(afterAwaken){if(finished)return;deadline=Date.now()+45000;progressReadBack=false;
  publish(afterAwaken?'waiting_for_awaken_refresh':'waiting_for_refresh');
  try{store.dispatch({type:getRefresh()});}catch(_){stop('refresh_dispatch_failed');}}
 function readyToAwaken(i){
  if(!validState(i,config.states[step])||i.objectives[0].progressNumerator!==trace.requestedProgress)return false;
  var f=clone(fingerprint(i));f.objectives[0].progressNumerator=stageSource.objectives[0].progressNumerator;
  return same(f,stageSource);
 }
 function requestAwaken(){
  if(finished||trace.status==='awakening_requested')return;
  var state=store.getState(),item=find(state);
  if(!readyToAwaken(item)){stop('source_changed_before_awaken',item);return;}
  if(equipped(state)){stop('equipped_source_not_supported',item);return;}
  deadline=Date.now()+45000;publish('awakening_requested',item);
  try{store.dispatch({type:getAwaken(),payload:{gear:clone(item)}});}catch(_){stop('awaken_dispatch_failed',item);}
 }
 function beginStage(){
  if(finished)return;
  var state=store.getState(),item=find(state);
  if(!item||!same(fingerprint(item),stageSource)){stop('source_changed_before_next_layer',item);return;}
  if(equipped(state)){stop('equipped_source_not_supported',item);return;}
  var objective=stageSource.objectives[0];trace.beforeProgress=objective.progressNumerator;trace.requestedProgress=objective.progressDenominator;
  deadline=Date.now()+45000;progressReadBack=false;
  if(objective.progressNumerator===objective.progressDenominator){requestAwaken();return;}
  publish('request_started',item);
  try{store.dispatch({type:getUpdate(),payload:{id:config.source.id+'|0',progressNumerator:trace.requestedProgress}});}catch(_){stop('operation_failed',item);}
 }
 function tick(){if(finished)return;var state,item;
  try{store=getStore&&getStore();if(!store||typeof store.getState!=='function'||typeof store.dispatch!=='function'){
    if(++waitTicks>=180)stop('inventory_timeout');return;}
   state=store.getState();item=find(state);
   if(!started){
    if(!item){if(++waitTicks>=180)stop('source_missing');return;}
    if(validState(item,config.states[total])){step=total;stop('already_cleansed_verified',item);return;}
    if(!same(fingerprint(item),config.source)){stop('source_changed',item);return;}
    if(equipped(state)){stop('equipped_source_not_supported',item);return;}
    var storage=g.localStorage,key='godfall.uncurse-trial.'+config.planId;
    if(!storage||typeof storage.getItem!=='function'||typeof storage.setItem!=='function'){stop('storage_failed');return;}
    if(storage.getItem(key)){stop('already_requested_previous_run',item);return;}
    var marker=JSON.stringify({sourceId:config.source.id,planId:config.planId});storage.setItem(key,marker);
    if(storage.getItem(key)!==marker){stop('storage_failed');return;}
    started=true;beginStage();return;
   }
   if(trace.status==='waiting_for_refresh'||trace.status==='waiting_for_awaken_refresh'){
    if(Date.now()>deadline)stop(progressReadBack?'progress_saved_curse_still_present':'refresh_timeout',item);
   }else if(Date.now()>deadline)stop('request_ack_timeout',item);
  }catch(_){stop('operation_failed');}
 }
 function ack(id,index,progress,success){
  if(!started||finished||trace.status!=='request_started'||id!==config.source.id||String(index)!=='0'||progress!==trace.requestedProgress)return;
  if(!success){stop('original_request_failed');return;}
  publish('original_request_acknowledged');g.setTimeout(function(){requestRefresh(false);},250);
 }
 function awakenAck(id,success){
  if(!started||finished||trace.status!=='awakening_requested'||id!==config.source.id)return;
  if(!success){stop('original_awaken_request_failed');return;}
  publish('original_awaken_request_acknowledged');g.setTimeout(function(){requestRefresh(true);},250);
 }
 function readback(response){
  if(!started||finished||['waiting_for_refresh','waiting_for_awaken_refresh'].indexOf(trace.status)<0||!response||!Array.isArray(response.gear)||response.gear.length>10000)return;
  var rows=response.gear.filter(function(i){return i&&i.id===config.source.id;});if(rows.length!==1)return;
  var item=rows[0],remaining=count(item),expected=total-step;
  if(remaining<expected-1){stop('unexpected_layer_state',item);return;}
  if(remaining===expected-1){
   if(!validState(item,config.states[step+1])){stop('unexpected_layer_state',item);return;}
   if(equipped(store.getState())){stop('equipped_source_not_supported',item);return;}
   step++;stageSource=clone(fingerprint(item));
   if(step===total){stop('cleansed_after_refresh_verified',item);return;}
   trace.beforeProgress=item.objectives[0].progressNumerator;trace.requestedProgress=item.objectives[0].progressDenominator;
   deadline=Date.now()+45000;publish('next_layer_pending',item);g.setTimeout(beginStage,250);return;
  }
  if(!validState(item,config.states[step]))return;
  progressReadBack=item.objectives[0].progressNumerator===trace.requestedProgress;
  if(trace.status==='waiting_for_refresh'&&config.autoAwaken&&readyToAwaken(item)){
   publish('awaken_pending',item);g.setTimeout(requestAwaken,250);
  }
 }
 function bind(s,u,r,a){if(getStore)return;getStore=s;getUpdate=u;getRefresh=r;getAwaken=a;timer=g.setInterval(tick,500);}
 function safeReadback(response){try{readback(response);}catch(_){stop('operation_failed');}}
 g.__GodfallUncurseTrial={version:3,bind:bind,ack:ack,awakenAck:awakenAck,readback:safeReadback};publish('waiting_for_inventory');
})(window);
