'use strict';
let businessDays=63,businessMetric='units',businessCompare='day',businessData=null,businessBusy=false,businessError='',businessLoadedKey='';
let testMonthData=null;
const businessMetrics=[['revenue','Doanh thu',true],['sold','Đã bán',false],['prepared','Đã chuẩn bị',false],['stock','Tồn cuối ngày',false]];
function businessKey(){return state.id+':'+state.revision+':'+businessDays}
function reportValue(value,cash=false){return value==null?'Chưa có dữ liệu':cash?money(value):units(value)+' chiếc'}
function reportChange(c){
 if(!c||c.reason==='missing_closed_day')return '<span class="trend-muted">Chưa đủ hai ngày đã chốt</span>';
 const delta=(c.value>0?'+':'')+fmt(c.value);
 if(c.reason==='zero_baseline')return '<span class="trend-muted">'+delta+' · Mốc trước bằng 0, không tính %</span>';
 return '<span class="'+(c.value>0?'trend-up':c.value<0?'trend-down':'trend-muted')+'">'+(c.percent>0?'+':'')+fmt(c.percent)+'% <small>('+delta+')</small></span>';
}
function businessChart(rows,series,cash=false){
 const width=860,height=245,left=66,right=20,top=24,bottom=42,plotW=width-left-right,plotH=height-top-bottom;
 const maximum=Math.max(1,...rows.flatMap(r=>series.map(s=>r.metrics?.[s.key]??0)))*1.12;
 const x=i=>left+(rows.length>1?i*plotW/(rows.length-1):plotW/2),y=v=>top+plotH-v/maximum*plotH;
 let body='';
 for(let i=0;i<=4;i++){const value=maximum*i/4,yy=y(value);body+='<line x1="'+left+'" y1="'+yy+'" x2="'+(width-right)+'" y2="'+yy+'" stroke="#eee9ef"/><text x="'+(left-9)+'" y="'+(yy+4)+'" text-anchor="end">'+esc(cash?(maximum<1e6?(value/1000).toLocaleString('vi-VN',{maximumFractionDigits:1})+' ngh\u00ecn':(value/1e6).toLocaleString('vi-VN',{maximumFractionDigits:1})+' tr'):units(value))+'</text>'}
 series.forEach(s=>{
  let segment=[];const segments=[];
  rows.forEach((r,i)=>{const v=r.metrics?.[s.key];if(v==null){if(segment.length)segments.push(segment);segment=[]}else segment.push(x(i)+','+y(v))});if(segment.length)segments.push(segment);
  segments.forEach(points=>body+='<polyline points="'+points.join(' ')+'" fill="none" stroke="'+s.color+'" stroke-width="2.5"/>');
  rows.forEach((r,i)=>{const v=r.metrics?.[s.key];if(v==null)return;body+='<circle tabindex="0" cx="'+x(i)+'" cy="'+y(v)+'" r="4" stroke="'+s.color+'" fill="'+(r.status==='provisional'?'white':s.color)+'"><title>'+esc((r.label||dateVN(r.day))+' · '+s.label+': '+reportValue(v,cash)+(r.status==='provisional'?' · Tạm tính':''))+'</title></circle>'});
 });
 rows.forEach((r,i)=>{if(i===0||i===rows.length-1||i%Math.max(1,Math.ceil(rows.length/6))===0)body+='<text x="'+x(i)+'" y="'+(height-14)+'" text-anchor="middle">'+esc(r.label||r.day.slice(8,10)+'/'+r.day.slice(5,7))+'</text>'});
 return '<div class="business-legend">'+series.map(s=>'<span><i style="background:'+s.color+'"></i>'+s.label+'</span>').join('')+'</div><svg class="business-chart" viewBox="0 0 '+width+' '+height+'" role="img" aria-label="'+esc(series.map(s=>s.label).join(', '))+'"><title>Diễn biến '+esc(series.map(s=>s.label).join(', '))+'; ngày thiếu dữ liệu để trống</title>'+body+'</svg>';
}
function intradayReport(){
 const valid=!state.reconciliation?.errors?.length;
 if(!state.products||!Object.keys(state.products).length||!valid)return '<p class="muted">Chưa có tồn đã xác nhận và sổ bán hợp lệ để vẽ diễn biến trong ngày.</p>';
 const rows=[],times=[];
 for(let t=480;t<=state.minute;t+=60)times.push(t);
 if(state.minute>=480&&times.at(-1)!==state.minute)times.push(state.minute);
 const tx=[...state.ledger].sort((a,b)=>a.minute-b.minute);let index=0,sold=0;
 times.forEach(t=>{while(index<tx.length&&tx[index].minute<=t){sold+=tx[index].qty;index++}rows.push({label:hour(t),status:'closed',metrics:{prepared:Object.values(state.products).reduce((n,p)=>n+p.prepared-(p.refills||[]).filter(b=>b.received&&Number(b.ready_time.slice(0,2))*60+Number(b.ready_time.slice(3))>t).reduce((a,b)=>a+b.qty,0),0),sold,stock:Object.values(state.products).reduce((n,p)=>n+p.prepared-(p.refills||[]).filter(b=>b.received&&Number(b.ready_time.slice(0,2))*60+Number(b.ready_time.slice(3))>t).reduce((a,b)=>a+b.qty,0),0)-sold}})});
 return rows.length?businessChart(rows,[{key:'prepared',label:'Đã chuẩn bị',color:'#8c79bd'},{key:'sold',label:'Bán lũy kế',color:'#c02b83'},{key:'stock',label:'Còn trên quầy',color:'#31857c'}]):'<p class="muted">Chưa đến giờ mở cửa 08:00.</p>';
}
function businessHistoryPanel(){
 const r=businessData?.session_id===state.id&&businessData.days===businessDays?businessData:null;
 const comparison=r?.comparisons[businessCompare];
 const header='<section class="panel business-history"><div class="panel-head"><div><h2>Hiệu quả bán hàng qua các ngày</h2><p>'+dateVN(state.day)+' · '+(state.mode==='simulation'?'Mô phỏng, seed '+state.seed:'Giao dịch nhập')+' · '+(r?r.closed_days+' ngày đã chốt trong khoảng xem':'Đang tải lịch sử')+'</p></div><label>Khoảng xem <select data-business-days aria-label="Khoảng lịch sử">'+[7,30,63,90].map(n=>'<option value="'+n+'" '+(businessDays===n?'selected':'')+'>'+n+' ngày</option>').join('')+'</select></label></div>';
 if(!r)return header+'<div class="panel-body"><p role="status">'+esc(businessError||'Đang tải các ca đã lưu…')+'</p>'+(businessError?'<button data-business-retry>Thử tải lại</button>':'')+'</div></section>';
 const labels={day:'ngày trước',week:'cùng thứ tuần trước',month:'cùng ngày tháng trước'};
 const comparisonControls='<div class="business-comparison"><label>So sánh ngày '+dateVN(state.day)+' với <select data-business-compare aria-label="Mốc so sánh">'+Object.entries(labels).map(([key,label])=>'<option value="'+key+'" '+(businessCompare===key?'selected':'')+'>'+label+'</option>').join('')+'</select></label><span>'+dateVN(comparison.day)+'</span></div>';
 const cards='<div class="business-kpis">'+businessMetrics.map(([key,label,cash])=>'<article><small>'+(key==='stock'&&state.phase!=='closed'?'Tồn hiện tại':label)+'</small><strong>'+reportValue(r.selected_metrics?.[key],cash)+'</strong>'+reportChange(comparison.changes[key])+'</article>').join('')+'</div>';
 const count=r.rows.filter(d=>d.metrics).length;
 const series=businessMetric==='revenue'?[{key:'revenue',label:'Doanh thu',color:'#c02b83'}]:[{key:'prepared',label:'Đã chuẩn bị',color:'#8c79bd'},{key:'sold',label:'Đã bán',color:'#c02b83'},{key:'stock',label:'Tồn cuối ngày / hiện tại',color:'#31857c'}];
 const controls='<div class="business-chart-heading"><h3>Lịch sử theo ngày</h3><label>Chỉ số <select data-business-metric aria-label="Chỉ số biểu đồ"><option value="units" '+(businessMetric==='units'?'selected':'')+'>Chuẩn bị · bán · tồn</option><option value="revenue" '+(businessMetric==='revenue'?'selected':'')+'>Doanh thu</option></select></label></div>';
 const table='<details class="business-details" open><summary>Xem số liệu từng ngày</summary><div class="table-scroll"><table><thead><tr><th>Ngày</th><th>Trạng thái / policy</th><th>Doanh thu</th><th>Chuẩn bị</th><th>Đã bán</th><th>Tồn</th><th>Tỷ lệ bán hết</th></tr></thead><tbody>'+r.rows.filter(d=>d.metrics).map(d=>'<tr><td>'+dateVN(d.day)+'</td><td>'+(d.status==='closed'?'Đã chốt':'Tạm tính')+'<small class="block">'+esc(d.model_version)+'</small></td><td>'+money(d.metrics.revenue)+'</td>'+['prepared','sold','stock'].map(k=>'<td>'+units(d.metrics[k])+'</td>').join('')+'<td>'+(d.metrics.sell_through_pct==null?'—':fmt(d.metrics.sell_through_pct)+'%')+'</td></tr>').join('')+'</tbody></table></div></details>';
 return header+'<div class="panel-body">'+(r.current_status==='provisional'?'<p class="notice">Ca đang chọn chưa chốt. Biểu đồ ghi số tạm tính; phần trăm so sánh chờ chốt ca để tránh so một phần ngày với cả ngày.</p>':r.current_status==='invalid'?'<p class="notice">Sổ bán chưa đối soát khớp. Không công bố chỉ số hoặc phần trăm của ca này.</p>':'')+comparisonControls+cards+controls+(count?businessChart(r.rows,series,businessMetric==='revenue'):'<p>Chưa có ca đủ dữ liệu trong khoảng này.</p>')+(count<2?'<p class="muted">Chưa đủ hai ngày để thấy xu hướng. Lịch sử sẽ tích lũy khi bạn chạy và chốt các ngày tiếp theo.</p>':'')+'<p class="business-note">Chấm rỗng: ngày đang chạy. Khoảng trống: chưa có ngày tương ứng. Mức tăng/giảm chỉ thể hiện thay đổi, không tự kết luận tốt hay xấu.</p>'+table+'<details class="business-details"><summary>Nguồn dữ liệu & cách so sánh</summary><p>'+esc(r.note)+'</p>'+(r.excluded_invalid?'<p>'+r.excluded_invalid+' ngày bị loại do lệch sổ.</p>':'')+'</details></div></section><section class="panel business-intraday"><div class="panel-head"><div><h2>Nhịp bán và tồn trong ngày '+dateVN(state.day)+'</h2><p>08:00 đến '+hour(state.minute)+' · Đọc từ sổ giao dịch của ca đang chọn.</p></div></div><div class="panel-body">'+intradayReport()+'</div></section>';
}
function testMonthPanel(){
 return '';
}
async function refreshBusinessHistory(force=false){
 if(currentView!=='reports'||businessBusy)return;
 const key=businessKey();if(!force&&businessLoadedKey===key)return;
 businessBusy=true;businessError='';
 try{const [main,testMonth]=await Promise.allSettled([api('/api/business-report/'+state.id+'?days='+businessDays),api('/api/test-month-report')]);if(key!==businessKey())return;if(testMonth.status==='fulfilled')testMonthData=testMonth.value;if(main.status==='rejected')throw main.reason;businessData=main.value;businessLoadedKey=key}
 catch(e){businessError='Không tải được lịch sử: '+e.message;businessLoadedKey=key}
 finally{businessBusy=false;if(currentView==='reports')render()}
}
document.addEventListener('change',e=>{
 if(e.target.hasAttribute('data-business-days')){businessDays=Number(e.target.value);businessError='';render()}
 if(e.target.hasAttribute('data-business-compare')){businessCompare=e.target.value;render()}
 if(e.target.hasAttribute('data-business-metric')){businessMetric=e.target.value;render()}
});
document.addEventListener('click',e=>{if(e.target.closest('[data-business-retry]'))refreshBusinessHistory(true)});
setInterval(()=>{if(currentView==='reports'&&!document.hidden&&state?.phase==='running')refreshBusinessHistory(true)},30000);
