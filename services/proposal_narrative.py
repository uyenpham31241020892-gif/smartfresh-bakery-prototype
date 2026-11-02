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
    for p in state['plan']:
        sku=p['sku'];e=evidence(sku);used.append(dict(tool='get_model_evidence',sku=sku))
        if component=='m2':
            m=e['m2'];s=m.get('supply') or {};f=m.get('features') or {};plan=m.get('v4_plan') or {}
            refs='; '.join(b['ready_time']+': '+number(b['qty'])+' bánh' for b in plan.get('production_batches',[])) or 'không có'
            text=f"### {p['name']} · Đề xuất {number(m['prepared'])} bánh cả ngày\n- Lịch sử V4: bán ngày trước {number(f.get('sold_calendar_lag1'))}, cùng thứ tuần trước {number(f.get('sold_calendar_lag7'))}; trung bình 7 ngày quan sát {number(f.get('sold_last7_observed_mean'))}.\n- Model dự báo gốc Q50: {number(m['forecast'])}; nhánh bundle Q75 {number(s.get('q75'))}, Q90 {number(s.get('q90'))}. Adapter V4 chọn theo thứ/nhóm SKU, làm tròn mẻ 4 và trần công suất {number(s.get('capacity'))}. Tên Q75/Q90 không thay cho coverage thực đo.\n- Đầu ngày: {number(plan.get('initial_qty'))} bánh; refill: {refs}. Tổng đề xuất khác lượng đã làm thực tế.\n- Mưa ngày trước {number(f.get('prior_day_rain_mm'))} mm; nhiệt độ {number(f.get('prior_day_temp_c'))} °C. Manager kiểm tra rồi duyệt; mục tiêu phục vụ 21:30 không phải bảo đảm."
            options=['Kế hoạch đầu ngày và hai đợt refill giúp cân đối cung ứng trong ca.','Manager có thể điều chỉnh đúng mẻ/công suất và ghi lý do.']
        else:
            m=e.get('m1')
            if not m:continue
            hold=m.get('predicted_hold_next30');policy=m.get('pricing_policy') or {}
            text=f"### {p['name']} · {'Giữ giá' if m['discount']==m['previous'] else 'Đề xuất giảm '+number(m['discount'])+'%'}\n- Tồn {number(m['stock'])} bánh; bán {number(m['sales30'])}/30 phút và {number(m['sales60'])}/60 phút.\n- Giá lúc lập đề xuất giảm {number(m['previous'])}%; giá đề xuất {number(m['new_price'])}đ. Model dự báo bán 30 phút nếu giữ giá: {number(hold)} bánh.\n- V4 so lượng bán dự kiến giữa các mức và lợi ích ròng với HOLD. Đây là kỳ vọng của model, chưa phải số bán thêm thực đo. Kết quả 0 là HOLD, không tăng giá trở lại.\n- Trần hiện tại {number(m['cap'])}%, không tăng giá, cách ít nhất 30 phút và tối đa 2 lần đổi/SKU/ngày. Duyệt rồi Áp dụng mới cập nhật price_version và ACK POS/E-ink mô phỏng."
            options=['So tồn và sức bán riêng từng món trước khi duyệt.','Manager đổi mức khác đề xuất cần lý do, vẫn qua các ràng buộc V4.']
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
