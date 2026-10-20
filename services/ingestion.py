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
                ['history.csv', 'history_through_aug15_synthetic.csv', 'weather.csv', 'weather_forecast_feed_2022.csv']
                and ('01_Dataset_moi/' in n or '/' not in n)]
            if not candidates:
                raise ValueError('ZIP cần history.csv và/hoặc weather.csv; ZIP V9 gốc cũng được hỗ trợ.')
            result = []
            for n in candidates:
                result += tables(n, z.read(n))
            return result
    raise ValueError('Hỗ trợ CSV, XLSX hoặc ZIP dữ liệu; chưa hỗ trợ đọc PDF thành giao dịch.')


def inspect(name, raw, day, master, mapping=None):
    day = iso(day)
    result = {'filename': PurePosixPath(name.replace('\\', '/')).name, 'sha256': hashlib.sha256(raw).hexdigest(),
              'day': day, 'errors': [], 'warnings': [], 'history': [], 'weather': None, 'transactions': [], 'tables': []}
    if day > '2022-09-30':
        result['warnings'].append('Model được khóa từ dữ liệu năm 2022. Dự báo cho ngày ngoài giai đoạn này chưa được xác nhận độ chính xác.')
    history_keys = set()
    for table_name, frame in tables(name, raw):
        if len(frame) > 20000 or len(frame.columns) > 100:
            raise ValueError('Mỗi bảng tối đa 20.000 dòng và 100 cột.')
        frame.columns = [str(c).strip() for c in frame.columns]
        frame = frame.rename(columns=mapping or {c: ALIASES.get(c.lower(), c) for c in frame.columns})
        if frame.columns.duplicated().any():
            raise ValueError('Tên cột trùng sau ánh xạ. Hãy giữ mỗi trường ở một cột.')
        cols = set(frame.columns)
        kind = 'history' if {'date', 'sku_code', 'sold_qty'} <= cols else 'weather' if {'date', 'forecast_rain_mm_previous_day1', 'forecast_temperature_max_c_previous_day1'} <= cols else 'transactions' if {'sku_code', 'minute', 'quantity'} <= cols else 'unknown'
        result['tables'].append({'name': table_name, 'kind': kind, 'rows': len(frame), 'columns': list(frame.columns),
                                 'sample': json.loads(frame.head(5).to_json(orient='records', date_format='iso'))})
        if kind == 'unknown':
            result['errors'].append({'table': table_name, 'row': 1, 'message': 'Chưa nhận diện cấu trúc cột. Dùng file mẫu hoặc nhờ GPT ánh xạ cột.'})
            continue
        for i, r in enumerate(frame.to_dict('records'), 2):
            try:
                if kind == 'history':
                    d, sku = iso(r['date']), str(r['sku_code']).strip()
                    if sku not in master:
                        raise ValueError('SKU không có trong SKU master V9')
                    if d >= day:
                        raise ValueError('Lịch sử phải trước ngày mục tiêu; dữ liệu hiện tại/tương lai không được làm feature')
                    key = (d, sku)
                    if key in history_keys:
                        raise ValueError('Trùng khóa ngày–SKU')
                    history_keys.add(key)
                    result['history'].append({'date': d, 'sku_code': sku, 'sold_qty': integer(r['sold_qty'], 'sold_qty')})
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
                    issued = r.get('issued_at')
                    if issued is not None and not pd.isna(issued):
                        issued = pd.Timestamp(issued)
                        cutoff = pd.Timestamp(day + 'T06:00:00+07:00')
                        if issued.tzinfo is None or issued > cutoff:
                            raise ValueError('issued_at cần múi giờ và không sau 06:00 ngày lập kế hoạch')
                    elif not ('JMA_GSM_PREVIOUS_DAY1' in str(r.get('forecast_source', '')) and day <= '2022-09-30'):
                        raise ValueError('Dự báo mới cần issued_at có múi giờ, trước 06:00 ngày mục tiêu')
                    else:
                        result['warnings'].append('Forecast V9 có giả định previous_day1; chưa xác minh timestamp phát hành từng giờ.')
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
                        'issued_at': str(issued) if issued is not None else None}
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
    result['valid'] = not result['errors'] and bool(result['history'] or result['weather'] or result['transactions'])
    return result
