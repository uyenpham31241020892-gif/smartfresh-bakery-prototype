import io
import hashlib
import json
import zipfile
import numpy as np
import pandas as pd
import pytest
from services.engine import DATA, ROOT
from services.ingestion import inspect, tables


def test_archive_finance_and_accuracy_reconcile():
    summary=json.loads((ROOT/'reference/drive_v9/summary.json').read_text())
    for system in ['BASELINE','M1_M2_SELECTED']:
        p=DATA/'outputs'/f'{system}_daily_sep.csv'
        assert hashlib.sha256(p.read_bytes()).hexdigest()==summary['outputs_sha256'][p.name]
        daily=pd.read_csv(p)
        ledger=pd.read_csv(DATA/'outputs'/f'{system}_transaction_ledger_sep.csv')
        assert len(daily)==240 and not daily.duplicated(['date','sku_code']).any()
        assert (daily.prepared_qty==daily.sold_qty+daily.waste_qty).all()
        amounts=ledger.groupby(['date','sku_code']).paid_vnd.sum()
        counts=ledger.groupby(['date','sku_code']).size()
        indexed=daily.set_index(['date','sku_code'])
        np.testing.assert_array_equal(indexed.revenue_vnd,amounts.reindex(indexed.index,fill_value=0))
        np.testing.assert_array_equal(indexed.sold_qty,counts.reindex(indexed.index,fill_value=0))
        for key,val in summary['systems'][system].items():
            assert int(daily[key].sum())==val
    daily=pd.read_csv(DATA/'outputs/M1_M2_SELECTED_daily_sep.csv').set_index(['date','sku_code'])
    ledger=pd.read_csv(DATA/'outputs/M1_M2_SELECTED_transaction_ledger_sep.csv')
    regular=ledger[ledger.origin_type=='BASE_SYNTHETIC'].groupby(['date','sku_code']).size()
    actual=regular.reindex(daily.index,fill_value=0)+daily.lost_regular_qty
    predictions=pd.read_csv(DATA/'outputs/M2_FORECASTS.csv').set_index(['date','sku_code']).predicted_base_demand.reindex(daily.index)
    errors=(predictions-actual).abs()
    assert errors.sum()/actual.sum()*100 == pytest.approx(summary['m2_metrics']['wape_pct'],abs=1e-8)
    assert errors.mean()==pytest.approx(summary['m2_metrics']['mae'],abs=1e-8)


def test_ingest_history_duplicates_future_and_unknown_sku(engine):
    content=b'date,sku_code,sold_qty\n2022-08-15,BK-001,9\n2022-08-15,BK-001,8\n2022-08-16,BK-002,3\n2022-08-15,UNKNOWN,2\n2022-08-14,BK-001,-2\n'
    result=inspect('data.csv',content,'2022-08-16',engine.master)
    assert not result['valid']
    assert len(result['errors'])==4
    assert [e['row'] for e in result['errors']]==[3,4,5,6]


def test_new_weather_requires_availability_timestamp(engine):
    content=b'date,forecast_rain_mm_previous_day1,forecast_temperature_max_c_previous_day1,issued_at\n2026-10-21,6,31,2026-10-21T07:00:00+07:00\n'
    p=inspect('weather.csv',content,'2026-10-21',engine.master)
    assert not p['valid'] and '06:00' in p['errors'][0]['message']
    p=inspect('weather.csv',content.replace(b'07:00:00',b'05:00:00'),'2026-10-21',engine.master)
    assert p['valid']


def test_zip_ingestion_never_loads_models_or_executes_scripts(engine):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        z.writestr('history.csv','date,sku_code,sold_qty\n2022-08-15,BK-001,9\n')
        z.writestr('model.joblib',b'not a model')
        z.writestr('../../attack.py','raise RuntimeError("should never run")')
    p=inspect('upload.zip',out.getvalue(),'2022-08-16',engine.master)
    assert p['valid'] and len(p['history'])==1


def test_xlsx_sheets_are_understood(engine):
    out=io.BytesIO()
    with pd.ExcelWriter(out,engine='openpyxl') as w:
        pd.DataFrame([{'date':'2022-08-15','sku_code':'BK-001','sold_qty':7}]).to_excel(w,index=False,sheet_name='history')
    p=inspect('sales.xlsx',out.getvalue(),'2022-08-16',engine.master)
    assert p['valid'] and p['history'][0]['sold_qty']==7
