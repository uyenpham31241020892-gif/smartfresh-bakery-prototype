"""Verify the settings UI without an API key or a real API request."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
            headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        response = page.goto('http://127.0.0.1:8000/?view=settings')
        assert response.status == 200
        page.wait_for_selector('#settings-form')
        assert page.locator('#api-key').input_value() == ''
        assert page.locator('#api-key').get_attribute('type') == 'password'
        assert page.locator('#settings-form [type="submit"]').is_visible()
        page.locator('#ai-provider').select_option('Gemini')
        page.locator('#settings-form [type="submit"]').click()
        assert page.locator('#toast').is_visible()
        assert not errors, errors
        page.locator('#toast').evaluate('(el)=>el.hidden=true')
        page.locator('#ai-provider').select_option('Ollama')
        assert page.locator('#ai-model').input_value() == 'qwen3.5:4b'
        assert page.locator('#api-key').is_disabled()
        page.locator('#ai-provider').select_option('Gemini')
        assert page.locator('#ai-model').input_value() == 'gemini-3.8-flash'
        assert page.locator('#api-key').is_enabled()
        assert page.locator('#check-gemini-models').is_visible()
        def catalogue(route):
            assert route.request.post_data_json['provider'] == 'Gemini'
            route.fulfill(status=200, content_type='application/json', body=json.dumps({
                'models': [{'id': 'gemini-test-flash', 'name': 'Test catalogue only'}],
                'key_accepted': True, 'note': 'Mocked catalogue; no external request.'}))
        page.route('**/api/ai/models', catalogue)
        page.locator('#api-key').fill('test-key-only-not-real-000000')
        page.locator('#check-gemini-models').click()
        page.wait_for_selector('#gemini-model-picker')
        page.locator('#gemini-model-picker').select_option('gemini-test-flash')
        assert page.locator('#ai-model').input_value() == 'gemini-test-flash'
        page.locator('#api-key').fill('')
        out = Path(__file__).resolve().parents[1] / 'docs/qa/ai-settings.png'
        page.screenshot(path=str(out), full_page=True)
        browser.close()
    print('PASS: settings deep link, masked field, live-test button, empty-key guard; no JS errors.')


if __name__ == '__main__':
    main()
