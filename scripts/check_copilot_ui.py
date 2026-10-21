"""Check presentation with mocked AI replies; no keys or external model calls."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright

ANSWER = '''**Nhu cầu dự báo (M2):** Khoảng **45 chiếc** Bánh Mỳ Baguette Size Lớn (BK-001).

**Sản lượng đề xuất:** **60 chiếc**.
* **Cách tính:** Dự báo 44,73 + buffer 5,57 → làm tròn mẻ 4 thành **52 chiếc**. Sàn sản lượng **60 chiếc** cao hơn nên được áp dụng.
* **Lưu ý:** Đây là sản lượng đề xuất, chưa phải lượng đã sản xuất.

**Bước đang chờ xác nhận:**
Ca đang ở trạng thái `plan_pending`. Bạn cần duyệt kế hoạch trên dashboard trước khi chuẩn bị sản phẩm.'''


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', headless=True)
        page = browser.new_page(viewport={'width':1440,'height':1100})
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        reply = {'answer':ANSWER,'model':'test-render-only','response_id':'test-no-external-call',
                 'tools_used':['get_session_context','get_model_evidence']}
        page.route('**/api/ai/verify',lambda r:r.fulfill(status=200,content_type='application/json',body=json.dumps({
            'ai':{'provider':'Gemini','model':'test-render-only','configured':True,'verified':True},'verification':reply})))
        def chat(route):
            assert 'Yêu cầu trình bày' in route.request.post_data_json['message']
            route.fulfill(status=200,content_type='application/json',body=json.dumps(reply))
        page.route('**/api/chat',chat)
        page.goto('http://127.0.0.1:8000/?view=settings')
        page.wait_for_selector('[data-verify-ai]')
        page.locator('[data-verify-ai]').click()
        page.wait_for_selector('.copilot-response')
        response = page.locator('#settings-form .copilot-response')
        assert response.locator('.copilot-section').count() == 5
        assert response.locator('.copilot-section-icon svg').count() == 5
        assert response.locator('strong',has_text='60 chiếc').count() >= 1
        assert '**' not in response.inner_text() and 'plan_pending' not in response.inner_text()
        assert not response.locator('.copilot-technical dd').first.is_visible()
        response.locator('summary').click()
        assert response.locator('.copilot-technical dd').first.is_visible()
        response.locator('summary').click()
        assert page.evaluate("""()=>{
            window.copilotXss=0;
            const holder=document.createElement('div');
            holder.innerHTML=copilotResponse({answer:'**Lý do:** <img src=x onerror="window.copilotXss=1"> **60 chiếc**'});
            document.body.append(holder);
            const safe=holder.querySelectorAll('img,script').length===0&&window.copilotXss===0;
            holder.remove();return safe;
        }""")
        assert page.evaluate("copilotPrompt('x'.repeat(4000)).length===4000")
        output=Path(__file__).resolve().parents[1]/'docs'/'qa'
        output.mkdir(parents=True,exist_ok=True)
        response.screenshot(path=str(output/'copilot-sections.png'))
        page.evaluate('openChat()')
        page.locator('#chat-input').fill('Giải thích kế hoạch của BK-001')
        page.locator('#chat-form [type=submit]').click()
        page.wait_for_selector('#drawer .copilot-response')
        assert page.locator('#drawer .copilot-section').count()==5
        page.screenshot(path=str(output/'copilot-chat-desktop.png'))
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+3')
        page.screenshot(path=str(output/'copilot-chat-mobile.png'))
        assert not errors,errors
        browser.close()
    print('PASS: sections/icons, bold text, localized status, collapsed metadata, safe HTML, chat, mobile; no AI calls or JS errors.')


if __name__=='__main__':
    main()
