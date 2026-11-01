'use strict';
const HOST='cn.schoollauncher.autofill';
const rulesPromise=fetch(chrome.runtime.getURL('sites.json')).then(r=>r.json());
let serial=Promise.resolve();
async function native(message){try{return await chrome.runtime.sendNativeMessage(HOST,message);}catch{return {ok:false,error:'无法连接桌面助手，请打开助手并检查扩展安装。'};}}
async function clientId(){let {client}=await chrome.storage.local.get('client');if(!client){client=crypto.randomUUID();await chrome.storage.local.set({client});}return client;}
async function taskFor(tab){return (await chrome.storage.session.get('task-'+tab))['task-'+tab];}
function matches(url,origin,paths){try{const u=new URL(url);return u.origin===origin&&!u.username&&paths.some(p=>p==='/*'||u.pathname===p||(p.endsWith('/')&&p!=='/'&&u.pathname.startsWith(p)));}catch{return false;}}
async function report(tab,task,code){const result=await native({op:'result',task:task.token,client:task.client,tab,code});await chrome.storage.session.remove('task-'+tab);return result;}
async function handle(message,sender){
 if(sender.id!==chrome.runtime.id)return {ok:false};
 const ownPage=sender.url?.startsWith(chrome.runtime.getURL(''));
 if(message.type==='hello'&&ownPage)return native({op:'hello',check:message.check});
 if(message.type==='launch'&&ownPage&&sender.tab){
   const tab=sender.tab.id,client=await clientId(),token=message.task;
   if(!/^[A-Za-z0-9_-]{40,64}$/.test(token||''))return {ok:false,error:'无效任务，请从桌面助手打开。'};
   const prior=await taskFor(tab);if(prior)await report(tab,prior,'closed');
   const result=await native({op:'claim',task:token,client,tab});if(!result.ok)return result;
   const task={token,client,site:result.site,rule:result.rule,expires:Date.now()+120000};
   await chrome.storage.session.set({['task-'+tab]:task});
   await chrome.alarms.create('expire-'+tab,{when:task.expires});
   await chrome.tabs.update(tab,{url:result.url});return {ok:true};
 }
 if(!sender.tab)return {ok:false};
 const tab=sender.tab.id,task=await taskFor(tab);
 if(!task)return {ok:false,inactive:true};
 if(Date.now()>task.expires){await report(tab,task,'timeout');return {ok:false,inactive:true};}
 const rule=task.rule||(await rulesPromise).find(r=>r.id===task.site);
 const current=await chrome.tabs.get(tab);
 if(!rule||!matches(current.url,rule.origin,rule.paths)){await report(tab,task,'navigation');return {ok:false,inactive:true};}
 const frame=await chrome.webNavigation.getFrame({tabId:tab,frameId:sender.frameId});
 if(!frame||frame.url!==sender.url)return {ok:false,inactive:true};
 const eligibleFrame=sender.frameId===0 ? matches(frame.url,rule.origin,rule.paths) : rule.frameOrigin&&matches(frame.url,rule.frameOrigin,rule.framePaths);
 if(!eligibleFrame)return {ok:false,inactive:true};
 if(message.type==='probe')return {ok:true,rule,expires:task.expires};
 if(message.type==='result')return report(tab,task,message.code);
 if(message.type==='credentials'){
   if(task.claimed)return {ok:false,inactive:true};
   const loginFrame=rule.frameOrigin?matches(frame.url,rule.frameOrigin,rule.framePaths):sender.frameId===0;
   if(!matches(current.url,rule.origin,rule.loginPaths)||!loginFrame)return {ok:false,inactive:true};
   task.claimed=true;await chrome.storage.session.set({['task-'+tab]:task});
   const result=await native({op:'credentials',task:task.token,client:task.client,tab,top:current.url,frame:frame.url,frameId:sender.frameId});
   // Recheck navigation after the native round-trip, before returning any fields.
   const after=await chrome.webNavigation.getFrame({tabId:tab,frameId:sender.frameId});
   const afterTop=await chrome.tabs.get(tab);
   if(!after||after.documentId!==frame.documentId||after.url!==frame.url||afterTop.url!==current.url){await report(tab,task,'changed');return {ok:false,inactive:true};}
   return result;
 }
 return {ok:false};
}
chrome.runtime.onMessage.addListener((message,sender,respond)=>{
 // Serializing claims prevents two frames or duplicate messages consuming one task.
 serial=serial.catch(()=>{}).then(()=>handle(message,sender));
 serial.then(respond,()=>respond({ok:false,error:'浏览器连接中断，请从助手重新打开。'}));return true;
});
chrome.tabs.onRemoved.addListener(tab=>{serial=serial.catch(()=>{}).then(async()=>{const task=await taskFor(tab);if(task)await report(tab,task,'closed');});});
chrome.alarms.onAlarm.addListener(alarm=>{if(alarm.name.startsWith('expire-')){const tab=Number(alarm.name.slice(7));serial=serial.catch(()=>{}).then(async()=>{const task=await taskFor(tab);if(task)await report(tab,task,'timeout');});}});
chrome.runtime.onStartup.addListener(()=>{native({op:'hello'});});
chrome.runtime.onInstalled.addListener(()=>{native({op:'hello'});});
