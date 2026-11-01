'use strict';
async function check(){try{const r=await chrome.runtime.sendMessage({type:'hello'});document.querySelector('#message').textContent=r.ok?'已连接桌面助手':r.error;}catch{document.querySelector('#message').textContent='请先打开桌面助手。';}}
document.querySelector('#check').onclick=check;check();
