(() => {
 'use strict';
 if(globalThis.__schoolLauncherActive)return;
 globalThis.__schoolLauncherActive=true;
 const pause=ms=>new Promise(r=>setTimeout(r,ms));
 const visible=e=>e.isConnected&&!e.disabled&&!e.readOnly&&e.type!=='hidden'&&e.getClientRects().length>0&&getComputedStyle(e).visibility!=='hidden'&&getComputedStyle(e).display!=='none';
 const send=async msg=>{try{return await chrome.runtime.sendMessage(msg);}catch{return {ok:false,inactive:true};}};
 const notice=text=>{const box=document.createElement('div');box.textContent='申请书架 · '+text;Object.assign(box.style,{position:'fixed',right:'20px',top:'20px',zIndex:'2147483647',padding:'13px 18px',background:'#213b4c',color:'#fff',font:'13px Microsoft YaHei,sans-serif',borderRadius:'8px',boxShadow:'0 4px 20px #0003',maxWidth:'320px',lineHeight:'1.6'});document.documentElement.append(box);setTimeout(()=>box.remove(),6500);};
 function locate(rule){const found={};for(const [key,selector] of Object.entries(rule.fields)){const elements=[...document.querySelectorAll(selector)].filter(visible);if(elements.length>1)return {code:'ambiguous'};if(elements.length!==1)return {code:'waiting'};found[key]=elements[0];}return {elements:found};}
 function prepare(rule){
   if(rule.id==='hkust'&&!location.pathname.startsWith('/util/cgi-bin/login.cgi')){
     const links=[...document.querySelectorAll('a[href]')].filter(e=>visible(e)&&e.textContent.trim()==='Login to your application');
     if(links.length===1){const u=new URL(links[0].href);if(u.origin===rule.origin&&u.pathname.startsWith('/cgi-bin/')){links[0].click();return true;}}
   }
   if(rule.id==='diantou'&&!document.querySelector('input[placeholder="账号"]')){
     const controls=[...document.querySelectorAll('button,a,span,div')].filter(e=>visible(e)&&e.children.length===0&&e.textContent.trim()==='登录');
     if(controls.length===1){controls[0].click();return true;}
   }
   if(rule.id==='netease'&&location.origin===rule.origin){const buttons=[...document.querySelectorAll('a,button,span')].filter(e=>visible(e)&&e.textContent.trim()==='密码登录');if(buttons.length===1){buttons[0].click();return true;}}
   return false;
 }
 async function finish(code,text){await send({type:'result',code});if(text)notice(text);}
 async function run(){
   const probe=await send({type:'probe'});if(!probe?.ok)return;
   const rule=probe.rule;let navigated=false,lastProbe=Date.now();
   while(Date.now()<probe.expires){
     if(Date.now()-lastProbe>2000){const current=await send({type:'probe'});if(!current?.ok)return;lastProbe=Date.now();}
     if(!navigated)navigated=prepare(rule);
     if(rule.frameOrigin&&location.origin===rule.origin){await pause(400);continue;}
     const found=locate(rule);
     if(found.code==='ambiguous'){await finish('ambiguous','输入框匹配不唯一，未填入。');return;}
     if(found.elements){
       const reply=await send({type:'credentials'});
       if(!reply?.ok){if(reply?.error)notice(reply.error);return;}
       let fields=reply.fields;const again=locate(rule);
       if(!again.elements||Object.keys(found.elements).some(k=>found.elements[k]!==again.elements[k]||!visible(found.elements[k]))){fields=null;reply.fields=null;await finish('changed','表单已变化，请重新点击助手。');return;}
       if(Object.entries(found.elements).some(([k,e])=>e.value!==''&&e.value!==fields[k])){fields=null;reply.fields=null;await finish('conflict','网页已有不同内容，未覆盖。');return;}
       const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;
       const inserted=[];
       for(const [key,element] of Object.entries(found.elements)){
         if(!visible(element)||(element.value!==''&&element.value!==fields[key])){fields=null;reply.fields=null;await finish('changed','表单已变化，请检查并重新点击。');return;}
         if(element.value===''){setter.call(element,fields[key]);element.dispatchEvent(new Event('input',{bubbles:true}));element.dispatchEvent(new Event('change',{bubbles:true}));}
         inserted.push([element,fields[key]]);
       }
       await pause(200);
       const valid=inserted.every(([e,value])=>visible(e)&&e.value===value);
       inserted.length=0;fields=null;reply.fields=null;
       await finish(valid?'filled':'changed',valid?'已填入，请自行确认并点击登录。':'页面重新渲染，请检查后重试。');return;
     }
     await pause(350);
   }
   await finish('timeout','未找到登录表单，请打开登录区域后重试。');
 }
 run().catch(()=>finish('error','未能完成填入，请使用助手复制。'));
})();
