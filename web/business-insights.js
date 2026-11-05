'use strict';
let businessTab='overview',businessSku='all',reportAiBusy=false;
let baselineDays=180,baselineData=null,baselineBusy=false,baselineLoadedKey='';
const reportAiResults=new Map(),reportAiRefresh=new Map();
const basicBusinessHistoryPanel=businessHistoryPanel;
function reportScopeKey(){return state.id+':'+businessDays+':'+businessTab+':'+(businessTab==='products'?businessSku:'all')+':'+(state.phase==='closed'?'closed':'open')}
function analysisKey(){const key=reportScopeKey();return key+':'+(reportAiRefresh.get(key)??'initial')}
function insightData(){return businessData?.session_id===state.id&&businessData.days===businessDays?businessData:null}
function smallMetric(label,value,detail=''){return '<article><small>'+label+'</small><strong>'+value+'</strong>'+(detail?'<span class="trend-muted">'+detail+'</span>':'')+'</article>'}
function horizontalBars(rows,value,cash=false,color='#b72c82'){
 const max=Math.max(1,...rows.map(r=>Math.abs(r[value]||0)));
 return '<div class="report-bars">'+rows.map(r=>'<div class="report-bar-row"><span>'+esc(r.label||r.name||r.sku)+'</span><div class="report-bar-track"><i style="width:'+Math.max(0,Math.abs(r[value]||0)/max*100)+'%;background:'+color+'"></i></div><b>'+reportValue(r[value],cash)+'</b></div>').join('')+'</div>';
}
function reportAiPanel(){
 const r=reportAiResults.get(analysisKey());
 const labels={overview:'xu hướng bán hàng',prices:'giá bán & giảm giá',products:businessSku==='all'?'cơ cấu sản phẩm':state.plan.find(p=>p.sku===businessSku)?.name||businessSku};
 let body='<p class="muted">AI đang đọc số liệu và biểu đồ '+esc(labels[businessTab]||'báo cáo')+'…</p>';
 if(r?.status==='ready')body='<small class="muted">Ảnh chụp '+dateVN(r.as_of_day||state.day)+' · '+hour(r.as_of_minute)+' · '+businessDays+' ngày</small>'+copilotResponse(r,true);
 if(r?.status==='unavailable')body='<p>Chưa nhận được phân tích AI: '+esc(r.error)+'</p><p>Các số liệu và nhận xét tính từ sổ bán vẫn dùng được.</p><button data-go="settings">Kiểm tra kết nối AI</button>';
 return '<aside class="panel report-ai"><div class="panel-head"><h2>'+icon('spark')+' AI phân tích '+esc(labels[businessTab])+'</h2></div><div class="panel-body" id="report-ai-text">'+body+'</div><div class="report-ai-actions"><button data-report-ai-refresh>Phân tích lại số mới</button><button class="small" data-chat>Hỏi sâu hơn</button><small>AI đọc đúng mục, khoảng ngày và SKU đang chọn. Bấm phân tích lại khi số liệu đổi.</small></div></aside>';
}
function simulationPriceCheck(r){
  if(r.scenario_price_check?.status==='ASSUMED_PRICE_SENSITIVITY_NOT_CAUSAL_EVIDENCE')return '<div class="report-scenario-check"><b>Kịch bản thử phản ứng giá</b><p>Lượt mua thêm do giảm giá được sinh theo giả định mô phỏng, chưa phải phản ứng khách AEON đã đo. M1 dự báo sức bán còn lại; mức giảm do policy cân đối tồn và doanh thu chọn. Hiệu quả còn phụ thuộc độ nhạy giá thực tế. Ca cũ dùng luồng khách cố định được giữ riêng.</p></div>';
  if(r.scenario_price_check?.status!=='FIXED_CUSTOMERS_NO_PRICE_RESPONSE')return '';
 return '<div class="report-scenario-check"><b>Vì sao giảm giá có thể không giảm tồn trong demo?</b><p>Luồng khách hiện không phản ứng với giá. Với cùng lượng chuẩn bị, đổi giá không tự làm tăng số bánh bán hoặc giảm tồn. Phần nhượng giá trên lượng đã bán là '+money(r.scenario_price_check.same_quantity_price_reduction)+'. Đây là giới hạn của kịch bản, chưa phải kết luận về khách mua thực tế. Hệ thống giữ giá khi chưa có bằng chứng lợi ích tăng thêm.</p></div>';
}
function priceInsights(r){
 const m=r.selected_metrics;if(!m)return '<section class="panel panel-body">Chưa có sổ bán hợp lệ để phân tích giá.</section>';
 const cards='<div class="business-kpis">'+smallMetric('Giá thực thu bình quân',money(m.average_price),'Doanh thu / số bánh đã bán')+smallMetric('Giảm so niêm yết',money(m.discount_value),'Trên đúng lượng đã bán')+smallMetric('Giảm bình quân theo tiền',m.weighted_discount_pct==null?'—':fmt(m.weighted_discount_pct)+'%','Giá trị giảm / giá trị niêm yết')+smallMetric('Bánh bán ở giá giảm',units(m.discounted_units)+' chiếc','Còn '+units(m.sold-m.discounted_units)+' chiếc bán nguyên giá')+'</div>';
 const reference=[{label:'Giá trị theo niêm yết',value:m.list_value},{label:'Doanh thu thực thu',value:m.revenue},{label:'Phần giảm so niêm yết',value:m.discount_value}];
 const daily=r.rows.map(d=>({...d,metrics:d.metrics?{average_price:d.metrics.average_price}:null}));
 const hours=r.hourly.map(h=>({label:h.label,status:'closed',metrics:{average_price:h.average_price}}));
 const comp=r.comparisons[businessCompare],bridge=comp.revenue_bridge;
 const bridgeText=bridge?'<p>So ngày '+dateVN(comp.day)+': doanh thu đổi <b>'+money(bridge.revenue_change)+'</b> = phần số lượng <b>'+money(bridge.volume_component)+'</b> + phần giá thực thu bình quân/cơ cấu món <b>'+money(bridge.average_price_and_mix_component)+'</b>. Đây là phân rã số học, chưa phải tác động nhân quả của giảm giá.</p>':'<p>Chưa đủ hai ngày đã chốt để phân rã thay đổi doanh thu thành phần lượng bán và giá thực thu.</p>';
 return '<section class="panel"><div class="panel-head"><div><h2>Giá bán thực thu & chiết khấu</h2><p>'+dateVN(state.day)+' · '+(r.current_status==='closed'?'Đã chốt':'Tạm tính đến '+hour(state.minute))+'</p></div></div><div class="panel-body">'+cards+simulationPriceCheck(r)+'<h3 class="report-subtitle">Từ giá niêm yết đến doanh thu thực thu</h3>'+horizontalBars(reference,'value',true)+'<p class="business-note">Phần giảm trên sổ bán không đồng nghĩa toàn bộ số tiền này sẽ thu được nếu giữ nguyên giá. Giá vốn đơn vị V4 tính trên toàn bộ hàng đã làm, không trừ thêm lần nữa khi bán giảm.</p>'+bridgeText+'</div></section><section class="panel"><div class="panel-head"><h2>Giá thực thu bình quân qua các ngày</h2></div><div class="panel-body">'+businessChart(daily,[{key:'average_price',label:'Giá thực thu / bánh',color:'#b72c82'}],true)+'</div></section><section class="panel"><div class="panel-head"><h2>Giá thực thu theo giờ trong ca</h2></div><div class="panel-body">'+businessChart(hours,[{key:'average_price',label:'Giá thực thu / bánh',color:'#31857c'}],true)+'<p class="business-note">Giờ không có giao dịch để trống. Giá bình quân có thể đổi do tỷ trọng các loại bánh, không chỉ do giảm giá.</p></div></section>';
}
function productInsights(r){
 const rows=businessSku==='all'?r.products:r.products.filter(p=>p.sku===businessSku);
 const sorted=[...rows].sort((a,b)=>b.revenue-a.revenue);
 const history=r.rows.map(d=>({...d,metrics:businessSku==='all'?d.metrics:d.products.find(p=>p.sku===businessSku)||null}));
 const period=businessSku==='all'?r.period_products:r.period_products.filter(p=>p.sku===businessSku);
 const table='<div class="table-scroll"><table><thead><tr><th>Sản phẩm</th><th>Chuẩn bị</th><th>Bán</th><th>Tồn</th><th>Doanh thu</th><th>Giá thực thu TB</th><th>Giảm so niêm yết</th><th>Bán giá giảm</th><th>Chênh sau giá vốn giả định</th></tr></thead><tbody>'+rows.map(p=>'<tr><td>'+esc(p.name)+'</td>'+['prepared','sold','stock'].map(k=>'<td>'+units(p[k])+'</td>').join('')+'<td>'+money(p.revenue)+'</td><td>'+money(p.average_price)+'</td><td>'+money(p.discount_value)+'</td><td>'+units(p.discounted_units)+'</td><td>'+money(p.contribution_before_overhead)+'</td></tr>').join('')+'</tbody></table></div>';
 const stack='<div class="business-legend"><span><i style="background:#b72c82"></i>Đã bán</span><span><i style="background:#62a79d"></i>Còn lại</span></div><div class="report-stacks">'+rows.map(p=>'<div><span>'+esc(p.name)+'</span><div class="report-stack" title="Chuẩn bị '+p.prepared+'; bán '+p.sold+'; còn '+p.stock+'"><i style="width:'+(p.prepared?100*p.sold/p.prepared:0)+'%"></i><em style="width:'+(p.prepared?100*p.stock/p.prepared:0)+'%"></em></div><small>'+units(p.sold)+' / '+units(p.prepared)+' · còn '+units(p.stock)+'</small></div>').join('')+'</div>';
 return '<section class="panel"><div class="panel-head"><div><h2>Hiệu quả từng loại bánh</h2><p>Ngày '+dateVN(state.day)+' · '+(r.current_status==='closed'?'Đã chốt':'Tạm tính')+'</p></div><label>Sản phẩm <select data-business-sku aria-label="Sản phẩm phân tích"><option value="all">Tất cả sản phẩm</option>'+r.products.map(p=>'<option value="'+esc(p.sku)+'" '+(businessSku===p.sku?'selected':'')+'>'+esc(p.name)+'</option>').join('')+'</select></label></div><div class="panel-body"><h3>Đóng góp doanh thu</h3>'+horizontalBars(sorted,'revenue',true)+'<h3 class="report-subtitle">Bán được bao nhiêu trong lượng đã chuẩn bị?</h3>'+stack+'<details class="business-details"><summary>Bảng giá, bán, tồn và giá vốn theo từng món</summary>'+table+'</details></div></section><section class="panel"><div class="panel-head"><h2>Chuẩn bị · bán · tồn qua các ngày</h2></div><div class="panel-body">'+businessChart(history,[{key:'prepared',label:'Chuẩn bị',color:'#8c79bd'},{key:'sold',label:'Đã bán',color:'#b72c82'},{key:'stock',label:'Tồn',color:'#31857c'}])+'</div></section><section class="panel"><div class="panel-head"><h2>Doanh thu cộng dồn các ngày đã chốt trong khoảng xem</h2></div><div class="panel-body">'+horizontalBars(period,'revenue',true)+'<p class="business-note">'+r.closed_days+' ngày đủ dữ liệu, không tính ca đang chạy. Hàng còn là tồn cuối ngày, chưa xác nhận hủy vật lý.</p></div></section>';
}
function baselineBusinessPanel(){
 return '';
}
async function refreshBaselineHistory(){}
businessHistoryPanel=function(){
 const r=insightData();if(businessSku!=='all'&&r&&!r.products.some(p=>p.sku===businessSku))businessSku='all';if(businessTab==='baseline')businessTab='overview';const tabs='<div class="report-tabs" role="tablist" aria-label="Nội dung báo cáo">'+[['overview','Tổng quan'],['prices','Giá & chiết khấu'],['products','Từng loại bánh']].map(([v,t])=>'<button role="tab" aria-selected="'+(businessTab===v)+'" data-business-tab="'+v+'">'+t+'</button>').join('')+'</div>';
 const range=businessTab==='overview'?'':'<div class="report-filter"><label>Khoảng xem <select data-business-days aria-label="Khoảng lịch sử">'+[7,30,63,90].map(n=>'<option '+(businessDays===n?'selected':'')+' value="'+n+'">'+n+' ngày</option>').join('')+'</select></label><small>'+dateVN(state.day)+' · '+(r?.closed_days??0)+' ngày đã chốt</small></div>';
 const body=businessTab==='overview'?basicBusinessHistoryPanel():!r?'<section class="panel panel-body">'+esc(businessError||'Đang tải báo cáo…')+'</section>':businessTab==='prices'?priceInsights(r):productInsights(r);
 return tabs+range+'<div class="report-analysis-layout"><div class="report-charts">'+body+'</div>'+reportAiPanel()+'</div>';
};
async function refreshReportAnalysis(){
 if(currentView!=='reports'||!insightData()||reportAiBusy)return;
 const key=analysisKey();if(['ready','unavailable'].includes(reportAiResults.get(key)?.status))return;
 reportAiBusy=true;
 try{
  const scope=reportScopeKey(),revision=reportAiRefresh.get(scope);
  const q=new URLSearchParams({days:businessDays,section:businessTab,sku:businessTab==='products'?businessSku:'all'});
  if(revision!==undefined){q.set('refresh_revision',revision);q.set('retry','true');}
  const result=await api('/api/report-explanation/'+state.id+'?'+q);
  reportAiResults.set(key,result);
  if(key===analysisKey()&&currentView==='reports'){
   const target=document.getElementById('report-ai-text');
   if(target)target.innerHTML=result.status==='ready'?'<small class="muted">Ảnh chụp '+dateVN(result.as_of_day||state.day)+' · '+hour(result.as_of_minute)+' · '+businessDays+' ngày</small>'+copilotResponse(result,true):result.status==='unavailable'?'<p>AI chưa phản hồi: '+esc(result.error)+'</p><button data-go="settings">Kiểm tra kết nối AI</button>':'<p>AI đang đọc đúng báo cáo này tại '+hour(result.as_of_minute)+'…</p>';
  }
 }catch(e){reportAiResults.set(key,{status:'unavailable',error:e.message});const t=document.getElementById('report-ai-text');if(t&&key===analysisKey())t.textContent='Chưa nhận được phân tích AI: '+e.message}
 finally{reportAiBusy=false}
}
document.addEventListener('click',e=>{
 const tab=e.target.closest('[data-business-tab]');if(tab){businessTab=tab.dataset.businessTab;render();refreshReportAnalysis()}
 if(e.target.closest('[data-report-ai-refresh]')){reportAiRefresh.set(reportScopeKey(),state.revision);reportAiResults.delete(analysisKey());render();refreshReportAnalysis()}
});
document.addEventListener('change',e=>{if(e.target.hasAttribute('data-business-sku')){businessSku=e.target.value;render();refreshReportAnalysis()}});
setInterval(()=>{if(!document.hidden)refreshReportAnalysis()},2500);
