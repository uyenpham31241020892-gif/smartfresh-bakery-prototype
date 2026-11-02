"""Bounded CSV/XLSX/ZIP ingestion, row validation and immutable previews."""
import csv
from datetime import date, datetime
import hashlib
import io
import json
import math
from pathlib import PurePosixPath
import zipfile
import pandas as pd
from .quality import forbidden_columns, weather_check, timestamp, cutoff, history_quality

MAX_BYTES = 20 * 1024 * 1024
ALIASES = {'sku': 'sku_code', 'mã sku': 'sku_code', 'ma_sku': 'sku_code', 'ngày': 'date',
           'ngay': 'date', 'số bán': 'sold_qty', 'sold': 'sold_qty', 'đã bán': 'sold_qty',
           'số lượng': 'quantity', 'qty': 'quantity', 'phút': 'minute'}


def iso(value):
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return value.strftime('%Y-%m-%d')
    return date.fromisoformat(str(value).strip()).isoformat()


def integer(value, field):
    x = float(value)
    if not math.isfinite(x) or x != int(x) or x < 0 or x > 1000000:
        raise ValueError(field + ' cần là số nguyên không âm hợp lệ')
    return int(x)


def tables(name, raw):
    suffix = PurePosixPath(name).suffix.lower()
    if len(raw) > MAX_BYTES:
        raise ValueError('Tệp vượt quá 20 MB.')
    if suffix == '.csv':
        try:
            content = raw.decode('utf-8-sig')
        except UnicodeError:
            raise ValueError('CSV cần mã hóa UTF-8. Hãy lưu lại bằng CSV UTF-8.')
        try:
            dialect = csv.Sniffer().sniff(content[:4096], delimiters=',;\t')
        except csv.Error:
            dialect = csv.excel
        return [(name, pd.read_csv(io.StringIO(content), sep=dialect.delimiter))]
    if suffix == '.xlsx':
        # XLSX itself is a ZIP: check its expanded size before openpyxl reads it.
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            if sum(x.file_size for x in z.infolist()) > 80 * 1024 * 1024:
                raise ValueError('Workbook mở rộng quá lớn.')
        return list(pd.read_excel(io.BytesIO(raw), sheet_name=None, engine='openpyxl').items())
    if suffix == '.zip':
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            if len(z.infolist()) > 500 or sum(x.file_size for x in z.infolist()) > 80 * 1024 * 1024:
                raise ValueError('ZIP có quá nhiều tệp hoặc dung lượng mở rộng quá lớn.')
            candidates = [n for n in z.namelist() if PurePosixPath(n).name in
                ['history.csv','weather.csv','morning_features_V4.csv','morning_features.csv']
                ]
            if not candidates:
                raise ValueError('ZIP cần history.csv, weather.csv và/hoặc morning_features_V4.csv.')
            result = []
            for n in candidates:
                result += tables(n, z.read(n))
            return result
    raise ValueError('Hỗ trợ CSV, XLSX hoặc ZIP dữ liệu; chưa hỗ trợ đọc PDF thành giao dịch.')


