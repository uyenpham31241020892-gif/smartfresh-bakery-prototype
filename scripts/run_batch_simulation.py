"""Batch simulation runner for SmartFresh.
Runs the model and closed-loop daily operations across July and August 2022 test dates.
"""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from services.v606 import Engine, Simulator, CURRENT_VERSION
from services.store import Store
from services.workflow import Workflow
from services.learning import Learning

CHECKPOINTS = [1170, 1200, 1230, 1260, 1290, 1320]


def handle_pending_pricing(workflow, s):
    sid = s['id']
    if s.get('pending') and s['phase'] == 'price_pending':
        pid = s['pending']['id']
        s = workflow.mutate(sid, s['revision'], 'price_approve', {'proposal_id': pid})
        s = workflow.mutate(sid, s['revision'], 'price_apply', {'proposal_id': pid})
    return s


def get_totals(s):
    products = list(s.get('products', {}).values())
    prep = sum(p['prepared'] for p in products)
    sold = sum(p['sold'] for p in products)
    waste = sum(p['stock'] for p in products)
    rev = sum(p['revenue'] for p in products)
    return {'prepared': prep, 'sold': sold, 'waste': waste, 'revenue': rev}


def advance_day_to_close(workflow, s):
    sid = s['id']
    # 1. Approve plan if pending
    if s['phase'] == 'plan_pending':
        s = workflow.mutate(sid, s['revision'], 'plan_approve')
    
    # 2. Mark prepared
    if s['phase'] == 'plan_approved':
        s = workflow.mutate(sid, s['revision'], 'prepared')
    
    # 3. Handle checkpoints through 1320 (22:00)
    for cp in CHECKPOINTS:
        if s['minute'] < cp:
            # First handle any pending before ticking
            s = handle_pending_pricing(workflow, s)
            s = workflow.mutate(sid, s['revision'], 'tick', {'target': cp})
            s = handle_pending_pricing(workflow, s)
        elif s['minute'] == cp:
            s = handle_pending_pricing(workflow, s)

    # 4. Close day
    if s['phase'] in ('close_pending', 'running', 'price_approved'):
        s = workflow.mutate(sid, s['revision'], 'close')
    
    return s


def run_batch(max_days=None):
    store = Store()
    engine = Engine(allow_degraded=True)
    simulator = Simulator(engine)
    workflow = Workflow(engine, simulator, store)
    learning = Learning(store, engine)
    workflow.active_engine = learning.active
    workflow.version_engine = learning.resolve

    # Find the most recently updated session
    with store.read() as db:
        rows = db.execute('SELECT id, state, updated FROM sessions ORDER BY updated DESC').fetchall()
    
    if not rows:
        print('Không có ca nào trong DB. Bắt đầu ca đầu tiên 2022-07-01...')
        s = workflow.create(day='2022-07-01', mode='simulation')
    else:
        # Get the latest active or closed session
        latest_row = rows[0]
        s = json.loads(latest_row['state'])
        print(f"Tiếp tục từ ca gần nhất: {s['day']} (Phase: {s['phase']}, Phút: {s['minute']})")

    # If the session is not closed, advance it to close
    if s['phase'] != 'closed':
        print(f"Đang hoàn tất nốt ngày {s['day']}...")
        s = advance_day_to_close(workflow, s)
        tot = get_totals(s)
        print(f" -> Hoàn tất {s['day']}: Doanh thu {tot['revenue']:,}đ | Bán {tot['sold']} | Tồn hủy {tot['waste']}")

    days_run = 0
    calendar_dates = sorted(simulator.calendar.keys())
    
    print("\n" + "=" * 80)
    print(f"{'NGÀY':<12} | {'THỨ':<5} | {'CHUẨN BỊ':<8} | {'ĐÃ BÁN':<8} | {'TỒN HỦY':<8} | {'DOANH THU (VNĐ)':<15} | {'GIẢM GIÁ':<8}")
    print("=" * 80)

    # Print the closed current day first
    cal_info = simulator.calendar.get(s['day'], {})
    w_iso = cal_info.get('weekday_iso', '')
    discounts = sum(1 for d in s.get('decisions', []) if d.get('status') == 'applied')
    tot = get_totals(s)
    print(f"{s['day']:<12} | T{w_iso:<4} | {tot['prepared']:<8} | {tot['sold']:<8} | {tot['waste']:<8} | {tot['revenue']:>14,} | {discounts:<8}")

    while True:
        if max_days and days_run >= max_days:
            break

        current_date = s['day']
        next_date = str((datetime.fromisoformat(current_date) + timedelta(days=1)).date())
        
        if next_date not in simulator.calendar:
            print(f"\n[!] Đã đạt mốc kết thúc tập test ({current_date} là ngày cuối có trong lịch kịch bản).")
            break

        # Roll over to next day
        import time
        time.sleep(0.05)
        s = workflow.next_day(s['id'])
        s = advance_day_to_close(workflow, s)
        days_run += 1

        cal_info = simulator.calendar.get(s['day'], {})
        w_iso = cal_info.get('weekday_iso', '')
        discounts = sum(1 for d in s.get('decisions', []) if d.get('status') == 'applied')
        tot = get_totals(s)
        print(f"{s['day']:<12} | T{w_iso:<4} | {tot['prepared']:<8} | {tot['sold']:<8} | {tot['waste']:<8} | {tot['revenue']:>14,} | {discounts:<8}", flush=True)

    # Summary
    with store.read() as db:
        all_rows = db.execute("SELECT state FROM sessions ORDER BY json_extract(state, '$.day') ASC").fetchall()
    
    all_sessions = [json.loads(r['state']) for r in all_rows if json.loads(r['state']).get('phase') == 'closed']
    
    total_prep = sum(get_totals(s)['prepared'] for s in all_sessions)
    total_sold = sum(get_totals(s)['sold'] for s in all_sessions)
    total_waste = sum(get_totals(s)['waste'] for s in all_sessions)
    total_rev = sum(get_totals(s)['revenue'] for s in all_sessions)
    
    print("\n" + "=" * 80)
    print("TỔNG KẾT MÔ PHỎNG TOÀN BỘ KỲ TEST (62 NGÀY THÁNG 7 & THÁNG 8/2022)")
    print("=" * 80)
    print(f"Tổng số ngày đã hoàn thành : {len(all_sessions)} ngày (từ {all_sessions[0]['day']} đến {all_sessions[-1]['day']})")
    print(f"Tổng sản lượng chuẩn bị    : {total_prep:,} chiếc (TB {total_prep/len(all_sessions):.1f} chiếc/ngày)")
    print(f"Tổng số lượng đã bán      : {total_sold:,} chiếc (Tỷ lệ bán được: {total_sold/total_prep*100:.1f}%)")
    print(f"Tổng số lượng tồn hủy     : {total_waste:,} chiếc (Tỷ lệ hủy: {total_waste/total_prep*100:.1f}%)")
    print(f"Tổng doanh thu thực tế     : {total_rev:,} VNĐ (TB {total_rev/len(all_sessions):,.0f} VNĐ/ngày)")
    print("=" * 80)
    print("Toàn bộ dữ liệu đã được lưu trữ trong runtime/smartfresh.sqlite3.")
    print("Mở giao diện web http://127.0.0.1:8000 -> Tab 'Báo cáo hiệu quả' để xem biểu đồ chi tiết.")


if __name__ == '__main__':
    run_batch()
