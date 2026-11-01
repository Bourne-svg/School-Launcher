"""Headless UI acceptance using synthetic credentials only."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts'
OUT.mkdir(exist_ok=True)
names = ['网易邮箱','香港理工大学','香港大学','香港中文大学','香港科技大学','香港城市大学','点头-算力云','南洋理工大学','新加坡国立大学','爱丁堡大学','伦敦大学学院']
entries = []
for i, name in enumerate(names):
    pending = i in (5,8,9,10)
    entries.append(dict(id=str(i),autofill_supported=not pending,name=name,category='工具' if i in (0,6) else '院校',kind='application' if i==2 else 'email' if i==7 else 'password',url='' if pending else 'https://example.edu/admission',account='' if pending else 'demo@example.edu',password='' if pending else 'Preview-Only-2027!',email='demo@example.edu' if i in (2,7) else '',note='输入邮箱后，前往邮箱打开系统发送的登录链接。' if i==7 else ''))
script = '''window.testState = DATA;
window.calls=[];
window.pywebview={api:{
get_state:async()=>structuredClone(window.testState),
update_settings:async c=>{Object.assign(window.testState.settings,c);return {ok:true}},
copy_field:async(...a)=>{calls.push(['copy',...a]);return {ok:true}},
start_autofill:async(...a)=>{calls.push(['fill',...a]);return {ok:true,task:'test-task'}},
get_fill_status:async()=>({ok:true,status:'filled',message:'已填入，请确认登录'}),
get_connection_status:async()=>({ok:true,connected:false,profile:testState.settings.chrome_profile||'Default',profiles:[{id:'Default',name:'默认'},{id:'Profile 2',name:'工作'}],chrome_installed:false,extension_path:'C:/test/extension'}),
open_extension_setup:async()=>{calls.push(['setup']);return {ok:true}},
check_extension:async()=>{calls.push(['check']);return {ok:true}},
copy_extension_path:async()=>{calls.push(['path']);return {ok:true}},
create_desktop_shortcut:async()=>{calls.push(['shortcut']);return {ok:true}},
open_site:async(...a)=>{calls.push(['open',...a]);return {ok:true}},
save_entry:async e=>{e.id=e.id||'new';const i=testState.entries.findIndex(x=>x.id===e.id);if(i<0)testState.entries.push(e);else testState.entries[i]=e;return {ok:true}},
delete_entry:async id=>{testState.entries=testState.entries.filter(e=>e.id!==id);return {ok:true}},
quit:async()=>({ok:true})}};'''.replace('DATA',json.dumps(dict(ok=True,entries=entries,settings=dict(hidden=False,on_top=False,startup=True)),ensure_ascii=False))

with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge',headless=True)
    page = browser.new_page(viewport=dict(width=1180,height=800),device_scale_factor=1)
    errors=[]
    page.on('pageerror',lambda error: errors.append(str(error)))
    page.add_init_script(script)
    page.goto((ROOT/'ui'/'index.html').as_uri())
    page.wait_for_selector('.card')
    assert page.locator('.card').count()==11
    assert page.locator('.badge.pending').count()==4
    page.screenshot(path=str(OUT/'preview.png'))
    page.screenshot(path=str(OUT/'preview-wide.png'),full_page=True)
    page.locator('[data-id="1"] .copy').first.click()
    assert page.evaluate('calls.at(-1)[0]')=='copy'
    page.locator('[data-id="1"] .plain-open').click()
    assert page.evaluate('calls.at(-1)[0]')=='open'
    page.locator('[data-id="1"] .open-button').click()
    assert page.evaluate('calls.at(-1)[0]')=='fill'
    page.wait_for_function("""document.querySelector('[data-status="1"]').textContent.includes('已填入')""")
    page.locator('#hide-button').click()
    page.wait_for_function('document.querySelector(".field-value").textContent==="••••••••"')
    assert 'Preview-Only' not in page.locator('#cards').inner_text()
    page.locator('#search').fill('南洋')
    assert page.locator('.card').count()==1
    assert page.locator('.field').count()==1
    page.locator('#search').fill('')
    page.locator('[data-filter="待补充"]').click()
    assert page.locator('.card').count()==4
    assert page.locator('.open-button:disabled').count()==4
    page.locator('[data-filter="全部"]').click()
    page.locator('[data-id="2"] .edit-button').click()
    assert page.locator('#account-label span').inner_text()=='申请编号'
    assert page.locator('#password-label').is_hidden()
    assert page.locator('#email-label').is_visible()
    page.locator('#editor .close-dialog').first.click()
    page.locator('#add-button').click()
    page.locator('[name="name"]').fill('测试新增')
    page.locator('[name="url"]').fill('https://example.edu')
    page.locator('#save-button').click()
    page.wait_for_function('document.querySelectorAll(".card").length===12')
    page.locator('[data-id="new"] .edit-button').click()
    page.locator('#delete-button').click()
    page.locator('#confirm-no').click()
    assert page.locator('#editor').is_visible()
    page.locator('#delete-button').click()
    page.locator('#confirm-yes').click()
    page.wait_for_function('document.querySelectorAll(".card").length===11')
    # Long credentials and literal HTML text must remain readable without injection.
    page.evaluate('testState.entries[0].account="long".repeat(50);testState.entries[0].note="<img src=x onerror=alert(1)>"')
    page.locator('#hide-button').click()
    page.wait_for_function('document.querySelector(".field-value").textContent.startsWith("long")')
    assert page.locator('#cards img').count()==0
    for width,height in [(640,600),(790,600),(1180,800),(1536,864)]:
        page.set_viewport_size(dict(width=width,height=height))
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert page.locator('.field-value').first.evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
        page.screenshot(path=str(OUT/f'layout-{width}.png'),full_page=True)
    page.set_viewport_size(dict(width=1180,height=800))
    page.locator('#settings-button').click()
    page.screenshot(path=str(OUT/'settings.png'))
    page.locator('#top-toggle').check()
    assert page.evaluate('testState.settings.on_top')
    assert not errors,errors
    for scale in (1.25,1.5):
        context=browser.new_context(viewport=dict(width=round(1180/scale),height=round(800/scale)),device_scale_factor=scale)
        context.add_init_script(script)
        scaled=context.new_page()
        scaled.goto((ROOT/'ui'/'index.html').as_uri())
        scaled.wait_for_selector('.card')
        assert scaled.evaluate('document.documentElement.scrollWidth<=innerWidth')
        scaled.screenshot(path=str(OUT/f'scale-{scale}.png'))
        context.close()
    blank=browser.new_context(viewport=dict(width=1180,height=800))
    blank.add_init_script(script + "testState.entries=[];testState.settings={};")
    first=blank.new_page()
    first.goto((ROOT/'ui'/'index.html').as_uri())
    first.wait_for_selector('#welcome')
    assert first.locator('.card').count()==0
    first.screenshot(path=str(OUT/'welcome.png'))
    first.locator('#welcome-add').click()
    first.locator('[name="name"]').fill('我的申请入口')
    first.locator('[name="url"]').fill('https://example.edu/login')
    first.locator('[name="account"]').fill('fictional-user')
    first.locator('[name="password"]').fill('fictional-password')
    first.locator('#save-button').click()
    first.wait_for_selector('.card')
    assert first.locator('#welcome').is_hidden()
    assert first.locator('.open-button').inner_text().startswith('打开并填入')
    first.locator('.open-button').click()
    assert first.evaluate('calls.at(-1)[0]')=='fill'
    first.locator('#settings-button').click()
    assert not first.locator('#startup-toggle').is_checked()
    assert first.locator('#chrome-download').is_visible()
    first.locator('#profile-select').select_option('Profile 2')
    first.wait_for_function("testState.settings.chrome_profile==='Profile 2'")
    first.locator('#extension-copy').click()
    assert first.evaluate('calls.at(-1)[0]')=='path'
    first.locator('#extension-check').click()
    assert first.evaluate('calls.at(-1)[0]')=='check'
    assert '本次验证成功' not in first.locator('#extension-status').inner_text()
    first.locator('#desktop-shortcut').click()
    assert first.evaluate('calls.at(-1)[0]')=='shortcut'
    blank.close()
    browser.close()
print('UI PASS: rendering, 4 placeholders, copy/open routing, privacy, search/filter, special fields, CRUD/confirmation, XSS text, 4 viewport widths, settings; no JS errors.')
