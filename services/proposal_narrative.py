"""Immediate verified explanations; AI prioritizes facts without inventing numbers."""
from datetime import date, timedelta
import json
from .costs import estimate


def number(n):
    if n is None:
        return '-'
    return f'{round(n):,}'.replace(',', '.')


def prepare(state,component,evidence):
    facts={};used=[]
    joint=state['model_version']=='SMARTFRESH_V4_JOINT_V2'
    reasons={
        'SELLOUT_GATE_88':'Khả năng tự bán hết đạt ngưỡng 88%, giữ giá.',
        'PROTECT_STOCK_UNTIL_2130':'Giữ giá để bảo vệ khả năng còn hàng phục vụ tới 21:30.',
        'RESERVE_FINAL_CLEARANCE':'Giữ lượt đổi giá cuối cho mốc 21:30.',
        'MAX_APPLIED_CHANGES':'Đã đủ số lần đổi giá trong ngày.',
        'COOLDOWN':'Chưa đủ 30 phút từ lần đổi giá trước.',
        'NO_STOCK':'Đã hết hàng.',
        'NO_POSITIVE_NET_GAIN':'Chưa có mức giảm mang lại lợi ích ròng đủ lớn so với giữ giá.',
        'POSITIVE_INCREMENTAL_NET_GAIN':'Giá trị bánh dự kiến cứu được lớn hơn tiền bán hớ và phí đổi giá.'}
    for p in state['plan']:
        sku=p['sku'];e=evidence(sku);used.append(dict(tool='get_model_evidence',sku=sku))
        if component=='m2':
            m=e['m2'];s=m.get('supply') or {};f=m.get('features') or {};plan=m.get('v4_plan') or {}
            refs='; '.join(b['ready_time']+': '+number(b['qty'])+' bánh' for b in plan.get('production_batches',[])) or 'không có'
            selection=('Phân vị chọn Q'+number(100*plan['selected_quantile'])+'; dự báo tương ứng '+number(plan['selected_forecast'])+' bánh') if joint else 'Adapter V4 chọn sản lượng theo thứ và nhóm SKU'
            text=f"### {p['name']} · Đề xuất {number(m['prepared'])} bánh cả ngày\n- Lịch sử đầu vào: bán ngày trước {number(f.get('sold_calendar_lag1'))}, cùng thứ tuần trước {number(f.get('sold_calendar_lag7'))}; trung bình 7 ngày {number(f.get('sold_last7_observed_mean'))}.\n- {selection}. Làm tròn theo mẻ 4; công suất {number(s.get('capacity'))} bánh.\n- Đầu ngày {number(plan.get('initial_qty'))} bánh; bổ sung {refs}. Đây là kế hoạch, chưa phải lượng đã làm thực tế."
            if joint:text+=f"\n- Đã khử {number(plan.get('depromo_removed_last7',0))} bánh bán tăng thêm do khuyến mãi ước tính trong 7 ngày đầu vào."
            options=['Kiểm tra sản lượng và hai đợt bổ sung trước khi duyệt.','Điều chỉnh đúng kích thước mẻ và công suất nếu cần.']
        else:
            m=e.get('m1')
            if not m:continue
            policy=m.get('pricing_policy') or {};hold=m.get('predicted_hold_next30')
            text=f"### {p['name']} · {'Giữ giá' if m['discount']==m['previous'] else 'Đề xuất giảm '+number(m['discount'])+'%'}\n- Tồn {number(m['stock'])} bánh; bán {number(m['sales30'])}/30 phút và {number(m['sales60'])}/60 phút.\n- Giá hiện hành giảm {number(m['previous'])}%; giá đề xuất {number(m['new_price'])}đ. Nếu giữ giá, dự kiến bán {number(hold)} bánh trong 30 phút tới."
            if joint:
                text+=f"\n- {reasons.get(policy.get('reason'),'Đối chiếu tồn kho và sức bán trước khi duyệt.')} Xác suất tự bán hết ở giá niêm yết ước tính {number(100*policy.get('sellout_probability_list',0))}%."
                if m['discount']>m['previous']:text+=f" Lợi ích ròng dự kiến so với giữ giá: {number(policy.get('net_gain'))}đ."
            text+=f"\n- Trần đề xuất tại mốc này {number(m['cap'])}%; cách ít nhất 30 phút và tối đa {3 if joint else 2} lần đổi/SKU/ngày. Duyệt rồi Áp dụng mới đổi giá."
            options=['Đối chiếu lượng tồn và sức bán của từng món.','Quản lý chỉnh khác đề xuất cần ghi lý do.']
        facts[sku]=dict(text=text,commentary_options=options)
    actions=['Theo dõi tồn và sức bán tại checkpoint tiếp theo.','Đối chiếu kết quả cuối ca để lập kế hoạch ngày sau.']
    return dict(day=state['day'],minute=state['minute'],component=component,phase=state['phase'],facts=facts,actions=actions,financial_context=estimate(state['products'],closed=state.get('phase')=='closed'),evidence_delivery='SERVER_EXECUTED_READ_ONLY_TOOLS_BEFORE_GENERATION',tools_executed=used)


def schema(context):
    return {'type': 'object', 'properties': {'priorities': {'type': 'array', 'minItems': 1, 'maxItems': 3, 'items': {'type': 'string', 'enum': list(context['facts'])}},
            'action': {'type': 'string', 'enum': context['actions']}}, 'required': ['priorities', 'action'], 'additionalProperties': False}


def render(value, context):
    result = json.loads(value)
    keys = result.get('priorities')
    action = result.get('action')
    if not isinstance(keys, list) or not 1 <= len(keys) <= 3 or len(set(keys)) != len(keys) or any(k not in context['facts'] for k in keys) or action not in context['actions']:
        raise ValueError('Invalid proposal analysis selection')
    minute = context['minute']
    day = context['day']
    header = f"### Đề xuất ngày {day[8:10]}/{day[5:7]}/{day[:4]} · {minute//60:02}:{minute%60:02}, đọc trước quyết định duyệt."
    financial = context.get('financial_context', {})
    if context['component'] == 'm1' and financial:
        header += f"\n- Doanh thu lũy kế: **{number(financial['revenue'])} ₫** · Lãi góp mô phỏng tạm tính: **{number(financial['contribution_before_overhead'])} ₫** (theo sổ ca, chưa trừ chi phí cố định)."
    action_card = f"### Hành động tiếp theo\n- {action}"
    return header + '\n\n' + '\n\n'.join(context['facts'][key]['text'] for key in keys) + '\n\n' + action_card


def immediate(context):
    keys = list(context['facts'])[:3]
    if not keys:
        return 'Chưa có đề xuất giá ở mốc này; không cần duyệt.'
    return render(json.dumps(dict(priorities=keys, action=context['actions'][0])), context)
