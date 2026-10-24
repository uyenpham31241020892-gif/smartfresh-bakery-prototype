"""GD5: deterministic point-in-time gates and content-addressed lineage.
No evaluation-only assets are read by this module.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone
import math

VN = timezone(timedelta(hours=7))
POLICY = {'version': 'GD5-v1', 'forecast_max_age_hours': 48, 'history_max_gap_days': 2,
          'sales_max_age_minutes': 30, 'cutoff_local': '06:00', 'timezone': 'Asia/Ho_Chi_Minh'}
FORBIDDEN = {'hidden_demand', 'hidden_base_demand', 'base_demand', 'actual_demand', 'response_draw',
             'stock_at_21', 'future_sales', 'y_discount_pct', 'target', 'label', 'waste_qty', 'lost_regular_qty'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def timestamp(value):
    try:
        t = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (ValueError, TypeError):
        raise ValueError('Timestamp phải là ISO 8601 hợp lệ có múi giờ.')
    if t.tzinfo is None:
        raise ValueError('Timestamp cần múi giờ, ví dụ +07:00.')
    return t


def cutoff(day):
    return timestamp(day + 'T06:00:00+07:00')


def forbidden_columns(columns):
    return [str(c) for c in columns if str(c).lower().strip() in FORBIDDEN or
            any(t in str(c).lower() for t in ('era5', 'hidden_', 'response_draw', 'evaluation_only')) or
            str(c).lower().startswith(('target_', 'y_'))]


def weather_check(day, weather, trusted_demo=False):
    c = cutoff(day)
    source = str(weather.get('forecast_source') or 'USER_DECLARED_UPLOAD')
    if any(x in source.lower() for x in ('era5', 'reanalysis', 'retrospective', 'evaluation', 'hidden')):
        raise ValueError('Nguồn thời tiết hậu nghiệm/evaluation-only không được dùng cho inference.')
    issued = weather.get('issued_at')
    if issued is None or str(issued).strip() in ('', 'None', 'nan', 'NaT'):
        if not trusted_demo:
            raise ValueError('Forecast nhập cần issued_at có múi giờ, không sau 06:00; tên JMA không thay thế timestamp.')
        return {'status': 'WARN', 'source': source, 'issued_at': None, 'age_hours': None,
                'message': 'Demo V6.06 prior-day weather: chưa xác minh thời điểm phát hành; chỉ dùng mô phỏng.'}
    issued = timestamp(issued)
    available = timestamp(weather.get('available_at') or issued.isoformat())
    if available < issued:
        raise ValueError('available_at không được trước issued_at.')
    if issued > c or available > c:
        raise ValueError('Forecast chưa có tại cutoff 06:00 ngày dự báo (issued_at/available_at).')
    age = (c - issued).total_seconds() / 3600
    if age > POLICY['forecast_max_age_hours']:
        raise ValueError('Forecast quá cũ: vượt 48 giờ tại cutoff 06:00.')
    return {'status': 'PASS', 'source': source, 'issued_at': issued.isoformat(), 'available_at': available.isoformat(),
            'age_hours': round(age, 2), 'message': 'Timestamp khai báo hợp lệ; chưa xác thực nhà cung cấp bên ngoài.'}


def history_quality(day, visible, master):
    c = cutoff(day)
    rows = []
    for sku in master:
        dates = sorted(d for d, s in visible if s == sku)
        last = dates[-1] if dates else None
        gap = (c.date() - datetime.fromisoformat(last).date()).days if last else None
        missing = [(c.date()-timedelta(days=k)).isoformat() for k in range(1,8)
                   if ((c.date()-timedelta(days=k)).isoformat(),sku) not in visible]
        rows.append({'sku': sku, 'last_date': last, 'gap_days': gap, 'missing_last7': missing,
                     'status': 'BLOCK' if gap is None or gap > POLICY['history_max_gap_days'] else 'WARN' if missing else 'PASS'})
    return rows


def build_snapshot(day, visible, weather, engine, plans, outcomes, lineage, trusted_demo=False):
    if any(d >= day for d, sku in visible) or any(d >= day for d, sku in outcomes):
        raise ValueError('Data leakage: lịch sử/kết quả ngày hiện tại hoặc tương lai không được làm feature M2.')
    for (d, sku), value in visible.items():
        if sku not in engine.master or not math.isfinite(float(value)) or float(value) < 0:
            raise ValueError('Lịch sử đầu vào có SKU/số lượng không hợp lệ.')
    weather_result = weather_check(day, weather, trusted_demo)
    history = history_quality(day, visible, engine.master)
    if any(r['status']=='BLOCK' for r in history):
        raise ValueError('Lịch sử thiếu/quá cũ (>2 ngày) cho SKU: ' + ', '.join(r['sku'] for r in history if r['status']=='BLOCK'))
    features = [{'sku': p['sku'], 'features': p['features']} for p in plans]
    content = {'day': day, 'prediction_as_of': cutoff(day).isoformat(), 'policy': POLICY,
               'history': [{'date':d,'sku':s,'sold':v} for (d,s),v in sorted(visible.items())],
               'outcomes': [outcomes[k] for k in sorted(outcomes)], 'weather': weather,
               'features': features, 'model_version': engine.version, 'model_hashes': engine.manifest['native_model_hashes'],
               'lineage': lineage}
    status = 'WARN' if weather_result['status']=='WARN' or any(r['status']=='WARN' for r in history) or lineage.get('availability') != 'declared_timestamps' else 'PASS'
    return {'schema_version': 'GD5-v1', 'snapshot_id': digest(content), 'status':status,
            'prediction_as_of': content['prediction_as_of'], 'recorded_at':datetime.now(VN).isoformat(),
            'clock_basis': 'session_day_not_wall_clock', 'history': history, 'weather':weather_result,
            'lineage':lineage, 'policy':POLICY, 'feature_hash':digest(features),
            'model_hashes':content['model_hashes'], 'model_version':engine.version,
            'message':'Kiểm tra local theo thời gian ca; PASS không xác thực nguồn POS/JMA hoặc chứng nhận production.'}


def sales_quality(s):
    if s['mode']=='simulation':
        return {'status':'DEMO','age_minutes':0,'message':'Luồng mô phỏng theo đồng hồ ca; không phải POS thật.'}
    last=max([t['minute'] for t in s['ledger']]+[s.get('sales_verified_minute',-1)])
    age=s['minute']-last if last>=0 else None
    status='BLOCK' if age is None or age>POLICY['sales_max_age_minutes'] else 'PASS'
    return {'status':status,'age_minutes':age,'last_minute':last if last>=0 else None,
            'message':'Chặn gợi ý M1 khi chưa có dữ liệu hoặc quá 30 phút. Nhập bán hàng / xác nhận kiểm kê không có bán mới.'}
