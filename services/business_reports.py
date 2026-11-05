"""Read-only operating history. Never a model input or a synthetic backfill."""
import calendar
import json
from datetime import date, timedelta

from .evaluation import reconcile
from .costs import estimate

METRICS = ('revenue', 'sold', 'prepared', 'stock', 'contribution_before_overhead','average_price','discount_value','weighted_discount_pct')


def totals(state):
    products = state['products'].values()
    result = {key: sum(p[key] for p in products) for key in ('revenue', 'sold', 'prepared', 'stock')}
    result['contribution_before_overhead'] = estimate(state['products'],closed=state.get('phase')=='closed')['contribution_before_overhead']
    result['production_cost_assumed']=estimate(state['products'],closed=state.get('phase')=='closed')['preparation_cost']
    result['sell_through_pct'] = 100 * result['sold'] / result['prepared'] if result['prepared'] else None
    result['list_value']=sum(p['price']*p['sold'] for p in state['products'].values())
    result['discount_value']=result['list_value']-result['revenue']
    result['average_price']=result['revenue']/result['sold'] if result['sold'] else None
    result['weighted_discount_pct']=100*result['discount_value']/result['list_value'] if result['list_value'] else None
    result['discounted_units']=sum(t['qty'] for t in state['ledger'] if t['unit_price']<state['products'][t['sku']]['price'])
    result['transactions']=len(state['ledger'])
    return result


def product_metrics(state):
    return [dict(sku=sku,name=p.get('name',sku),list_price=p['price'],current_price=round(p['price']*(1-p.get('discount',0)/100)),stock_at_2130=p.get('stock_at_2130'),
                 **totals({**state,'products':{sku:p},'ledger':[t for t in state['ledger'] if t['sku']==sku]})) for sku,p in state['products'].items()]


def combine(states):
    grouped={}
    for s in states:
        for p in product_metrics(s):
            g=grouped.setdefault(p['sku'],dict(sku=p['sku'],name=p['name'],days=0,
                **{k:0 for k in ('prepared','sold','stock','revenue','list_value','discount_value','discounted_units','contribution_before_overhead','transactions')}))
            g['days']+=1
            for k in ('prepared','sold','stock','revenue','list_value','discount_value','discounted_units','contribution_before_overhead','transactions'):g[k]+=p[k]
    for g in grouped.values():
        g['average_price']=g['revenue']/g['sold'] if g['sold'] else None
        g['sell_through_pct']=100*g['sold']/g['prepared'] if g['prepared'] else None
        g['weighted_discount_pct']=100*g['discount_value']/g['list_value'] if g['list_value'] else None
    return list(grouped.values())


def hourly(state):
    rows=[]
    for start in range(480,min(state.get('minute',1320),1319)+1,60):
        tx=[t for t in state['ledger'] if start<=t.get('minute',-1)<start+60 and t.get('minute',-1)<=state.get('minute',1320)]
        quantity=sum(t['qty'] for t in tx);revenue=sum(t['paid'] for t in tx)
        rows.append(dict(minute=start,label=f'{start//60:02}:00',sold=quantity,revenue=revenue,
            average_price=revenue/quantity if quantity else None,
            discount_value=sum(state['products'][t['sku']]['price']*t['qty']-t['paid'] for t in tx)))
    return rows


def revenue_bridge(current,previous):
    if not current or not previous or current['average_price'] is None or previous['average_price'] is None:return None
    delta=current['revenue']-previous['revenue'];volume=round((current['sold']-previous['sold'])*previous['average_price'])
    return dict(revenue_change=delta,volume_component=volume,
        average_price_and_mix_component=delta-volume,rounding='INTEGER_VND; REMAINDER_ASSIGNED_TO_PRICE_MIX',
        qualification='ACCOUNTING_IDENTITY_NOT_CAUSAL; AVERAGE_PRICE_INCLUDES_PRODUCT_MIX')


def change(current, previous):
    if current is None or previous is None:
        return dict(value=None, percent=None, reason='missing_closed_day')
    delta = current - previous
    return dict(value=delta, percent=100 * delta / abs(previous) if previous else None,
                reason='zero_baseline' if not previous else None)


