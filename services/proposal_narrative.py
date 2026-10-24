"""Immediate verified explanations; AI prioritizes facts without inventing numbers."""
from datetime import date, timedelta
import json
from .costs import estimate


def number(n):
    if n is None:
        return '-'
    return f'{round(n):,}'.replace(',', '.')


def prepare(state, component, evidence):
    facts = {}
    used = []
    target_day_str = state.get('day', '2022-07-01')
    try:
        target_day = date.fromisoformat(target_day_str)
    except Exception:
        target_day = date(2022, 7, 1)

    d1_str = (target_day - timedelta(days=1)).isoformat()
    d2_str = (target_day - timedelta(days=2)).isoformat()
    d3_str = (target_day - timedelta(days=3)).isoformat()
    d7_str = (target_day - timedelta(days=7)).isoformat()

    history_by_sku = {}
    for r in state.get('input_history', []):
        sku = r.get('sku') or r.get('sku_code')
        if sku and r.get('date'):
            history_by_sku.setdefault(sku, {})[r['date']] = r.get('sold', 0)

    weekday_names = {1: 'Thứ Hai', 2: 'Thứ Ba', 3: 'Thứ Tư', 4: 'Thứ Năm', 5: 'Thứ Sáu', 6: 'Thứ Bảy', 7: 'Chủ Nhật'}

    for p in state['plan']:
        sku = p['sku']
        e = evidence(sku)
        used.append(dict(tool='get_model_evidence', sku=sku))

        if component == 'm2':
            m = e['m2']
            s = m.get('supply') or {}
            f = m.get('features') or {}
            scale = int(s.get('demand_scale', 4))

            sh = history_by_sku.get(sku, {})
            sold_d1 = sh.get(d1_str, f.get('sold_calendar_lag1'))
            sold_d2 = sh.get(d2_str)
            sold_d3 = sh.get(d3_str)
            sold_d7 = sh.get(d7_str, f.get('sold_calendar_lag7'))
            mean_7 = f.get('sold_last7_observed_mean')
            prep_last = f.get('prepared_last_observed')
            stockout_last = bool(f.get('censored_last_observed'))
            rem_last = max(0, prep_last - sold_d1) if (prep_last is not None and sold_d1 is not None and not stockout_last) else 0

            weekday_iso = f.get('weekday_iso', target_day.isoweekday())
            weekday_vn = weekday_names.get(weekday_iso, f'Thứ {weekday_iso}')
            is_weekend = f.get('is_weekend', 0)
            temp = f.get('prior_day_temp_c')
            rain = f.get('prior_day_rain_mm')

            raw_forecast = s.get('raw_forecast', m.get('forecast', 0))
            scenario_forecast = s.get('scenario_forecast', raw_forecast * scale)
            buffer = s.get('uncertainty_buffer', m.get('buffer', 0))
            reserve = s.get('service_reserve', 4)
            prepared = m.get('prepared', s.get('quantity', 0))
            batches = m.get('batches', prepared // 4)
            to2130 = s.get('expected_sold_to_2130', 0)
            stock2130 = s.get('expected_stock_at_2130', 0)

            hist_items = []
            if sold_d1 is not None:
                rem_str = f"; tồn cuối ca **{number(rem_last)}** bánh" if rem_last is not None else ""
                chay_str = " - hết hàng sớm" if stockout_last else ""
                hist_items.append(f"Hôm qua ({d1_str[8:10]}/{d1_str[5:7]}): bán **{number(sold_d1)}** bánh{rem_str}{chay_str}")
            if sold_d2 is not None:
                hist_items.append(f"hôm kia ({d2_str[8:10]}/{d2_str[5:7]}): bán **{number(sold_d2)}**")
            if sold_d3 is not None:
                hist_items.append(f"ngày trước ({d3_str[8:10]}/{d3_str[5:7]}): bán **{number(sold_d3)}**")
            if sold_d7 is not None:
                hist_items.append(f"cùng {weekday_vn} tuần trước ({d7_str[8:10]}/{d7_str[5:7]}): bán **{number(sold_d7)}**")
            if mean_7 is not None:
                scale_note = f" (quy đổi tải cao điểm {scale}× tương đương ~**{number(mean_7 * scale)}** bánh)" if scale > 1 else ""
                hist_items.append(f"trung bình 7 ngày qua: **{number(mean_7)}** bánh/ngày{scale_note}")
            hist_desc = "; ".join(hist_items) if hist_items else "Dựa trên trung bình bán và lịch sử quan sát"

            weather_note = "; điều kiện bán ổn định" if (rain is not None and rain < 50 and 20 <= (temp or 25) <= 35) else "; cần lưu ý ảnh hưởng thời tiết"
            weather_desc = f"{weekday_vn} ({'cuối tuần' if is_weekend else 'ngày thường'}), nhiệt độ ngày trước **{f'{temp:.1f}' if temp is not None else '27.0'}°C**, mưa **{f'{rain:.1f}' if rain is not None else '0.0'} mm**{weather_note}"

            math_desc = f"Dự báo gốc M2 **{number(raw_forecast)}** bánh (thang chuẩn 1×) ➔ Quy đổi tải khách cao điểm {scale}×: **{number(scenario_forecast)}** bánh. Đệm an toàn bù biến động nhu cầu 95%: **+{number(buffer)}** bánh + dự phòng phục vụ: **+{number(reserve)}** bánh ➔ Làm tròn mẻ 4 chiếc đề xuất: **{number(prepared)}** bánh (**{batches}** mẻ)"
            target_desc = f"Dự kiến bán **{number(to2130)}** bánh trước 21:30; giữ tồn mục tiêu lúc 21:30 là **{number(stock2130)}** bánh để quầy luôn đầy đặn không bị trống trước giờ đóng cửa"

            text = f"""### Đề xuất chuẩn bị: {p['name']} ({number(prepared)} bánh · {batches} mẻ)\n- 📊 Căn cứ lịch sử bán & tồn: {hist_desc}.\n- ⛅ Căn cứ thời tiết & thứ: {weather_desc}.\n- ⚙️ Công thức tính từ M2: {math_desc}.\n- 🎯 Mục tiêu phục vụ 21:30: {target_desc}."""
            options = ['Cần xét cả rủi ro dư cuối ca và mục tiêu đủ hàng trước khi xác nhận chuẩn bị.', 'Dự báo gốc và lượng chuẩn bị sau policy là hai chỉ số khác nhau.']

        else:
            m = e.get('m1')
            if not m:
                continue
            policy = m.get('pricing_policy') or {}
            g = m.get('economic_gate') or {}
            changed = m['new_price'] < round(m['price'] * (1 - m['previous'] / 100))

            if changed:
                text = f"""### Đề xuất giảm giá: {p['name']} · Giảm tổng {number(m['discount'])}% (còn {number(m['new_price'])} ₫)\n- 📦 Tồn kho & nhịp bán: Tồn quầy **{number(m['stock'])}** chiếc; bán **{number(m['sales30'])}** / 30 phút và **{number(m['sales60'])}** / 60 phút. Dự kiến cuối ca còn dư **{number(policy.get('projected_closing_stock_at_current_pace', 0))}** chiếc nếu giữ giá.\n- 🏷️ Mức giá đề xuất: Đề xuất mức tổng **{number(m['discount'])}%** so niêm yết (**{number(m['new_price'])} ₫/chiếc**, niêm yết **{number(m['price'])} ₫**); không cộng dồn phần trăm.\n- 💰 Phân tích hòa vốn: Theo giả định nhạy giá bán thêm **{number(g.get('assumed_extra_units', 0))}** chiếc; cần bán thêm ít nhất **{number(g.get('minimum_extra_units_to_break_even', 0))}** chiếc để hòa vốn doanh thu. Nếu khách không phản ứng: nhượng doanh thu khoảng **{number(-g.get('zero_response_revenue_change', 0))} ₫**.\n- 🛡️ Ngân sách & phục vụ: Ngân sách nhượng giá cả ngày **{number(policy.get('daily_concession_budget', 0))} ₫**, đã nhượng **{number(policy.get('past_discount_value', 0))} ₫**. Đảm bảo đệm hàng phục vụ khách đến 21:30."""
                options = ['Mức giảm cần quản lý duyệt; số bán thêm là giả định, chưa phải hiệu quả đã xác minh.', 'Cần theo dõi tốc độ bán sau áp giá, không suy từ doanh thu đơn lẻ rằng mức giảm có hiệu quả.']
            else:
                reasons = {'HOLD_PREFER_AFTER_2100': 'Chưa đạt điều kiện ngoại lệ giảm sớm; ưu tiên giữ giá đánh giá lại sau 21:00.',
                           'HOLD_CONCESSION_BUDGET_OR_SERVICE_RISK': 'Giảm thêm sẽ vượt ngân sách nhượng giá cả ngày hoặc ảnh hưởng lượng bánh phục vụ đến 21:30.',
                           'HOLD_PROTECT_STOCK_TO_2130': 'Cần bảo vệ lượng bánh phục vụ khách đến 21:30.',
                           'HOLD_NO_MATERIAL_SURPLUS': 'Phần dư dự kiến chưa vượt ngưỡng để mở đợt giảm giá.',
                           'HOLD_SOLD_OUT': 'Không còn hàng tồn trên quầy để đổi giá.'}
                reason_desc = reasons.get(m.get('reason'), 'Chưa có phương án giảm thêm phù hợp với bằng chứng và rủi ro hiện tại.')
                text = f"""### Giữ giá: {p['name']} · Giá hiện tại {number(m['new_price'])} ₫ (đang giảm {number(m['previous'])}%)\n- 📦 Tồn kho & nhịp bán: Tồn quầy **{number(m['stock'])}** chiếc; bán **{number(m['sales30'])}** / 30 phút và **{number(m['sales60'])}** / 60 phút. Dự kiến cuối ca còn **{number(policy.get('projected_closing_stock_at_current_pace', 0))}** chiếc nếu giữ giá.\n- ⚖️ Căn cứ quyết định: {reason_desc} Không cần duyệt giữ giá.\n- 🛡️ Ngân sách nhượng giá: Ngân sách cả ngày **{number(policy.get('daily_concession_budget', 0))} ₫**, đã nhượng **{number(policy.get('past_discount_value', 0))} ₫**."""
                options = ['Giữ giá ở mốc này không có nghĩa giữ giá suốt ca; cần đánh giá lại tồn và sức bán tại mốc sau.', 'Không áp cùng một quyết định cho mọi món; ưu tiên kiểm tra riêng món dư hoặc bán chậm.']

        facts[p['sku']] = dict(text=text, commentary_options=options)

    actions = ['Theo dõi tốc độ bán và lượng tồn tại checkpoint tiếp theo.', 'Đối chiếu hàng dư để điều chỉnh lượng chuẩn bị ngày sau.']
    if component == 'm1' and state['minute'] < 1260:
        actions.append('Ưu tiên đánh giá lại sau 21:00; chỉ giảm sớm khi có nguy cơ dư lớn và sức bán chậm.')
    if component == 'm1' and state.get('pending'):
        actions.append('Đọc rủi ro nhượng doanh thu trước khi chọn duyệt hoặc giữ giá.')
    return dict(day=state['day'], minute=state['minute'], component=component, phase=state['phase'], facts=facts, actions=actions,
                financial_context=estimate(state['products']), evidence_delivery='SERVER_EXECUTED_READ_ONLY_TOOLS_BEFORE_GENERATION', tools_executed=used)


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
        header += f"\n- Doanh thu lũy kế: **{number(financial['revenue'])} ₫** · Chênh sau giá vốn chuẩn bị giả định: **{number(financial['contribution_before_overhead'])} ₫** (chưa trừ chi phí vận hành)."
    action_card = f"### Hành động tiếp theo\n- {action}"
    return header + '\n\n' + '\n\n'.join(context['facts'][key]['text'] for key in keys) + '\n\n' + action_card


def immediate(context):
    keys = list(context['facts'])[:3]
    if not keys:
        return 'Chưa có đề xuất giá ở mốc này; không cần duyệt.'
    return render(json.dumps(dict(priorities=keys, action=context['actions'][0])), context)
