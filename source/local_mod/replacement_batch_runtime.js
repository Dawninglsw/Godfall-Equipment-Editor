/* Independent child guards retain their single-item storage keys across workflows. */
(function(g){
 'use strict';
 var config=__GODFALL_REPLACEMENT_BATCH_CONFIG__,children=[],blocked=[];
 var trace={godfallReplacementBatch:1,startedAt:Date.now(),sequence:0,batchId:config.batchId,
  items:config.configs.map(function(c){return {trialId:c.trialId,sourceId:c.sourceId,status:'waiting',generatedId:'',eventTag:''};})};
 function publish(){trace.sequence++;g.__GodfallReplacementBatchTrace=JSON.stringify(trace);}
 function create(__config,index){
  var local={};Object.defineProperty(local,'localStorage',{get:function(){return g.localStorage;}});
  Object.defineProperty(local,'__GodfallReplacementCopyTrace',{set:function(value){
   var item=JSON.parse(value);trace.items[index].status=item.status;
   trace.items[index].generatedId=item.generatedId;trace.items[index].eventTag=item.eventTag;publish();
  }});
  (function(window){
   __SINGLE_ITEM_RUNTIME__
  })(local);
  return local.__GodfallReplacementCopyTrial;
 }
 config.configs.forEach(function(c,index){children.push(create(c,index));});
 function run(event,original,state,generate,eligiblePlayers){
  var result=original;
  children.forEach(function(child,index){
   if(blocked[index])return;
   try{
    var next=child.run(event,result,state,generate,eligiblePlayers);
    if(next!==result&&(!Array.isArray(next)||!Array.isArray(result)||next.length!==result.length+1||
     !result.every(function(item,n){return next[n]===item;})))throw new Error('child_result_rejected');
    result=next;
   }catch(_){blocked[index]=true;trace.items[index].status='batch_child_error';publish();}
  });
  return result;
 }
 g.__GodfallReplacementCopyTrial={version:1,run:run};
 g.__GodfallReplacementBatch={version:1,run:run};publish();
})(window);
