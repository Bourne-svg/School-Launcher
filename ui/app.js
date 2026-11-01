'use strict';
const $ = s => document.querySelector(s);
let state = {entries:[],settings:{}}, filter = '全部', ready = false;
let toastTimer;
const fillTasks=new Map();
let polling=false;
const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icons = {copy:'<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></svg>'};
const abbreviations = {'香港理工大学':'理工','香港大学':'港大','香港中文大学':'中大','香港科技大学':'科大','香港城市大学':'城大','南洋理工大学':'南洋','新加坡国立大学':'国大','爱丁堡大学':'爱大','伦敦大学学院':'UCL','网易邮箱':'邮','点头-算力云':'云'};
const fieldsFor = e => e.kind === 'email' ? [['email','邮箱']] : e.kind === 'application' ? [['account','申请编号'],['email','邮箱']] : [['account','账号'],['password','密码']];
const incomplete = e => !e.url || fieldsFor(e).some(([key])=>!e[key]);
function toast(message){$('#toast').textContent=message;$('#toast').classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').classList.remove('show'),2600);}
async function call(method,...args){try{if(!window.pywebview?.api)throw Error();const result=await window.pywebview.api[method](...args);if(result && result.ok===false)toast(result.error||'操作未完成');return result;}catch{toast('连接暂时不可用，请关闭后重新打开应用');return {ok:false};}}
async function refresh(){const data=await call('get_state');if(!data?.ok){$('#error-panel').hidden=false;$('#error-message').textContent=data?.error||'无法连接本机应用';$('#restore-button').disabled=!data?.backup;$('#cards').replaceChildren();$('#add-button').disabled=true;$('#summary').textContent='本机资料需要恢复';return;}state=data;$('#error-panel').hidden=true;$('#add-button').disabled=false;render();}
function render(){
 $('#welcome').hidden=state.entries.length>0;
 const entries=state.entries, query=$('#search').value.toLocaleLowerCase().trim();
 $('#count-all').textContent=entries.length;$('#count-schools').textContent=entries.filter(e=>e.category==='院校').length;$('#count-tools').textContent=entries.filter(e=>e.category==='工具').length;$('#count-pending').textContent=entries.filter(incomplete).length;
 $('#page-title').textContent=filter==='全部'?'全部条目':filter==='院校'?'申请院校':filter==='工具'?'邮箱与工具':'待补充';
 $('#summary').textContent=`${entries.length} 个入口，${entries.filter(incomplete).length} 个待补充。需要的资料，都在手边。`;
 $('#hide-button').textContent=state.settings.hidden?'显示凭据':'隐藏凭据';$('#hide-button').setAttribute('aria-pressed',String(!!state.settings.hidden));
 const visible=entries.filter(e=>(filter==='全部'||(filter==='待补充'?incomplete(e):e.category===filter))&&(!query||[e.name,e.url,e.note].some(v=>v.toLocaleLowerCase().includes(query))));
 $('#cards').innerHTML=visible.map(e=>{
   const pending=incomplete(e),type=e.kind==='application'?'申请编号与邮箱':e.kind==='email'?'邮箱登录链接':'账号与密码';
   return `<article class="card" data-id="${esc(e.id)}" data-category="${esc(e.category)}"><div class="card-top"><div class="school-mark" aria-hidden="true">${esc(abbreviations[e.name]||e.name.slice(0,2))}</div><div class="school-info"><h2>${esc(e.name)}</h2><span class="type-label">${type}</span></div><button class="icon-button edit-button" data-action="edit" aria-label="编辑${esc(e.name)}" title="编辑条目">编辑</button></div><button class="url-button" data-action="open" ${!e.url?'disabled':''} title="${esc(e.url||'待补充网址')}"><span class="url-symbol">↗</span><span class="url-text">${esc(e.url||'待补充网址')}</span></button><div class="fields">${fieldsFor(e).map(([key,label])=>`<div class="field"><span class="field-label">${label}</span><span class="field-value ${!e[key]?'missing':''}">${e[key]?(state.settings.hidden?'••••••••':esc(e[key])):'待补充'}</span><button class="copy" data-action="copy" data-field="${key}" aria-label="复制${label}" title="复制${label}" ${!e[key]?'disabled':''}>${icons.copy}</button></div>`).join('')}</div>${e.note?`<p class="note">${esc(e.note)}</p>`:''}<div class="card-bottom"><span class="badge ${pending?'pending':''}">${pending?'待补充':'已就绪'}</span><div class="card-links"><button class="plain-open" data-action="open" ${!e.url?'disabled':''}>仅打开网站</button><button class="open-button" data-action="fill" ${!e.url?'disabled':''}>打开并填入 ↗</button></div></div><p class="fill-status" data-status="${esc(e.id)}" ${!fillTasks.has(e.id)?'hidden':''}>${esc(fillTasks.get(e.id)?.message||'')}</p></article>`;
 }).join('');$('#empty').hidden=visible.length>0||entries.length===0;$('#visible-count').textContent=`显示 ${visible.length} / ${entries.length}`;
}
function updateFields(){const form=$('#entry-form'),kind=form.elements.kind.value;$('#account-label').hidden=kind==='email';$('#account-label span').textContent=kind==='application'?'申请编号':'账号';$('#password-label').hidden=kind!=='password';$('#email-label').hidden=kind==='password';form.elements.email.disabled=kind==='password';form.elements.account.disabled=kind==='email';form.elements.password.disabled=kind!=='password';}
function edit(entry){if(!ready)return;const form=$('#entry-form');form.reset();['id','name','url','account','password','email','note'].forEach(k=>form.elements[k].value=entry?.[k]||'');form.elements.kind.value=entry?.kind||'password';form.elements.category.value=entry?.category||'院校';form.elements.password.type=state.settings.hidden?'password':'text';$('#editor-title').textContent=entry?'编辑条目':'新增条目';$('#delete-button').hidden=!entry;$('#form-error').textContent='';updateFields();$('#editor').showModal();}
function confirmAction(title,message,action){$('#confirm-title').textContent=title;$('#confirm-message').textContent=message;$('#confirm-yes').onclick=async()=>{$('#confirm').close();await action();};$('#confirm').showModal();}
document.querySelectorAll('[data-filter]').forEach(button=>button.onclick=()=>{filter=button.dataset.filter;document.querySelectorAll('[data-filter]').forEach(b=>b.classList.toggle('active',b===button));render();});
$('#search').addEventListener('input',render);
$('#cards').onclick=async event=>{const button=event.target.closest('[data-action]'),card=event.target.closest('[data-id]');if(!button||!card||button.disabled)return;const entry=state.entries.find(e=>e.id===card.dataset.id);if(button.dataset.action==='edit')edit(entry);else if(button.dataset.action==='open')await call('open_site',entry.id);else if(button.dataset.action==='fill'){button.disabled=true;const result=await call('start_autofill',entry.id);if(result?.ok){fillTasks.set(entry.id,{task:result.task,message:'等待浏览器连接',done:false});render();}else button.disabled=false;}else{const result=await call('copy_field',entry.id,button.dataset.field);if(result?.ok)toast('已复制，可前往网页粘贴');}};
$('#add-button').onclick=()=>edit();$('#hide-button').onclick=async()=>{if((await call('update_settings',{hidden:!state.settings.hidden}))?.ok)await refresh();};
document.querySelectorAll('.close-dialog').forEach(b=>b.onclick=()=>b.closest('dialog').close());$('#confirm-no').onclick=()=>$('#confirm').close();
$('#entry-form').elements.kind.addEventListener('change',updateFields);
$('#password-toggle').onclick=()=>{const field=$('#entry-form').elements.password;field.type=field.type==='password'?'text':'password';$('#password-toggle').setAttribute('aria-label',field.type==='password'?'显示编辑密码':'隐藏编辑密码');};
$('#entry-form').onsubmit=async event=>{event.preventDefault();const form=event.currentTarget;const entry=Object.fromEntries(new FormData(form));$('#save-button').disabled=true;try{const result=await call('save_entry',entry);if(result?.ok){$('#editor').close();await refresh();toast('条目已保存');}else $('#form-error').textContent=result?.error||'保存失败，请重试';}finally{$('#save-button').disabled=false;}};
$('#delete-button').onclick=()=>{const id=$('#entry-form').elements.id.value;confirmAction('删除这个条目？','删除后将从助手中移除，请确认是否删除。',async()=>{if((await call('delete_entry',id))?.ok){$('#editor').close();await refresh();toast('条目已删除');}});};
$('#settings-button').onclick=async()=>{await refresh();$('#startup-toggle').checked=!!state.settings.startup;$('#top-toggle').checked=!!state.settings.on_top;$('#settings').showModal();await updateConnection();};
for(const [selector,key] of [['#startup-toggle','startup'],['#top-toggle','on_top']]){$(selector).onchange=async event=>{const input=event.target;input.disabled=true;const result=await call('update_settings',{[key]:input.checked});if(!result?.ok)input.checked=!input.checked;await refresh();input.disabled=false;};}
$('#quit-button').onclick=()=>call('quit');
$('#restore-button').onclick=()=>confirmAction('恢复上一份备份？','恢复后将使用上次保存前的资料。当前损坏的文件会另外保留。',async()=>{if((await call('restore_backup'))?.ok){await refresh();toast('已恢复备份');}});
document.addEventListener('keydown',e=>{if(e.ctrlKey&&e.key.toLowerCase()==='k'){e.preventDefault();$('#search').focus();}});
async function initialize(){if(ready)return;ready=true;await refresh();}
window.addEventListener('pywebviewready',initialize);if(window.pywebview?.api)initialize();
setTimeout(()=>{if(!ready){$('#summary').textContent='正在连接本机应用，请稍候…';}},4000);

async function updateConnection(){
 const r=await call('get_connection_status');if(!r?.ok)return;
 $('#extension-status').textContent=r.error||(r.connected?'Chrome 已连接（本次验证成功）':'尚未验证连接；加载扩展后点击“验证连接”');
 $('#extension-path').value=r.extension_path;$('#chrome-profile').textContent='使用 Google Chrome · '+r.profile;
 $('#chrome-download').hidden=r.chrome_installed!==false;
 $('#integration-note').textContent=r.moved?'检测到程序目录变化，请重新加载此目录中的扩展并更新桌面快捷方式。':'';
 const profiles=r.profiles||[{id:r.profile,name:r.profile}];
 const select=$('#profile-select'), signature=JSON.stringify(profiles);
 if(select.dataset.profiles!==signature){select.innerHTML=profiles.map(p=>`<option value="${esc(p.id)}">${esc(p.name)} (${esc(p.id)})</option>`).join('');select.dataset.profiles=signature;}
 if(document.activeElement!==select)select.value=r.profile;
}
$('#profile-select').onchange=async e=>{const r=await call('update_settings',{chrome_profile:e.target.value});if(r.ok){toast('配置已保存，请重新验证连接');fillTasks.clear();await refresh();}await updateConnection();};
$('#welcome-add').onclick=()=>edit();
$('#welcome-extension').onclick=()=>$('#settings-button').click();
$('#chrome-download').onclick=()=>call('open_chrome_download');
$('#extension-folder').onclick=()=>call('open_extension_folder');
$('#extension-copy').onclick=async()=>{if((await call('copy_extension_path')).ok)toast('扩展目录已复制');};
$('#desktop-shortcut').onclick=async()=>{if((await call('create_desktop_shortcut')).ok)toast('桌面快捷方式已创建／更新');};
$('#cleanup-integration').onclick=()=>confirmAction('清理本机连接？','仅移除指向当前程序的浏览器注册与快捷方式，保留账号数据。清理后请退出应用并删除解压目录；再次运行会重新注册。',async()=>{if((await call('cleanup_integration')).ok){toast('连接已清理，账号数据已保留');await updateConnection();}});
$('#extension-setup').onclick=async()=>{const result=await call('copy_extension_page_url');$('#extension-setup-result').textContent=result?.ok?result.message:'请手动复制上方网址，粘贴到 Chrome 地址栏并回车。';};
$('#extension-check').onclick=async()=>{await call('check_extension');setTimeout(updateConnection,2000);};
$('#extension-path').onclick=e=>e.target.select();
setInterval(async()=>{if(!ready||polling)return;polling=true;try{for(const [id,item] of fillTasks){if(item.done)continue;const result=await call('get_fill_status',item.task);item.message=result.message||result.error||'连接中断，请重试';item.done=!result.ok||['filled','failed','expired'].includes(result.status);const element=document.querySelector('[data-status="'+CSS.escape(id)+'"]');if(element){element.hidden=false;element.textContent=item.message;}}if($('#settings').open)await updateConnection();}finally{polling=false;}},1500);
