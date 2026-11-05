"""Gate the revised 62-day scenario on waste, revenue and contribution."""
import json
import sqlite3
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.evaluate_test_period import summary
JOINT=ROOT/'docs/JOINT_TWO_MONTH_JOINT_V3FULL2.json'
BASELINE=ROOT/'docs/JOINT_TWO_MONTH_SEASONAL_V3FULL.json'
OUTPUT=ROOT/'docs/JOINT_TWO_MONTH_V3_EVALUATION.json'


def shelf_coverage(report, start, end):
    with sqlite3.connect(report['db_path']) as connection:
        states={s['day']:s for (raw,) in connection.execute('SELECT state FROM sessions')
                if (s:=json.loads(raw))['phase']=='closed'}
    selected=[states[row['day']] for row in report['rows'][start:end]]
    positive=sum(p.get('stock_at_2130',0)>0 for state in selected for p in state['products'].values())
    count=sum(len(state['products']) for state in selected)
    return {'sku_days_with_stock_at_2130':positive,'sku_days':count,
            'coverage_pct':round(100*positive/count,2)}


def evaluate():
    joint=json.loads(JOINT.read_text(encoding='utf-8'))
    baseline=json.loads(BASELINE.read_text(encoding='utf-8'))
    a,b=joint['rows'],baseline['rows']
    if len(a)!=62 or len(b)!=62 or joint['simulator_version']!='AEON_GENERATED_POS_V3':
        raise ValueError('Expected 62 completed V3 POS days in both branches.')
    for left,right in zip(a,b):
        if left['day']!=right['day'] or left['market_context']!=right['market_context']:
            raise ValueError('The branches used different market contexts.')
        if [(p['sku'],p['base_intent']) for p in left['skus']]!=[(p['sku'],p['base_intent']) for p in right['skus']]:
            raise ValueError('The branches used different SKU demand streams.')
    periods={'july':(0,31),'august':(31,62),'all':(0,62),
             'july_first_half':(0,16),'july_second_half':(16,31),
             'august_first_half':(31,47),'august_second_half':(47,62)}
    results={}
    for name,(start,end) in periods.items():
        j=summary(a[start:end]);base=summary(b[start:end])
        paired=list(zip(a[start:end],b[start:end]))
        results[name]={'joint':j,'seasonal_baseline':base,
                       'shelf_at_2130':{'joint':shelf_coverage(joint,start,end),
                                        'seasonal_baseline':shelf_coverage(baseline,start,end)},
                       'days_with_less_waste':sum(left['stock']<right['stock'] for left,right in paired),
                       'days_with_more_waste':sum(left['stock']>right['stock'] for left,right in paired),
                       'days_with_higher_revenue':sum(left['revenue_vnd']>right['revenue_vnd'] for left,right in paired),
                       'joint_minus_baseline':{key:round(j[key]-base[key],2)
                           for key in ('prepared','sold','stock','revenue_vnd','contribution_vnd',
                                       'stockout_sku_days','preparation_base_mae')}}
    gates={name:(results[name]['joint']['stock']<results[name]['seasonal_baseline']['stock'] and
                 results[name]['joint']['revenue_vnd']>=results[name]['seasonal_baseline']['revenue_vnd'] and
                 results[name]['joint']['contribution_vnd']>=results[name]['seasonal_baseline']['contribution_vnd'] and
                 results[name]['shelf_at_2130']['joint']['coverage_pct']>=80)
           for name in ('july','august','all')}
    daily_base=[row['base_intent'] for row in a]
    daily_sold=[row['sold'] for row in a]
    factors=[p['online'].get('online_factor',1) for row in a for p in row['skus']]
    result={'period':joint['period'],'simulator_version':joint['simulator_version'],
            'baseline_policy':'SEASONAL_SAME_WEEKDAY_CENSOR_AWARE_X10_STATIC_BAKES',
            'market_equal':True,'gates':gates,'passed':all(gates.values()),
            'base_intent_range':[min(daily_base),max(daily_base)],
            'joint_sold_range':[min(daily_sold),max(daily_sold)],
            'online_factor_range':[min(factors),max(factors)],'periods':results}
    OUTPUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if not result['passed']:
        raise SystemExit('The revised policy did not pass waste, revenue and contribution gates for both months.')
    return result


if __name__=='__main__':
    evaluate()
