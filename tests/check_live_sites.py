"""Opt-in live login-form checks using synthetic values; never submit login."""
import json
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from autofill import Tasks
from store import validate

ROOT = Path(__file__).resolve().parents[1]
SITES = [
    ('HKU', 'https://sweb.hku.hk/tola/servlet/CreateUserScreen/loginForm'),
    ('GitHub', 'https://github.com/login'),
    ('PythonAnywhere', 'https://www.pythonanywhere.com/login/'),
]

def main():
    extension = Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'extension'
    content = (extension/'content.js').read_text(encoding='utf-8')
    results=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        for name,url in SITES:
            page=browser.new_page()
            blocked=[]
            page.route('**/*',lambda route: route.continue_() if route.request.method in ('GET','HEAD','OPTIONS') else (blocked.append(route.request.method),route.abort())[1])
            page.add_init_script("document.addEventListener('submit',e=>e.preventDefault(),true); HTMLFormElement.prototype.submit=function(){throw Error('Test forbids login submission')};")
            tasks=Tasks()
            entry=validate(dict(name=name,url=url,kind='password',account='schoollauncher-test@example.invalid',password='Synthetic-Test-Only-003!'))
            token=tasks.create(entry)
            base=dict(task=token,client='live-test-client-0003',tab=7)
            claim=tasks.dispatch(dict(op='claim',**base))
            rule=claim['rule']
            def bridge(message):
                if message['type']=='probe':
                    return dict(ok=True,rule=rule,expires=__import__('time').time()*1000+12000)
                if message['type']=='credentials':
                    return tasks.dispatch(dict(op='credentials',top=page.url,frame=page.url,frameId=0,**base))
                if message['type']=='result':
                    return tasks.dispatch(dict(op='result',code=message['code'],**base))
                return dict(ok=False)
            page.expose_function('testBridge',bridge)
            try:
                response=page.goto(url,wait_until='domcontentloaded',timeout=45000)
                assert response and response.ok, f'HTTP {response.status if response else "no response"}'
                page.evaluate("window.chrome={runtime:{sendMessage:m=>window.testBridge(m)}}")
                page.evaluate(content)
                page.wait_for_function("Array.from(document.querySelectorAll('input')).some(e=>e.value==='Synthetic-Test-Only-003!')",timeout=18000)
                page.wait_for_timeout(500)
                status=tasks.status(token)
                assert status['status']=='filled', status
                values=page.locator('input').evaluate_all('(es)=>es.map(e=>e.value)')
                assert entry['account'] in values and entry['password'] in values
                results.append(dict(site=name,url=url,final_url=page.url,status='PASS',http=response.status,blocked_non_read_requests=len(blocked)))
            except Exception as exc:
                results.append(dict(site=name,url=url,final_url=page.url,status='FAIL',error=str(exc).splitlines()[0]))
            finally:
                page.close()
        browser.close()
    print(json.dumps(results,ensure_ascii=False,indent=2))
    raise SystemExit(any(r['status']!='PASS' for r in results))

if __name__=='__main__':
    main()
