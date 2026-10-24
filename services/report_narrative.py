"""Server-owned report facts paired with qualitative, schema-checked AI commentary."""
import json

def number(value):
    return 'chưa có dữ liệu' if value is None else f'{value:,.0f}'.replace(',','.')


def facts(context):
    m=context.get('selected');products=context.get('selected_products',[])
    if not m:return {'availability':('Dữ liệu','Chưa có số liệu bán hợp lệ để kết luận hiệu quả.')}
    result={
        'revenue':('Doanh thu & lượng bán',f"Doanh thu {number(m['revenue'])} ₫; bán {number(m['sold'])} chiếc; giá thực thu bình quân {number(m.get('average_price'))} ₫/chiếc."),
        'discount':('Giá bán & chiết khấu',f"Phần giảm so niêm yết trên đúng lượng đã bán: {number(m.get('discount_value'))} ₫; {number(m.get('discounted_units'))} chiếc bán ở giá giảm. Đây không phải doanh thu mất nhân quả."),
        'stock':('Chuẩn bị & tồn',f"Chuẩn bị {number(m['prepared'])} chiếc; còn {number(m['stock'])} chiếc. Tồn chưa đồng nghĩa hàng đã hủy vật lý."),
        'contribution':('Chênh sau giá vốn giả định',f"Chênh sau giá vốn giả định {number(m.get('contribution_before_overhead'))} ₫. Giá vốn bằng 45% niêm yết × toàn bộ chuẩn bị, đã bao gồm hàng còn; chưa trừ vận hành hoặc phí hủy."),
    }
    if products:
        top=max(products,key=lambda p:p['revenue']);excess=max(products,key=lambda p:p['stock'])
        result['products']=('Theo sản phẩm',f"Doanh thu cao nhất trong phạm vi chọn: {top['name']} ({number(top['revenue'])} ₫). Tồn nhiều nhất: {excess['name']} ({number(excess['stock'])} chiếc).")
    comp=context.get('comparisons',{}).get('day',{});delta=comp.get('changes',{}).get('revenue',{})
    if context['status']=='closed' and delta.get('percent') is not None:
        result['comparison']=('So ngày trước',f"So ngày {comp['day']}: doanh thu đổi {number(delta['value'])} ₫ ({delta['percent']:+.2f}%). So sánh ngày khác không chứng minh tác động giá.")
    elif context['status']=='closed' and delta.get('value') is not None:
        result['comparison']=('So ngày trước',f"Doanh thu đổi {number(delta['value'])} ₫; mốc trước bằng không nên không tính phần trăm.")
    else:result['comparison']=('Độ đầy đủ dữ liệu','Chưa có đủ hai ngày đã chốt cho so sánh trong phạm vi chọn; không tự điền ngày thiếu bằng số không.')
    return result


ACTIONS={'HOLD_PRICE':'Giữ giá khi chưa có lợi ích tăng thêm được xác minh.',
 'REVIEW_PREPARATION':'Rà soát lượng chuẩn bị của món dư, kiểm tra cả mục tiêu còn hàng đến 21:30 trước khi điều chỉnh.',
 'VERIFY_PRICE_EFFECT':'Cần bằng chứng phản ứng giá hoặc thử nghiệm phù hợp trước khi kết luận giảm giá có hiệu quả.',
 'MONITOR_CLOSE':'Theo dõi tiếp số bán và tồn, chốt ca để so sánh đầy đủ.',
 'VERIFY_DATA':'Bổ sung hoặc đối soát dữ liệu trước khi kết luận.'}


