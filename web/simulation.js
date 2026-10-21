'use strict';
let historySession=null;
function dayChainPanel(){
  if(state.phase==='closed')return '<article class="panel" style="margin-top:20px"><div class="panel-head"><div><h2>Từ chốt ngày đến kế hoạch hôm sau</h2><p>Ghi nhận bán, tồn hủy và trạng thái hết hàng hôm nay; dùng lịch sử trước ngày mục tiêu và forecast mới.</p></div></div><div class="panel-body"><button class="primary" data-next-day>Tạo kế hoạch ngày kế tiếp</button><p class="muted" style="font-size:11px;margin-top:12px">M2 không dùng dữ liệu bán tương lai. Ngày ngoài lịch V9 cần nạp forecast thời tiết mới. Dữ liệu mô phỏng không được trộn vào tập học thật.</p></div></article>';
  const c=state.day_context;if(!c)return '';
  const rows=c.previous_day_outcomes||[];
  return '<article class="panel" style="margin-top:20px"><div class="panel-head"><div><h2>Dữ liệu nào tạo ra kế hoạch '+dateVN(state.day)+'?</h2><p>Ngày trước: '+dateVN(c.lag1_day)+' · Cùng thứ tuần trước: '+dateVN(c.same_weekday_day)+' · '+c.past_closed_days+' ca quá khứ đã chốt.</p></div></div><div class="panel-body"><p>M2 đọc bán ngày trước, bán 7 ngày trước, trung bình 7/14 ngày, thứ, lịch và forecast thời tiết đúng ngày. M1 lấy chính dự báo đó cùng tồn hiện tại và sổ giao dịch trong ngày.</p>'+(rows.length?'<div class="table-scroll"><table><thead><tr><th>SKU</th><th>Bán hôm trước</th><th>Tồn hủy</th><th>Hết hàng</th></tr></thead><tbody>'+rows.map(r=>'<tr><td>'+esc(r.sku_code)+'</td><td>'+units(r.sold_qty)+'</td><td>'+units(r.waste_qty)+'</td><td>'+(r.stockout?'Có':'Không')+'</td></tr>').join('')+'</tbody></table></div>':'<p class="muted" style="font-size:11px">Chưa có sổ tồn/hủy ngày trước trong chuỗi ca này; chỉ có lịch sử bán làm đầu vào.</p>')+'<p class="muted" style="font-size:11px;margin-top:12px">'+(c.inventory_features_active?'Model này đã được fit với đặc trưng tồn/hủy, hết hàng và lịch sử cùng thứ.':'Model gốc V9 chưa có đặc trưng tồn/hủy. Luồng học mới đã bổ sung các đặc trưng này; cần đủ dữ liệu, đạt kiểm tra và được duyệt trước khi sử dụng.')+'</p></div></article>';
}
function simulationStatus(){
  if(state.mode==='live')return '<div class="notice '+(state.sales_feed?.missing?'pink':'')+'">'+icon('database')+' Nguồn bán: giao dịch nhập từ tệp. '+(state.sales_feed?.missing?'Chưa nhận dữ liệu bán; không tự coi là bán bằng 0. ':'')+'<button class="small" data-fork-simulation>Tạo bản mô phỏng riêng</button></div>';
  const c=state.realtime||{},waiting=c.enabled&&c.pause_confirm&&['price_pending','price_approved'].includes(state.phase);
  return '<div class="simulation-strip"><div><strong>'+icon('activity')+' Nguồn bán mô phỏng · '+(waiting?'Đợi xác nhận giá':c.enabled?'Đang chạy trên backend':'Đã tạm dừng')+'</strong><small>Mỗi lượt mua trừ đúng tồn và ghi sổ. M1/M2 không quyết định trước lượt bán. <button class="ghost small" data-simulator-report>Nguồn &amp; kiểm tra</button></small></div><label>Tốc độ<select data-sim-speed>'+[[1/60,'Thời gian thực · 1×'],[1,'1 giây = 1 phút'],[5,'1 giây = 5 phút'],[30,'1 giây = 30 phút']].map(([v,label])=>'<option value="'+v+'" '+(Math.abs((c.speed??5)-v)<.00001?'selected':'')+'>'+label+'</option>').join('')+'</select></label><label class="simulation-check"><input type="checkbox" data-pause-confirm '+(c.pause_confirm!==false?'checked':'')+'>Dừng ở bước duyệt</label></div><p class="muted" style="font-size:11px;margin:-7px 0 18px">Cửa hàng mở 08:00, đóng 22:00. Đây là đồng hồ mô phỏng; đóng tab vẫn tiếp tục khi backend đang chạy. '+(c.error?esc(c.error):'')+'</p>';
}
async function changeClock(enabled,speed=state.realtime?.speed??5,pause_confirm=state.realtime?.pause_confirm!==false){
  if(working)return;working=true;
  try{storeState(await api('/api/realtime/'+state.id,{enabled,speed,pause_confirm}))}catch(e){toast(e.message,true)}finally{working=false;render()}
}
async function manualAdvance(target){
  stop();
  if(state.realtime?.enabled)await changeClock(false);
  if(state.phase!=='running'){toast('Hãy hoàn tất bước xác nhận đang chờ trước khi chuyển mốc.',true);return}
  await act('advance',{target});
}
async function nextDay(){
  if(working)return;working=true;
  try{const next=await api('/api/day-chain/'+state.id,{});currentView='m2';storeState(next);toast('Đã tạo kế hoạch ngày '+dateVN(next.day)+' từ kết quả chốt ngày trước và forecast đúng ngày.')}catch(e){toast(e.message,true)}finally{working=false}
}
document.addEventListener('click',async e=>{
  const b=e.target.closest('button');if(!b||b.disabled)return;
  if(b.hasAttribute('data-fork-simulation')){
    if(working)return;working=true;
    try{const s=await api('/api/scenarios/'+state.id+'/fork',{});currentView='m2';storeState(s);toast('Đã tạo bản mô phỏng riêng. Duyệt và xác nhận chuẩn bị để bắt đầu bán tự động.')}catch(err){toast(err.message,true)}finally{working=false}
  }
  if(b.hasAttribute('data-next-day'))await nextDay();
  if(b.hasAttribute('data-confirm-zero')){
    modal('Xác nhận thực tế chưa có bán','<p>Chỉ xác nhận nếu bạn đã kiểm tra và thực tế chưa bán sản phẩm nào. Thiếu file giao dịch không có nghĩa là chưa bán.</p><label class="field">Lý do<textarea id="zero-reason" required></textarea></label><button class="primary" id="zero-confirm">Xác nhận chưa bán</button>');
    $('zero-confirm').onclick=async()=>{const reason=$('zero-reason').value.trim();if(!reason){toast('Cần lý do xác nhận.',true);return}$('modal').close();await act('confirm_zero_sales',{confirmed:true,reason})};
  }
  if(b.hasAttribute('data-simulator-report')){
    try{const r=await api('/api/simulator');modal('Bộ tạo lượt mua đã học gì?','<p><strong>'+esc(r.type)+'</strong></p><p>'+r.training_rows+' dòng fit đến '+esc(r.train_until)+'. Hiệu chỉnh đến '+esc(r.calibrated_until)+'. Kiểm tra '+r.test_rows+' SKU-ngày từ '+esc(r.test_from)+' đến '+esc(r.evaluated_until)+'.</p><div class="setting-line"><span>MAE nhu cầu/ngày</span><strong>'+fmt(r.test_mae)+' chiếc</strong></div><div class="setting-line"><span>Baseline trung bình SKU</span><strong>'+fmt(r.sku_mean_baseline_mae)+' chiếc</strong></div><p>Ngẫu nhiên chỉ nằm ở việc lấy mẫu từng lượt mua từ phân phối đã hiệu chỉnh, có seed để tái lập. Số lượng bán và tồn luôn nguyên.</p><div class="notice">Nguồn V9 là dữ liệu tổng hợp. Nhịp bán 30/60 phút được hiệu chỉnh từ nhãn train; hình dạng bán đầu ngày và phản ứng giảm giá còn có giả định. Chưa chứng minh giống giao dịch AEON thực tế.</div><details style="margin-top:15px"><summary>Kiểm tra artifact</summary><p>SHA-256: '+esc(r.sha256)+'</p></details>')}catch(err){toast(err.message,true)}
  }
});
document.addEventListener('change',e=>{
  if(e.target.hasAttribute('data-sim-speed'))changeClock(!!state.realtime?.enabled,Number(e.target.value));
  if(e.target.hasAttribute('data-pause-confirm'))changeClock(!!state.realtime?.enabled,state.realtime?.speed??5,e.target.checked);
});
setInterval(async()=>{
  if(typeof state==='undefined'||!state||!state.realtime?.enabled||working||$('modal').open||chatting)return;
  const sid=state.id;
  try{const fresh=await api('/api/state?session_id='+sid);if(state.id===sid&&!working){state=fresh;render()}}catch(e){toast(e.message,true)}
},1000);
function refreshDayHistory(){
  if(!state||historySession===state.id)return;
  historySession=state.id;const sid=state.id;
  api('/api/history?session_id='+sid).then(rows=>{if(state.id===sid){history=rows;if(currentView==='overview')render()}}).catch(e=>toast(e.message,true));
}
