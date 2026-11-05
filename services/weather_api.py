"""Fetch Open-Meteo weather with explicit vintage limits for historical data."""
from datetime import date, datetime, timedelta, timezone
import math
import httpx

from .quality import VN, cutoff, weather_check

FORECAST_URL = 'https://api.open-meteo.com/v1/forecast'
RUN_URL = 'https://single-runs-api.open-meteo.com/v1/forecast'
PREVIOUS_RUNS_URL = 'https://previous-runs-api.open-meteo.com/v1/forecast'
EARLIEST_RUN = date(2024, 3, 14)


def fetch_weather(day, latitude, longitude, *, now=None, client=None):
    try:
        target = date.fromisoformat(day)
        latitude, longitude = float(latitude), float(longitude)
    except (ValueError, TypeError):
        raise ValueError('Ngày và tọa độ thời tiết không hợp lệ.') from None
    if not all(map(math.isfinite, (latitude, longitude))) or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError('Tọa độ thời tiết nằm ngoài phạm vi hợp lệ.')
    captured = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    current = target >= captured.astimezone(VN).date()
    if current and captured > cutoff(day):
        raise ValueError('Đã qua cutoff 06:00 ngày mục tiêu; không thể lấy forecast mới rồi coi là đã có trước quyết định.')
    if current and (target - captured.astimezone(VN).date()).days > 14:
        raise ValueError('Ngày mục tiêu vượt tầm dự báo Open-Meteo 15 ngày.')
    reference = target - timedelta(days=1)
    historical_lead = not current and target - timedelta(days=2) < EARLIEST_RUN
    params = dict(latitude=latitude, longitude=longitude, timezone='Asia/Ho_Chi_Minh',
                  daily='precipitation_sum,temperature_2m_max', start_date=reference.isoformat(), end_date=day)
    url = FORECAST_URL
    run_at = None
    if not current and not historical_lead:
        # This run precedes both forecast dates. +6h availability estimate is
        # still 29 hours before the planning cutoff.
        run_at = datetime.combine(target - timedelta(days=2), datetime.min.time(), timezone.utc).replace(hour=12)
        params.pop('daily')
        params.pop('start_date')
        params.pop('end_date')
        params.update(hourly='precipitation,temperature_2m', forecast_days=4,
                      models='ecmwf_ifs', run=run_at.strftime('%Y-%m-%dT%H:%M'))
        url = RUN_URL
    elif historical_lead:
        params.pop('daily')
        params.update(hourly='precipitation_previous_day1,temperature_2m_previous_day1',models='jma_gsm')
        url = PREVIOUS_RUNS_URL
    try:
        if client is None:
            with httpx.Client(timeout=20) as owned:
                response = owned.get(url, params=params)
        else:
            response = client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ValueError('Không lấy được dự báo Open-Meteo cho ngày và lần chạy đã chọn. Kiểm tra mạng hoặc ngày mục tiêu.') from exc
    if now is None:
        captured = datetime.now(timezone.utc)
    if current and captured > cutoff(day):
        raise ValueError('API trả sau cutoff 06:00; forecast này chưa có tại thời điểm lập kế hoạch.')
    if historical_lead:
        hourly=payload.get('hourly') or {}
        times=hourly.get('time') or []
        rains=hourly.get('precipitation_previous_day1') or []
        temps=hourly.get('temperature_2m_previous_day1') or []
        if len(times)!=len(rains) or len(times)!=len(temps):
            raise ValueError('Open-Meteo JMA Previous Runs trả dữ liệu giờ không đồng bộ.')
        values={}
        for wanted in (reference.isoformat(),day):
            rows=[(rains[i],temps[i]) for i,stamp in enumerate(times) if stamp.startswith(wanted+'T')]
            if len(rows)!=24 or any(v is None for pair in rows for v in pair):
                raise ValueError('Open-Meteo JMA Previous Runs không trả đủ 24 giờ cho ngày '+wanted+'.')
            values[wanted]=(sum(float(pair[0]) for pair in rows),max(float(pair[1]) for pair in rows))
        rain,temp=values[reference.isoformat()]
        target_rain,target_temp=values[day]
    elif run_at:
        hourly = payload.get('hourly') or {}
        times = hourly.get('time') or []
        rains = hourly.get('precipitation') or []
        temps = hourly.get('temperature_2m') or []
        if len(times) != len(rains) or len(times) != len(temps):
            raise ValueError('Open-Meteo trả dữ liệu giờ không đồng bộ.')
        values = {}
        for wanted in (reference.isoformat(), day):
            rows = [(rains[i], temps[i]) for i, stamp in enumerate(times) if stamp.startswith(wanted + 'T')]
            if len(rows) != 24 or any(v is None for pair in rows for v in pair):
                raise ValueError('Open-Meteo không trả đủ 24 giờ cho ngày ' + wanted + '.')
            values[wanted] = (sum(float(pair[0]) for pair in rows), max(float(pair[1]) for pair in rows))
        rain, temp = values[reference.isoformat()]
        target_rain, target_temp = values[day]
    else:
        daily = payload.get('daily') or {}
        if daily.get('time') != [reference.isoformat(), day] or len(daily.get('precipitation_sum') or []) != 2 or len(daily.get('temperature_2m_max') or []) != 2:
            raise ValueError('Open-Meteo không trả đủ dự báo cho ngày tham chiếu và ngày mục tiêu.')
        rain, temp = daily['precipitation_sum'][0], daily['temperature_2m_max'][0]
        target_rain, target_temp = daily['precipitation_sum'][1], daily['temperature_2m_max'][1]
    if any(v is None for v in (rain, temp, target_rain, target_temp)) or not all(math.isfinite(float(v)) for v in (rain, temp, target_rain, target_temp)):
        raise ValueError('Open-Meteo trả giá trị thời tiết trống hoặc không hợp lệ.')
    if not all(0 <= float(v) <= 1000 for v in (rain, target_rain)) or not all(-20 <= float(v) <= 60 for v in (temp, target_temp)):
        raise ValueError('Open-Meteo trả mưa hoặc nhiệt độ ngoài phạm vi hợp lệ.')
    # The API does not expose an exact historical publication timestamp. For an
    # archived run, +6h is only a conservative estimate, never a verified fact.
    issued = run_at if run_at else None if historical_lead else captured
    available = run_at + timedelta(hours=6) if run_at else None if historical_lead else captured
    d = target
    result = dict(date=day, weekday_iso=d.isoweekday(), is_weekend=int(d.weekday() >= 5),
                  month=d.month, day_of_year=d.timetuple().tm_yday,
                  is_public_holiday=0, is_festival_non_public=0,
                  forecast_rain_mm_previous_day1=float(rain),
                  forecast_temperature_max_c_previous_day1=float(temp),
                  forecast_source='OPEN_METEO_ECMWF_SINGLE_RUN' if run_at else 'OPEN_METEO_JMA_GSM_PREVIOUS_DAY1' if historical_lead else 'OPEN_METEO_FORECAST_SNAPSHOT',
                  issued_at=issued.astimezone(VN).isoformat() if issued else None,
                  available_at=available.astimezone(VN).isoformat() if available else None,
                  weather_reference_date=reference.isoformat(),
                  weather_provenance=dict(vintage_verified=not bool(run_at or historical_lead),
                      timestamp_kind='model_initialization' if run_at else 'fixed_24h_lead_no_run_timestamp' if historical_lead else 'api_snapshot_captured',
                      forecast_lead_hours=24 if historical_lead else None,
                      run_initialized_at=run_at.isoformat() if run_at else None,
                      availability_basis='estimated_6h_after_run' if run_at else 'fixed_24h_lead_issue_time_unverified' if historical_lead else 'observed_api_response',
                      captured_at=captured.isoformat(), latitude=latitude, longitude=longitude,
                      target_date_forecast=dict(date=day, precipitation_sum_mm=float(target_rain),
                                                temperature_2m_max_c=float(target_temp)),
                      api_url=url, holiday_flags='not_provided_by_weather_api'))
    weather_check(day, result, trusted_demo=historical_lead)
    return result
