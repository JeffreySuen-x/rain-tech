import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import readline from 'node:readline';
function completion(text,calls=[]){const blocks=[...(text?[{type:'text',text}]:[]),...calls];return {chunks:[...blocks.flatMap((b,index)=>[{type:'block-start',index,blockType:b.type},b.type==='text'?{type:'text-delta',index,text:b.text}:{type:'tool-call-delta',index,id:b.id,name:b.name,argumentsDelta:b.arguments},{type:'block-end',index,block:b}]),{type:'finish',reason:{kind:calls.length?'tool-calls':'stop'}}]};}
test('official DSH AgentLoop executes model, permitted tool, model, finish',async()=>{
 const proc=spawn(process.execPath,['src/worker.mjs'],{stdio:['pipe','pipe','pipe']});const lines=readline.createInterface({input:proc.stdout});let errors='';proc.stderr.on('data',v=>errors+=v);const trace=[];let model=0;let finished=false;
 const send=x=>proc.stdin.write(JSON.stringify(x)+'\n');
 send({turnId:'runtime-test',inputSnapshot:{prompt:'Read observations'},toolSchemas:[{name:'read_observations',description:'Read observations',parameters:{type:'object',properties:{},additionalProperties:false}}]});
 for await(const line of lines){const e=JSON.parse(line);trace.push(e.type==='callback'?e.kind:e.type);if(e.type==='finish'){finished=true;break;}assert.equal(e.type,'callback',line);if(e.kind==='model'){model++;if(model===2)assert.ok(e.request.messages.some(m=>m.role==='tool'));send({callId:e.callId,ok:true,result:model===1?completion('',[{type:'tool-call',id:'fixture-read',name:'read_observations',arguments:'{}'}]):completion('Observed fixture data')});}else{assert.equal(e.name,'read_observations');send({callId:e.callId,ok:true,result:{observations:[],source:'test'}});}}
 proc.stdin.end();await new Promise(resolve=>proc.on('close',resolve));assert.equal(proc.exitCode,0,errors);assert.ok(finished);assert.deepEqual(trace,['model','tool','model','finish']);
});
