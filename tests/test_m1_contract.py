"""Hand-calculated contract edge cases, independent of Engine feature builder."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.engine import Engine
@pytest.fixture(scope='module')
def engine():return Engine()
@pytest.mark.parametrize('s30,s60,pace,acc,cover,surplus',[(6,8,.2,6/30-8/60,100,0),(0,6,.1,-.1,200,5),(0,0,0,0,None,20)])
def test_m1_units_and_zero_pace(engine,s30,s60,pace,acc,cover,surplus):
 row=engine.price('TP-DN-001',0,20,40,0,s30,s60,0,{'date':'2022-05-02'})
 f=row['model_features']
 assert f['sales_pace_units_per_minute']==pytest.approx(pace)
 assert f['pace_acceleration']==pytest.approx(acc)
 assert f['inventory_cover_minutes']==cover
 assert f['projected_surplus_at_current_pace']==surplus
 assert f['baseline_announced_2100_pct'] is None

def test_explicit_observed_state_is_preserved(engine):
 row=engine.price('TP-DN-001',1,20,40,0,2,4,0,{'date':'2022-05-02'},observed_context={'shelf_inventory':7,'backroom_inventory':13,'observed_buyers_last30':1,'observed_stockout_last60_minutes':15})
 f=row['model_features']
 assert (f['shelf_inventory'],f['backroom_inventory'],f['observed_buyers_last30'],f['observed_stockout_last60_minutes'])==(7,13,1,15)
