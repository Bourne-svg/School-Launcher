"""Run the shipped content script against isolated synthetic login documents."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
rules=json.loads((ROOT/'extension/sites.json').read_text(encoding='utf-8'))
content=(ROOT/'extension/content.js').read_text(encoding='utf-8')
HTML={
 'polyu':'<input id="username"><input name="password" type="password"><div hidden><input id="jupasNo"><input name="password" type="password"></div>',
 'hku':'<input id="appNo" type="tel"><input id="email">',
 'cuhk':'<input id="txt_email"><input id="txt_pwd" type="password">',
 'hkust':'<input id="username"><input id="password" type="password">',
 'ntu':'<input id="EmailInput" type="email">',
 'netease':'<input name="email"><input name="password" type="password">',
 'diantou':'<input placeholder="账号"><input placeholder="密码" type="password">'
}
def scenario(browser,rule,html,expected='filled',delay=0):
    page=browser.new_page()
    origin=rule.get('frameOrigin',rule['origin'])
    path=rule.get('framePaths',rule['loginPaths'])[0]
    page.route('**/*',lambda route:route.fulfill(status=200,content_type='text/html; charset=utf-8',body='<html><body>'+('' if delay else html)+'<button type="submit">Login</button></body></html>'))
    page.goto(origin+path)
    fields={k:'synthetic-'+k for k in rule['fields']}
    page.evaluate('''({rule,fields})=>{window.requests=[];window.submits=0;document.addEventListener('submit',e=>{submits++;e.preventDefault()});document.querySelector('button').onclick=()=>submits++;window.chrome={runtime:{sendMessage:async m=>{requests.push(m);if(m.type==='probe')return {ok:true,rule,expires:Date.now()+8000};if(m.type==='credentials')return {ok:true,fields:{...fields}};return {ok:true};}}};}''',dict(rule=rule,fields=fields))
    if delay:
        page.evaluate('(html)=>setTimeout(()=>document.body.insertAdjacentHTML("afterbegin",html),500)',html)
    page.evaluate(content)
    page.wait_for_function('requests.some(r=>r.type==="result")',timeout=10000)
    code=page.evaluate('requests.find(r=>r.type==="result").code')
    assert code==expected,(rule['id'],code,expected)
    assert page.evaluate('submits')==0
    if expected=='filled':
        for key,selector in rule['fields'].items():
            assert page.locator(selector+':visible').input_value()==fields[key]
    if expected=='ambiguous':
        assert not page.evaluate('requests.some(r=>r.type==="credentials")')
    page.close()

with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    for rule in rules:
        scenario(browser,rule,HTML[rule['id']])
    hku=next(r for r in rules if r['id']=='hku')
    scenario(browser,hku,HTML['hku'],delay=500)
    scenario(browser,hku,'<input id="appNo" value="synthetic-account"><input id="email">')
    scenario(browser,hku,'<input id="appNo" value="already-typed"><input id="email">','conflict')
    scenario(browser,hku,'<input id="appNo"><input id="appNo"><input id="email">','ambiguous')
    scenario(browser,hku,'<input id="appNo" oninput="this.outerHTML=\'<input id=appNo>\'"><input id="email">','changed')
    browser.close()
print('PASS: 7 adapters; delayed render; conflict and ambiguity refusal; rerender detection; no login submissions.')
