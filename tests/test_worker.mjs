import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
const rules=JSON.parse(fs.readFileSync('extension/sites.json','utf8'));
const code=fs.readFileSync('extension/worker.js','utf8');
const extension='chrome-extension://test-extension/';
const session={},local={},nativeCalls=[];
let claimRule=null;
let handler,tabUrl='about:blank',frameUrl='',documentId='one',redirectOnRead=false;
const event=()=>({addListener:()=>{}});
const storage=obj=>({get:async key=>({[key]:structuredClone(obj[key])}),set:async data=>Object.assign(obj,structuredClone(data)),remove:async key=>{delete obj[key];}});
const chrome={
 runtime:{id:'test-extension',getURL:path=>extension+path,onMessage:{addListener:f=>{handler=f;}},onStartup:event(),onInstalled:event(),
 sendNativeMessage:async(host,m)=>{nativeCalls.push(structuredClone(m));if(m.op==='claim')return {ok:true,url:claimRule?claimRule.origin+'/start':'https://tpgadmission.engg.hku.hk/',site:claimRule?.id||'hku',rule:claimRule};if(m.op==='credentials'){if(redirectOnRead){documentId='two';frameUrl='https://evil.example/';}return {ok:true,fields:{account:'test-only',email:'test@example.edu'}};}return {ok:true};}},
 storage:{local:storage(local),session:storage(session)},
 tabs:{get:async()=>({url:tabUrl}),update:async(tab,data)=>{tabUrl=data.url;frameUrl=data.url;},onRemoved:event()},
 webNavigation:{getFrame:async()=>({url:frameUrl,documentId})},
 alarms:{create:async()=>{},onAlarm:event()}
};
function boot(){vm.runInNewContext(code,{chrome,fetch:async()=>({json:async()=>rules}),URL,crypto:webcrypto,Date,console});}
async function message(msg,sender){return new Promise(resolve=>handler(msg,{id:chrome.runtime.id,...sender},resolve));}
async function launch(tab=1){return message({type:'launch',task:'a'.repeat(43)},{url:extension+'launch.html',tab:{id:tab},frameId:0});}
const sender=()=>({url:frameUrl,tab:{id:1},frameId:0});
boot();
assert.equal((await message({type:'hello',check:'verification-nonce'},{url:extension+'launch.html'})).ok,true);
assert.equal(nativeCalls.at(-1).check,'verification-nonce');
assert.equal((await launch()).ok,true);
assert.equal((await message({type:'probe'},sender())).rule.id,'hku');
// Foreign tabs cannot receive a task, even on the same login page.
assert.equal((await message({type:'credentials'},{...sender(),tab:{id:2}})).ok,false);
const concurrent=await Promise.all([message({type:'credentials'},sender()),message({type:'credentials'},sender())]);
assert.equal(concurrent.filter(r=>r.ok).length,1);
assert.equal(nativeCalls.filter(r=>r.op==='credentials').length,1);
await message({type:'result',code:'filled'},sender());
assert.equal(Object.keys(session).length,0);
// Restored service worker can resume metadata, but never persisted credentials.
await launch();boot();
assert.equal((await message({type:'hello',check:'verification-nonce'},{url:extension+'launch.html'})).ok,true);
assert.equal(nativeCalls.at(-1).check,'verification-nonce');
assert.equal((await message({type:'probe'},sender())).ok,true);
assert.ok(!JSON.stringify(session).includes('test@example.edu'));
// A document change during the native request drops the response.
redirectOnRead=true;
assert.equal((await message({type:'credentials'},sender())).ok,false);
assert.equal(Object.keys(session).length,0);
redirectOnRead=false;await launch();tabUrl='https://evil.example/';
assert.equal((await message({type:'credentials'},sender())).ok,false);
assert.equal(Object.keys(session).length,0);
assert.equal((await message({type:'launch',task:'a'.repeat(43)},{id:'foreign',url:extension+'launch.html',tab:{id:1}})).ok,false);
console.log('PASS: worker tab binding, concurrent claim, restart metadata, redirect race, origin rejection, no stored fields.');

// Generic rule metadata survives worker restarts and allows same-origin login navigation.
claimRule={id:'generic',generic:true,origin:'https://custom.example',paths:['/*'],loginPaths:['/*'],kind:'password',fields:{account:'',password:''}};
await launch();boot();
tabUrl=frameUrl=claimRule.origin+'/login';
assert.equal((await message({type:'probe'},sender())).rule.generic,true);
assert.equal((await message({type:'credentials'},sender())).ok,true);
await message({type:'result',code:'filled'},sender());
await launch();tabUrl=frameUrl='https://other.example/login';
assert.equal((await message({type:'credentials'},sender())).ok,false);
assert.equal(Object.keys(session).length,0);
console.log('PASS: generic custom-origin rules, same-origin navigation, worker restart and cross-origin refusal.');
