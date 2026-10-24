/* GD7: read-only analytics with explicit source/target labels; writes require Manager. */
let monitoringState=null,monitoringTab='data',monitoringGroup='',monitoringBusy=false,monitoringSequence=0;
let monitoringFilters={source:'runtime',sandbox_id:'',date_from:'',date_to:'',mode:'',sku:'',model_version:''};
let monitoringAuto=true;
const mn=(v,digits=2)=>v===null||v===undefined?'—':Number(v).toLocaleString('vi-VN',{maximumFractionDigits:digits});
const mlabel={synthetic_base_demand:'Nhu cầu gốc · mô phỏng',observed_sales_proxy:'Số bán quan sát · proxy',controlled_synthetic_demand:'Nhu cầu shock · minh họa cô lập'};
const mstatus=s=>badge(({INSUFFICIENT:'Chưa đủ mẫu',UNCONFIGURED:'Chưa đặt ngưỡng',WITHIN_LOCAL_THRESHOLD:'Trong ngưỡng local',REVIEW:'Cần xem xét',PASS:'Đạt kiểm tra',BLOCK:'Bị chặn',WARN:'Còn hạn chế',LEGACY:'Ca cũ',CLOSED:'Ca đã chốt',DEMO:'Luồng mô phỏng'})[s]||s,['PASS','WITHIN_LOCAL_THRESHOLD'].includes(s)?'green':['BLOCK','REVIEW','WARN'].includes(s)?'amber':'');
function mtable(headers,rows){return '<div class="table-scroll"><table><thead><tr>'+headers.map(h=>'<th>'+esc(h)+'</th>').join('')+'</tr></thead><tbody>'+(rows.length?rows.map(r=>'<tr>'+r.map(c=>'<td>'+c+'</td>').join('')+'</tr>').join(''):'<tr><td colspan="'+headers.length+'"><div class="empty">Chưa có dữ liệu phù hợp bộ lọc.</div></td></tr>')+'</tbody></table></div>';}
function mcard(title,subtitle,body,extra=''){return '<article class="panel monitor-panel"><div class="panel-head"><div><h2>'+esc(title)+'</h2><p>'+esc(subtitle)+'</p></div>'+extra+'</div><div class="panel-body">'+body+'</div></article>';}
function monitorFilters(){
 const d=monitoringState||{},f=monitoringFilters,options=(items,value)=>items.map(([v,t])=>'<option value="'+esc(v)+'" '+(v===value?'selected':'')+'>'+esc(t)+'</option>').join('');
 return '<section class="monitor-filters" aria-label="Bộ lọc giám sát"><label>Nguồn phân tích<select data-monitor-filter="source">'+options([['runtime','Các ca vận hành local'],['sandbox','Minh họa drift cô lập']],f.source)+'</select></label>'+
 (f.source==='sandbox'?'<label>Bộ minh họa<select data-monitor-filter="sandbox_id"><option value="">Chọn bộ minh họa…</option>'+options((d.sandboxes||[]).map(s=>[s.id,s.label+' · '+s.created.slice(11,19)]),f.sandbox_id)+'</select></label>':'<label>Chế độ ca<select data-monitor-filter="mode">'+options([['','Tất cả · tách nhóm'],['simulation','Chỉ mô phỏng'],['live','Chỉ dữ liệu nhập']],f.mode)+'</select></label>')+
 '<label>Từ ngày ca<input type="date" data-monitor-filter="date_from" value="'+esc(f.date_from)+'"></label><label>Đến ngày ca<input type="date" data-monitor-filter="date_to" value="'+esc(f.date_to)+'"></label><label>SKU<select data-monitor-filter="sku">'+options([['','Tất cả SKU'],...state.plan.map(p=>[p.sku,p.sku+' · '+p.name])],f.sku)+'</select></label><label>Model<select data-monitor-filter="model_version">'+options([['','Tất cả · metric tách nhóm'],...(d.models||[state.model_version]).map(v=>[v,v])],f.model_version)+'</select></label></section>';
}
function monitoringView(){
 const d=monitoringState,manager=authUser?.role==='manager';
 let html='<div class="monitor-top"><div><div class="eyebrow">SMARTFRESH OBSERVABILITY · GD7</div><p>Đọc bằng chứng, phát hiện thay đổi và mở đúng luồng xử lý.</p></div><div class="safety-actions"><button data-monitor-refresh>'+icon('history')+'Làm mới</button><button data-monitor-demo '+(!manager||monitoringBusy?'disabled':'')+'>Tạo minh họa drift cô lập</button></div></div>'+monitorFilters();
 if(monitoringFilters.source==='sandbox'&&!monitoringFilters.sandbox_id)return html+'<article class="panel empty"><h3>Chọn hoặc tạo một bộ minh họa</h3><p>Bộ minh họa dùng dự báo M2 thật trên dữ liệu synthetic, tiêm shock nhu cầu có kiểm soát và không sửa ca, model hay dữ liệu học đang dùng.</p></article>';
 if(!d)return html+'<div class="panel empty">Đang tính giám sát từ dữ liệu đã lưu…</div>';
 if(d.scope.source!==monitoringFilters.source||['date_from','date_to','mode','sku'].some(k=>d.scope[k]!==monitoringFilters[k])||(monitoringFilters.source==='sandbox'&&d.scope.sandbox_id!==monitoringFilters.sandbox_id)||(monitoringFilters.model_version&&d.scope.selected_model!==monitoringFilters.model_version))return html+'<div class="panel empty">Đang áp dụng bộ lọc mới…</div>';
 html+='<div class="monitor-source '+(d.scope.source==='sandbox'?'sandbox':'')+'"><strong>'+esc(d.scope.source==='sandbox'?'MINH HỌA CÔ LẬP':'WORKSPACE LOCAL')+'</strong><span>'+esc(d.scope.source_label)+'</span><small>Cập nhật '+new Date(d.generated_at).toLocaleTimeString('vi-VN')+' · '+mn(d.calculation_ms,0)+' ms tính toán</small></div>';
 if(d.scope.source==='sandbox')html+='<div class="notice">Các metric M2/drift/cảnh báo mô hình dưới đây thuộc bộ minh họa, không phải chất lượng AEON thực tế. DQ ca hiện tại và API vẫn được gắn nhãn workspace riêng.</div>';
 const o=d.overview;
 html+='<section class="kpis monitor-kpis">'+kpi('Chất lượng ca hiện tại',esc(d.data_quality.status),'','Ca '+esc(state.day),'database')+
 kpi('Model đã chọn',o.model_integrity?'HASH OK':'CẦN KIỂM TRA','','Nguồn '+esc(d.scope.selected_model),'shield')+
 kpi('Dòng đã có nhãn đánh giá',mn(o.closed_metric_rows,0),'','M2 · không tính accuracy ca đang mở','chart')+
 kpi('Cảnh báo đang còn',mn(o.active_alerts,0),'','Tiếp nhận không đồng nghĩa đã hết','activity')+'</section>';
 html+='<div class="toolbar monitor-tabs"><div class="tabs">'+[['data','Dữ liệu'],['model','Mô hình'],['operations','Vận hành'],['alerts','Cảnh báo']].map(([key,label])=>'<button data-monitor-tab="'+key+'" class="'+(monitoringTab===key?'active':'')+'">'+label+(key==='alerts'?' · '+o.active_alerts:'')+'</button>').join('')+'</div><label class="monitor-auto"><input type="checkbox" data-monitor-auto '+(monitoringAuto?'checked':'')+'>Làm mới 30 giây</label></div>';
 const views={data:monitorData,model:monitorModel,operations:monitorOperations,alerts:monitorAlerts};html+=views[monitoringTab](d);
 if(d.scope.truncated)html+='<div class="notice">Đang giới hạn 500 ca mới nhất theo bộ lọc. Thu hẹp ngày/model để tránh đọc thống kê chưa đủ lịch sử.</div>';
 if(d.scope.unevaluated_closed_sessions)html+='<div class="notice">'+d.scope.unevaluated_closed_sessions+' ca chốt chưa tái lập được nhãn đúng phiên bản simulator; không tự lấy số bán thay thế nhu cầu.</div>';
 return html+'<p class="monitor-footnote">Giám sát không tự retrain, rollback hoặc đổi mode. Ngưỡng drift là cấu hình local, chưa được nghiệm thu production. Chi tiết: docs/GIAI_DOAN_7_HUONG_DAN.md.</p>';
}
function monitorData(d){
 const q=d.data_quality,i=q.imports;
 return '<section class="monitor-two">'+mcard('Độ mới & thời điểm','Ca đang chọn · '+state.day,mtable(['SKU','Ngày lịch sử cuối','Cách ngày ca','Thiếu trong 7 ngày','Trạng thái'],q.history.map(r=>[esc(r.sku),esc(r.last_date||'Chưa có'),mn(r.gap_days,0),mn(r.missing_last7.length,0),mstatus(r.status)]))+'<p class="monitor-note">'+esc(q.note)+'</p>')+
 mcard('Forecast & luồng bán','Workspace hiện tại, không lấy timestamp giả cho demo','<dl class="monitor-dl"><dt>Mốc dự báo M2</dt><dd>'+esc(q.prediction_as_of||'Chưa có')+'</dd><dt>Forecast phát hành</dt><dd>'+esc(q.weather.issued_at||'Chưa xác minh')+'</dd><dt>Tuổi forecast tại cutoff</dt><dd>'+mn(q.weather.age_hours)+' giờ</dd><dt>Kiểm tra forecast</dt><dd>'+mstatus(q.weather.status||'LEGACY')+'</dd><dt>Luồng bán/tồn</dt><dd>'+mstatus(q.sales.status)+'</dd><dt>Tuổi luồng bán</dt><dd>'+mn(q.sales.age_minutes)+' phút</dd></dl><p class="monitor-note">'+esc(q.weather.message||'Ca cũ chưa có timestamp đầy đủ.')+'</p><details><summary>Feature snapshot</summary><code class="monitor-code">'+esc(q.feature_snapshot_id||'Chưa có')+'</code></details>')+'</section>'+
 mcard('Chất lượng các lượt nhập','Theo ngày mục tiêu · tối đa 1.000 lượt mới nhất',mtable(['Lượt đã quét','Preview hợp lệ','Đã xác nhận','Cách ly','Xác nhận bị chặn','Lỗi dòng','Lỗi trùng','Dòng lịch sử đã nhận','Giao dịch đã nhận'],[[i.scanned,i.valid_previews,i.confirmed,i.quarantined,i.blocked_confirmations,i.row_errors,i.duplicate_errors,i.accepted_history_rows,i.accepted_transaction_rows].map(v=>mn(v,0))])+'<p class="monitor-note">Dòng hợp lệ trong preview của file bị cách ly chưa được tính là đã nhận. Một lỗi có thể là lỗi trùng; không cộng hai cột như hai tập độc lập.</p>')+
 monitorDrift(d);
}
function monitorDrift(d){
 const drift=d.drift,ref=drift.reference;
 return mcard('Dịch chuyển phân phối feature','Data drift · '+(ref.available?'TRAIN '+ref.from+' → '+ref.through:'Reference chưa sẵn có'),
 '<div class="notice">'+esc(ref.available?ref.source:ref.reason)+'</div>'+mtable(['Feature','Mẫu tham chiếu','Mẫu hiện tại / ngày','Mean tham chiếu','Mean hiện tại','PSI','KS statistic','Đánh giá'],drift.data.map(r=>[
 esc(featureNames[r.feature]||r.feature),mn(r.reference_n,0),mn(r.current_n,0)+' / '+r.current_days,mn(r.reference_mean),mn(r.current_mean),mn(r.psi,4),mn(r.ks_statistic,4),mstatus(r.status)]))+
 '<p class="monitor-note">'+esc(drift.note)+' Tối thiểu '+d.config.min_rows+' dòng và '+d.config.min_days+' ngày hiện tại để bật đánh giá; lặp 8 SKU trong một ngày không tạo 8 ngày độc lập.</p><details><summary>Phương pháp & reference hash</summary><p>PSI dùng bins theo reference, pseudocount 0,5. KS chỉ là statistic; không trả p-value hay kết luận nhân quả.</p><code class="monitor-code">'+esc(ref.sha256||'Chưa có')+'</code></details>');
}
function selectedMetric(d){
 const key=g=>g.model_version+'|'+g.origin+'|'+g.target_kind;
 return d.accuracy.find(g=>key(g)===monitoringGroup)||d.accuracy.find(g=>g.model_version===d.scope.selected_model&&g.origin==='AI_M2')||d.accuracy[0];
}
function monitorModel(d){
 const g=selectedMetric(d),key=g=>g.model_version+'|'+g.origin+'|'+g.target_kind;
 let body='<div class="notice">Chỉ đọc metric sau chốt ca. Nhu cầu gốc simulator, số bán proxy và Rolling-7 được tách nhóm, không gộp thành một điểm accuracy.</div>';
 if(!g)return body+mcard('M2 chưa có nhãn để tính sai số','Không hiển thị 0% như thể dự báo hoàn hảo','<div class="empty">Chốt một ca để có số liệu, hoặc tạo bộ minh họa drift cô lập ở đầu trang. Ca đang mở vẫn có DQ và kiểm tra feature.</div>')+monitorThresholds(d);
 body+='<label class="field monitor-group">Nhóm metric đang xem<select data-monitor-group>'+d.accuracy.map(x=>'<option value="'+esc(key(x))+'" '+(key(x)===key(g)?'selected':'')+'>'+esc(x.model_version+' · '+x.origin+' · '+(mlabel[x.target_kind]||x.target_kind))+'</option>').join('')+'</select></label>';
 body+='<div class="monitor-source"><strong>'+esc(mlabel[g.target_kind]||g.target_kind)+'</strong><span>'+esc(g.target_note)+'</span></div>';
 const m=g.metrics;
 body+='<section class="kpis monitor-kpis">'+kpi('WAPE',mn(m.wape_pct),'%',m.actual_sum===0?'Mẫu số actual bằng 0 → N/A':'Σ|forecast − actual| / Σactual','chart')+kpi('MAE',mn(m.mae),'bánh','Sai lệch tuyệt đối trung bình','bread')+kpi('Bias',mn(m.bias_pct),'%','Dương: dự báo cao hơn actual','activity')+kpi('Độ phủ',g.day_count,'ngày',g.metrics.n+' dòng · '+g.session_count+' ca','history')+'</section>';
 body+=mcard('Sai số M2 theo ngày','Cùng một nhóm model / nguồn dự báo / loại nhãn',monitorLine(g.daily,'wape_pct','WAPE (%)')+'<p class="monitor-note">'+(g.target_kind==='observed_sales_proxy'?'Đây là sai số so số bán đã ghi nhận; '+g.stockout_rows+' dòng có tồn cuối ca bằng 0, chưa chứng minh nhãn nhu cầu không bị thiếu.':'Đây là dữ liệu synthetic, không phải kiểm định POS AEON.')+'</p>');
 body+=mcard('Performance drift','So hai cửa sổ ngày có quan sát, không trộn phiên bản',mtable(['Loại nhãn','WAPE cửa sổ trước','WAPE gần đây','Chênh lệch (điểm %)','Ngày trước / gần đây','Đánh giá'],d.drift.performance.map(r=>[
 esc(mlabel[r.target_kind]||r.target_kind),mn(r.reference.wape_pct)+'%',mn(r.recent.wape_pct)+'%',mn(r.delta_wape_pp),r.reference_days.length+' / '+r.recent_days.length,mstatus(r.status)]))+'<p class="monitor-note">Live observed-sales proxy không được dùng để tự tuyên bố performance drift của nhu cầu gốc. Mục tiêu 18% là học thuật, không phải SLA.</p>');
 body+=mcard('Phân tích lát cắt','SKU, lịch và thời tiết · nhóm metric đang chọn',mtable(['Lát cắt','Nhóm','N','WAPE (%)','MAE (bánh)','Bias (%)'],Object.entries(g.slices).flatMap(([field,rows])=>rows.map(r=>[esc(field),esc(r.slice),r.n,mn(r.wape_pct),mn(r.mae),mn(r.bias_pct)]))));
 body+=mcard('Các nhóm được giữ riêng','Không so sánh lẫn AI/fallback hoặc nhãn khác nhau',mtable(['Model','Nguồn','Loại nhãn','N','Ngày','WAPE (%)'],d.accuracy.map(x=>[esc(x.model_version),esc(x.origin),esc(mlabel[x.target_kind]||x.target_kind),x.metrics.n,x.day_count,mn(x.metrics.wape_pct)])));
 return body+monitorThresholds(d);
}
function monitorThresholds(d){
 const c=d.config,manager=authUser?.role==='manager';
 if(d.scope.source==='sandbox')return mcard('Ngưỡng minh họa','Chỉ trong sandbox này','<p>PSI ≥ '+mn(c.psi_threshold)+'; WAPE tăng ≥ '+mn(c.performance_delta_pp)+' điểm %. Đây là ngưỡng cố ý phục vụ diễn tập, không đổi cấu hình workspace.</p>');
 return '<details class="monitor-config"><summary>Ngưỡng drift local & ghi chú hiệu chỉnh · Manager</summary><p>'+esc(c.calibration_note)+'</p><form id="monitor-config-form"><div class="monitor-two"><label class="field">PSI cần xem xét · bỏ trống nếu chưa đặt<input type="number" name="psi" min="0.0001" max="100" step="any" value="'+esc(c.psi_threshold??'')+'" '+(!manager?'disabled':'')+'></label><label class="field">WAPE tăng · điểm phần trăm<input type="number" name="delta" min="0.0001" max="100" step="any" value="'+esc(c.performance_delta_pp??'')+'" '+(!manager?'disabled':'')+'></label></div><label class="field">Ghi chú hiệu chỉnh / thử nghiệm<textarea name="note" minlength="8" maxlength="500" required '+(!manager?'disabled':'')+'>'+esc(c.calibration_note)+'</textarea></label><button class="primary" '+(!manager?'disabled':'')+'>Lưu cấu hình local</button><p class="monitor-note">Không tự tắt AI/retrain/rollback. Mọi thay đổi ngưỡng có audit; để trống là chưa đánh giá theo ngưỡng.</p></form></details>';
}
function monitorOperations(d){
 const o=d.operations,h=o.http,s=d.m1_safety,w=o.workflow;
 return '<section class="kpis monitor-kpis">'+kpi('API 24 giờ',mn(h.requests,0),'requests','Theo thời gian máy, không phải ngày ca','activity')+kpi('p95 backend',mn(h.p95_ms),'ms','Đến response headers; không phải latency POS','clock')+kpi('HTTP 4xx / 5xx',h.http_4xx+' / '+h.http_5xx,'','Tách từ chối request và lỗi server','shield')+kpi('Job đang báo lỗi',o.job_failures.length,'','Nguồn đồng hồ mô phỏng đã lưu','settings')+'</section>'+
 mcard('API local theo route','Không lưu request body, query string, mật khẩu hay API key',mtable(['Method','Route','Requests','4xx','5xx','p50 ms','p95 ms'],h.routes.map(r=>[esc(r.method),esc(r.route),r.requests,r.http_4xx,r.http_5xx,mn(r.p50_ms),mn(r.p95_ms)]))+'<details><summary>Request lỗi gần đây</summary>'+mtable(['Thời điểm UTC','Route','HTTP','Request ID'],h.recent_errors.map(r=>[esc(r.created),esc(r.route),r.status,'<code>'+esc(r.request_id)+'</code>']))+'</details><p class="monitor-note">'+esc(h.note)+'</p>')+
 mcard('M1 safety & luồng duyệt','Các ca workspace theo bộ lọc; không phải dữ liệu minh họa drift',mtable(['Đề xuất đã kiểm','Vi phạm đề xuất','Dòng applied đã kiểm','Vi phạm applied','Incident hard-rule'],[[s.checked_proposal_rows,s.proposal_violations,s.checked_applied_rows,s.checked_applied_rows?s.applied_violations:'Chưa có applied',s.hard_rule_incidents].map(v=>esc(v))])+mtable(['Chờ sản lượng','Chờ giá','Đã duyệt chưa áp','Lượt duyệt','Từ chối','Lượt override'],[[w.pending_plan,w.pending_price,w.approved_not_applied,w.approvals,w.rejections,w.overrides].map(v=>esc(v))])+'<p class="monitor-note">'+esc(s.note)+' Override là thay đổi thực sự so đề xuất, không đếm chỉ vì có ô reason.</p>')+
 mcard('Business guardrails','Chỉ ca đã chốt · đơn vị bánh / VND',mtable(['Chế độ','Ca','Chuẩn bị','Bán','Dư','Waste (%)','Doanh thu VND','SKU-ca tồn cuối = 0','Lost sales mô phỏng'],d.business.groups.map(r=>[esc(r.mode),r.sessions,mn(r.prepared,0),mn(r.sold,0),mn(r.waste,0),mn(r.waste_rate_pct),mn(r.revenue_vnd,0),r.stockout_sku_rows,r.lost_simulator_only===null?'Chưa biết':mn(r.lost_simulator_only,0)]))+'<p class="monitor-note">'+esc(d.business.note)+'</p>')+
 mcard('Lịch sử job local','24 giờ theo thời gian máy; rejected khác với lỗi runtime',mtable(['Loại job','Trạng thái','Thời điểm UTC','Thời gian ms','Loại lỗi'],o.jobs_recent.map(r=>[esc(r.kind),esc(r.status),esc(r.created),mn(r.elapsed_ms),esc(r.error_type||'—')]))+'<p class="monitor-note">Ứng viên model không đạt chỉ tiêu vẫn có thể là job chạy thành công. Job bị ngắt do restart có trạng thái interrupted.</p>')+
 mcard('Lỗi job và đối soát cần xem','Đối chiếu dữ liệu đang lưu; không tự sửa sổ',mtable(['Nguồn','Ca / SKU','Chi tiết'],[...o.job_failures.map(r=>['Đồng hồ',esc(r.sid),esc(r.error)]),...d.business.mismatches.map(r=>['Đối soát',esc(r.session_id)+' / '+esc(r.sku),'Prepared/Sold/Stock hoặc doanh thu không khớp'])]));
}
function monitorAlerts(d){
 const manager=authUser?.role==='manager',active=d.alerts.filter(a=>a.active),cleared=d.alerts.filter(a=>!a.active);
 const card=a=>'<article class="monitor-alert '+esc(a.severity)+'"><div class="toolbar">'+badge(a.severity==='critical'?'CẦN XỬ LÝ':'CẦN XEM XÉT',a.severity==='critical'?'amber':'')+badge(a.active?(a.ack_by?'Đã tiếp nhận · điều kiện còn':'Đang còn điều kiện'):'Điều kiện đã hết',a.active?'amber':'green')+'<strong>'+esc(a.title)+'</strong></div><p>'+esc(a.message)+'</p><small>'+esc(a.code)+' · lần thấy gần nhất '+esc(a.last_seen)+'</small>'+(a.ack_by?'<p>Tiếp nhận: <b>'+esc(a.ack_by)+'</b> · '+esc(a.ack_note)+'</p>':'')+'<details><summary>Bằng chứng & số liệu</summary><pre>'+esc(JSON.stringify(a.evidence,null,2))+'</pre></details><div class="safety-actions">'+(a.active&&!a.ack_by?'<button data-monitor-ack="'+a.id+'" data-evidence="'+a.evidence_hash+'" '+(!manager?'disabled':'')+'>Tiếp nhận cảnh báo</button>':'')+'<button data-go="safety">Mở An toàn & sự cố</button></div></article>';
 return '<div class="notice">Cảnh báo giám sát không tự tạo incident hay đổi chế độ. “Tiếp nhận” là đã đọc và ghi chú, không xóa điều kiện. Khi điều kiện hết trong lần đánh giá tiếp theo, cảnh báo chuyển sang đã hết.</div>'+mcard('Cảnh báo đang còn','Nguồn và bộ lọc hiện tại · '+active.length+' cảnh báo',active.length?active.map(card).join(''):'<div class="empty">Chưa có điều kiện cảnh báo trong dữ liệu hiện có. Điều này không thay thế nghiệm thu production.</div>')+(cleared.length?mcard('Điều kiện đã hết','Lịch sử của cùng phạm vi giám sát',cleared.map(card).join('')):'');
}
function monitorLine(rows,field,label){
 const points=rows.filter(r=>r[field]!==null&&Number.isFinite(Number(r[field])));
 if(!points.length)return '<div class="empty">Chưa đủ mẫu số để vẽ '+esc(label)+'.</div>';
 const W=800,H=230,left=55,right=20,top=20,bottom=42,max=Math.max(1,...points.map(p=>Number(p[field])))*1.1;
 const x=i=>left+(W-left-right)*(points.length===1?.5:i/(points.length-1)),y=v=>H-bottom-(H-top-bottom)*v/max;
 const line=points.map((p,i)=>(i?'L':'M')+x(i).toFixed(2)+','+y(p[field]).toFixed(2)).join(' ');
 return '<svg class="monitor-chart" viewBox="0 0 '+W+' '+H+'" role="img" aria-label="'+esc(label)+' theo ngày">'+[0,.5,1].map(t=>'<line x1="'+left+'" x2="'+(W-right)+'" y1="'+y(t*max)+'" y2="'+y(t*max)+'" stroke="#eee8ed"/><text x="'+(left-8)+'" y="'+(y(t*max)+4)+'" text-anchor="end">'+mn(t*max,1)+'</text>').join('')+'<path d="'+line+'" stroke="#a50870" stroke-width="3" fill="none"/>'+points.map((p,i)=>'<circle cx="'+x(i)+'" cy="'+y(p[field])+'" r="3" fill="#a50870"><title>'+esc(p.day)+': '+mn(p[field])+'</title></circle>').join('')+[0,Math.floor((points.length-1)/2),points.length-1].filter((x,i,a)=>a.indexOf(x)===i).map(i=>'<text x="'+x(i)+'" y="'+(H-15)+'" text-anchor="middle">'+esc(points[i].day.slice(5))+'</text>').join('')+'</svg>';
}
async function loadMonitoring(){
 if(!state||!authUser)return;
 if(monitoringFilters.source==='sandbox'&&!monitoringFilters.sandbox_id)return;
 const seq=++monitoringSequence,sid=state.id,params=new URLSearchParams({session_id:sid,...monitoringFilters});
 try{const data=await api('/api/monitoring?'+params);if(seq!==monitoringSequence||state.id!==sid)return;monitoringState=data;if(currentView==='monitoring')render();}
 catch(e){if(seq===monitoringSequence)toast(e.message,true);}
}
function bindMonitoring(){
 document.querySelectorAll('[data-monitor-filter]').forEach(el=>el.onchange=()=>{
  monitoringFilters[el.dataset.monitorFilter]=el.value;
  if(el.dataset.monitorFilter==='source'&&el.value==='sandbox'&&!monitoringFilters.sandbox_id)monitoringFilters.sandbox_id=monitoringState?.sandboxes[0]?.id||'';
  if(monitoringFilters.source==='sandbox'&&!monitoringFilters.sandbox_id){render();return;}loadMonitoring();
 });
 const form=$('monitor-config-form');if(form)form.onsubmit=async e=>{e.preventDefault();if(authUser.role!=='manager')return;const elements=form.elements;
  try{await api('/api/monitoring/config',{expected_version:monitoringState.config.version,psi_threshold:elements.namedItem('psi').value.trim()===''?null:Number(elements.namedItem('psi').value),performance_delta_pp:elements.namedItem('delta').value.trim()===''?null:Number(elements.namedItem('delta').value),calibration_note:elements.namedItem('note').value});toast('Đã lưu ngưỡng local và audit.');await loadMonitoring();}catch(err){toast(err.message,true);}
 };
}
document.addEventListener('click',async e=>{
 const b=e.target.closest('button');if(!b||b.disabled)return;
 if(b.hasAttribute('data-monitor-refresh'))loadMonitoring();
 if(b.dataset.monitorTab){monitoringTab=b.dataset.monitorTab;render();}
 if(b.hasAttribute('data-monitor-demo')){
  if(monitoringBusy)return;monitoringBusy=true;render();
  try{const r=await api('/api/monitoring/sandbox',{session_id:state.id});monitoringFilters={...monitoringFilters,source:'sandbox',sandbox_id:r.id,date_from:'',date_to:'',model_version:r.model_version};monitoringTab='model';await loadMonitoring();toast('Đã tạo minh họa riêng; không đổi ca/model đang dùng.');}catch(err){toast(err.message,true);}finally{monitoringBusy=false;render();}
 }
 if(b.dataset.monitorAck){const note=prompt('Ghi chú tiếp nhận cảnh báo (ít nhất 3 ký tự):');if(!note||note.trim().length<3)return;try{await api('/api/monitoring/alerts/'+b.dataset.monitorAck+'/acknowledge',{evidence_hash:b.dataset.evidence,note:note.trim()});await loadMonitoring();toast('Đã tiếp nhận; điều kiện cảnh báo vẫn được theo dõi.');}catch(err){toast(err.message,true);}}
});
document.addEventListener('change',e=>{
 if(e.target.hasAttribute('data-monitor-auto'))monitoringAuto=e.target.checked;
 if(e.target.hasAttribute('data-monitor-group')){monitoringGroup=e.target.value;render();}
});
setInterval(()=>{if(typeof currentView!=='undefined'&&currentView==='monitoring'&&monitoringAuto&&!monitoringBusy&&!working&&!$('modal').open&&!document.activeElement?.closest('#monitor-config-form'))loadMonitoring();},3000);
function monitoringLink(){const known=monitoringState?.scope.session_id===state.id&&monitoringState.scope.source==='runtime';return '<div class="monitor-overview-link"><span>'+icon('activity')+'<b>Giám sát hệ thống</b> · '+(known?monitoringState.overview.active_alerts+' cảnh báo ở lần kiểm tra gần nhất':'Mở để kiểm tra dữ liệu, sai số và drift')+'</span><button class="small" data-go="monitoring">Xem giám sát '+icon('arrow')+'</button></div>';}
