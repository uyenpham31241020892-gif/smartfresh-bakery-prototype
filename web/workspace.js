'use strict';
// One operational workspace per shift. Technical pages remain under a closed menu.
let shiftSession='',shiftName='',explainBusy=false,manualPriceOpen=false;

document.addEventListener('toggle',e=>{
 if(e.target.id==='manual-price-section')manualPriceOpen=e.target.open;
},true);

document.addEventListener('click',async event=>{
 const summary=event.target.closest('#manual-price-section summary');
 const button=event.target.closest('[data-manual-pricing]');
 if(!summary&&!button)return;

 if(summary){
  const details=summary.parentElement;
  if(details&&details.open){
   manualPriceOpen=false;
   return;
  }
 }

 manualPriceOpen=true;
 const editable=state.phase==='price_pending'&&state.pending?.status!=='missing_data';
 const isManager=authUser?.role==='manager';
 if((!editable||button)&&isManager&&state.phase!=='price_approved'&&!working){
  if(summary)event.preventDefault();
  working=true;
  try{
   await pausePricingClock();
   const updated=await api('/api/sessions/'+state.id+'/refresh_price',{revision:state.revision,payload:{manual_edit:true},key:crypto.randomUUID()});
   manualPriceOpen=true;
   storeState(updated);
  }catch(error){
   toast(error.message,true);
  }finally{
   working=false;
   render();
  }
 }
});
const explanationResults=new Map();
views.m1=['Giảm giá cuối ngày','Ưu tiên sau 21:00 · Trước đó chỉ xét ngoại lệ dư lớn và bán chậm.'];
views.m2=['Kế hoạch sản lượng','M2 V4 · Kiểm tra lượng chuẩn bị và lý do đề xuất trước mở cửa.'];
function shiftView(){return state.minute>=1020&&!state.phase.startsWith('plan')?'m1':'m2'}
function compactClock(){
 const active=state.phase==='running',canRun=['running','price_pending','price_approved'].includes(state.phase);
 const next=state.minute<1170?1170:Math.min(1320,state.minute+30);
 return '<div class="shift-clock"><div><b>'+hour(state.minute)+'</b><span>'+dateVN(state.day)+' · '+esc(phases[state.phase])+'</span></div><div class="shift-actions">'+
 (state.mode==='simulation'?'<button data-play '+(!canRun?'disabled':'')+'>'+icon(state.realtime?.enabled?'pause':'play')+(state.realtime?.enabled?'Tạm dừng':'Chạy mô phỏng')+'</button>':'')+
 '<button data-advance="'+next+'" '+(!active?'disabled':'')+'>Đến '+hour(next)+'</button><details><summary>Điều khiển</summary><label>Tốc độ <select data-sim-speed>'+[[1,'1 giây = 1 phút'],[5,'1 giây = 5 phút'],[30,'1 giây = 30 phút']].map(([v,t])=>'<option value="'+v+'" '+(state.realtime?.speed===v?'selected':'')+'>'+t+'</option>').join('')+'</select></label><button data-advance="'+Math.min(1320,state.minute+30)+'" '+(!active?'disabled':'')+'>+30 phút</button><button data-simulator-report>Nguồn mô phỏng</button></details></div></div>';
}
function explanationKey(component){const p=state.pending||state.decisions.at(-1);return state.id+':'+component+':'+(component==='m2'?state.input_hash:(p?.id||'waiting')+':'+(p?.status||'none'))}
function explanationPanel(component){
 const cached=explanationResults.get(explanationKey(component));
 const immediate=state.proposal_explanation?.component===component?state.proposal_explanation.answer:null;
 let content=immediate?'<small class="muted">Giải thích từ bằng chứng · có trước khi duyệt</small>'+copilotResponse({answer:immediate},true)+'<p class="muted">Copilot đang chọn các điểm cần chú ý…</p>':'<p class="muted">Copilot đang đọc dữ liệu đề xuất…</p>';
 if(component==='m1'&&state.minute<1170)content='<p>Chưa đến mốc 19:30. Copilot sẽ giải thích cùng đề xuất giá đầu tiên.</p>';
 else if(cached?.answer)content='<small class="muted">Theo đề xuất lúc '+hour(cached.as_of_minute)+(cached.ai_status==='ready'?' · Copilot đã tổng hợp':' · giải thích từ bằng chứng')+'</small>'+copilotResponse(cached,true)+(cached.ai_status==='unavailable'?'<button data-retry-proposal>Thử tổng hợp lại</button>':'');
 else if(cached?.status==='unavailable')content='<p>Copilot chưa phản hồi: '+esc(cached.error)+'</p><p>Tóm tắt từ dữ liệu vẫn hiển thị cạnh từng sản phẩm.</p><button data-go="settings">Kiểm tra kết nối AI</button>';
 return '<aside class="proposal-copilot panel"><div class="panel-head"><h2>'+icon('spark')+' Vì sao đề xuất như vậy?</h2></div><div class="panel-body" id="proposal-ai-text">'+content+'</div><div class="copilot-followup"><button class="small" data-chat>Hỏi thêm Copilot</button><small>Đọc đúng ca và mốc đề xuất; không tự duyệt.</small></div></aside>';
}
function supplyReason(p){const s=p.supply||{},f=p.features||{};return 'Ngày trước (sau khử kích cầu) '+fmt(f.sold_calendar_lag1)+'; trung bình 7 ngày '+fmt(f.sold_last7_observed_mean)+'. '+(p.quantile?'Chọn Q'+fmt(p.quantile*100)+' theo thứ và biên lợi nhuận':'Q50 '+fmt(p.forecast))+' → trần duyệt '+p.prepared+' bánh. Làm đầu ngày '+(s.initial_qty??'—')+'; mẻ 14:00/17:00 chỉ đặt theo lượt bán đã quan sát lúc 12:00/15:00, không tự làm hết trần. Công suất '+s.capacity+'.'+(f.depromo_removed_last7?' Đã tách ước tính '+fmt(f.depromo_removed_last7)+' bánh tăng thêm do khuyến mãi trong 7 ngày.':'');}
function planningWeather(){
 const w=state.weather,rain=w.prior_day_rain_mm,temp=w.prior_day_temp_c;
 return '<div class="planning-weather"><span>'+icon('activity')+' Thời tiết ngày trước '+dateVN(w.weather_reference_date||state.plan[0]?.features?.weather_reference_date)+'</span><b>'+(rain==null||temp==null?'Thiếu dữ liệu — dùng phương án lịch sử':fmt(rain)+' mm mưa · '+fmt(temp)+' °C')+'</b><small>Reanalysis phục vụ mô phỏng, chưa phải forecast có thời điểm phát hành. Mục tiêu còn hàng 21:30 là ước tính, không bảo đảm.</small></div>';
}
function trainingReviewNote(){return '<p>Phiên bản của ca: '+esc(state.model_version)+'. Adapter TRAINED_TESTED/agent_sandbox; M2 đa phân vị Q45/Q50/Q75/Q90 và M1 học từ POS cùng nhịp khách. Quy mô sản lượng mới là cấu hình chính. Tên phân vị không thay cho coverage thực đo.</p>';}
function reportDayActions(){
 if(state.phase==='closed')return '<div class="toolbar"><p>Ngày đã chốt. Kế hoạch tiếp theo dùng kết quả bán và tồn vừa ghi nhận.</p><button class="primary" data-next-day>Tạo kế hoạch ngày kế tiếp</button></div>';
 if(state.phase==='close_pending')return '<div class="toolbar"><p>Đã đến 22:00. Chốt ca để cập nhật lịch sử cho ngày tiếp theo.</p><button class="primary" data-act="close">Chốt ca</button></div>';
 return '';
}
function compactM2(){
 const editable=state.phase==='plan_pending';
 return compactClock()+planningWeather()+'<div class="proposal-layout"><section class="panel"><div class="panel-head"><div><h2>Kế hoạch sáng · '+state.plan.length+' loại bánh</h2><p>Kiểm tra số lượng rồi duyệt; xác nhận chuẩn bị để bắt đầu bán.</p></div></div><div class="table-scroll"><table><thead><tr><th>Sản phẩm và căn cứ đề xuất</th><th>Dự báo gốc</th><th>Chuẩn bị</th></tr></thead><tbody>'+
 state.plan.map(p=>{const s=p.supply;return '<tr><td>'+product(p)+'<p class="sku-reason">'+esc(supplyReason(p))+'</p></td><td>'+fmt(p.v4_plan?.selected_forecast??p.forecast)+'<small class="block muted">'+(p.quantile?'Q'+fmt(p.quantile*100)+' · theo ngày':'Q50 · trước policy V4')+'</small></td><td>'+(editable?'<input class="quantity" type="number" min="4" step="4" max="'+(s?.capacity||100000)+'" data-qty="'+p.sku+'" aria-label="Sản lượng duyệt '+p.sku+'" value="'+(quantityDraft[p.sku]??p.prepared)+'">':String(p.approved??p.prepared))+'<small class="block muted">Đề xuất '+p.prepared+'</small></td></tr>'}).join('')+
 '</tbody></table></div><div class="actionbar"><strong>'+units(state.totals.proposed_prepared)+' chiếc đề xuất</strong>'+(editable?'<button data-reject="plan">Từ chối</button><button class="primary" data-approve="plan">Duyệt kế hoạch</button>':state.phase==='plan_approved'?'<button class="primary" data-act="prepared">Xác nhận đã chuẩn bị</button>':'<span>Đã ghi nhận chuẩn bị</span>')+'</div><details class="context-details"><summary>Giả định & chi tiết model</summary>'+trainingReviewNote()+'<p>M2 chọn Q45–Q50 giữa tuần, Q75–Q90 từ thứ Sáu đến Chủ nhật/ngày lễ; làm tròn mẻ, giới hạn công suất và bổ sung lúc 14:00/17:00. Lịch sử được khử phần bán tăng thêm do khuyến mãi.</p><button data-explain="'+state.plan[0].sku+'">Xem feature và cách tính</button></details></section>'+explanationPanel('m2')+'</div>';
}
function pricingReason(r){const hold=r.predicted_hold_next30,p=r.pricing_policy||{};const reasons={SELLOUT_GATE_88:'Sức bán tốt: khả năng tự bán hết đạt ngưỡng 88%, giữ giá.',PROTECT_STOCK_UNTIL_2130:'Giữ hàng phục vụ đến 21:30.',NO_POSITIVE_NET_GAIN:'Chưa có mức giảm mang lại lợi ích ròng dương.',RESERVE_FINAL_CLEARANCE:'Đã giảm từng bước; giữ lượt điều chỉnh cuối lúc 21:30.',COOLDOWN:'Chưa đủ 30 phút từ lần đổi giá trước.',MAX_APPLIED_CHANGES:'Đã đạt giới hạn số lần đổi giá.',NO_STOCK:'Đã hết hàng.',POSITIVE_INCREMENTAL_NET_GAIN:'Giảm giá cứu được hàng dư với lợi ích ròng kỳ vọng '+money(p.net_gain)+'.'};return 'Tồn '+r.stock+'; bán '+r.sales30+'/30 phút, '+r.sales60+'/60 phút. '+(reasons[r.decision_reason]||(r.reason==='V4_HOLD'?'Giữ giá hiện tại.':'Quản lý xem xét mức giá.'))+(hold==null?'':' Dự báo nếu giữ giá: '+fmt(hold)+' bánh/30 phút.')+(p.sellout_probability_hold==null?'':' Khả năng bán hết trước 22:00: '+fmt(p.sellout_probability_hold*100)+'%; khả năng còn hàng đến 21:30: '+fmt(p.availability_probability_2130*100)+'%.')+' Đây là ước lượng theo mô hình; cần duyệt rồi áp dụng.';}
function priceHistoryReferences(r){
 const h=r.pricing_policy?.history;if(!h?.comparisons)return '';
 const labels={yesterday:'Hôm trước',two_days_ago:'Hai ngày trước',week_ago:'Tuần trước',month_ago:'Tháng trước'};
 return '<details class="context-details"><summary>Lịch sử sức bán tham chiếu</summary>'+Object.entries(h.comparisons).map(([k,v])=>'<p>'+labels[k]+' · '+dateVN(v.day)+': '+(v.source==='MISSING'?'chưa có dữ liệu':units(v.sold)+' chiếc cả ngày; '+units(v.sales60)+' chiếc cùng cửa sổ 60 phút · '+(v.source==='OWN_CLOSED_BRANCH'?'ca trước đã chốt cùng kịch bản':'baseline proxy, chỉ tham khảo vì khác kịch bản'))+'</p>').join('')+'<p>Ước tính bán tiếp từ lịch sử cùng kịch bản: '+(h.own_remaining_projection==null?'chưa đủ dữ liệu':units(h.own_remaining_projection)+' chiếc')+'.</p></details>';
}
function changedPriceRows(proposal){return (proposal?.rows||[]).filter(r=>(r.approved??r.discount)!==r.previous);}
function heldPriceReasons(proposal){
 const rows=(proposal?.rows||[]).filter(r=>(r.approved??r.discount)===r.previous).concat(proposal?.held_rows||[]);
 const editable=state.phase==='price_pending'&&state.pending?.status!=='missing_data',manager=authUser?.role==='manager';
 if(!manager||state.minute<1170||state.minute>=1320)return '';
 const controls=editable?(rows.map(r=>'<label class="field">'+esc(state.plan.find(p=>p.sku===r.sku)?.name||r.sku)+' · hiện tại '+money(Math.round(r.price*(1-r.previous/100)))+'<select data-discount="'+r.sku+'" data-price="'+r.price+'">'+ladder.filter(t=>t>=Math.max(r.previous,r.floor)&&t<=r.cap).map(t=>'<option value="'+t+'" '+((discountDraft[r.sku]??r.discount)===t?'selected':'')+'>'+fmt(t)+'%</option>').join('')+'</select><span data-new-price="'+r.sku+'">'+money(Math.round(r.price*(1-(discountDraft[r.sku]??r.discount)/100)))+'</span></label>').join('')+'<div class="actionbar" style="margin-top:14px"><button class="primary" data-approve="price">Duyệt thay đổi giá</button></div>'):'<button data-manual-pricing '+(state.phase==='price_approved'?'disabled':'')+'>Mở bảng chỉnh giá thủ công</button>';
 const isOpen=(manualPriceOpen||editable)?' open':'';
 return '<details class="context-details" id="manual-price-section"'+isOpen+'><summary>Quản lý chỉnh giá món đang giữ giá</summary><p>Chọn món cần điều chỉnh, ghi lý do khi duyệt rồi áp dụng giá.</p>'+controls+'</details>';
}
function compactM1(){
 const proposal=state.pending||state.decisions.at(-1),pending=state.phase==='price_pending',approved=state.phase==='price_approved';
 let body='';
 if(state.pending?.status==='missing_data')body='<p class="notice">'+esc(state.pending.blocked_reason)+'</p>';
 else if(pending||approved){
  body='<div class="panel-head"><div><h2>'+changedPriceRows(state.pending).length+' sản phẩm thay đổi giá</h2><p>Mức giảm tổng so với niêm yết, không cộng dồn. Các món giữ giá nằm trong mục chỉnh thủ công.</p></div></div><div class="price-changes">'+changedPriceRows(state.pending).map(r=>{
   const p=state.plan.find(p=>p.sku===r.sku),v=discountDraft[r.sku]??r.approved??r.discount;
   return '<article class="price-change">'+product(p)+'<div style="margin:14px 0;padding:10px 14px;background:#f6f7fb;border-radius:8px;color:#17324d"><span>Còn tồn / Sản lượng đã duyệt đầu ngày</span><strong style="display:block;margin-top:4px;font-size:18px">'+fmt(r.stock??state.products[r.sku].stock)+' / '+fmt(state.products[r.sku].planned_total??p.approved??p.prepared)+' bánh</strong><span style="font-size:12px">Snapshot '+String(Math.floor(state.pending.minute/60)).padStart(2,'0')+':'+String(state.pending.minute%60).padStart(2,'0')+'</span></div><div class="cash-change"><span>'+money(Math.round(r.price*(1-r.previous/100)))+'</span><b>→ '+money(r.new_price)+'</b><strong>Giảm '+fmt(r.discount)+'%</strong></div><p class="sku-reason">'+esc(pricingReason(r))+'</p>'+priceHistoryReferences(r)+'<label class="field">Kênh đổi giá<select data-v4-channel="'+r.sku+'"><option value="eink" '+((v4Channels[state.id+':'+r.sku]||state.products[r.sku].price_channel||'eink')==='eink'?'selected':'')+'>E-ink có sẵn · 0đ/lần (mô phỏng)</option><option value="sticker" '+((v4Channels[state.id+':'+r.sku]||state.products[r.sku].price_channel)==='sticker'?'selected':'')+'>Tem sản phẩm đóng hộp · 350đ/lần</option></select></label>'+(pending?'<div class="manager-discount-edit"><label>Mức giảm Manager duyệt</label><select data-discount="'+r.sku+'" data-price="'+r.price+'">'+[...new Set([...ladder,r.discount])].sort((a,b)=>a-b).filter(t=>t>=Math.max(r.previous,r.floor)&&t<=r.cap).map(t=>'<option value="'+t+'" '+(v===t?'selected':'')+'>'+fmt(t)+'%</option>').join('')+'</select><span data-new-price="'+r.sku+'">'+money(Math.round(r.price*(1-v/100)))+'</span></div>':'')+'</article>';
  }).join('')+'</div><div class="actionbar">'+(pending?'<button data-reject="price">Giữ giá hiện tại</button><button class="primary" data-approve="price">Duyệt thay đổi giá</button>':'<button class="primary" data-act="price_apply">Áp dụng giá đã duyệt</button>')+'</div>';
 }else if(proposal?.status==='applied'||proposal?.status==='shadow_only'){
  body='<div class="panel-head"><h2>'+(proposal.status==='applied'?'Đã áp dụng giá đã duyệt':'Đã ghi nhận thử nghiệm Shadow')+'</h2></div><div class="panel-body"><p>'+(proposal.status==='applied'?'Giá hiện tại trong ca đã cập nhật theo quyết định Manager.':'Giá giao dịch giữ nguyên; chỉ lưu quyết định thử.')+'</p><div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px">'+changedPriceRows(proposal).map(r=>{const p=state.products[r.sku];return '<article class="card" style="padding:16px;min-width:0"><strong>'+esc(r.sku)+'</strong><p>Giá hiện tại: <b>'+money(Math.round(p.price*(1-p.discount/100)))+'</b></p><p>Đã duyệt '+fmt(r.approved)+'% · price_version '+p.price_version+'</p><small style="overflow-wrap:anywhere">'+esc(p.pos_ack?.channel||'Giữ giá')+' · '+esc(p.pos_ack?.status||'Không phát lệnh mới')+'</small></article>'}).join('')+'</div><p>Mở mục chỉnh thủ công bên dưới nếu cần xem xét tiếp; hệ thống vẫn kiểm tra khoảng cách và số lần đổi giá.</p></div>';
 }else body='<div class="hold-message"><span>'+icon('check')+'</span><h2>'+(state.minute<1170?'Chưa đến mốc đánh giá giá':'Giữ nguyên giá hiện tại')+'</h2><p>'+(state.minute<1170?'Từ 19:30, đánh giá từng món theo sức bán, tồn dự kiến và thời gian còn lại; không bắt buộc giảm.':'Chưa có phương án giảm thêm phù hợp với tồn, sức bán và mục tiêu phục vụ. Quản lý có thể mở mục chỉnh thủ công bên dưới. Không cần duyệt; ca tiếp tục chạy.')+'</p></div>';
 const scenarioNote=state.weather.price_response_scenario?'<p class="notice">M1 xem xét giá từ 19:30. Giảm từng bước khi có lợi hơn giữ giá; đến 21:30 có thể giảm sâu nếu cần xả tồn trước 22:00. Quản lý duyệt rồi áp dụng.</p>':'';
 return compactClock()+kpis()+scenarioNote+'<div class="proposal-layout"><section class="panel">'+body+heldPriceReasons(proposal)+'</section>'+explanationPanel('m1')+'</div>'+(state.phase==='close_pending'?'<div class="actionbar"><button class="primary" data-act="close">Chốt ca</button></div>':'');
}
function compactReport(){
 const t=state.totals;
 return reportDayActions()+businessHistoryPanel()+'<section class="report-summary"><article class="panel panel-body"><h2>Lãi góp mô phỏng</h2><strong class="unknown-value">'+(t.prepared?money(t.contribution_before_overhead):'Chưa xác nhận chuẩn bị')+'</strong><p>Doanh thu '+money(t.revenue)+' − tổng chi phí SX và phí vận hành markdown/hủy '+money(t.revenue-t.contribution_before_overhead)+'.</p><p><b>Giá vốn đơn vị từ bộ V4 × toàn bộ số bánh đã làm; phí hủy 150đ/bánh khi chốt và phí markdown theo kênh.</b> Đã bao gồm giá vốn hàng còn lại, không trừ lần hai. Phí hủy chỉ ghi nhận lúc chốt. Chưa trừ chi phí cố định; đây là lãi góp mô phỏng, chưa phải lợi nhuận ròng.</p></article><article class="panel panel-body"><h2>Lượt mua không phục vụ được</h2><strong class="unknown-value">'+(t.lost_simulator_only===null?'Chưa đo lường':units(t.lost_simulator_only)+' lượt')+'</strong><p>'+(t.lost_simulator_only===null?'Giao dịch thực không tự cung cấp nhu cầu bị mất.':t.lost_simulator_only===0?'Không có yêu cầu mua bị mất do hết hàng trong luồng khách mô phỏng đã sinh.':'Các lượt yêu cầu mua không được đáp ứng do hết hàng trong mô phỏng.')+'</p></article></section><details class="context-details"><summary>Đối soát và xác nhận báo cáo</summary>'+evaluationPanel()+'</details>';
}
function compactSettings(){const ai=state.ai;return '<section class="panel panel-body compact-settings"><h2>Kết nối Copilot</h2><p>M1/M2 V4 chạy local. Copilot đọc kết quả để giải thích ngay bên cạnh đề xuất.</p><form id="settings-form"><label class="field">Dịch vụ<select id="ai-provider">'+['Ollama','Gemini','OpenAI'].map(v=>'<option '+(ai.provider===v?'selected':'')+'>'+v+'</option>').join('')+'</select></label><label class="field">Model<input id="ai-model" value="'+esc(ai.model)+'"></label><label class="field">API key<input id="api-key" type="password" autocomplete="off" placeholder="Ollama không cần key"></label><button class="primary" type="submit">Kết nối & gọi thử AI</button></form><p>'+(ai.verified?'Đã xác minh bằng công cụ dữ liệu của ca.':'Chưa xác minh kết nối hiện tại.')+'</p></section>'}