def inspect(name, raw, day, master, mapping=None):
    day = iso(day)
    result = {'filename': PurePosixPath(name.replace('\\', '/')).name, 'sha256': hashlib.sha256(raw).hexdigest(),
              'day': day, 'errors': [], 'warnings': [], 'history': [], 'weather': None, 'transactions': [], 'tables': [],'outcomes':[],'feature_rows':[]}
    if day > '2022-09-30':
        result['warnings'].append('Model được khóa từ dữ liệu năm 2022. Dự báo cho ngày ngoài giai đoạn này chưa được xác nhận độ chính xác.')
    history_keys = set()
    for table_name, frame in tables(name, raw):
        if len(frame) > 20000 or len(frame.columns) > 100:
            raise ValueError('Mỗi bảng tối đa 20.000 dòng và 100 cột.')
        frame.columns = [str(c).strip() for c in frame.columns]
        blocked_original = forbidden_columns(frame.columns)
        if blocked_original:
            result['errors'].append({'table':table_name,'row':1,'message':'Cột nguồn evaluation/target bị cách ly: '+', '.join(blocked_original)})
            continue
        frame = frame.rename(columns=mapping or {c: ALIASES.get(c.lower(), c) for c in frame.columns})
        if frame.columns.duplicated().any():
            raise ValueError('Tên cột trùng sau ánh xạ. Hãy giữ mỗi trường ở một cột.')
        cols = set(frame.columns)
        blocked = forbidden_columns(cols)
        if blocked:
            result['errors'].append({'table': table_name, 'row': 1, 'message': 'Cột evaluation/target bị cách ly: ' + ', '.join(blocked)})
            continue
        kind = 'features' if {'date','sku_code','decision_at','sold_calendar_lag1','prepared_last_observed'}<=cols else 'history' if {'date', 'sku_code', 'sold_qty'} <= cols else 'weather' if {'date', 'forecast_rain_mm_previous_day1', 'forecast_temperature_max_c_previous_day1'} <= cols else 'transactions' if {'sku_code', 'minute', 'quantity'} <= cols else 'unknown'
        result['tables'].append({'name': table_name, 'kind': kind, 'rows': len(frame), 'columns': list(frame.columns),
                                 'sample': json.loads(frame.head(5).to_json(orient='records', date_format='iso'))})
        if kind == 'unknown':
            result['errors'].append({'table': table_name, 'row': 1, 'message': 'Chưa nhận diện cấu trúc cột. Dùng file mẫu hoặc nhờ GPT ánh xạ cột.'})
            continue
        for i, r in enumerate(frame.to_dict('records'), 2):
            try:
                if kind=='features':
                    from .engine import clean,adapter_module
                    f=clean(r);sku=f.get('sku_code')
                    if sku not in master or f.get('date')!=day:raise ValueError('Feature V4 sai SKU/ngày mục tiêu.')
                    if any(x['sku_code']==sku for x in result['feature_rows']):raise ValueError('Trùng feature SKU.')
                    if timestamp(f['decision_at'])>cutoff(day) or timestamp(f['decision_at']).date().isoformat()!=day:raise ValueError('decision_at V4 sai cutoff/ngày.')
                    if str(f.get('history_through','9999'))>=day or str(f.get('weather_reference_date','9999'))>=day:raise ValueError('Feature chứa lịch sử/thời tiết hiện tại hoặc tương lai.')
                    for column in adapter_module()._M2_BUNDLE['preprocessor'].numeric_cols:
                        if column in ['sold_calendar_lag1','sold_calendar_lag7'] and f.get(column) is None and f.get(column+'_missing')==1 and f.get(column+'_fallback_observed_sales') is not None and math.isfinite(float(f[column+'_fallback_observed_sales'])):continue
                        if f.get(column) is None or not math.isfinite(float(f[column])):raise ValueError('Thiếu/sai feature '+column)
                    result['feature_rows'].append(f)
                elif kind == 'history':
                    d, sku = iso(r['date']), str(r['sku_code']).strip()
                    if sku not in master:
                        raise ValueError('SKU không có trong SKU master V4')
                    if d >= day:
                        raise ValueError('Lịch sử phải trước ngày mục tiêu; dữ liệu hiện tại/tương lai không được làm feature')
                    key = (d, sku)
                    if key in history_keys:
                        raise ValueError('Trùng khóa ngày–SKU')
                    if 'available_at' in r and not pd.isna(r['available_at']):
                        if timestamp(r['available_at']) > cutoff(day):
                            raise ValueError('Lịch sử chưa có tại thời điểm dự báo 06:00 (available_at).')
                    if {'prepared_qty','censored_demand_flag'}<=cols:
                        prep=integer(r['prepared_qty'],'prepared_qty');sold=integer(r['sold_qty'],'sold_qty');censor=integer(r['censored_demand_flag'],'censored_demand_flag')
                        if prep<sold or censor not in [0,1]:raise ValueError('prepared >= sold, censor nhận 0/1.')
                        result['outcomes'].append({'date':d,'sku_code':sku,'prepared_qty':prep,'sold_qty':sold,'stockout':censor,'censored_demand_flag':censor})
                    history_keys.add(key)
                    result['history'].append({'date': d, 'sku_code': sku, 'sold_qty': integer(r['sold_qty'], 'sold_qty'),
                        'available_at': str(r['available_at']) if 'available_at' in r and not pd.isna(r['available_at']) else None})
                elif kind == 'weather':
                    d = iso(r['date'])
                    if d != day:
                        continue
                    if result['weather'] is not None:
                        raise ValueError('Trùng dự báo cho ngày mục tiêu')
                    rain = float(r['forecast_rain_mm_previous_day1'])
                    temp = float(r['forecast_temperature_max_c_previous_day1'])
                    if not math.isfinite(rain) or not math.isfinite(temp) or not 0 <= rain <= 1000 or not -20 <= temp <= 60:
                        raise ValueError('Mưa/nhiệt độ không hợp lệ')
                    weather_check(day, r, trusted_demo=False)
                    issued = r.get('issued_at')
                    dt = date.fromisoformat(day)
                    holiday = integer(r.get('is_public_holiday', 0), 'is_public_holiday')
                    festival = integer(r.get('is_festival_non_public', 0), 'is_festival_non_public')
                    if holiday not in [0, 1] or festival not in [0, 1]:
                        raise ValueError('Cờ ngày lễ và sự kiện chỉ nhận 0 hoặc 1.')
                    result['weather'] = {'weekday_iso': dt.isoweekday(), 'is_weekend': int(dt.weekday() >= 5),
                        'month': dt.month, 'day_of_year': dt.timetuple().tm_yday,
                        'is_public_holiday': holiday, 'is_festival_non_public': festival,
                        'forecast_rain_mm_previous_day1': rain, 'forecast_temperature_max_c_previous_day1': temp,
                        'forecast_source': str(r.get('forecast_source', 'UPLOADED_FORECAST')),
                        'issued_at': str(issued) if issued is not None else None,'weather_reference_date':str(r.get('weather_reference_date') or (date.fromisoformat(day)-__import__('datetime').timedelta(days=1)).isoformat()),'date':day,
                        'available_at': str(r['available_at']) if 'available_at' in r and not pd.isna(r['available_at']) else str(issued)}
                else:
                    sku = str(r['sku_code']).strip()
                    if sku not in master:
                        raise ValueError('SKU không có trong master')
                    minute, quantity = integer(r['minute'], 'minute'), integer(r['quantity'], 'quantity')
                    if not 360 <= minute < 1320 or not quantity:
                        raise ValueError('Phút giao dịch phải từ 06:00 đến trước 22:00; số lượng dương')
                    if 'date' in r and iso(r['date']) != day:
                        raise ValueError('Ngày giao dịch khác ngày mục tiêu')
                    result['transactions'].append({'sku_code': sku, 'minute': minute, 'quantity': quantity})
            except (ValueError, TypeError, KeyError, OverflowError) as e:
                result['errors'].append({'table': table_name, 'row': i, 'message': str(e)})
    if result['history'] and result['transactions']:
        result['errors'].append({'row': 1, 'message': 'Tách lịch sử và giao dịch hiện tại thành hai lượt nhập để xác nhận riêng.'})
    if result['history']:
        for sku in master:
            count = sum(r['sku_code'] == sku for r in result['history'])
            if count < 7:
                result['warnings'].append(f'{sku}: ít hơn 7 ngày lịch sử; model sẽ dùng giá trị dự phòng đã khóa.')
    if result['feature_rows']:
        if len(result['feature_rows'])!=len(master) or {x['sku_code'] for x in result['feature_rows']}!=set(master):result['errors'].append({'row':1,'message':'Feature V4 cần đủ 7 SKU không trùng.'})
        if result['weather'] is not None:result['weather']['v4_features']={x['sku_code']:x for x in result['feature_rows']}
    result['quality_policy'] = 'GD5-v1'
    result['prediction_as_of'] = cutoff(day).isoformat()
    result['source_assurance'] = 'User-declared upload; SHA256 chứng minh nội dung, không chứng minh nguồn POS/JMA.'
    result['history_availability'] = 'declared_timestamps' if result['history'] and all(r.get('available_at') for r in result['history']) else 'date_only_unverified'
    if result['history'] and result['history_availability']!='declared_timestamps':
        result['warnings'].append('Lịch sử chỉ có ngày bán chưa chứng minh lúc dữ liệu thực sự sẵn có; cần available_at để audit đầy đủ.')
    if result['history']:
        result['freshness'] = history_quality(day, {(r['date'],r['sku_code']):r['sold_qty'] for r in result['history']}, master)
        # Full coverage and freshness are enforced at inference, preserving preview diagnostics for partial uploads.
        for q in result['freshness']:
            if q['status'] == 'BLOCK':
                result['warnings'].append(q['sku'] + ': thiếu/quá cũ; sẽ chặn tạo dự báo nếu không đủ dữ liệu.')
    result['quarantine'] = bool(result['errors'])
    result['valid'] = not result['errors'] and bool(result['history'] or result['weather'] or result['transactions'] or result['feature_rows'])
    result['quarantine'] = not result['valid']
    return result
