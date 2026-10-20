'use strict';
const $ = id => document.getElementById(id);
const paths = {
  spark:'M12 2 4 13h7l-1 9 10-13h-7l1-7Z',
  dashboard:'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
  bread:'M5 11C1 9 3 4 7 4c2-3 8-3 10 0 4 0 6 5 2 7v9H5zM9 12v4m6-4v4',
  store:'M3 10 5 3h14l2 7M3 10c0 4 5 4 6 0 0 4 6 4 6 0 1 4 6 4 6 0M5 13v8h14v-8M9 21v-6h6v6',
  tag:'M3 3h8l10 10-8 8L3 11V3Z M7 7h.01',
  activity:'M3 12h4l3-8 4 16 3-8h4',
  chart:'M4 3v18h17M8 16v-4m5 4V7m5 9v-6',
  database:'M20 6c0 2-4 4-8 4S4 8 4 6s4-4 8-4 8 2 8 4ZM4 6v12c0 2 4 4 8 4s8-2 8-4V6M4 12c0 2 4 4 8 4s8-2 8-4',
  history:'M3 11a9 9 0 1 1 2 7M3 4v7h7M12 7v5l3 2',
  settings:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM9 3l1-1h4l1 3 3 1 3 1v4l-2 2v3l-2 3-3 1-2 2-3-2-3-1-1-3-2-2V9l2-2 3-1Z',
  chevron:'m9 5 7 7-7 7', plus:'M12 5v14M5 12h14',
  upload:'M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6',
  download:'M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4',
  arrow:'M4 12h16m-5-5 5 5-5 5', clock:'M12 7v5l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z',
  check:'m5 12 4 4L19 6', close:'m6 6 12 12M6 18 18 6',
  shield:'m12 2 9 4v6c0 6-9 10-9 10S3 18 3 12V6l9-4Zm-4 10 3 3 5-6',
  box:'m3 7 9-5 9 5-9 5-9-5Zm0 0v11l9 4 9-4V7M12 12v10m-5-17 10 5',
  coin:'M3 7c0-2 4-4 9-4s9 2 9 4-4 4-9 4-9-2-9-4Zm0 0v10c0 2 4 4 9 4s9-2 9-4V7M3 12c0 2 4 4 9 4s9-2 9-4',
  search:'M20 20 15 15M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0Z',
  info:'M12 11v6m0-10h.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z',
  play:'m8 4 12 8-12 8V4Z', pause:'M8 4v16M16 4v16',
  file:'M14 2H5v20h14V7l-5-5Zm0 0v6h5M8 12h8m-8 4h8',
  sun:'M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1 1m12 12 1 1M5 19l1-1M18 6l1-1M17 12a5 5 0 1 1-10 0 5 5 0 0 1 10 0Z',
  chat:'M21 11a9 9 0 0 1-9 9H3l2-5a9 9 0 1 1 16-4ZM8 10h8m-8 4h5',
  menu:'M3 6h18M3 12h18M3 18h18'
};
const icon = (name, cls='') => '<svg class="icon '+cls+'" viewBox="0 0 24 24" aria-hidden="true"><path d="'+(paths[name] || paths.spark)+'"/></svg>';
function icons(root=document){root.querySelectorAll('[data-icon]').forEach(el=>{el.innerHTML=icon(el.dataset.icon);el.removeAttribute('data-icon')});}
const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = n => new Intl.NumberFormat('vi-VN',{maximumFractionDigits:1}).format(n ?? 0);
const units = n => new Intl.NumberFormat('vi-VN',{maximumFractionDigits:0}).format(Math.round(n??0));
const money = n => new Intl.NumberFormat('vi-VN',{maximumFractionDigits:0}).format(n ?? 0)+' ₫';
const hour = n => String(Math.floor(n/60)).padStart(2,'0')+':'+String(n%60).padStart(2,'0');
const dateVN = d => d.split('-').reverse().join('/');
const phases = {plan_pending:'Chờ duyệt sản lượng',plan_approved:'Chờ xác nhận chuẩn bị',plan_rejected:'Kế hoạch đã từ chối',running:'Đang vận hành',price_pending:'Chờ duyệt giá',price_approved:'Chờ áp dụng giá',close_pending:'Chờ chốt ngày',closed:'Đã chốt ngày'};
const views = {
  overview:['Tổng quan vận hành','Một ngày tươi mới, bắt đầu từ những quyết định tốt hơn.'],
  m2:['Kế hoạch sản lượng','M2 · Dự báo nhu cầu và lập kế hoạch chuẩn bị theo từng SKU.'],
  m1:['Giảm giá cuối ngày','M1 · Tối ưu lịch giá từ 19:30 đến 22:00, cập nhật mỗi 30 phút.'],
  ledger:['Giao dịch & theo dõi','Theo dõi tồn kho và doanh thu theo giá có hiệu lực tại từng giao dịch.'],
  reports:['Báo cáo hiệu quả','Đọc đồng thời doanh thu, hàng dư và nguy cơ thiếu hàng.'],
  data:['Dữ liệu đầu vào','Tải tệp, kiểm tra và xác nhận. AI tự tạo kế hoạch từ dữ liệu hợp lệ.'],
  learning:['Học từ dữ liệu','Kết quả thực tế → huấn luyện → đánh giá → xác nhận phiên bản mới.'],
  audit:['Nhật ký quyết định','Mỗi đề xuất, xác nhận và lần áp dụng đều có dấu vết.'],
  settings:['Cài đặt AI','Quản lý Ollama, Gemini, OpenAI và nguồn dữ liệu.']
};
let state=null, meta=null, history=[], currentView='overview', working=false, fetchCount=0, timer=null, preview=null, uploadDay='', reportTab='current', reference=null, auditRows=[], query='', chatMessages=[], chatSession=null;
const ladder=[0,20,25,30,35,40,45,50];
let toastTimer;
let quantityDraft={}, discountDraft={};
let connectionResult=null;
let learningState=null;
let geminiModels=[];
function toast(message,error=false){$('toast').textContent=message;$('toast').classList.toggle('error',error);$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,error?10000:4500)}
async function api(path,body,method){
  fetchCount++;$('loading').hidden=false;
  try{
    const options={method:method || (body?'POST':'GET')};
    if(body instanceof FormData) options.body=body;
    else if(body){options.body=JSON.stringify(body);options.headers={'Content-Type':'application/json'};}
    const r=await fetch(path,options);
    const result=await r.json();
    if(!r.ok)throw Error(result.error || (Array.isArray(result.detail)?result.detail.map(x=>x.msg).join('; '):result.detail) || 'Không thực hiện được yêu cầu.');
    return result;
  }finally{fetchCount--;if(!fetchCount)$('loading').hidden=true}
}
function stop(){clearInterval(timer);timer=null;}
function storeState(value){state=value;quantityDraft={};discountDraft={};localStorage.setItem('smartfresh-session',state.id);if(state.phase!=='running')stop();render();refreshDayHistory();}
async function act(name,payload={}){
  if(working)return;working=true;
  document.querySelectorAll('[data-act],[data-approve],[data-advance]').forEach(b=>b.disabled=true);
  try{
    const value=await api('/api/sessions/'+state.id+'/'+name,{revision:state.revision,payload,key:crypto.randomUUID()});
    storeState(value);
    if(value.learning_collection){const c=value.learning_collection;toast(c.warning?'Đã chốt ca; chưa thu được dữ liệu học: '+c.warning:'Đã chốt ca và lưu '+c.added+' dòng kết quả để học. Model chưa tự thay đổi.',!!c.warning)}
    else if(['plan_approve','prepared','price_approve','price_apply','close','plan_reject','price_reject'].includes(name))toast('Đã lưu: '+phases[state.phase]+'.');
    if(name==='advance' && state.phase==='price_pending')toast('M1 đã tính đề xuất lúc '+hour(state.minute)+'. Cần quản lý xác nhận.');
  }catch(e){stop();toast(e.message,true);try{storeState(await api('/api/state?session_id='+state.id))}catch(_){}}
  finally{working=false;render()}
}
function badge(text,color=''){return '<span class="badge '+color+'">'+esc(text)+'</span>'}
function kpi(label,value,unit,detail,ic){return '<article class="card kpi"><div class="kpi-top">'+label+'<span class="kpi-icon">'+icon(ic)+'</span></div><div class="value">'+value+(unit?'<small>'+unit+'</small>':'')+'</div><div class="kpi-foot">'+detail+'</div></article>'}
function kpis(){
  const t=state.totals, started=Object.keys(state.products).length>0;
  return '<section class="kpis" aria-label="Chỉ số ca vận hành">'+
    kpi(started?'Đã chuẩn bị':'Sản lượng đề xuất',fmt(started?t.prepared:t.proposed_prepared),'bánh',started?'Đã xác nhận chuẩn bị':'Dự kiến · Chờ xác nhận', 'bread')+
    kpi('Bán đã ghi nhận',started&&!state.sales_feed?.missing?fmt(t.sold):'—','bánh',state.sales_feed?.missing?'Chưa có nguồn giao dịch':started?'<em>'+fmt(t.sell_through_pct)+'%</em> sản lượng đã bán':'Chưa bắt đầu ca bán','box')+
    kpi(state.phase==='closed'?'Hàng dư cuối ngày':'Tồn hiện tại',started?fmt(t.stock):'—','bánh',state.phase==='closed'?'Đã chốt · Cần xử lý hàng dư':started?'Đối soát từ sổ giao dịch':'Ghi nhận sau khi chuẩn bị','database')+
    kpi('Doanh thu đã ghi nhận',started?money(t.revenue):'—','',started?fmt(state.ledger.length)+' dòng giao dịch':'Chưa phát sinh giao dịch','coin')+'</section>';
}
function clockbar(){
  const active=state.phase==='running';
  const canRun=state.mode==='simulation'&&['running','price_pending','price_approved'].includes(state.phase),playing=!!state.realtime?.enabled;
  const next=state.minute<1170?1170:Math.min(1320,state.minute+30);
  return '<div class="clockbar"><span class="clock-icon">'+icon('clock')+'</span><time>'+hour(state.minute)+'</time><div class="clock-meta"><strong>'+dateVN(state.day)+'</strong><br>Đồng hồ '+(state.mode==='simulation'?'mô phỏng':'ca nhập liệu')+'</div>'+
    badge(phases[state.phase],active?'green':state.phase==='closed'?'blue':'amber')+
    '<div class="clock-controls">'+(state.mode==='simulation'?'<button data-play '+(!canRun?'disabled':'')+'>'+icon(playing?'pause':'play')+(playing?'Tạm dừng':'Bán tự động')+'</button>':'')+'<button data-advance="'+Math.min(1320,state.minute+30)+'" '+(!active?'disabled':'')+'>+30 phút</button><button data-advance="'+next+'" '+(!active?'disabled':'')+'>Đến '+hour(next)+'</button><button data-advance="1320" '+(!active?'disabled':'')+'>Đến 22:00</button></div></div>'+simulationStatus();
}
function stage(){
  const p=state.phase;
  return p.startsWith('plan')?0:p==='closed'?3:p==='close_pending'?2:1;
}
function progress(){
  const n=stage();
  return '<article class="card progress-card"><h3>Tiến trình ca làm '+badge(state.mode==='simulation'?'MÔ PHỎNG':'DỮ LIỆU NHẬP',state.mode==='simulation'?'pink':'blue')+'</h3><div class="steps">'+
    [['Kế hoạch sản lượng','Dự báo & xác nhận chuẩn bị','06:00'],['Giá cuối ngày','Đề xuất & duyệt giá','19:30'],['Chốt kết quả','Đối soát & lưu lịch sử','22:00']].map((s,i)=>'<div class="step '+(i<n?'done':i===n?'current':'')+'"><span class="step-number">'+(i<n?'✓':i+1)+'</span><div><strong>'+s[0]+'</strong><small>'+s[1]+'</small></div><time>'+s[2]+'</time></div>').join('')+'</div></article>';
}
function pendingContent(){
  const p=state.phase;
  const text={
    plan_pending:['Kế hoạch mới đang chờ bạn',state.plan.length+' SKU đã được M2 dự báo và tính sản lượng. Xem chi tiết trước khi duyệt.','Xem kế hoạch','m2'],
    plan_approved:['Đã duyệt kế hoạch sản lượng','Xác nhận đã chuẩn bị xong để hệ thống ghi nhận tồn đầu ngày.','Xác nhận đã chuẩn bị','prepared'],
    plan_rejected:['Kế hoạch đã được từ chối','Tạo một ca mới hoặc tải dữ liệu mới để AI lập lại kế hoạch.','Tạo ca mới','new'],
    running:['Ca làm đang được theo dõi','Tới mốc 19:30, M1 tự tính đề xuất từ tồn và doanh số vừa quan sát.','Xem hoạt động','ledger'],
    price_pending:['Đề xuất giá đang chờ duyệt','M1 đã tính các phương án hợp lệ cho chu kỳ '+hour(state.minute)+'.','Xem đề xuất giá','m1'],
    price_approved:['Giá mới đã được duyệt','Xác nhận áp dụng để các giao dịch tiếp theo sử dụng giá mới.','Áp dụng giá đã duyệt','price_apply'],
    close_pending:['Sẵn sàng chốt ngày','Hệ thống đã đi qua đầy đủ các mốc. Xác nhận lưu kết quả cuối ngày.','Chốt ngày','close'],
    closed:['Ca vận hành đã hoàn tất','Doanh thu và tồn kho đã đối soát. Dữ liệu bán được lưu cho ngày tiếp theo.','Xem kết quả','reports']
  }[p];
  const action=['prepared','price_apply','close'].includes(text[3])?'data-act="'+text[3]+'"':text[3]==='new'?'data-new':'data-go="'+text[3]+'"';
  return '<h4>'+text[0]+'</h4><p>'+text[1]+'</p><div class="status-line">'+(p.includes('pending')?'● Cần xác nhận của quản lý':p==='running'?'● Đang vận hành':'● Đã ghi nhận')+'</div><button '+action+' class="'+(p.includes('pending')?'primary':'')+'">'+text[2]+icon('arrow')+'</button>';
}
function product(p){
  return '<div class="product-cell"><span class="product-icon">'+icon('bread')+'</span><div><strong>'+esc(p.name)+'</strong><small>'+esc(p.sku)+'</small></div></div>';
}
function explainButton(sku){return '<button class="ghost small" data-explain="'+sku+'" aria-label="Xem giải thích '+sku+'">'+icon('info')+'</button>'}
function searchBox(){return '<label class="search">'+icon('search')+'<input type="search" id="table-search" placeholder="Tìm sản phẩm…" value="'+esc(query)+'" aria-label="Tìm sản phẩm"></label>'}
function filtered(){return state.plan.filter(p=>(p.name+' '+p.sku).toLowerCase().includes(query.toLowerCase()))}
function historyChart(){
  const rows=history.slice(-7), w=650,h=170, top=16,bottom=35,left=34, max=Math.ceil(Math.max(...rows.map(r=>r.sold),1)/50)*50;
  let svg='<svg class="chart" viewBox="0 0 '+w+' '+h+'" role="img" aria-label="Số bánh đã bán theo 7 ngày lịch sử nguồn V9">';
  for(let i=0;i<=3;i++){const y=top+(h-bottom-top)*i/3;svg+='<line class="grid" x1="'+left+'" y1="'+y+'" x2="'+(w-8)+'" y2="'+y+'"/><text x="0" y="'+(y+3)+'">'+Math.round(max*(1-i/3))+'</text>';}
  const step=(w-left-15)/Math.max(rows.length,1);
  rows.forEach((r,i)=>{const height=r.sold/max*(h-bottom-top),x=left+i*step+step*.2;svg+='<rect class="bar '+(i===rows.length-1?'last':'')+'" x="'+x+'" y="'+(h-bottom-height)+'" width="'+step*.55+'" height="'+height+'" rx="4"><title>'+dateVN(r.day)+': '+r.sold+' bánh</title></rect><text text-anchor="middle" x="'+(x+step*.275)+'" y="'+(h-11)+'">'+r.day.slice(8)+'/'+r.day.slice(5,7)+'</text>';});
  return svg+'</svg>';
}
function overview(){
  const plan=stage()===0;
  return '<section class="hero-grid"><article class="hero"><div class="eyebrow">SMARTFRESH AI · '+(plan?'KẾ HOẠCH SẴN SÀNG':'ĐỒNG HÀNH CÙNG CA LÀM')+'</div><h2>'+(plan?'Sẵn sàng cho một ngày<br>tươi mới, vừa đủ.':'Đúng lượng hàng.<br>Đúng thời điểm. Đúng giá.')+'</h2><p>'+(plan?'AI đã phân tích lịch sử và thời tiết để đề xuất sản lượng cho từng loại bánh.':'M1 và M2 kết nối kế hoạch sản lượng với diễn biến bán hàng trong ngày.')+'</p><div class="hero-bottom"><button data-go="'+(plan?'m2':'m1')+'">'+(plan?'Xem kế hoạch AI':'Xem đề xuất giá')+icon('arrow')+'</button><span class="hero-meta">'+state.plan.length+' SKU · '+fmt(state.totals.proposed_prepared)+' bánh đề xuất</span></div><span class="spark">✧</span></article>'+progress()+'</section>'+
    kpis()+clockbar()+'<section class="cols"><div class="col-stack"><article class="panel"><div class="panel-head"><div><h2>Lịch sử bán gần đây</h2><p>7 ngày trước '+dateVN(state.day)+' · Lịch sử của ca đã chọn</p></div><span class="chart-legend"><i></i>Đã bán · bánh</span></div><div class="panel-body">'+historyChart()+'</div></article>'+
    '<article class="panel"><div class="panel-head"><div><h2>Kế hoạch theo sản phẩm</h2><p>Đầu ra suy luận mới từ mô hình M2 đã khóa</p></div><button class="ghost small" data-go="m2">Xem tất cả '+icon('arrow')+'</button></div><div class="table-scroll"><table><thead><tr><th>Sản phẩm</th><th>Dự báo</th><th>Đề xuất</th><th>Trạng thái</th><th></th></tr></thead><tbody>'+
    state.plan.map(p=>'<tr><td>'+product(p)+'</td><td>'+units(p.forecast)+'</td><td class="num-accent">'+p.prepared+' bánh</td><td>'+badge(p.approved?'Đã duyệt':state.phase==='plan_rejected'?'Từ chối':'Chờ duyệt',p.approved?'green':'amber')+'</td><td>'+explainButton(p.sku)+'</td></tr>').join('')+'</tbody></table></div><div class="table-foot"><span>'+state.plan.length+' sản phẩm · Mẻ 4 bánh</span><span>Tổng đề xuất <strong>'+fmt(state.totals.proposed_prepared)+' bánh</strong></span></div></article></div>'+
    '<div class="col-stack right-column"><article class="panel attention"><h3>'+icon('check')+'Việc cần xác nhận</h3>'+pendingContent()+'</article><article class="copilot-card"><h3>'+icon('spark')+'SmartFresh Copilot</h3><p>Hiểu vì sao AI đề xuất, từ dữ liệu và kết quả mô hình của chính ca này.</p><button data-chat>Trao đổi với Copilot '+icon('arrow')+'</button></article><article class="card"><div class="eyebrow muted">CONTEXT NGÀY VẬN HÀNH</div><div class="setting-line"><span>Ngày mục tiêu</span><strong>'+dateVN(state.day)+'</strong></div><div class="setting-line"><span>Mưa dự báo</span><strong>'+fmt(state.weather.forecast_rain_mm_previous_day1)+' mm</strong></div><div class="setting-line"><span>Nhiệt độ dự báo</span><strong>'+fmt(state.weather.forecast_temperature_max_c_previous_day1)+'°C</strong></div><div class="setting-line"><span>Ngày lễ</span><strong>'+(state.weather.is_public_holiday?'Có':'Không')+'</strong></div><small class="muted" style="font-size:9px;line-height:1.7;display:block;margin-top:13px">Forecast V9 theo previous_day1; thời điểm phát hành từng giờ chưa được xác minh.</small></article></div></section>';
}
function m2(){
  const editable=state.phase==='plan_pending';
  return clockbar()+'<div class="notice pink">'+icon('spark')+' Nhu cầu dự báo và sản lượng chuẩn bị là hai giá trị khác nhau. M2 cộng đệm theo SKU, làm tròn mẻ 4 và bảo vệ sàn 90% baseline.</div><div class="toolbar"><div class="toolbar-left">'+badge('M2 · LightGBM','pink')+badge('Quantile 0,85')+'</div>'+searchBox()+'</div><article class="panel"><div class="panel-head"><div><h2>Kế hoạch cho '+dateVN(state.day)+'</h2><p>'+esc(state.source)+' · '+state.plan.length+' SKU</p></div>'+badge(phases[state.phase],editable?'amber':'green')+'</div><div class="table-scroll"><table><thead><tr><th>Sản phẩm</th><th>Baseline</th><th>Nhu cầu dự báo</th><th>Đệm &amp; quy đổi mẻ</th><th>Sàn</th><th>AI đề xuất</th><th>Số duyệt</th><th></th></tr></thead><tbody>'+
    filtered().map(p=>'<tr><td>'+product(p)+'</td><td>'+p.baseline+'</td><td>'+units(p.forecast)+'</td><td>+'+units(Math.max(0,Math.ceil((p.forecast+p.buffer)/4)*4-Math.round(p.forecast)))+'</td><td>'+p.floor+'</td><td class="num-accent">'+p.prepared+'</td><td>'+(editable?'<input class="quantity" aria-label="Sản lượng duyệt '+p.sku+'" data-qty="'+p.sku+'" type="number" min="'+p.floor+'" step="4" max="100000" value="'+(quantityDraft[p.sku]??p.approved??p.prepared)+'">':p.approved??'—')+'</td><td>'+explainButton(p.sku)+'</td></tr>').join('')+'</tbody></table></div><div class="actionbar"><div class="summary"><strong>'+fmt(state.totals.proposed_prepared)+'</strong>bánh đề xuất · '+units(state.totals.forecast_units??state.totals.forecast)+' bánh nhu cầu dự báo</div>'+
    (editable?'<button class="danger" data-reject="plan">Từ chối</button><button class="primary" data-approve="plan">'+icon('check')+'Duyệt kế hoạch</button>':state.phase==='plan_approved'?'<button class="primary" data-act="prepared">'+icon('check')+'Xác nhận đã chuẩn bị</button>':'<button data-new>Tạo ca mới</button>')+'</div></article><div class="notice" style="margin-top:20px">Quantile 0,85 dùng để tính đệm tồn kho; không phải cam kết dự báo chính xác 85%. Giá và số lượng theo SKU master V9.</div>';
}
function m1(){
  const proposal=state.pending || state.decisions.at(-1);
  const rows=proposal?.rows || [], editable=state.phase==='price_pending';
  if(proposal?.status==='missing_data')return clockbar()+'<article class="panel empty"><div class="empty-icon">'+icon('database')+'</div><h3>Thiếu dữ liệu bán hàng để đề xuất giá</h3><p>Ca này nhận giao dịch từ tệp; hiện chưa có giao dịch nào. 0/0 không chứng minh thực tế chưa bán.</p><div class="modal-actions"><button data-go="data">Nạp giao dịch</button><button class="primary" data-fork-simulation>Tạo bản mô phỏng riêng</button><button data-confirm-zero>Xác nhận thực tế chưa bán</button></div></article>';
  if(!rows.length)return clockbar()+'<article class="panel empty"><div class="empty-icon">'+icon('tag')+'</div><h3>Chờ khung giờ giảm giá</h3><p>M1 bắt đầu lúc 19:30, sử dụng tồn hiện tại, doanh số 30/60 phút và dự báo M2. Xác nhận chuẩn bị rồi chuyển đến mốc đầu tiên.</p><button class="primary" '+(state.phase==='running'?'data-advance="1170"':'data-go="m2"')+'>'+(state.phase==='running'?'Đến 19:30':'Mở kế hoạch sản lượng')+icon('arrow')+'</button></article>';
  return clockbar()+'<div class="toolbar"><div class="toolbar-left">'+badge('M1 · Price response','pink')+badge('Chu kỳ '+hour(proposal.minute),'blue')+badge(proposal.status==='applied'?'Đã áp dụng':proposal.status==='approved'?'Đã duyệt':proposal.status==='rejected'?'Đã từ chối':'Chờ duyệt',proposal.status==='applied'?'green':'amber')+'</div>'+searchBox()+'</div>'+
    '<div class="notice">Sàn '+rows[0].floor+'% · Trần '+rows[0].cap+'% · Mức giảm không đi ngược. Sàn 30% từ 21:00 là giả định V9, cần xác minh trước pilot thực.</div>'+
    '<article class="panel"><div class="panel-head"><div><h2>Đề xuất giá · '+hour(proposal.minute)+'</h2><p>M1 so sánh doanh thu dự kiến của các lịch giá hợp lệ đến 22:00.</p></div>'+badge('8 SKU','pink')+'</div><div class="table-scroll"><table><thead><tr><th>Sản phẩm</th><th>Tồn</th><th>Bán 30 phút / 60 phút</th><th>Giá gốc</th><th>Giảm hiện tại</th><th>AI đề xuất</th><th>Giảm duyệt</th><th>Giá sau giảm</th><th></th></tr></thead><tbody>'+
    rows.filter(r=>filtered().some(p=>p.sku===r.sku)).map(r=>{const p=state.plan.find(x=>x.sku===r.sku),v=discountDraft[r.sku]??r.approved??r.discount;return '<tr><td>'+product(p)+'</td><td>'+r.stock+(r.low_stock?' '+badge('Thấp','amber'):'')+'</td><td>'+r.sales30+' / '+r.sales60+'</td><td>'+money(r.price)+'</td><td>'+r.previous+'%</td><td class="num-accent">'+r.discount+'%</td><td>'+(editable?'<select class="discount-select" data-discount="'+r.sku+'" data-price="'+r.price+'" aria-label="Giảm giá duyệt '+r.sku+'">'+ladder.filter(t=>t>=Math.max(r.previous,r.floor)&&t<=r.cap).map(t=>'<option value="'+t+'" '+(v===t?'selected':'')+'>'+t+'%</option>').join('')+'</select>':v+'%')+'</td><td data-new-price="'+r.sku+'">'+money(Math.round(r.price*(1-v/100)))+'</td><td>'+explainButton(r.sku)+'</td></tr>'}).join('')+'</tbody></table></div><div class="actionbar"><div class="summary">Giá hiệu lực sau bước <b>Áp dụng</b></div>'+
    (editable?'<button class="danger" data-reject="price">Từ chối</button><button class="primary" data-approve="price">'+icon('check')+'Duyệt đề xuất giá</button>':state.phase==='price_approved'?'<button class="primary" data-act="price_apply">Áp dụng giá đã duyệt '+icon('arrow')+'</button>':'<span class="badge green">'+esc(proposal.status==='rejected'?'Giữ giá trước đó':'Đã ghi nhận quyết định')+'</span>')+'</div></article>';
}
function ledger(){
  const tx=state.ledger.slice(-100).reverse();
  return kpis()+clockbar()+'<div class="toolbar"><div>'+badge(state.mode==='simulation'?'GIAO DỊCH MÔ PHỎNG':'GIAO DỊCH NHẬP',state.mode==='simulation'?'pink':'blue')+'</div><a href="/api/export/'+state.id+'" download>'+icon('download')+' Xuất sổ CSV</a></div>'+
    '<article class="panel"><div class="panel-head"><div><h2>Sổ giao dịch</h2><p>100 dòng gần nhất · Giá tại thời điểm bán được lưu cùng giao dịch</p></div>'+(state.mode==='live'?'<button class="small" data-go="data">Nhập giao dịch '+icon('plus')+'</button>':'')+'</div>'+
    (tx.length?'<div class="table-scroll"><table><thead><tr><th>Thời gian</th><th>SKU</th><th>Số lượng</th><th>Giảm giá</th><th>Đơn giá</th><th>Thành tiền</th><th>Nguồn</th></tr></thead><tbody>'+tx.map(t=>'<tr><td>'+hour(t.minute)+'</td><td>'+t.sku+'</td><td>'+t.qty+'</td><td>'+t.discount+'%</td><td>'+money(t.unit_price)+'</td><td class="num-accent">'+money(t.paid)+'</td><td>'+badge(t.origin==='SIMULATED'?'Mô phỏng':'Nhập tệp',t.origin==='SIMULATED'?'pink':'blue')+'</td></tr>').join('')+'</tbody></table></div>':'<div class="empty"><div class="empty-icon">'+icon('activity')+'</div><h3>Chưa có giao dịch</h3><p>Giao dịch sẽ xuất hiện khi đồng hồ mô phỏng đi qua lượt mua, hoặc khi bạn xác nhận tệp giao dịch ở chế độ nhập liệu.</p></div>')+'</article>';
}
function reportCurrent(){
  const t=state.totals;
  if(state.phase!=='closed')return '<div class="notice">Ca hiện tại chưa chốt. Các số đang hiển thị là số đã ghi nhận tới '+hour(state.minute)+', hàng tồn chưa được tính thành hàng dư cuối ngày.</div>'+kpis()+'<article class="panel attention"><h3>'+icon('clock')+'Bước tiếp theo</h3>'+pendingContent()+'</article>';
  return kpis()+'<section class="report-summary"><article class="panel report-block"><span class="eyebrow muted">BIÊN ĐÓNG GÓP TRƯỚC OVERHEAD</span><div class="large">'+money(t.contribution_before_overhead)+'</div><p>Doanh thu '+money(t.revenue)+' − giá vốn sản xuất giả định '+money(t.cost_assumed)+'. Giá vốn bằng 45% giá tham chiếu, chưa trừ chi phí vận hành.</p></article><article class="panel report-block"><span class="eyebrow muted">CHẤT LƯỢNG PHỤC VỤ</span><div class="large">'+(t.lost_simulator_only===null?'Chưa có đo lường':fmt(t.lost_simulator_only)+' lượt')+'</div><p>'+(t.lost_simulator_only===null?'Dữ liệu bán thực không tự cung cấp số nhu cầu không được đáp ứng. Cần log tình trạng hết hàng.':'Nhu cầu đủ điều kiện nhưng không còn hàng trong kịch bản mô phỏng mới, seed '+state.seed+'.')+'</p></article></section><div class="notice green" style="margin-top:20px">Đã đối soát: '+t.prepared+' chuẩn bị = '+t.sold+' bán + '+t.stock+' tồn cuối. Doanh thu bằng tổng tiền của từng dòng giao dịch.</div>';
}
function reportReference(){
  if(!reference)return '<article class="panel empty">Đang tải báo cáo đối chiếu V9…</article>';
  const b=reference.systems[0],a=reference.systems[1],delta=100*(a.revenue_vnd/b.revenue_vnd-1),waste=100*(1-a.waste_qty/b.waste_qty);
  const fields=[['Chuẩn bị','prepared_qty',false],['Đã bán','sold_qty',false],['Hàng dư cuối ngày','waste_qty',false],['Nhu cầu không đáp ứng','lost_sales_qty',false],['Doanh thu','revenue_vnd',true],['Giá vốn giả định','production_cost_assumed_vnd',true],['Biên đóng góp trước overhead','contribution_before_overhead_vnd',true]];
  return '<div class="notice">Đối chiếu output lưu trữ tháng 09/2022 · Run d8b621a5. Đây là kết quả lịch sử; không phải kết quả của ca đang chạy. ZIP thiếu observations gốc nên chưa thể tái chạy toàn bộ thí nghiệm.</div>'+
    '<section class="kpis">'+kpi('Doanh thu so baseline','+'+fmt(delta),'%','Tính lại từ daily outputs','coin')+kpi('Giảm lượng hàng dư',fmt(waste),'%','2.682 → 2.219 bánh','bread')+kpi('Nhu cầu không đáp ứng','+'+(a.lost_sales_qty-b.lost_sales_qty),'lượt','Đánh đổi chất lượng phục vụ','activity')+kpi('WAPE nhu cầu M2',Number(reference.metrics.wape_pct).toLocaleString('vi-VN',{maximumFractionDigits:4}),'%','Run hiện tại · 240 SKU-ngày','chart')+'</section>'+
    '<article class="panel"><div class="panel-head"><div><h2>Baseline và M1 + M2</h2><p>Cùng kỳ 01–30/09/2022 · Dữ liệu nhu cầu và phản ứng giá mô phỏng</p></div>'+badge('ĐỐI CHIẾU NGUỒN','blue')+'</div><div class="table-scroll"><table><thead><tr><th>Chỉ tiêu</th><th>Baseline</th><th>M1 + M2</th><th>Chênh lệch</th></tr></thead><tbody>'+fields.map(([label,key,isMoney])=>'<tr><td>'+label+'</td><td>'+(isMoney?money(b[key]):fmt(b[key]))+'</td><td class="num-accent">'+(isMoney?money(a[key]):fmt(a[key]))+'</td><td>'+(a[key]>b[key]?'+':'')+(isMoney?money(a[key]-b[key]):fmt(a[key]-b[key]))+'</td></tr>').join('')+'</tbody></table></div></article><div class="notice pink" style="margin-top:20px">Workbook kỹ thuật có WAPE 12,0772% thuộc nguồn/hash khác. Dashboard dùng WAPE '+Number(reference.metrics.wape_pct).toLocaleString('vi-VN',{maximumFractionDigits:4})+'% của run d8b621a5, không ghép hai kết quả thành một.</div>';
}
function reports(){return '<div class="toolbar"><div class="tabs"><button data-report="current" class="'+(reportTab==='current'?'active':'')+'">Ca hiện tại</button><button data-report="reference" class="'+(reportTab==='reference'?'active':'')+'">Đối chiếu V9 · 09/2022</button></div><button class="small" data-sessions>'+icon('history')+'Lịch sử ca</button></div>'+(reportTab==='current'?reportCurrent():reportReference())}
function dataView(){
  return '<section class="cols"><div class="col-stack"><article class="panel"><div class="panel-head"><div><h2>Đưa dữ liệu vào SmartFresh</h2><p>CSV, Excel hoặc ZIP · Tối đa 20 MB</p></div>'+badge('TỰ ĐỘNG KIỂM TRA','pink')+'</div><div class="panel-body"><label class="field" style="margin-top:0">Ngày mục tiêu / ngày giao dịch<input id="upload-day" type="date" min="2022-08-16" value="'+esc(uploadDay||state.day)+'"></label><label class="upload-zone" id="dropzone">'+icon('upload')+'<strong>Kéo thả tệp vào đây</strong><p>hoặc <span style="color:var(--magenta)">chọn tệp từ máy tính</span></p><small>.csv, .xlsx, .zip · Dữ liệu chỉ được nhập sau xác nhận</small><input id="file-input" type="file" accept=".csv,.xlsx,.zip"></label><div class="template-list"><a href="/api/templates/history" download>↓ Lịch sử mẫu</a><a href="/api/templates/weather" download>↓ Thời tiết mẫu</a><a href="/api/templates/transactions" download>↓ Giao dịch mẫu</a></div></div></article>'+
    (preview?previewHTML():'')+'</div><div class="col-stack"><article class="card"><h3>AI sẽ làm gì với dữ liệu?</h3><div class="steps" style="margin-top:23px">'+[['Kiểm tra cấu trúc','Ngày, SKU, số âm, dữ liệu trùng và tương lai.'],['Chạy mô hình đã huấn luyện','M2 dự báo mới; M1 tính giá từ trạng thái ca.'],['Chờ bạn xác nhận','Duyệt kế hoạch hoặc mức giá trước khi áp dụng.']].map((s,i)=>'<div class="step"><span class="step-number">'+(i+1)+'</span><div><strong>'+s[0]+'</strong><small>'+s[1]+'</small></div></div>').join('')+'</div></article><article class="notice pink" style="margin:0">Ngày mới ngoài bộ V9: dùng một Excel có hai sheet <b>history</b> và <b>weather</b>, hoặc ZIP chứa <b>history.csv</b> và <b>weather.csv</b>. Forecast cần <b>issued_at</b> có múi giờ, trước 06:00 ngày mục tiêu.</article><article class="card"><h3>Nhập giao dịch hiện tại</h3><p class="muted" style="font-size:11px;margin-top:12px">Chế độ dữ liệu nhập cần các cột sku_code, minute, quantity. Phút giao dịch phải khớp đồng hồ ca, hiện là <b>'+state.minute+' ('+hour(state.minute)+')</b>.</p><p class="muted" style="font-size:11px;margin-top:12px">Khi tồn thay đổi trong lúc chờ duyệt, đề xuất giá cũ sẽ hết hiệu lực và M1 tự tính lại.</p></article></div></section>';
}
function previewHTML(){
  let html='<article class="panel data-preview"><div class="panel-head"><div class="file-meta">'+icon('file')+'<div><strong>'+esc(preview.filename)+'</strong><small>SHA256 '+preview.sha256.slice(0,16)+'…</small></div></div>'+badge(preview.valid?'Dữ liệu hợp lệ':'Cần sửa dữ liệu',preview.valid?'green':'amber')+'</div><div class="panel-body">';
  if(preview.errors.length)html+='<div class="issue-list">'+preview.errors.slice(0,40).map(e=>'<div>Dòng '+e.row+': '+esc(e.message)+'</div>').join('')+(preview.errors.length>40?'<div>… '+(preview.errors.length-40)+' lỗi khác</div>':'')+'</div>';
  preview.warnings.forEach(w=>html+='<div class="notice">'+esc(w)+'</div>');
  if(preview.ai_column_mapping)html+='<div class="notice pink">GPT đã đề nghị ánh xạ cột: '+esc(JSON.stringify(preview.ai_column_mapping))+'. Kiểm tra bản xem trước trước khi xác nhận.</div>';
  preview.tables.forEach(t=>{
    html+='<h3 style="margin:12px 0">'+esc(t.name)+' · '+t.rows+' dòng</h3><div class="table-scroll"><table><thead><tr>'+t.columns.slice(0,6).map(c=>'<th>'+esc(c)+'</th>').join('')+'</tr></thead><tbody>'+t.sample.map(r=>'<tr>'+t.columns.slice(0,6).map(c=>'<td>'+esc(r[c])+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>';
  });
  html+='</div><div class="actionbar"><div class="summary">'+(preview.history_rows?preview.history_rows+' dòng lịch sử':preview.transaction_rows?preview.transaction_rows+' dòng giao dịch':'Dữ liệu thời tiết')+'</div><button data-clear-preview>Hủy bản nhập</button><button class="primary" data-confirm-import '+(!preview.valid?'disabled':'')+'>Xác nhận & '+(preview.transaction_rows?'ghi giao dịch':'chạy AI')+' '+icon('arrow')+'</button></div></article>';
  return html;
}
function settings(){
  const a=state.ai;
  return '<section class="settings-grid"><article class="panel"><div class="panel-head"><div><h2>Kết nối SmartFresh Copilot</h2><p>Ollama · Gemini · OpenAI — Giải thích từ công cụ</p></div>'+badge(a.verified?'Đã xác minh '+esc(a.provider)+'':a.configured?'Đã cấu hình · chưa thử':'Chưa cấu hình',a.verified?'green':'amber')+'</div>'+
    '<form id="settings-form" class="setting-body"><label class="field">Nhà cung cấp<select id="ai-provider">'+['OpenAI','Ollama','Gemini'].map(p=>'<option '+(p===a.provider?'selected':'')+'>'+p+'</option>').join('')+'</select></label><label class="field">API key (Ollama không cần)<input id="api-key" type="password" autocomplete="off" placeholder="Chỉ nhập key cloud tại đây" aria-label="API key"></label><label class="field">Model<input id="ai-model" value="'+esc(a.model)+'" autocomplete="off" required></label>'+
    '<p>Key được giữ trong bộ nhớ backend của phiên chạy. Để dùng sau khi khởi động lại, cấu hình OPENAI_API_KEY và OPENAI_MODEL trong tệp .env local.</p>'+
    '<p><a href="https://aistudio.google.com/api-keys" target="_blank" rel="noopener noreferrer">Tạo Gemini API key ↗</a> · <a href="https://ollama.com/download/windows" target="_blank" rel="noopener noreferrer">Cài Ollama ↗</a></p><p>Ollama: chạy <code>ollama pull qwen3.5:4b</code>, sau đó chọn Ollama và kết nối. Gemini: nhập key Google AI Studio. Google AI Pro không bảo đảm quota API; kiểm tra free tier/billing của project.</p>'+
    '<button type="submit" class="primary">Kết nối &amp; gọi thử AI</button><button type="button" data-disconnect class="ghost small">Ngắt kết nối</button>'+
    '<div class="notice" style="margin:20px 0 0">M1/M2 tính sản lượng và giá; Copilot đọc bằng chứng, không tự duyệt. Ollama chạy local, không phí API; model nhỏ có thể giải thích kém hơn. Gemini gửi ngữ cảnh ca lên Google; free tier có giới hạn và điều khoản sử dụng dữ liệu riêng. Không tự chuyển provider khi gặp lỗi.</div>'+aiVerificationPanel()+'</form></article>'+
    '<div class="col-stack"><article class="panel"><div class="panel-head"><h2>Mô hình đang hoạt động</h2>'+badge('HASH ĐÃ XÁC MINH','green')+'</div><div class="setting-body"><div class="setting-line"><span>Phiên bản</span><strong>'+esc(state.model_version)+'</strong></div><div class="setting-line"><span>M2</span><strong>LightGBM · Nhu cầu cơ sở</strong></div><div class="setting-line"><span>M1</span><strong>LightGBM + tối ưu lịch giá</strong></div><div class="setting-line"><span>Khóa train</span><strong>15/08/2022 · 608 SKU-ngày</strong></div><div class="setting-line"><span>Chọn chính sách</span><strong>16–31/08/2022</strong></div><div class="setting-line"><span>Policy</span><strong>q = 0,85 · Sàn prep 90% · Mẻ 4</strong></div><div class="setting-line"><span>Giải thích M2</span><strong>TreeSHAP từ model thật</strong></div><div class="setting-line"><span>Giải thích M1</span><strong>So sánh lịch giá & mục tiêu</strong></div></div></article><article class="panel"><div class="panel-head"><h2>Nguồn dữ liệu</h2></div><div class="setting-body"><p style="margin-top:0">'+esc(meta.archive)+'</p><div class="setting-line"><span>SHA256</span><strong style="font-size:9px;max-width:220px">'+meta.archive_sha256+'</strong></div><p>Đã đọc 173 tệp. Nhu cầu, phản ứng giá và giá vốn là dữ liệu hoặc giả định mô phỏng. Observations gốc của thí nghiệm tháng 9 chưa có trong ZIP.</p><p>Kịch bản tương tác dùng bộ sinh lượt mua mới có seed; không thay thế kiểm chứng trên dữ liệu cửa hàng.</p></div></article></div></section>';
}
function aiVerificationPanel(){
  let html=state.ai.configured?'<button type="button" class="small" data-verify-ai style="margin-top:18px">Kiểm tra kết nối hiện tại</button>':'';
  if(connectionResult)html+=copilotResponse(connectionResult);
  return html;
}
const actionNames={M2_PROPOSED:'AI tạo kế hoạch M2',PLAN_APPROVE:'Quản lý duyệt sản lượng',PLAN_REJECT:'Quản lý từ chối kế hoạch',PREPARED:'Xác nhận đã chuẩn bị',ADVANCE:'Cập nhật đồng hồ & suy luận M1',PRICE_APPROVE:'Quản lý duyệt mức giá',PRICE_APPLY:'Áp dụng giá đã duyệt',PRICE_REJECT:'Từ chối đề xuất giá',SALES:'Nhập giao dịch & tính lại',CLOSE:'Chốt kết quả ngày',OPENAI_EXPLANATION:'Copilot giải thích từ công cụ'};
actionNames.OPENAI_CONNECTION_TEST='Kiểm tra kết nối AI thật';
for(const provider of ['OLLAMA','GEMINI']){actionNames[provider+'_CONNECTION_TEST']='Kiểm tra kết nối '+provider;actionNames[provider+'_EXPLANATION']='Copilot '+provider+' giải thích từ công cụ';}
function auditView(){
  return '<div class="toolbar"><div>'+badge('CA '+state.id.slice(0,8),'pink')+' '+badge('Phiên bản dữ liệu '+state.revision)+'</div><button data-sessions class="small">'+icon('history')+'Lịch sử ca</button></div><article class="panel"><div class="panel-head"><div><h2>Nhật ký ca '+dateVN(state.day)+'</h2><p>Lưu trong SQLite local · Nhật ký hệ thống dùng UTC; thời gian dưới đây đổi sang giờ Việt Nam.</p></div><button class="ghost small" data-refresh-audit>'+icon('history')+'Tải lại</button></div><div class="panel-body">'+(auditRows.length?auditRows.map(r=>{let d={};try{d=JSON.parse(r.detail)}catch(_){};return '<div class="timeline-item"><span class="dot"></span><div><strong>'+esc(actionNames[r.action]||r.action)+'</strong><small>'+esc(d.payload?.reason||'Đã ghi nhận vào nhật ký')+(d.revision?' · revision '+d.revision:'')+'</small><small><code>'+esc(r.action)+'</code></small></div><time>'+new Date(r.created.replace(' ','T')+'Z').toLocaleTimeString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'})+'</time></div>'}).join(''):'<div class="empty">Đang tải nhật ký…</div>')+'</div></article>';
}
function render(){
  if(!state)return;
  const titles=views[currentView];$('page-title').textContent=titles[0];$('page-subtitle').textContent=titles[1];$('breadcrumb-title').textContent=titles[0];document.title=titles[0]+' · SmartFresh';
  $('footer-model').textContent=state.model_version;
  $('plan-count').textContent=state.phase==='plan_pending'?state.plan.length:'✓';
  document.querySelectorAll('[data-view]').forEach(b=>{b.classList.toggle('active',b.dataset.view===currentView);b.setAttribute('aria-current',b.dataset.view===currentView?'page':'false')});
  const fn={overview,m2,m1,ledger,reports,data:dataView,learning:learningView,audit:auditView,settings};
  $('view').innerHTML=fn[currentView]();
  if(['overview','m2','reports'].includes(currentView))$('view').insertAdjacentHTML('beforeend',dayChainPanel());
  if(currentView==='data')bindUpload();
  if(currentView==='learning')bindLearning();
  if(currentView==='settings'){
    $('settings-form').onsubmit=saveSettings;
    $('ai-provider').onchange=()=>{$('ai-model').value={OpenAI:'gpt-4.1-mini',Ollama:'qwen3.5:4b',Gemini:'gemini-3.8-flash'}[$('ai-provider').value];$('api-key').value='';$('api-key').disabled=$('ai-provider').value==='Ollama';geminiModels=[];bindGeminiModels()};
    $('api-key').disabled=$('ai-provider').value==='Ollama';
    bindGeminiModels();
  }
  const search=$('table-search');if(search){search.oninput=()=>{const pos=search.selectionStart;query=search.value;render();$('table-search').focus();$('table-search').setSelectionRange(pos,pos)}}
}
async function go(view){
  currentView=view;query='';$('sidebar').classList.remove('open');render();
  if(view==='audit')await loadAudit();
  if(view==='learning')await loadLearning();
  if(view==='reports'&&reportTab==='reference')await loadReference();
}
function modal(title,html){$('modal-title').textContent=title;$('modal-content').innerHTML=html;if(!$('modal').open)$('modal').showModal();}
function drawer(title,html){$('drawer-title').textContent=title;$('drawer-content').innerHTML=html;if(!$('drawer').open)$('drawer').showModal();}
function confirmAction(action){
  const text={
    prepared:['Xác nhận đã chuẩn bị','Số bánh đã duyệt sẽ trở thành tồn đầu ngày. Xác nhận khi công việc chuẩn bị thực tế đã hoàn tất.'],
    price_apply:['Áp dụng giá đã duyệt','Giá mới có hiệu lực trong ca local từ '+hour(state.minute)+'. Các giao dịch trước đó giữ nguyên giá đã ghi nhận.'],
    close:['Chốt ca vận hành','Kết quả bán, hàng dư và doanh thu sẽ được khóa. Lịch sử được lưu cho những ngày tiếp theo.']
  }[action];
  modal(text[0],'<p>'+text[1]+'</p><div class="modal-actions"><button data-close="modal">Quay lại</button><button class="primary" id="confirm-action">Xác nhận '+icon('check')+'</button></div>');
  $('confirm-action').onclick=async()=>{$('modal').close();await act(action,action==='price_apply'?{proposal_id:state.pending.id}:{});};
}
function approve(kind){
  const quantities={},discounts={};
  if(kind==='plan')document.querySelectorAll('[data-qty]').forEach(e=>quantities[e.dataset.qty]=Number(e.value));
  else document.querySelectorAll('[data-discount]').forEach(e=>discounts[e.dataset.discount]=Number(e.value));
  // Include unchanged rows even when the table is filtered.
  if(kind==='plan')state.plan.forEach(p=>{if(!(p.sku in quantities))quantities[p.sku]=quantityDraft[p.sku]??p.prepared});
  else state.pending.rows.forEach(p=>{if(!(p.sku in discounts))discounts[p.sku]=discountDraft[p.sku]??p.discount});
  const adjusted=kind==='plan'?state.plan.some(p=>quantities[p.sku]!==p.prepared):state.pending.rows.some(p=>discounts[p.sku]!==p.discount);
  modal(kind==='plan'?'Duyệt kế hoạch sản lượng':'Duyệt đề xuất giảm giá','<p>'+(kind==='plan'?'Tổng sản lượng duyệt: <b>'+fmt(Object.values(quantities).reduce((a,b)=>a+b,0))+' bánh</b>. Bước tiếp theo là xác nhận đã chuẩn bị.':'Duyệt mức giảm cho '+state.pending.rows.length+' SKU tại '+hour(state.minute)+'. Bạn sẽ xác nhận áp dụng ở bước kế tiếp.')+'</p><label class="field">Lý do '+(adjusted?'điều chỉnh (bắt buộc)':'ghi chú (tùy chọn)')+'<textarea id="approval-reason" maxlength="500" placeholder="Ghi nhận bối cảnh vận hành…"></textarea></label><div class="modal-actions"><button data-close="modal">Quay lại</button><button class="primary" id="confirm-approval">Xác nhận duyệt '+icon('check')+'</button></div>');
  $('confirm-approval').onclick=async()=>{
    const reason=$('approval-reason').value.trim();if(adjusted&&!reason){toast('Cần ghi lý do khi điều chỉnh đề xuất.',true);return;}
    $('modal').close();await act(kind==='plan'?'plan_approve':'price_approve',kind==='plan'?{quantities,reason}:{discounts,reason,proposal_id:state.pending.id});
  };
}
function reject(kind){
  modal('Từ chối đề xuất','<p>Ghi lý do để lưu lại cùng đề xuất gốc. Từ chối giá giữ mức đang áp dụng nếu mức đó còn thỏa sàn theo giờ.</p><label class="field">Lý do từ chối<textarea id="reject-reason" maxlength="500" required></textarea></label><div class="modal-actions"><button data-close="modal">Quay lại</button><button class="danger" id="confirm-reject">Xác nhận từ chối</button></div>');
  $('confirm-reject').onclick=async()=>{const reason=$('reject-reason').value.trim();if(!reason){toast('Cần lý do từ chối.',true);return;}$('modal').close();await act(kind==='plan'?'plan_reject':'price_reject',{reason,...(kind==='price'?{proposal_id:state.pending.id}:{})});};
}
function newSession(){
  modal('Bắt đầu ca vận hành','<p>Tạo ca riêng và giữ nguyên lịch sử của những ca trước.</p><form id="new-form"><label class="field">Ngày vận hành<input id="new-day" type="date" min="2022-08-16" max="2022-09-30" value="'+state.day+'" required></label><div class="form-row"><label class="field">Chế độ<select id="new-mode"><option value="simulation">Mô phỏng lượt mua mới</option><option value="live">Nhận giao dịch từ tệp</option></select></label><label class="field">Seed mô phỏng<input id="new-seed" type="number" min="0" max="2147483647" value="'+state.seed+'" required></label></div><label class="simulation-check"><input id="new-auto" type="checkbox" checked>Tự bán sau xác nhận chuẩn bị (chỉ ca mô phỏng)</label><p>Chọn ngày trong 16/08–30/09/2022 để dùng forecast V9. Để chạy ngày mới, tải lịch sử và thời tiết qua mục Dữ liệu đầu vào.</p><div class="modal-actions"><button type="button" data-close="modal">Quay lại</button><button class="primary" type="submit">Tạo kế hoạch bằng AI '+icon('spark')+'</button></div></form>');
  $('new-form').onsubmit=async e=>{e.preventDefault();if(working)return;working=true;try{const s=await api('/api/sessions',{day:$('new-day').value,seed:Number($('new-seed').value),mode:$('new-mode').value,auto_run:$('new-auto').checked});$('modal').close();currentView='m2';preview=null;storeState(s);toast('M2 đã tạo kế hoạch mới.')}catch(e){toast(e.message,true)}finally{working=false}};
}
const featureNames={lag1_sales:'Bán ngày trước',lag7_sales:'Bán 7 ngày trước',rolling7_sales:'Trung bình bán 7 ngày',rolling14_sales:'Trung bình bán 14 ngày',rolling7_std:'Biến động bán 7 ngày',rain_forecast_proxy:'Lượng mưa dự báo',temp_forecast_jma:'Nhiệt độ dự báo',weekday:'Thứ trong tuần',is_weekend:'Ngày cuối tuần',is_holiday:'Ngày lễ',festival_nonpublic:'Sự kiện trong lịch',ref_mean_train_only:'Trung bình khóa từ train',history_days:'Số ngày lịch sử',dayofyear:'Ngày trong năm',month:'Tháng',weekday_sin:'Chu kỳ thứ (sin)',weekday_cos:'Chu kỳ thứ (cos)',calendar_month_trend:'Xu hướng theo tháng'};
async function explain(sku){
  drawer('Giải thích quyết định','<div class="empty">Đang lấy bằng chứng từ mô hình…</div>');
  try{
    const e=await api('/api/evidence/'+state.id+'/'+sku),p=e.m2;
    let html=badge(sku,'pink')+' '+badge(e.model_version)+'<h3 style="font-size:19px;margin-top:15px">'+esc(p.name)+'</h3><div class="evidence-number"><div><small>Nhu cầu dự báo</small><div class="value">'+units(p.forecast)+'</div></div><div><small>Sản lượng đề xuất</small><div class="value">'+p.prepared+'</div></div><div><small>Baseline</small><div class="value">'+p.baseline+'</div></div></div><h3>Cơ chế lập sản lượng</h3><div class="formula">max(4, làm tròn mẻ(<strong>'+units(p.forecast)+' + '+units(Math.max(0,Math.ceil((p.forecast+p.buffer)/4)*4-Math.round(p.forecast)))+'</strong>), sàn <strong>'+p.floor+'</strong>) = <strong>'+p.prepared+'</strong></div><h3>Yếu tố ảnh hưởng nhu cầu · M2</h3><p class="muted" style="font-size:11px;line-height:1.8">6 đóng góp TreeSHAP có độ lớn cao nhất, tính trực tiếp từ LightGBM. Đơn vị: bánh. Dấu dương làm tăng dự báo; dấu âm làm giảm dự báo.</p>';
    const max=Math.max(...p.contributions.map(x=>Math.abs(x.units)),1);
    html+=p.contributions.map(c=>'<div class="impact '+(c.units<0?'negative':'')+'"><span>'+esc(featureNames[c.feature]||(c.feature.startsWith('sku_code_')?'Đặc trưng '+c.feature.slice(9):c.feature))+'</span><span class="impact-track"><i class="impact-fill" style="display:block;width:'+Math.abs(c.units)/max*100+'%"></i></span><strong>'+(c.units>0?'+':'')+fmt(c.units)+'</strong></div>').join('');
    html+='<p class="muted" style="font-size:10px;margin:16px 0">Giá trị nền M2: '+fmt(p.model_bias)+' bánh. Biểu đồ chỉ hiển thị các đóng góp lớn nhất, không phải toàn bộ tổng SHAP.</p>';
    if(e.m1){
      const r=e.m1;
      html+='<h3>Vì sao M1 chọn '+r.discount+'%?</h3><p class="muted" style="font-size:11px">Tồn '+r.stock+' bánh · Bán 60 phút: '+r.sales60+' · Sàn '+r.floor+'% / trần '+r.cap+'%. Mục tiêu = doanh thu dự kiến còn lại − 2,5% giá gốc × tồn dự kiến, kèm quy tắc phá hòa.</p><div class="table-scroll" style="margin-top:16px"><table><thead><tr><th>Giảm ngay</th><th>Doanh thu dự kiến</th><th>Tồn dự kiến</th></tr></thead><tbody>'+r.candidates.map(c=>'<tr><td>'+c.discount+'%'+(c.discount===r.discount?' ✓':'')+'</td><td>'+money(c.expected_revenue)+'</td><td>'+fmt(c.expected_leftover)+'</td></tr>').join('')+'</tbody></table></div><div class="notice pink" style="margin-top:17px">Mỗi dòng là lịch giá tốt nhất nếu bắt đầu ở mức đó. Đây là giá trị dự kiến của optimizer, không phải doanh thu đã ghi nhận hoặc SHAP quyết định giá.</div>';
    }
    html+='<button class="primary" style="width:100%;margin-top:20px" data-ask-sku="'+sku+'">'+icon('spark')+'Nhờ Copilot giải thích</button><p class="muted" style="font-size:10px;margin:13px 0">Ca '+e.session_id.slice(0,8)+' · revision '+e.revision+' · '+p.features.history_days+' ngày lịch sử liên tục</p>';
    $('drawer-content').innerHTML=html;
  }catch(e){$('drawer-content').innerHTML='<div class="notice">'+esc(e.message)+'</div>'}
}
function openChat(){
  if(chatSession!==state.id){chatMessages=[];chatSession=state.id;}
  let html='<div class="notice pink">'+icon('spark')+' Phân tích dữ liệu của ca hiện tại. Đề xuất chỉ được áp dụng sau khi bạn xác nhận.</div>';
  if(!state.ai.configured)html+='<div class="empty"><div class="empty-icon">'+icon('chat')+'</div><h3>Kết nối Copilot</h3><p>Chọn Ollama hoặc nhập Gemini/OpenAI API key để hỏi đáp và giải thích. Các mô hình M1/M2 vẫn đang chạy local.</p><button class="primary" data-open-settings>Mở cài đặt AI '+icon('arrow')+'</button></div>';
  else html+='<div class="chat-feed" id="chat-feed">'+(chatMessages.length?chatMessages.map(copilotChatMessage).join(''):'<div class="suggested-questions"><button data-question="Giải thích kế hoạch sản lượng của BK-001, kèm số liệu.">Vì sao BK-001 có sản lượng này?</button><button data-question="Tóm tắt ca hiện tại và bước nào cần tôi xác nhận.">Tôi cần xử lý việc gì tiếp theo?</button><button data-question="Giải thích M1 và M2 phối hợp trong ca này.">M1 và M2 phối hợp thế nào?</button></div>')+'</div><form class="chat-form" id="chat-form"><input id="chat-input" maxlength="4000" autocomplete="off" placeholder="Hỏi về dữ liệu và quyết định…" aria-label="Câu hỏi cho Copilot"><button class="primary" type="submit" aria-label="Gửi câu hỏi">'+icon('arrow')+'</button></form>';
  drawer('SmartFresh Copilot',html);
  if($('chat-form'))$('chat-form').onsubmit=e=>{e.preventDefault();askChat($('chat-input').value);};
}
let chatting=false;
async function askChat(message){
  if(!message.trim()||chatting)return;
  if(!state.ai.configured){openChat();return}
  chatting=true;chatMessages.push({user:true,text:message});openChat();
  const feed=$('chat-feed'),pending=document.createElement('div');pending.className='copilot-thinking';pending.innerHTML=icon('spark')+'<span>Đang phân tích dữ liệu của ca…</span>';feed.append(pending);feed.scrollIntoView({block:'end',behavior:'smooth'});$('chat-input').disabled=true;
  try{const result=await api('/api/chat',{session_id:state.id,message:copilotPrompt(message)});chatMessages.push({text:result.answer,result})}catch(e){chatMessages.push({text:e.message,error:true})}finally{chatting=false;if($('drawer').open&&$('drawer-title').textContent==='SmartFresh Copilot')openChat()}
}
function bindUpload(){
  $('file-input').onchange=e=>{if(e.target.files[0])uploadFile(e.target.files[0])};
  $('upload-day').onchange=e=>uploadDay=e.target.value;
  const z=$('dropzone');z.ondragover=e=>{e.preventDefault();z.classList.add('dragging')};z.ondragleave=()=>z.classList.remove('dragging');z.ondrop=e=>{e.preventDefault();z.classList.remove('dragging');if(e.dataTransfer.files[0])uploadFile(e.dataTransfer.files[0])};
}
async function uploadFile(file){
  if(working)return;if(file.size>20*1024*1024){toast('Tệp tối đa 20 MB.',true);return}
  working=true;uploadDay=$('upload-day').value;
  const fd=new FormData();fd.append('file',file);fd.append('day',uploadDay);
  try{preview=await api('/api/imports',fd);render();toast(preview.valid?'Đã kiểm tra dữ liệu. Xem bản nhập trước khi xác nhận.':'Có lỗi dữ liệu cần sửa.',!preview.valid)}catch(e){toast(e.message,true)}finally{working=false}
}
async function confirmImport(){
  if(working)return;working=true;
  try{const s=await api('/api/imports/'+preview.import_id+'/confirm',{session_id:state.id,revision:state.revision,seed:state.seed});const isTx=preview.transaction_rows>0;preview=null;currentView=isTx?'ledger':'m2';storeState(s);toast(isTx?'Đã nhập giao dịch và cập nhật trạng thái.':'Đã nhập dữ liệu. M2 đã tạo kế hoạch mới.')}catch(e){toast(e.message,true)}finally{working=false}
}
function bindGeminiModels(){
  if(!$('gemini-catalog'))$('ai-model').parentElement.insertAdjacentHTML('afterend','<div id="gemini-catalog"><button type="button" id="check-gemini-models" class="small">Kiểm tra key &amp; tải model</button><p class="muted">Kiểm tra quyền liệt kê model trước khi gọi AI. Danh sách không bảo đảm model miễn phí hoặc có quota sinh nội dung.</p><div id="gemini-model-options"></div><p id="gemini-diagnostic" role="status" style="white-space:pre-wrap"></p></div>');
  $('gemini-catalog').hidden=$('ai-provider').value!=='Gemini';
  $('gemini-model-options').innerHTML=geminiModels.length?'<label class="field">Model Google trả về<select id="gemini-model-picker"><option value="">Chọn model để điền vào ô phía trên</option>'+geminiModels.map(m=>'<option value="'+esc(m.id)+'">'+esc(m.name)+' · '+esc(m.id)+'</option>').join('')+'</select></label>':'';
  if($('gemini-model-picker'))$('gemini-model-picker').onchange=()=>{if($('gemini-model-picker').value)$('ai-model').value=$('gemini-model-picker').value};
  $('check-gemini-models').onclick=async()=>{
    if(working)return;const key=$('api-key').value.trim();if(!key){toast('Nhập Gemini API key vào ô trên trước.',true);return}
    const button=$('check-gemini-models');working=true;button.disabled=true;button.textContent='Đang kiểm tra với Google…';
    try{const result=await api('/api/ai/models',{provider:'Gemini',api_key:key,model:$('ai-model').value.trim()});if($('api-key')?.value.trim()!==key)return;geminiModels=result.models;bindGeminiModels();$('gemini-diagnostic').textContent=result.note+(result.models.length?'':' Không có model generateContent phù hợp trong danh sách.');toast('Google chấp nhận key để liệt kê model. Chọn model rồi gọi thử AI.')}catch(e){toast(e.message,true);if($('gemini-diagnostic'))$('gemini-diagnostic').textContent=e.message}finally{working=false;if($('check-gemini-models')){$('check-gemini-models').disabled=false;$('check-gemini-models').textContent='Kiểm tra key & tải model'}}
  };
}
async function saveSettings(e){
  e.preventDefault();
  if(working)return;
  const button=$('settings-form').querySelector('[type="submit"]');
  const key=$('api-key').value.trim(),model=$('ai-model').value.trim(),provider=$('ai-provider').value;
  if(!key&&provider!=='Ollama'){toast('Nhập API key của bạn vào ô trên. Nếu đã cấu hình backend, chọn Kiểm tra kết nối hiện tại.',true);return}
  working=true;button.disabled=true;button.textContent='Đang gọi AI và kiểm tra công cụ…';
  try{
    const result=await api('/api/ai/connect',{api_key:key,model,provider,session_id:state.id});
    state.ai=result.ai;connectionResult=result.verification;$('api-key').value='';render();
    toast('Đã nhận phản hồi AI thật và kiểm tra công cụ thành công.');
  }catch(e){toast(e.message,true);if($('gemini-diagnostic')&&provider==='Gemini')$('gemini-diagnostic').textContent=e.message;button.disabled=false;button.textContent='Kết nối & gọi thử AI'}
  finally{working=false}
}
async function verifyCurrentAI(){
  if(working)return;working=true;
  const button=document.querySelector('[data-verify-ai]');if(button){button.disabled=true;button.textContent='Đang gọi AI…';}
  try{
    const result=await api('/api/ai/verify',{session_id:state.id,message:'Kiểm tra kết nối'});
    state.ai=result.ai;connectionResult=result.verification;render();
    toast('Copilot đã trả lời qua công cụ của ca hiện tại.');
  }catch(e){toast(e.message,true);if(button){button.disabled=false;button.textContent='Kiểm tra kết nối hiện tại';}}
  finally{working=false}
}
async function loadReference(){try{reference=await api('/api/reference');if(currentView==='reports')render()}catch(e){toast(e.message,true)}}
async function loadAudit(){try{auditRows=await api('/api/audit/'+state.id);if(currentView==='audit')render()}catch(e){toast(e.message,true)}}
async function showSessions(){
  try{
    const rows=await api('/api/sessions');modal('Lịch sử ca vận hành',rows.map(s=>'<div class="session-row"><div><strong>'+dateVN(s.day)+' · '+esc(phases[s.phase])+'</strong><small>'+s.id.slice(0,8)+' · '+(s.mode==='simulation'?'Mô phỏng':'Dữ liệu nhập')+'</small></div><button data-load-session="'+s.id+'">Mở ca '+icon('arrow')+'</button></div>').join(''));
  }catch(e){toast(e.message,true)}
}
document.addEventListener('click',async e=>{
  const b=e.target.closest('button,a');if(!b||b.disabled)return;
  if(b.dataset.view)go(b.dataset.view);
  if(b.dataset.go)go(b.dataset.go);
  if(b.dataset.close)$(b.dataset.close).close();
  if(b.hasAttribute('data-new'))newSession();
  if(b.dataset.act)confirmAction(b.dataset.act);
  if(b.dataset.approve)approve(b.dataset.approve);
  if(b.dataset.reject)reject(b.dataset.reject);
  if(b.dataset.advance)await manualAdvance(Number(b.dataset.advance));
  if(b.hasAttribute('data-play')){
    await changeClock(!state.realtime?.enabled);
  }
  if(b.dataset.explain)explain(b.dataset.explain);
  if(b.hasAttribute('data-chat'))openChat();
  if(b.dataset.askSku){openChat();askChat('Giải thích quyết định cho '+b.dataset.askSku+' dựa trên bằng chứng M2 và M1 của ca hiện tại.')}
  if(b.dataset.question)askChat(b.dataset.question);
  if(b.hasAttribute('data-open-settings')){$('drawer').close();go('settings')}
  if(b.hasAttribute('data-confirm-import'))confirmImport();
  if(b.hasAttribute('data-clear-preview')){preview=null;render()}
  if(b.dataset.report){reportTab=b.dataset.report;render();if(reportTab==='reference'&&!reference)loadReference()}
  if(b.hasAttribute('data-refresh-audit'))loadAudit();
  if(b.hasAttribute('data-sessions'))showSessions();
  if(b.dataset.loadSession){try{stop();storeState(await api('/api/state?session_id='+b.dataset.loadSession));$('modal').close();if(currentView==='audit')loadAudit()}catch(e){toast(e.message,true)}}
  if(b.hasAttribute('data-disconnect')){try{state.ai=await api('/api/ai/settings',{api_key:'',model:state.ai.model});connectionResult=null;render();toast('Đã ngắt Copilot trong phiên hiện tại.')}catch(e){toast(e.message,true)}}
  if(b.hasAttribute('data-verify-ai'))verifyCurrentAI();
});
document.addEventListener('change',e=>{const el=e.target;if(el.dataset.qty)quantityDraft[el.dataset.qty]=Number(el.value);if(el.dataset.discount){discountDraft[el.dataset.discount]=Number(el.value);const td=document.querySelector('[data-new-price="'+el.dataset.discount+'"]');if(td)td.textContent=money(Math.round(Number(el.dataset.price)*(1-Number(el.value)/100)))}})
$('new-session').onclick=newSession;$('upload-shortcut').onclick=()=>go('data');$('menu').onclick=()=>$('sidebar').classList.toggle('open');
document.querySelectorAll('dialog').forEach(d=>d.addEventListener('click',e=>{if(e.target===d){const r=d.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)d.close()}}));
async function init(){
  icons();
  const requestedView=new URL(location.href).searchParams.get('view');
  if(views[requestedView])currentView=requestedView;
  try{
    const sid=localStorage.getItem('smartfresh-session');
    const result=await Promise.all([api('/api/state'+(sid?'?session_id='+sid:'')),api('/api/metadata'),api('/api/history')]);
    state=result[0];meta=result[1];history=result[2];storeState(state);
  }catch(e){
    if(localStorage.getItem('smartfresh-session')){localStorage.removeItem('smartfresh-session');try{const r=await Promise.all([api('/api/state'),api('/api/metadata'),api('/api/history')]);state=r[0];meta=r[1];history=r[2];storeState(state);return}catch(_){}}
    $('view').innerHTML='<div class="notice">'+esc(e.message)+'</div><button onclick="location.reload()">Thử tải lại</button>';toast(e.message,true);
  }
}
init();