const originalWorkspaceRender=render;
render=function(){
 if(currentView==='overview')currentView='m2';
 if(!state)return;
 const shift=shiftView();
 if(['m1','m2'].includes(currentView))currentView=shift;
 shiftSession=state.id;shiftName=shift;
 m2=compactM2;m1=compactM1;reports=compactReport;settings=compactSettings;
 originalWorkspaceRender();
 const morning=document.querySelector('[data-view="m2"]'),evening=document.querySelector('[data-view="m1"]');
 if(morning){morning.hidden=shift!=='m2';morning.style.display=shift==='m2'?'':'none';}
 if(evening){evening.hidden=shift!=='m1';evening.style.display=shift==='m1'?'':'none';}

 const nav=document.querySelector('.sidebar nav');
 if(!document.getElementById('advanced-nav')){
  const details=document.createElement('details');details.id='advanced-nav';details.innerHTML='<summary>Hệ thống & dữ liệu</summary>';
  ['data','monitoring','readiness','registry','safety','audit'].forEach(v=>{const b=nav.querySelector('[data-view="'+v+'"]');if(b)details.appendChild(b)});
  nav.appendChild(details);nav.querySelectorAll('.nav-label,.nav-sep').forEach(n=>n.remove());
  const learning=nav.querySelector('[data-view="learning"]');if(learning)details.appendChild(learning);
 }
 $('upload-shortcut').hidden=true;
 document.querySelector('.footer span').textContent='SmartFresh V4 · POS mô phỏng · Ca '+dateVN(state.day);
 if(['m1','m2'].includes(currentView))refreshProposalExplanation();
 if(currentView==='reports'){refreshBusinessHistory();refreshReportAnalysis();}
};
async function refreshProposalExplanation(){
 if(explainBusy||!state||!['m1','m2'].includes(currentView)||currentView==='m1'&&state.minute<1170)return;
 const component=currentView,key=explanationKey(component);if(['ready','unavailable'].includes(explanationResults.get(key)?.status))return;
 explainBusy=true;
 try{
  const r=await api('/api/proposal-explanation/'+state.id+'?component='+component);explanationResults.set(key,r);
  if(state&&key===explanationKey(component)&&component===currentView){const target=$('proposal-ai-text');if(target)target.innerHTML=r.answer?'<small class="muted">Đọc trước khi duyệt · '+hour(r.as_of_minute)+(r.ai_status==='ready'?' · Copilot đã tổng hợp':' · lời giải thích từ bằng chứng')+'</small>'+copilotResponse(r,true)+(r.ai_status==='unavailable'?'<button data-retry-proposal>Thử tổng hợp lại</button>':''):target.innerHTML}
 }catch(e){explanationResults.set(key,{status:'unavailable',error:e.message});if($('proposal-ai-text'))$('proposal-ai-text').textContent='Chưa nhận được giải thích AI: '+e.message}
 finally{explainBusy=false}
}
setInterval(refreshProposalExplanation,2500);
document.addEventListener('click',async e=>{if(e.target.closest('[data-retry-proposal]')){const component=currentView;explanationResults.delete(explanationKey(component));await api('/api/proposal-explanation/'+state.id+'?component='+component+'&retry=true');refreshProposalExplanation()}});
