"""Local, read-only V9 replay viewer. Python 3.10+, standard library only."""
import csv
import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent

def read(name):
    with (ROOT / 'data/replay' / name).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

PREP = read('M1_M2_SELECTED_preparation_sep.csv')
DECISIONS = read('M1_M2_SELECTED_decisions_sep.csv')
LEDGER = read('M1_M2_SELECTED_transaction_ledger_sep.csv')
DATES = sorted({r['date'] for r in PREP})

def snapshot(day, minute):
    if day not in DATES or not 360 <= minute <= 1320:
        raise ValueError('Chọn ngày trong tháng 09/2022 và giờ từ 06:00 đến 22:00.')
    products = []
    for p in (r for r in PREP if r['date'] == day):
        sku = p['sku_code']
        tx = [r for r in LEDGER if r['date'] == day and r['sku_code'] == sku and int(r['minute']) < minute]
        ds = [r for r in DECISIONS if r['date'] == day and r['sku_code'] == sku and int(r['time'][:2])*60+int(r['time'][3:]) <= minute]
        last = ds[-1] if ds else None
        products.append(dict(sku=sku, forecast=round(float(p['m2_forecast_base_demand']), 1),
            prepared=int(p['prepared_qty']), sold=len(tx), stock=int(p['prepared_qty'])-len(tx),
            revenue=sum(int(r['paid_vnd']) for r in tx), discount=int(last['discount_after']) if last else 0,
            decision_time=last['time'] if last else None, reason=last['reason'] if last else 'Chưa đến khung giảm giá'))
    return dict(mode='REPLAY_V9', day=day, minute=minute, products=products,
        revenue=sum(r['revenue'] for r in products), sold=sum(r['sold'] for r in products),
        stock=sum(r['stock'] for r in products), dates=DATES,
        notice='Dữ liệu nhu cầu mô phỏng V9; phát lại kết quả đã chạy, chưa suy luận từ đầu vào mới.')

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path == '/api/snapshot':
                q = parse_qs(parsed.query)
                result = snapshot(q.get('day', [DATES[0]])[0], int(q.get('minute', ['1170'])[0]))
                body = json.dumps(result, ensure_ascii=False).encode()
                mime = 'application/json; charset=utf-8'
            elif parsed.path == '/':
                body = (ROOT/'web/index.html').read_bytes()
                mime = 'text/html; charset=utf-8'
            else:
                self.send_error(404)
                return
            self.send_response(200)
        except (ValueError, KeyError) as e:
            body = json.dumps({'error': str(e)}, ensure_ascii=False).encode()
            mime = 'application/json; charset=utf-8'
            self.send_response(400)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

if __name__ == '__main__':
    print('SmartFresh: http://127.0.0.1:8000 | Ctrl+C để dừng')
    HTTPServer(('127.0.0.1', 8000), Handler).serve_forever()
