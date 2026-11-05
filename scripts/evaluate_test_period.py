"""Compare the completed 62-day JOINT run with the same generated market baseline."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOINT = ROOT / 'docs/JOINT_TWO_MONTH_JOINT.json'
BASELINE = ROOT / 'docs/JOINT_TWO_MONTH_ROLLING7.json'


def summary(rows):
    prepared = sum(r['prepared'] for r in rows)
    sold = sum(r['sold'] for r in rows)
    return dict(days=len(rows),prepared=prepared,sold=sold,stock=sum(r['stock'] for r in rows),
                sell_through_pct=round(100*sold/prepared,2),
                revenue_vnd=sum(r['revenue_vnd'] for r in rows),
                contribution_vnd=sum(r['contribution_vnd'] for r in rows),
                stockout_sku_days=sum(r['stockout_skus'] for r in rows),
                preparation_base_mae=round(sum(abs(r['prepared']-r['base_intent']) for r in rows)/len(rows),2))


def main():
    joint=json.loads(JOINT.read_text(encoding='utf-8'))
    baseline=json.loads(BASELINE.read_text(encoding='utf-8'))
    a,b=joint['rows'],baseline['rows']
    if len(a)!=62 or len(b)!=62:
        raise ValueError('Both branches must contain all 62 test days.')
    for left,right in zip(a,b):
        if left['day']!=right['day'] or left['base_intent']!=right['base_intent'] or left['market_context']!=right['market_context']:
            raise ValueError('Branches have different market scenarios.')
        if [(p['sku'],p['base_intent']) for p in left['skus']]!=[(p['sku'],p['base_intent']) for p in right['skus']]:
            raise ValueError('Branches have different SKU demand streams.')
    periods={'july':(0,31),'august':(31,62),'all':(0,62),
             'july_first_half':(0,16),'july_second_half':(16,31),
             'august_first_half':(31,47),'august_second_half':(47,62)}
    results={name:{'joint':summary(a[start:end]),'rolling7':summary(b[start:end])}
             for name,(start,end) in periods.items()}
    for section in results.values():
        section['joint_minus_rolling7']={key:round(section['joint'][key]-section['rolling7'][key],2)
                                         for key in ('prepared','sold','stock','revenue_vnd','contribution_vnd',
                                                     'stockout_sku_days','preparation_base_mae')}
    factors=[p['online'].get('online_factor',1) for r in a for p in r['skus']]
    update_days=sum(any(p['online'].get('online_updates',0)>0 for p in r['skus']) for r in a)
    previous=ROOT/'docs/JOINT_TEST_MONTH_AUDIT.json'
    if previous.exists():
        old=json.loads(previous.read_text(encoding='utf-8'))['policies']['joint']
        if len(old)==31 and [r['base_intent'] for r in old]==[r['base_intent'] for r in a[:31]]:
            results['previous_july_policy']=summary(old)
            results['july_joint_minus_previous']={key:round(results['july']['joint'][key]-results['previous_july_policy'][key],2)
                                                    for key in ('prepared','sold','stock','revenue_vnd','contribution_vnd',
                                                                'stockout_sku_days','preparation_base_mae')}
    artifact={'period':joint['period'],'seed':joint['seed'],'market_equal':True,
              'online_factor_min':min(factors),'online_factor_max':max(factors),
              'days_using_prior_closed_sessions':update_days,'periods':results}
    (ROOT/'docs/JOINT_TWO_MONTH_EVALUATION.json').write_text(json.dumps(artifact,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(artifact,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