def commentary_options(context):
    """Only interpretations supported by this snapshot may be selected by the AI."""
    m=context.get('selected')
    if not m:return {'availability':['Cần bổ sung hoặc đối soát dữ liệu trước khi đánh giá hiệu quả.']}
    closed=context['status']=='closed';previous=context.get('comparisons',{}).get('day',{}).get('previous')
    fixed=context.get('scenario_price_check',{});fixed=bool(fixed and fixed.get('status')=='FIXED_CUSTOMERS_NO_PRICE_RESPONSE')
    return {
      'revenue':['Cần đọc đồng thời lượng bán, giá thực thu và cơ cấu món; doanh thu đơn lẻ chưa giải thích được hiệu quả.',
                 'Ca chưa chốt nên chưa so một phần ngày với cả ngày trước.' if not closed else 'Ca đã chốt cho phép đối chiếu số bán và tiền thu theo sổ.'],
      'discount':['Trong mô phỏng luồng khách cố định, giảm giá không tự tạo thêm lượt mua; ưu tiên giữ giá khi chưa có lợi ích tăng thêm.' if fixed else 'Chưa có bằng chứng phản ứng giá để kết luận chiết khấu làm tăng lượng mua.',
                  'Không quy phần giảm so niêm yết thành toàn bộ doanh thu có thể thu thêm nếu giữ giá ngoài thực tế.'],
      'stock':['Không còn tồn theo sổ; kiểm tra lượng chuẩn bị và thời điểm hết hàng trước khi kết luận nhu cầu.' if not m['stock'] else 'Rà soát sản lượng ngày sau ở món còn nhiều, đồng thời bảo vệ mục tiêu còn hàng đến giờ phục vụ đã đặt.' if context['as_of_minute']>=1290 else 'Tồn giữa ca cần được xem cùng tốc độ bán và thời gian phục vụ còn lại.',
               'Chưa có biên bản hủy vật lý nên chỉ kết luận lượng tồn, không khẳng định lượng đã hủy.'],
      'contribution':['Chênh sau giá vốn giả định không âm, nhưng còn thiếu chi phí vận hành để kết luận lợi nhuận ròng.' if m.get('contribution_before_overhead',0)>=0 else 'Chênh sau giá vốn giả định âm; cần xem lại lượng chuẩn bị và giá thực thu.',
                      'Giá vốn đã gồm toàn bộ hàng chuẩn bị, không trừ giá vốn hàng dư thêm lần nữa.'],
      'products':['Đọc đồng thời đóng góp doanh thu và tồn của từng món trước khi điều chỉnh kế hoạch.',
                  'Ưu tiên kiểm tra món còn nhiều, tránh áp cùng một quyết định giảm giá cho mọi sản phẩm.'],
      'comparison':['Đã có dữ liệu ngày trước, nhưng ca hiện tại chưa chốt nên chưa công bố so sánh cả ngày.' if previous and not closed else 'So sánh hai ngày là đối chiếu kinh doanh, chưa phải bằng chứng tác động nhân quả của giá.' if previous else 'Thiếu mốc ngày trước phù hợp; không tự điền số không hoặc suy ra phần trăm tăng giảm.']}


def schema(context):
    options=commentary_options(context)
    return {'type':'object','properties':{
        'insights':{'type':'array','minItems':min(3,len(facts(context))),'maxItems':5,'items':{'anyOf':[
            {'type':'object','properties':{'fact_key':{'type':'string','enum':[key]},'commentary':{'type':'string','enum':options[key]}},
             'required':['fact_key','commentary'],'additionalProperties':False} for key in facts(context)]}},
        'actions':{'type':'array','minItems':1,'maxItems':3,'items':{'type':'string','enum':list(ACTIONS)}}},
        'required':['insights','actions'],'additionalProperties':False}


def render(answer,context):
    try:data=json.loads(answer)
    except (TypeError,ValueError):raise ValueError('Phân tích báo cáo cần đúng JSON có fact_key và commentary.') from None
    if not isinstance(data,dict) or not isinstance(data.get('insights'),list):raise ValueError('Phân tích báo cáo cần danh sách insights hợp lệ.')
    allowed=facts(context);seen=set();parts=[]
    options=commentary_options(context)
    for item in data.get('insights',[]):
        if not isinstance(item,dict):raise ValueError('Nhận xét báo cáo không hợp lệ.')
        key=item.get('fact_key');comment=item.get('commentary','')
        if key not in allowed or key in seen or comment not in options[key]:
            raise ValueError('Nhận xét phải chọn đúng diễn giải đã kiểm tra trong commentary_options của fact_key.')
        seen.add(key);title,metric=allowed[key]
        parts.append('**'+title+':**\n'+metric+'\n'+comment)
    if not parts or len(parts)>6:raise ValueError('Thiếu nhận xét theo dữ kiện báo cáo.')
    actions=data.get('actions',[])
    if not isinstance(actions,list) or not 1<=len(actions)<=3 or any(not isinstance(a,str) or a not in ACTIONS for a in actions):raise ValueError('Hành động báo cáo không hợp lệ.')
    minute=context['as_of_minute'];day=context['selected_day']
    header=f"Phân tích ngày {day[8:10]}/{day[5:7]}/{day[:4]} · {minute//60:02}:{minute%60:02} · {'đã chốt' if context['status']=='closed' else 'tạm tính'}."
    if context['scope']['section']=='baseline':header='Lịch sử baseline ZIP 02 (proxy, không phải doanh thu AEON đã xác minh). '+header
    return header+'\n\n'+'\n\n'.join(parts)+'\n\n**Hành động ưu tiên:**\n'+'\n'.join('- '+ACTIONS[a] for a in actions)
