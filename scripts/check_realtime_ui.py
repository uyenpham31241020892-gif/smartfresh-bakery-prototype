"""Run an isolated complete day, including backend-only clock movement and next-day linkage."""
from pathlib import Path
import json,os,socket,subprocess,sys,tempfile,time
import httpx
from playwright.sync_api import sync_playwright


def main():
    root=Path(__file__).resolve().parents[1];qa=root/'runtime/qa';qa.mkdir(parents=True,exist_ok=True)
    directory=Path(tempfile.mkdtemp(prefix='day-loop-',dir=qa))
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    env=os.environ.copy();env.update(PORT=str(port),SMARTFRESH_DB=str(directory/'app.sqlite3'),SMARTFRESH_LEARNING_DIR=str(directory/'models'))
    log=(directory/'server.log').open('wb')
    server=subprocess.Popen([sys.executable,'app.py'],cwd=root,env=env,creationflags=subprocess.CREATE_NO_WINDOW,stdout=log,stderr=subprocess.STDOUT)
    client=httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=60)
    def post(path,body):
        r=client.post(path,json=body);r.raise_for_status();return r.json()
    def action(s,name,payload=None):return post('/api/sessions/'+s['id']+'/'+name,{'revision':s['revision'],'payload':payload or {}})
    try:
        for _ in range(80):
            try:
                if client.get('/api/health').status_code==200:break
            except httpx.RequestError:pass
            time.sleep(.25)
        live=post('/api/sessions',{'day':'2022-08-19','mode':'live'})
        live=action(live,'plan_approve');live=action(live,'prepared');live=action(live,'advance',{'target':1170})
        assert live['pending']['status']=='missing_data'
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',headless=True)
            context=browser.new_context(viewport={'width':1440,'height':1100});page=context.new_page();errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.add_init_script('localStorage.setItem("smartfresh-session",'+json.dumps(live['id'])+')')
            page.goto(str(client.base_url)+'?view=m1')
            page.get_by_text('Thiếu dữ liệu bán hàng để đề xuất giá',exact=True).wait_for()
            page.locator('[data-fork-simulation]').first.click()
            page.wait_for_selector('[data-approve="plan"]')
            sim_id=page.evaluate('state.id');assert sim_id!=live['id']
            assert page.locator('table tbody tr').first.locator('td').nth(2).inner_text().isdigit()
            page.locator('[data-approve="plan"]').click();page.locator('#confirm-approval').click()
            page.wait_for_selector('[data-act="prepared"]');page.locator('[data-act="prepared"]').click();page.locator('#confirm-action').click()
            page.wait_for_function('!working&&state.phase==="running"&&state.realtime.enabled');page.locator('[data-sim-speed]').select_option('30')
            page.wait_for_function('state.realtime.enabled&&state.realtime.speed===30')
            before=client.get('/api/state?session_id='+sim_id).json()['minute']
            page.close();time.sleep(1.5)
            after=client.get('/api/state?session_id='+sim_id).json()['minute'];assert after>before
            page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(str(client.base_url)+'?view=m1')
            page.wait_for_function('state&&state.phase==="price_pending"&&state.minute===1170',timeout=60000)
            s=client.get('/api/state?session_id='+sim_id).json()
            assert s['ledger'] and sum(r['sales60'] for r in s['pending']['rows'])>0
            output=root/'docs/qa';output.mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(output/'realtime-1930.png'),full_page=True)
            page.locator('[data-play]').click();page.wait_for_function('!state.realtime.enabled')
            s=client.get('/api/state?session_id='+sim_id).json()
            while s['phase']!='close_pending':
                if s['phase']=='price_pending':s=action(s,'price_approve',{'proposal_id':s['pending']['id']})
                elif s['phase']=='price_approved':s=action(s,'price_apply',{'proposal_id':s['pending']['id']})
                else:s=action(s,'advance',{'target':1320})
            page.goto(str(client.base_url)+'?view=reports');page.wait_for_selector('[data-act="close"]')
            page.locator('[data-act="close"]').click();page.locator('#confirm-action').click()
            page.wait_for_selector('[data-next-day]');page.locator('[data-next-day]').click()
            page.wait_for_function('state.day==="2022-08-20"')
            next_s=client.get('/api/state?session_id='+page.evaluate('state.id')).json()
            closed=client.get('/api/state?session_id='+sim_id).json()
            assert all(p['features']['lag1_sales']==closed['products'][p['sku']]['sold'] for p in next_s['plan'])
            assert all(p['prepared']==p['sold']+p['stock'] for p in closed['products'].values())
            assert client.get('/api/state?session_id='+live['id']).json()['ledger']==[]
            page.screenshot(path=str(output/'next-day-feedback.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+3')
            assert not errors,errors
            browser.close()
            (output/'realtime-flow.json').write_text(json.dumps({'passed':True,'isolated':True,'js_errors':errors,
                'backend_clock_without_browser':[before,after],'day':closed['day'],'next_day':next_s['day'],
                'prepared':closed['totals']['prepared'],'sold':closed['totals']['sold'],'waste':closed['totals']['stock']},indent=2),encoding='utf-8')
        print('PASS: missing live feed blocked; separate trained simulation; backend clock without browser; 19:30 windows; full ledger; close -> next-day feedback; integer UI; mobile.')
    finally:
        client.close();server.terminate();server.wait(timeout=15);log.close()


if __name__=='__main__':main()