def report(store, sid, days=30, selected=None):
    if days not in (7, 30, 63, 90):
        raise ValueError('Chọn lịch sử 7, 30, 63 hoặc 90 ngày.')
    selected = selected or store.get(sid)
    end = date.fromisoformat(selected['day'])
    start = end - timedelta(days=days-1)
    # One comparable scenario only; multiple reruns of a day are not additional sales.
    scope_keys = ['mode', 'model_hashes' if selected.get('model_hashes') else 'model_version']
    if selected['mode'] == 'simulation':
        scope_keys += ['seed', 'simulator_version', 'simulator_hash']
    scope = {k: selected.get(k) for k in scope_keys}
    with store.connect() as db:
        states = [json.loads(r['state']) for r in db.execute(
            "SELECT state FROM sessions WHERE json_extract(state,'$.day')<=? "
            "AND json_extract(state,'$.phase')='closed' ORDER BY rowid", (selected['day'],))]
    daily = {}
    excluded_invalid = 0
    for s in states:
        if any(s.get(k) != v for k, v in scope.items()) or s['day'] == selected['day']:
            continue
        # Only the most recent saved closed rerun per date is represented.
        daily[s['day']] = s
    for day, s in list(daily.items()):
        if reconcile(s)['errors']:
            del daily[day]
            excluded_invalid += 1
    valid = not reconcile(selected)['errors']
    if selected['products'] and valid:
        daily[selected['day']] = selected
    rows = []
    for i in range(days):
        day = (start + timedelta(days=i)).isoformat()
        s = daily.get(day)
        rows.append(dict(day=day, session_id=s['id'] if s else None,model_version=s['model_version'] if s else None,
                         status=('closed' if s['phase']=='closed' else 'provisional') if s else 'missing',
                         metrics=totals(s) if s else None,products=product_metrics(s) if s else []))
    month = end.month - 1 or 12
    year = end.year if end.month > 1 else end.year - 1
    month_day = date(year, month, min(end.day, calendar.monthrange(year, month)[1]))
    comparison_days = dict(day=end-timedelta(days=1), week=end-timedelta(days=7), month=month_day)
    current = totals(selected) if valid and selected['phase']=='closed' and selected['products'] else None
    comparisons = {}
    for key, day in comparison_days.items():
        previous = daily.get(day.isoformat())
        base = totals(previous) if previous else None
        comparisons[key] = dict(day=day.isoformat(), previous=base,
            previous_products=product_metrics(previous) if previous else [],
            changes={k: change(current[k] if current else None, base[k] if base else None) for k in METRICS},
            revenue_bridge=revenue_bridge(current,base))
    closed=[s for day,s in daily.items() if start.isoformat()<=day<=end.isoformat() and s['phase']=='closed']
    selected_products=product_metrics(selected) if valid else []
    pricing_checks=[]
    if valid and selected.get('decisions'):
        proposal=selected.get('pending') or selected['decisions'][-1]
        pricing_checks=[dict(sku=r['sku'],reason=r.get('reason'),economic_gate=r.get('economic_gate')) for r in proposal.get('rows',[])+proposal.get('held_rows',[]) if r.get('economic_gate')]
        pricing_checks=list({r['sku']:r for r in pricing_checks}.values())
    return dict(session_id=sid, revision=selected['revision'], days=days, end_day=end.isoformat(),
                scope=scope, rows=rows, comparisons=comparisons, current=current,
                selected_metrics=totals(selected) if valid and selected['products'] else None,
                current_status='invalid' if not valid else 'closed' if current else 'provisional',
                closed_days=sum(r['status']=='closed' for r in rows), excluded_invalid=excluded_invalid,
                products=selected_products,period_products=combine(closed),hourly=hourly(selected) if valid else [],
                pricing_checks=pricing_checks,as_of_minute=selected.get('minute',1320),
                scenario_price_check=dict(status='ASSUMED_PRICE_SENSITIVITY_NOT_CAUSAL_EVIDENCE' if selected.get('weather',{}).get('price_response_scenario') else 'FIXED_CUSTOMERS_NO_PRICE_RESPONSE' if selected.get('simulator_version','').startswith('V4_VALIDATION_POS_REPLAY') else 'OBSERVATIONAL_NO_CAUSAL_IDENTIFICATION',
                    same_quantity_list_value=totals(selected)['list_value'] if valid else None,
                    same_quantity_price_reduction=totals(selected)['discount_value'] if valid else None,
                    inventory_change_due_to_price_by_simulator_rule=0 if selected.get('simulator_version','').startswith('V4_VALIDATION_POS_REPLAY') and not selected.get('weather',{}).get('price_response_scenario') else None,
                    qualification='SAME_PREPARED_QUANTITY; SIMULATOR_ASSUMPTION_NOT_REAL_WORLD_EVIDENCE'),
                price_effect_note='Giá trị giảm so niêm yết tính trên đúng lượng đã bán, không phải doanh thu bị mất nhân quả. '
                    'Tồn cuối ngày chưa phải số hủy vật lý. Không có bằng chứng giảm giá sinh thêm khách; chi phí giá vốn đơn vị V4 là giả định.',
                note='Chỉ ca lưu trong prototype cùng chế độ, trọng số model và seed/thị trường mô phỏng. '
                     'Policy cung ứng có thể khác phiên bản; đây là lịch sử kinh doanh, không phải bằng chứng tác động nhân quả. '
                     'Mỗi ngày lấy ca đã chốt tạo gần nhất; ngày đang chọn luôn dùng đúng ca đã chọn. '
                     'Không cộng các lần chạy lại, không trộn lịch sử train, không tự sinh ngày thiếu. '
                     'So sánh từng ngày với ngày trước, cùng thứ tuần trước và cùng ngày tháng trước '
                     '(tháng ngắn lấy ngày cuối tháng). Phần trăm chỉ tính khi cả hai ngày đã chốt.')


