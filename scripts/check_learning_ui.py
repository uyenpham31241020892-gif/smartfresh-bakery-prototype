"""Exercise real training and confirmation in an isolated local application/database."""
from pathlib import Path
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import httpx
from playwright.sync_api import sync_playwright
from services.engine import Engine
from services.learning import demo_data


def main():
    root = Path(__file__).resolve().parents[1]
    qa = root / 'runtime' / 'qa'
    qa.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix='learning-', dir=qa))
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env.update(PORT=str(port), SMARTFRESH_DB=str(directory/'app.sqlite3'), SMARTFRESH_LEARNING_DIR=str(directory/'models'))
    log = (directory/'server.log').open('wb')
    server = subprocess.Popen([sys.executable, 'app.py'], cwd=root, env=env,
                              creationflags=subprocess.CREATE_NO_WINDOW, stdout=log, stderr=subprocess.STDOUT)
    base = f'http://127.0.0.1:{port}'
    client = httpx.Client(base_url=base, timeout=20)
    try:
        for _ in range(60):
            try:
                if client.get('/api/health').status_code == 200:
                    break
            except httpx.RequestError:
                pass
            time.sleep(.25)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 1100})
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(base+'/?view=learning')
            page.wait_for_selector('#learning-demo')
            original = client.get('/api/state').json()
            page.locator('#learning-demo').click()
            page.get_by_text('Chỉ demo', exact=True).wait_for(timeout=60000)
            assert page.locator('[data-promote]').count() == 0
            raw = demo_data('m2', Engine().master)
            page.locator('#learning-file').set_input_files({'name': 'isolated-test.csv', 'mimeType': 'text/csv', 'buffer': raw})
            page.locator('#learning-upload').click()
            page.wait_for_function("document.querySelector('#learning-train') && !document.querySelector('#learning-train').disabled")
            page.locator('#learning-train').click()
            page.wait_for_selector('[data-promote]', timeout=60000)
            page.locator('[data-promote]').click()
            page.locator('#model-reason').fill('Isolated browser test confirmation')
            page.locator('#confirm-model-change').click()
            page.wait_for_selector('[data-rollback-model]')
            adopted = client.get('/api/learning').json()
            assert adopted['active'] != original['model_version']
            assert client.get('/api/state?session_id='+original['id']).json()['model_version'] == original['model_version']
            output = root/'docs'/'qa'
            output.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(output/'learning-desktop.png'), full_page=True)
            page.locator('[data-rollback-model]').click()
            page.locator('#model-reason').fill('Isolated browser test rollback')
            page.locator('#confirm-model-change').click()
            page.wait_for_function("!document.querySelector('[data-rollback-model]')")
            assert client.get('/api/learning').json()['active'] == original['model_version']
            page.set_viewport_size({'width':390, 'height':844})
            page.screenshot(path=str(output/'learning-mobile.png'), full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 3'), 'Mobile horizontal overflow'
            assert not errors, errors
            browser.close()
            (output/'learning-browser.json').write_text(json.dumps({'passed': True, 'isolated': True, 'js_errors': errors,
                'checks': ['demo blocked', 'upload', 'actual LightGBM training', 'explicit promotion', 'old session pinned', 'rollback', 'mobile layout']}), encoding='utf-8')
        print('PASS: isolated browser upload, real training, demo restriction, confirmation, version pinning, rollback, mobile; no JS errors.')
    finally:
        client.close()
        server.terminate()
        server.wait(timeout=15)
        log.close()


if __name__ == '__main__':
    main()
