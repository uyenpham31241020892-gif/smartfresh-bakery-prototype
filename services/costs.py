"""Use V4 unit production costs, charge all prepared units exactly once."""
import json
from pathlib import Path
COST_POLICY_ID='V4_UNIT_COST_ALL_PREPARED_DISPOSAL_MARKDOWN_V1'
MASTER=json.loads((Path(__file__).resolve().parents[1]/'v4/artifacts_build/models/operational_lookup.json').read_text())
def estimate(products,closed=False):
    rows=[]
    for sku,p in products.items():
        unit=int(p.get('unit_cost',MASTER[sku]['unit_production_cost_vnd_assumed']))
        rows.append(dict(sku=sku,unit_cost_assumed=unit,prepared=p['prepared'],preparation_cost=unit*p['prepared'],unsold_cost_included=unit*p['stock']))
    revenue=sum(p['revenue'] for p in products.values());cost=sum(r['preparation_cost'] for r in rows)
    disposal=sum(p['stock']*MASTER[sku]['unit_disposal_cost_vnd_assumed'] for sku,p in products.items()) if closed else 0
    markdown=sum(p.get('markdown_cost',0) for p in products.values())
    return dict(policy_id=COST_POLICY_ID,status='V4_ASSUMED_NOT_AEON_VERIFIED',rate=None,basis='V4_UNIT_COST_TIMES_ALL_PREPARED',rows=rows,revenue=revenue,
        preparation_cost=cost,contribution_before_overhead=revenue-cost-disposal-markdown,unsold_cost_included=sum(r['unsold_cost_included'] for r in rows),
        disposal_fee=disposal,disposal_pending=not closed,markdown_cost=markdown,operating_expenses=None,net_profit=None,
        note='Lãi góp mô phỏng = doanh thu − giá vốn toàn bộ bánh đã làm − phí hủy 150đ/bánh cuối ca − chi phí đổi giá. E-ink 0đ/lần, tem 350đ/lần; đây là giả định vận hành, không đổi chi phí 350đ trong quyết định V4 đã khóa.')
