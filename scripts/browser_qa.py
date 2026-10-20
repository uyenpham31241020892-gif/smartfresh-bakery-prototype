"""Exercise the real local dashboard in installed Edge, including approval flows."""
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright, expect

BASE='http://127.0.0.1:8000'
OUT=ROOT/'docs/qa'
OUT.mkdir(parents=True,exist_ok=True)


def main():
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1100},device_scale_factor=1)
        page=context.new_page()
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        response=page.request.post(BASE+'/api/sessions',data={'day':'2022-08-16','seed':42,'mode':'simulation'})
        assert response.ok,response.text()
        sid=response.json()['id']
        page.goto(BASE)
        page.evaluate('(sid)=>localStorage.setItem("smartfresh-session",sid)',sid)
        page.reload()
        expect(page.locator('#page-title')).to_have_text('Tổng quan vận hành')
        expect(page.locator('.hero')).to_contain_text('296 bánh')
        page.screenshot(path=str(OUT/'overview-desktop.png'),full_page=True)
        page.locator('[data-view="m2"]').click()
        expect(page.locator('[data-approve="plan"]')).to_be_visible()
        page.locator('[data-qty="BK-001"]').fill('64')
        page.locator('[data-qty="BK-001"]').press('Tab')
        page.locator('#table-search').fill('croissant')
        page.locator('#table-search').fill('')
        expect(page.locator('[data-qty="BK-001"]')).to_have_value('64')
        page.locator('[data-qty="BK-001"]').fill('60')
        page.locator('[data-qty="BK-001"]').press('Tab')
        page.locator('[data-explain="BK-001"]').click()
        expect(page.locator('#drawer-content')).to_contain_text('TreeSHAP')
        page.screenshot(path=str(OUT/'m2-evidence.png'))
        page.locator('[data-close="drawer"]').click()
        page.locator('[data-approve="plan"]').click()
        page.locator('#confirm-approval').click()
        expect(page.locator('[data-act="prepared"]')).to_be_visible()
        page.locator('[data-act="prepared"]').click()
        page.locator('#confirm-action').click()
        expect(page.locator('.clockbar')).to_contain_text('Đang vận hành')
        page.locator('[data-advance="1170"]').click()
        expect(page.locator('.clockbar time')).to_have_text('19:30')
        page.locator('[data-view="m1"]').click()
        expect(page.locator('[data-approve="price"]')).to_be_visible()
        page.screenshot(path=str(OUT/'pricing-desktop.png'),full_page=True)
        page.locator('[data-explain="BK-001"]').click()
        expect(page.locator('#drawer-content')).to_contain_text('Doanh thu dự kiến')
        page.locator('[data-close="drawer"]').click()
        page.locator('[data-approve="price"]').click()
        page.locator('#confirm-approval').click()
        expect(page.locator('[data-act="price_apply"]')).to_be_visible()
        page.locator('[data-act="price_apply"]').click()
        page.locator('#confirm-action').click()
        expect(page.locator('.clockbar')).to_contain_text('Đang vận hành')
        page.locator('[data-view="ledger"]').click()
        expect(page.locator('tbody tr').first).to_be_visible()
        page.locator('[data-view="reports"]').click()
        page.locator('[data-report="reference"]').click()
        expect(page.locator('#view')).to_contain_text('106.158.050')
        page.screenshot(path=str(OUT/'reference-report.png'),full_page=True)
        page.locator('[data-view="audit"]').click()
        expect(page.locator('#view')).to_contain_text('Áp dụng giá đã duyệt')
        page.locator('[data-view="data"]').click()
        page.locator('#file-input').set_input_files(str(ROOT/'data/current_v9/history_through_aug15_synthetic.csv'))
        expect(page.locator('.data-preview')).to_contain_text('Dữ liệu hợp lệ')
        page.locator('[data-confirm-import]').click()
        expect(page.locator('#page-title')).to_have_text('Kế hoạch sản lượng')
        expect(page.locator('.panel-head')).to_contain_text('history_through_aug15_synthetic.csv')
        page.locator('[data-view="settings"]').click()
        expect(page.locator('#view')).to_contain_text('Chưa cấu hình')
        assert page.locator('#api-key').input_value() == ''
        page.locator('[data-view="overview"]').click()
        page.set_viewport_size({'width':390,'height':844})
        page.locator('#toast').evaluate('(el)=>el.hidden=true')
        page.screenshot(path=str(OUT/'overview-mobile.png'),full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth') <= 390
        page.locator('#menu').click()
        expect(page.locator('.sidebar')).to_be_visible()
        page.locator('[data-view="m2"]').click()
        expect(page.locator('#page-title')).to_have_text('Kế hoạch sản lượng')
        assert page.evaluate('document.documentElement.scrollWidth') <= 390
        assert not errors,errors
        browser.close()
        (OUT/'browser-result.json').write_text(json.dumps({'passed':True,'browser':'installed Microsoft Edge','console_errors':errors,
            'checks':['desktop overview','model evidence','plan approval','preparation confirmation','M1 inference at 19:30',
                      'price approval and apply','transaction ledger','reference finance','audit trail','CSV import and inference','settings','draft edits survive table filtering','mobile layout and navigation']},indent=2))
        print('PASS: desktop and mobile browser flow; no JavaScript errors.')


if __name__=='__main__':
    main()
