/* GD5 quality is returned by backend gates; UI never grants a PASS itself. */
let importLog=[];
function qualityPanel(){
  const q=state.data_quality||{}, w=q.weather||{}, lineage=q.lineage||{}, weatherMeta=state.weather?.weather_provenance||{};
  const tag=v=>badge(v||'Chưa có',v==='PASS'?'green':'amber');
  const line=(k,v)=>'<div class="setting-line"><span>'+esc(k)+'</span><strong style="overflow-wrap:anywhere;max-width:65%">'+esc(v??'Chưa xác minh')+'</strong></div>';
  return '<article class="panel gd5-quality"><div class="panel-head"><div><h2>Chất lượng & nguồn dữ liệu</h2><p>Giai đoạn 5 · Nhóm A + B06</p></div>'+tag(q.status)+'</div><div class="panel-body">'+
    '<div class="notice">Độ mới tính theo ngày và đồng hồ ca '+esc(state.day)+', không so demo 2022 với hôm nay. WARN vẫn cho demo chạy; lỗi thời gian / leakage bị chặn ở backend.</div>'+
    line('Thời điểm dự báo M2',q.prediction_as_of)+line('Ghi snapshot vào máy',q.recorded_at)+line('Nguồn',lineage.source||state.source)+
    line('Loại nguồn',lineage.type)+line('Nguồn lịch sử',lineage.history_origin)+line('Nguồn thời tiết',lineage.weather_origin)+line('Import ID',lineage.import_id)+line('SHA-256 tệp nhập',lineage.file_sha256)+
    line('Feature snapshot ID',state.feature_snapshot_id)+line('Model',q.model_version)+line('Hash đặc trưng',q.feature_hash)+
    '<h3 style="margin-top:20px">Dự báo thời tiết '+tag(w.status)+'</h3>'+line('Nguồn khai báo',w.source)+line(weatherMeta.timestamp_kind==='api_snapshot_captured'?'Chụp từ API':weatherMeta.timestamp_kind==='model_initialization'?'Khởi tạo lần chạy':'Phát hành',w.issued_at)+
    (weatherMeta.target_date_forecast?line('Ngày mục tiêu: mưa / nhiệt độ',weatherMeta.target_date_forecast.precipitation_sum_mm+' mm / '+weatherMeta.target_date_forecast.temperature_2m_max_c+'°C'):'')+
    (weatherMeta.target_date_forecast?line('Ngày thời tiết dùng cho M2',state.weather.weather_reference_date):'')+
    (weatherMeta.timestamp_kind==='model_initialization'?'<p>Giờ công bố lịch sử chưa được API xác nhận; thời điểm sẵn có là ước tính, chỉ dùng mô phỏng.</p>':'')+
    line('Sẵn có',w.available_at)+line('Tuổi tại 06:00 (giờ)',w.age_hours)+'<p>'+esc(w.message||'Ca cũ chưa có metadata GD5.')+'</p>'+
    '<h3 style="margin-top:20px">Độ mới lịch sử theo SKU</h3><div class="table-scroll"><table><thead><tr><th>SKU</th><th>Ngày mới nhất</th><th>Cách ngày dự báo</th><th>Thiếu trong 7 ngày</th><th>Kiểm tra</th></tr></thead><tbody>'+
    (q.history||[]).map(r=>'<tr><td>'+esc(r.sku)+'</td><td>'+esc(r.last_date)+'</td><td>'+esc(r.gap_days)+' ngày</td><td>'+r.missing_last7.length+'</td><td>'+tag(r.status)+'</td></tr>').join('')+'</tbody></table></div>'+
    '<h3 style="margin-top:20px">Nguồn bán hàng M1 '+tag(q.sales?.status)+'</h3><p>'+esc(q.sales?.message)+'</p>'+line('Tuổi dữ liệu (phút)',q.sales?.age_minutes)+
    (state.mode==='live'&&['running','price_pending','price_approved'].includes(state.phase)?'<button data-quality-verify>Đã kiểm tra: không có bán mới đến phút hiện tại</button>':'')+
    '<p class="muted">SHA-256 giúp phát hiện nội dung thay đổi; không chứng minh tệp đến từ POS/JMA thật. Demo/synthetic và timestamp chưa xác minh luôn được ghi rõ.</p></div></article>';
}
function importHistoryPanel(){
  return '<article class="panel" style="margin-top:20px"><div class="panel-head"><div><h2>Lịch sử nhập & cách ly</h2><p>100 lượt mới nhất · lưu sau khởi động lại</p></div><button data-quality-refresh>Tải lại</button></div><div class="panel-body">'+
    (importLog.length?importLog.map(r=>'<details style="padding:12px 0;border-bottom:1px solid var(--border)"><summary>'+esc(r.filename)+' · '+esc(r.status)+' · '+r.error_count+' lỗi</summary><p>Nguồn: '+esc(r.source_name)+'<br>Nhập: '+esc(r.created_at)+'<br>Ngày mục tiêu: '+esc(r.day)+'<br>SHA-256: <code style="overflow-wrap:anywhere">'+esc(r.sha256)+'</code><br>Ca: '+esc(r.confirmed_session||'Chưa xác nhận')+'</p>'+(r.confirmation_error?'<p>'+esc(r.confirmation_error)+'</p>':'')+r.errors.map(e=>'<p>Dòng '+esc(e.row)+': '+esc(e.message)+'</p>').join('')+r.warnings.map(w=>'<p>'+esc(w)+'</p>').join('')+'</details>').join(''):'<p>Chưa có lượt nhập. Demo chạy được ngay, không bắt buộc upload.</p>')+'</div></article>';
}
async function refreshQuality(){try{const r=await api('/api/imports');importLog=r.imports;if(currentView==='data')render()}catch(e){toast(e.message,true)}}
document.addEventListener('click',async e=>{
  if(e.target.closest('[data-quality-refresh]'))refreshQuality();
  if(e.target.closest('[data-quality-verify]')){
    const reason=window.prompt('Lý do / cách kiểm tra không có bán mới (lưu nhật ký):');
    if(reason?.trim())await act('confirm_zero_sales',{confirmed:true,reason:reason.trim()});
  }
});
