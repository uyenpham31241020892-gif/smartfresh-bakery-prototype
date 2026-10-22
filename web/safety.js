let safetyData=null;
function safetyView(){
 const c=state.safety||{},d=safetyData||{},manager=authUser?.role==='manager';
 const btn=(label,action,value='')=>'<button data-safety-post="'+action+'" data-value="'+value+'" '+(!manager?'disabled':'')+'>'+esc(label)+'</button>';
 return '<div class="notice">Chế độ <b>'+esc(c.mode||'assisted')+'</b> · '+esc(c.open_incidents||0)+' sự cố đang mở. Đây là hành động trong prototype local, chưa kết nối POS.</div>'+
 '<article class="panel"><div class="panel-head"><h2>Artifact & quyền truy cập</h2>'+badge(d.integrity?.passed?'HASH OK':'CẦN KIỂM TRA',d.integrity?.passed?'green':'amber')+'</div><div class="panel-body"><p>'+esc(d.integrity?.message||'Đang tải…')+'</p><p>Đăng nhập: <b>'+esc(authUser?.username)+' · '+esc(authUser?.role)+'</b></p><p>Staff vận hành nhưng không duyệt giá/sản lượng. Viewer chỉ xem. Tất cả quyền được kiểm tra lại ở API.</p><p>Audit lưu danh tính từ phiên đăng nhập, revision, model, giá trước/sau và lý do.</p><button data-safety-refresh>Tải lại trạng thái</button></div></article>'+
 '<article class="panel" style="margin-top:20px"><div class="panel-head"><div><h2>Trung tâm sự cố</h2><p>Open → Acknowledged → Verify → Resolved → bật lại AI</p></div></div><div class="panel-body">'+
 ((d.incidents||[]).length?(d.incidents||[]).map(i=>'<article class="incident-card"><div class="toolbar">'+badge(i.priority,'amber')+badge(i.status,i.status==='resolved'?'green':'amber')+'<strong>'+esc(i.kind)+'</strong></div><p>'+esc(i.detail)+'</p><small>ID '+esc(i.id)+' · Phụ trách: '+esc(i.owner||'Chưa tiếp nhận')+'</small>'+(i.verification?'<details><summary>Bằng chứng kiểm tra</summary><pre>'+esc(JSON.stringify(JSON.parse(i.verification),null,2))+'</pre></details>':'')+'<div class="safety-actions">'+(i.status==='open'?'<button data-incident="acknowledge" data-id="'+i.id+'">Tiếp nhận</button>':i.status==='acknowledged'?'<button data-incident="verify" data-id="'+i.id+'">Kiểm tra phục hồi</button><button data-incident="resolve" data-id="'+i.id+'">Đóng sự cố</button>':'')+'</div></article>').join(''):'<p>Chưa có sự cố cho ca này.</p>')+'</div></article>'+
 '<section class="cols safety-grid" style="margin-top:20px"><article class="panel"><div class="panel-head"><h2>Diễn tập lỗi có kiểm soát</h2>'+badge('CHỈ CA MÔ PHỎNG')+'</div><div class="panel-body"><p>Cờ lỗi giả lập, không sửa hay phá model/dữ liệu thật. Lỗi M2 cần ca mới chờ duyệt; lỗi M1 và tồn kho nên thử từ 19:30.</p><div class="safety-actions">'+btn('M2 lỗi → Rolling-7','drill','m2_error')+btn('M1 lỗi → Manual','drill','m1_error')+btn('Tồn kho không đáng tin','drill','stale_stock')+btn('Gỡ cờ lỗi diễn tập','drill','clear')+btn('Diễn tập rollback cô lập','rollback_drill')+'</div><p>Gỡ cờ lỗi chưa đóng incident và chưa tự bật AI. Sau đó tiếp nhận → Verify → đóng sự cố → Assisted.</p></div></article>'+
 '<article class="panel"><div class="panel-head"><h2>Tài khoản local</h2></div><div class="panel-body">'+(manager?'<form id="add-user-form"><label class="field">Tên tài khoản<input name="username" minlength="3" maxlength="40" required></label><label class="field">Mật khẩu ban đầu<input name="password" type="password" minlength="8" maxlength="128" required></label><label class="field">Vai trò<select name="role"><option value="staff">Staff · vận hành</option><option value="viewer">Viewer · chỉ xem</option><option value="manager">Manager · được duyệt</option></select></label><button class="primary" data-user-create>Tạo tài khoản</button><p>Đăng xuất bằng cách nhấn tên tài khoản ở cuối menu, rồi đăng nhập tài khoản khác để thử quyền.</p></form>':'<p>Chỉ Manager có quyền tạo tài khoản.</p>')+'</div></article></section>';
}
async function loadSafety(){try{safetyData=await api('/api/safety?session_id='+state.id);if(currentView==='safety')render();}catch(e){toast(e.message,true);}}
function pricingModePanel(){
 const mode=state.safety?.mode||'assisted',manager=authUser?.role==='manager',closed=state.phase==='closed';
 return '<article class="panel panel-body" style="margin-bottom:18px"><h2>Chế độ vận hành của ca</h2><div class="safety-actions">'+[['assisted','AI hỗ trợ · Assisted'],['manual','Manager tự quyết · Manual'],['shadow','Thử nghiệm · Shadow']].map(([v,label])=>'<button data-safety-post="mode" data-value="'+v+'" class="'+(mode===v?'primary':'')+'" '+(!manager||closed||working||mode===v?'disabled':'')+'>'+label+'</button>').join('')+'</div><p>'+esc(currentView!=='m1'?(mode==='manual'?'M2 dùng quy tắc dự phòng Rolling-7 khi lập lại kế hoạch; Manager quyết định và duyệt sản lượng.':mode==='shadow'?'Chạy thử quyết định giá; xác nhận giá không thay đổi giá giao dịch trong ca.':'AI hỗ trợ đề xuất; Manager kiểm tra, điều chỉnh và phê duyệt.'):mode==='manual'?'Manager chọn mức giảm riêng từng SKU trong giới hạn chính sách; quy tắc giữ giá là điểm xuất phát, không phải đề xuất AI.':mode==='shadow'?'Chỉ ghi thử quyết định, không đổi giá giao dịch.':'Có thể chỉnh mức duyệt riêng từng SKU ngay trong Assisted; không bắt buộc đổi Manual.')+'</p><p class="muted">Ba trang dùng chung chế độ của ca. Chỉ Manager được đổi và phải ghi lý do; kế hoạch sản lượng đã duyệt được giữ nguyên.</p>'+(currentView==='m1'?'<p class="muted">Đổi chế độ tạm dừng bán tự động, vô hiệu đề xuất cũ và tạo bảng mới tại phút hiện tại. Luôn giữ sàn/trần theo giờ, thang giá và không giảm ngược. 50% chỉ khả dụng từ 21:30. Cần ghi lý do khi điều chỉnh.</p>':'<p class="muted">Đổi chế độ tạm dừng bán tự động; kế hoạch chưa duyệt được tính lại, bảng giá hiện tại được làm mới khi đang trong khung giảm giá.</p>')+(currentView==='m1'&&manager&&!closed&&state.products&&Object.keys(state.products).length&&state.minute>=1170&&state.minute<1320?'<button data-edit-pricing>Tạo lại bảng chỉnh giá tại '+hour(state.minute)+'</button>':'')+'</article>';
}
async function pausePricingClock(){
 if(state.realtime?.enabled)storeState(await api('/api/realtime/'+state.id,{enabled:false,speed:state.realtime.speed,pause_confirm:state.realtime.pause_confirm}));
}
async function safetyAction(action,value){
 if(working)return;
 const reason=prompt('Ghi lý do / hành động xử lý (bắt buộc, tối thiểu 3 ký tự):');if(!reason||reason.trim().length<3)return;
 working=true;
 try{if(action==='mode')await pausePricingClock();
 const r=await api('/api/safety/control',{session_id:state.id,revision:state.revision,action,value,reason:reason.trim()});storeState(r.state);await loadSafety();if(r.drill)modal('Kết quả rollback drill','<p>Không đổi active model.</p><pre>'+esc(JSON.stringify(r.drill,null,2))+'</pre>');toast('Đã ghi nhận chế độ và lý do cho toàn ca; kiểm tra đề xuất hiện tại trước khi duyệt.');
 }catch(e){toast(e.message,true);try{storeState(await api('/api/state?session_id='+state.id))}catch(_){}await loadSafety();}finally{working=false;render();}
}
async function editPricing(){
 if(working)return;working=true;
 try{await pausePricingClock();storeState(await api('/api/sessions/'+state.id+'/refresh_price',{revision:state.revision,payload:{reason:'Manager mở lại bảng chỉnh giá'},key:crypto.randomUUID()}));toast('Đã tạo đề xuất mới; chọn mức riêng từng SKU rồi duyệt và áp dụng.');}catch(e){toast(e.message,true);}finally{working=false;render();}
}
document.addEventListener('click',async e=>{
 const b=e.target.closest('button');if(!b||b.disabled)return;
 if(b.hasAttribute('data-safety-refresh'))loadSafety();
 if(b.hasAttribute('data-edit-pricing'))editPricing();
 if(b.dataset.safetyPost)safetyAction(b.dataset.safetyPost,b.dataset.value||'');
 if(b.dataset.incident){const reason=prompt('Lý do / cách khắc phục (ít nhất 3 ký tự):');if(!reason||reason.trim().length<3)return;try{await api('/api/safety/incidents/'+b.dataset.id,{action:b.dataset.incident,reason:reason.trim()});storeState(await api('/api/state?session_id='+state.id));await loadSafety();toast('Đã cập nhật sự cố.');}catch(e){toast(e.message,true);}}
});
function bindSafety(){const form=$('add-user-form');if(form)form.onsubmit=async e=>{e.preventDefault();try{await api('/api/auth/users',{username:form.elements.namedItem('username').value.trim(),password:form.elements.namedItem('password').value,role:form.elements.namedItem('role').value});form.reset();toast('Đã tạo tài khoản local.');}catch(err){toast(err.message,true);}};}
function safetyNotice(){
 const c=state.safety||{},origin=state.prediction_origin;
 let text='';if(c.mode==='manual')text='MANUAL · AI đang tạm dừng. Các số đề xuất có thể đến từ quy tắc dự phòng, cần Manager duyệt. Đổi chế độ bằng các nút ở đầu trang.';
 else if(c.mode==='shadow')text='SHADOW · Thử quyết định; xác nhận giá không thay đổi giá giao dịch trong ca.';
 if(c.open_incidents)text+=' Có sự cố cần xử lý. Mở An toàn & sự cố để xem chi tiết.';
 if(origin==='RULE_ROLLING7')text+=' Kế hoạch M2 hiện tại dùng Rolling-7, không phải dự báo LightGBM.';
 return text?'<div class="notice" style="margin-bottom:16px">'+esc(text)+(c.open_incidents?' <button class="small" data-go="safety">Mở An toàn & sự cố</button>':'')+'</div>':'';
}
