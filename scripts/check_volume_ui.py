"""Headless browser regression against an isolated DB, never the user's session."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
PORT=8017
BASE=f'http://127.0.0.1:{PORT}'


def serve():
    import app
    import uvicorn
    from services.identity import Identity
    salt='1'*32
    with app.store.connect() as db:
        db.execute("UPDATE local_users SET password_hash=?,salt=? WHERE username='manager.chau'",(Identity.password('volume-qa-password',salt),salt))
    # UI tests use deterministic local explanations; no external provider calls.
    app.assistant.request=lambda *args,**kwargs: (_ for _ in ()).throw(ValueError('QA offline'))
    uvicorn.run(app.app,host='127.0.0.1',port=PORT,log_level='error')


def main():
    from playwright.sync_api import sync_playwright,expect
    out=ROOT/'docs/qa';out.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='volume-browser-') as directory:
        env=dict(os.environ,SMARTFRESH_DB=str(Path(directory)/'qa.sqlite3'),SMARTFRESH_LEARNING_DIR=str(Path(directory)/'learning'),AI_PROVIDER='OpenAI',OPENAI_API_KEY='qa-unused',GEMINI_API_KEY='qa-unused')
        with (Path(directory)/'server.log').open('w',encoding='utf-8') as log:
            proc=subprocess.Popen([sys.executable,__file__,'--serve'],cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            try:
                for _ in range(100):
                    if proc.poll() is not None:raise RuntimeError((Path(directory)/'server.log').read_text())
                    try:
                        with urllib.request.urlopen(BASE+'/api/health',timeout=1) as response:
                            if json.load(response)['ok']:break
                    except Exception:time.sleep(.2)
                else:raise RuntimeError('QA server not ready')
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',headless=True)
                    context=browser.new_context(viewport={'width':1440,'height':1000})
                    response=context.request.post(BASE+'/api/auth/login',data={'username':'manager.chau','password':'volume-qa-password'})
                    assert response.ok,response.text()
                    response=context.request.post(BASE+'/api/sessions',data={'day':'2022-05-02','auto_run':False})
                    assert response.ok,response.text()
                    state=response.json()
                    page=context.new_page();errors=[]
                    page.on('pageerror',lambda e:errors.append(str(e)))
                    page.route('**/api/proposal-explanation/**',lambda route:route.fulfill(json={'answer':'Giải thích QA từ dữ liệu ca.','as_of_minute':state['minute'],'status':'ready','ai_status':'ready'}))
                    page.add_init_script("localStorage.setItem('smartfresh-session',"+json.dumps(state['id'])+");")
                    page.goto(BASE);expect(page.locator('#page-title')).to_have_text('Kế hoạch sản lượng')
                    expect(page.locator('[data-view="m2"]')).to_be_visible()
                    expect(page.locator('[data-view="m1"]')).to_be_hidden()
                    page.evaluate("currentView='m1';render()")
                    expect(page.locator('#page-title')).to_have_text('Kế hoạch sản lượng')
                    page.evaluate('newSession()')
                    expect(page.locator('#new-market')).to_have_count(0)
                    expect(page.locator('#new-mode option')).to_have_count(2)
                    page.evaluate("$('modal').close()")
                    page.screenshot(path=str(out/'joint-morning.png'),full_page=True)

                    def step(action,payload=None):
                        nonlocal state
                        response=context.request.post(BASE+'/api/sessions/'+state['id']+'/'+action,data={'revision':state['revision'],'payload':payload or {}})
                        assert response.ok,(action,response.text())
                        state=response.json();page.evaluate('s=>storeState(s)',state)

                    step('plan_approve');step('prepared');step('advance',{'target':1019})
                    expect(page.locator('[data-view="m1"]')).to_be_hidden()
                    step('advance',{'target':1020})
                    expect(page.locator('[data-view="m2"]')).to_be_hidden()
                    expect(page.locator('[data-view="m1"]')).to_be_visible()
                    expect(page.locator('#page-title')).to_have_text('Giảm giá cuối ngày')
                    step('advance',{'target':1170})
                    proposed=state.get('pending') or state['decisions'][-1]
                    changed=sum(r['discount']!=r['previous'] for r in proposed['rows'])
                    assert changed>0
                    expect(page.locator('.price-change')).to_have_count(changed)
                    expect(page.locator('#manual-price-section')).not_to_have_attribute('open','')
                    page.screenshot(path=str(out/'joint-evening.png'),full_page=True)
                    # Explicit manual panel even when AI holds every price.
                    if state['phase']=='running':
                        page.locator('#manual-price-section summary').click()
                        page.locator('[data-manual-pricing]').click()
                        expect(page.locator('#manual-price-section')).to_have_attribute('open','')
                        state=context.request.get(BASE+'/api/state?session_id='+state['id']).json()
                    else:
                        step('refresh_price',{'manual_edit':True})
                        page.locator('#manual-price-section summary').click()
                    sku=next(k for k,p in state['products'].items() if p['stock']>0)
                    page.locator('[data-discount="'+sku+'"]').select_option('20')
                    page.locator('[data-approve="price"]').click()
                    page.locator('#approval-reason').fill('QA: quản lý chỉnh riêng món đang giữ giá')
                    page.locator('#confirm-approval').click()
                    expect(page.locator('[data-act="price_apply"]')).to_be_visible()
                    expect(page.locator('.price-change')).to_have_count(1)
                    page.locator('[data-act="price_apply"]').click()
                    page.locator('#confirm-action').click()
                    page.wait_for_function("state.phase==='running'")
                    state=context.request.get(BASE+'/api/state?session_id='+state['id']).json()
                    assert state['products'][sku]['discount']==20
                    assert all(p['discount']==0 for k,p in state['products'].items() if k!=sku)
                    page.locator('#advanced-nav summary').click()
                    for view in ['registry','learning']:
                        page.locator('[data-view="'+view+'"]').click()
                        expect(page.locator('#view')).to_contain_text('M1/M2 JOINT · mô hình vận hành chính')
                    page.set_viewport_size({'width':390,'height':844})
                    page.evaluate("currentView='m1';render()")
                    page.screenshot(path=str(out/'joint-mobile.png'),full_page=True)
                    assert not errors,errors
                    result=dict(passed=True,browser='Edge headless',javascript_errors=errors,checks=['morning_tab_only','evening_tab_only_at_17','only_changed_price_cards','collapsed_manual_prices','manual_approval_then_apply_one_sku','registry_training_provenance','learning_view','mobile_render'])
                    (ROOT/'docs/JOINT_BROWSER_QA.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
                    print(json.dumps(result))
                    browser.close()
            finally:
                proc.terminate();proc.wait(timeout=15)


if __name__=='__main__':
    serve() if '--serve' in sys.argv else main()
