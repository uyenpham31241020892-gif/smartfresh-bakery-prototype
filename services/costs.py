"""User-authorized simulation cost assumption; never a trained model feature."""
from decimal import Decimal, ROUND_HALF_UP

COST_POLICY_ID = 'ASSUMED_45PCT_LIST_PRICE_ALL_PREPARED_V1'

def estimate(products):
    """Charge all confirmed preparation once, including unsold stock."""
    rows=[]
    for sku,p in products.items():
        unit=int((Decimal(str(p['price']))*Decimal('0.45')).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
        rows.append(dict(sku=sku,unit_cost_assumed=unit,prepared=p['prepared'],
                         preparation_cost=unit*p['prepared'],unsold_cost_included=unit*p['stock']))
    revenue=sum(p['revenue'] for p in products.values())
    cost=sum(r['preparation_cost'] for r in rows)
    return dict(policy_id=COST_POLICY_ID,status='ASSUMED_NOT_VERIFIED',rate=.45,
                basis='LIST_PRICE_TIMES_ALL_CONFIRMED_PREPARED',rows=rows,
                revenue=revenue,preparation_cost=cost,contribution_before_overhead=revenue-cost,
                unsold_cost_included=sum(r['unsold_cost_included'] for r in rows),
                disposal_fee=None,operating_expenses=None,net_profit=None)