def analysis_context(data,section='overview',sku='all',cache_revision=None):
    if section not in ('overview','prices','products','baseline'):raise ValueError('Unknown report section')
    if sku!='all' and sku not in {p['sku'] for p in data['products']}:raise ValueError('Unknown report SKU')
    pick=lambda rows:[p for p in rows if sku=='all' or p['sku']==sku]
    daily=[]
    keys=('revenue','sold','prepared','stock','average_price','discount_value','weighted_discount_pct','contribution_before_overhead')
    for r in data['rows']:
        m=r['metrics'] if sku=='all' else next((p for p in r['products'] if p['sku']==sku),None)
        daily.append(dict(day=r['day'],status=r['status'],metrics={k:m.get(k) for k in keys} if m else None))
    compact=lambda rows:[{k:p.get(k) for k in ('sku','name','prepared','sold','stock','stock_at_2130','revenue','average_price','discount_value','discounted_units','contribution_before_overhead')} for p in pick(rows)]
    comparisons={k:{f:v[f] for f in ('day','previous','changes','revenue_bridge')} for k,v in data['comparisons'].items()}
    if sku!='all':
        current=next(iter(pick(data['products'])),None) if data['current_status']=='closed' else None
        comparisons={}
        for key,comp in data['comparisons'].items():
            previous=next(iter(pick(comp['previous_products'])),None)
            comparisons[key]=dict(day=comp['day'],previous=previous,
                changes={k:change(current.get(k) if current else None,previous.get(k) if previous else None) for k in METRICS},
                revenue_bridge=revenue_bridge(current,previous))
    return dict(scope=dict(days=data['days'],section=section,sku=sku,cache_revision=cache_revision),
        selected_day=data['end_day'],as_of_minute=data['as_of_minute'],revision=data['revision'],
        status=data['current_status'],closed_days=data['closed_days'],daily=daily[-30:],daily_detail_limit=30,
        selected=data['selected_metrics'] if sku=='all' else next(iter(pick(data['products'])),None),selected_products=compact(data['products']),period_closed_products=compact(data['period_products']),
        comparisons=comparisons,
        hourly=data['hourly'] if sku=='all' else None,
        scenario_price_check=data['scenario_price_check'] if sku=='all' else None,
        pricing_checks=[r for r in data['pricing_checks'] if sku=='all' or r['sku']==sku],
        qualification=data['note']+' '+data['price_effect_note'])
