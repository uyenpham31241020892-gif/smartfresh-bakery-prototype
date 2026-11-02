'use strict';
let evaluationState=null,registryState=null,evaluationLoading=false;
async function loadEvaluation(){const id=state.id;evaluationLoading=true;try{const r=await api('/api/evaluation/'+id);if(state.id===id){evaluationState=r;if(currentView==='reports')render()}}catch(e){toast(e.message,true)}finally{evaluationLoading=false;if(state.id!==id&&currentView==='reports')loadEvaluation()}}
function evaluationPanel(){
 const r=evaluationState;if(!r||r.session_id!==state.id){if(!evaluationLoading)setTimeout(loadEvaluation,0);return '<article class="panel panel-body">Đang kiểm tra đối soát từ sổ giao dịch…</article>'}
 const manager=authUser?.role==='manager';
 return mcard('Đối soát cuối ca',r.day+' · '+r.mode+' · revision '+r.revision,'<div class="notice '+(r.publishable?'green':'')+'">'+esc(r.status)+' · '+(r.publishable?'Đủ điều kiện công bố KPI':'Chưa công bố KPI cuối ca')+'</div>'+(r.errors.length?'<div class="notice">'+r.errors.map(esc).join('<br>')+'</div>':'')+mtable(['SKU','Chuẩn bị','Bán báo cáo / sổ','Tồn cuối','Doanh thu báo cáo / sổ','Khớp'],r.rows.map(x=>[esc(x.sku),fmt(x.prepared),fmt(x.sold)+' / '+fmt(x.ledger_sold),fmt(x.ending_stock),money(x.reported_revenue)+' / '+money(x.ledger_revenue),x.passed?'✓':'✕']))+'<p>'+r.notes.map(esc).join('<br>')+'</p><details><summary>Bằng chứng</summary><p>Model '+esc(r.model_version)+'</p><code>'+esc(r.state_sha256)+'</code><p>'+(r.receipt_current?'Đã xác nhận bởi '+esc(r.receipt.actor.username)+' · '+esc(r.receipt.reason):'Chưa có xác nhận Manager cho snapshot này.')+'</p></details><div class="toolbar"><button data-eval-refresh>Làm mới đối soát</button><button data-eval-csv>Tải đối soát CSV</button><button data-eval-json>Tải bằng chứng JSON</button><button data-eval-certify '+(!manager||!r.publishable||r.receipt_current?'disabled':'')+'>Manager xác nhận đối soát</button><button data-eval-sensitivity '+(!r.publishable?'disabled':'')+'>Độ nhạy phản ứng giá</button></div>');
}
function bindEvaluation(){
 document.querySelector('[data-eval-csv]')?.addEventListener('click',()=>downloadReconciliation('csv'));
 document.querySelector('[data-eval-json]')?.addEventListener('click',()=>downloadReconciliation('json'));

 document.querySelector('[data-eval-refresh]')?.addEventListener('click',loadEvaluation);
 document.querySelector('[data-eval-certify]')?.addEventListener('click',()=>{
 const r=evaluationState;modal('Xác nhận đối soát','<p>Ghi nhận người duyệt và checksum sổ. Không chỉnh số liệu hoặc tự tạo chứng từ hủy.</p><label class="field">Lý do<textarea id="eval-reason" maxlength="2000"></textarea></label><button id="eval-confirm" class="primary">Xác nhận</button>');
 $('eval-confirm').onclick=async()=>{const reason=$('eval-reason').value.trim();if(reason.length<3)return toast('Nhập lý do ít nhất 3 ký tự.',true);$('eval-confirm').disabled=true;try{await api('/api/evaluation/'+r.session_id+'/certify',{revision:r.revision,state_sha256:r.state_sha256,reason});$('modal').close();await loadEvaluation()}catch(e){toast(e.message,true);$('eval-confirm').disabled=false}};
 });
 document.querySelector('[data-eval-sensitivity]')?.addEventListener('click',async()=>{try{const r=await api('/api/evaluation/'+state.id+'/sensitivity');modal('Sensitivity — phản ứng giá', '<div class="notice">'+esc(r.note)+'</div>'+mtable(['Hệ số phản ứng','Tổng đáp ứng cục bộ (bánh)','Giá trị đáp ứng cục bộ'],r.scenarios.map(x=>[x.response_factor+'×',fmt(x.incremental_units_sum),money(x.incremental_revenue_sum)])))}catch(e){toast(e.message,true)}});
}
async function loadRegistry(){try{registryState=await api('/api/registry');if(currentView==='registry')render()}catch(e){toast(e.message,true)}}
function registryView(){
 const r=registryState;if(!r)return '<article class="panel panel-body">Đang tải registry…</article>';
 const manager=authUser?.role==='manager';
 return '<div class="toolbar"><button data-reg-refresh>Tải lại registry</button><button data-go="learning">Nạp dữ liệu / huấn luyện ứng viên</button></div>'+r.versions.map(v=>mcard(esc(v.version),(v.active?'ĐANG DÙNG · ':'')+v.origin+' · '+v.status,'<p>Parent: '+esc(v.parent||'Bản gốc')+' · Checksum: '+(v.integrity?'PASS':'FAIL')+'</p>'+(v.error?'<div class="notice">'+esc(v.error)+'</div>':'')+'<details><summary>Manifest SHA256 & tương thích</summary><code>'+esc(v.manifest_sha256||'Không khả dụng')+'</code><p>'+Object.entries(v.compatibility).map(([k,b])=>esc(k)+': '+(b?'PASS':'FAIL')).join('<br>')+'</p></details>'+(v.report?'<p>Train đến '+esc(v.report.train_until)+' · calibration từ '+esc(v.report.calibration_from)+' · test '+esc(v.report.test_from)+' → '+esc(v.report.evaluated_until)+'</p>'+mtable(['Metric','Parent','Ứng viên'],[['MAE',fmt(v.report.current.mae),fmt(v.report.candidate.mae)],['WAPE (%)',v.report.current.wape_pct==null?'N/A':fmt(v.report.current.wape_pct),v.report.candidate.wape_pct==null?'N/A':fmt(v.report.candidate.wape_pct)]])+'<p>'+Object.entries(v.report.gates).map(([k,b])=>esc(k)+': '+(b?'PASS':'FAIL')).join('<br>')+'</p><button data-fresh-holdout="'+esc(v.version)+'" '+(!manager||!v.integrity?'disabled':'')+'>Kiểm tra 7 ngày holdout mới</button>':'')+(v.holdouts.length?mtable(['Holdout mới','Nguồn / dòng','MAE parent / ứng viên','Kết quả'],v.holdouts.map(h=>[esc(h.from+' → '+h.through),esc(h.origin)+' / '+h.rows,fmt(h.parent_metric.mae)+' / '+fmt(h.candidate.mae),h.passed?'PASS':'FAIL'])):'<p class="muted">Chưa có fresh holdout sau lần đánh giá ban đầu; không tạo điểm giả.</p>')+(manager&&v.report?.status==='awaiting_confirmation'&&v.parent===r.active?'<button data-reg-promote="'+esc(v.version)+'">Duyệt promotion</button>':'')+(manager&&v.active&&!v.frozen?'<button data-reg-rollback>Rollback về parent</button>':''))).join('')+mcard('Lịch sử vòng đời','Người thực hiện, lý do và phiên bản',mtable(['Thời điểm','Hành động','Bằng chứng'],r.events.map(e=>[esc(e.created),esc(e.action),'<details><summary>Xem</summary><pre>'+esc(JSON.stringify(JSON.parse(e.detail),null,2))+'</pre></details>'])));
}
function bindRegistry(){
 document.querySelector('[data-reg-refresh]')?.addEventListener('click',loadRegistry);
 document.querySelectorAll('[data-fresh-holdout]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{const h=await api('/api/learning/'+b.dataset.freshHoldout+'/holdout',{});toast('Fresh holdout: '+(h.passed?'PASS':'FAIL'));await loadRegistry()}catch(e){toast(e.message,true);b.disabled=false}});
 document.querySelectorAll('[data-reg-promote],[data-reg-rollback]').forEach(b=>b.onclick=()=>{
 const active=registryState.active,version=b.dataset.regPromote,rollback=b.hasAttribute('data-reg-rollback');
 modal(rollback?'Rollback về parent đã kiểm tra':'Phê duyệt ứng viên','<p>Chỉ ảnh hưởng ca tạo mới; ca đang chạy giữ nguyên phiên bản.</p><label class="field">Lý do<textarea id="reg-reason" maxlength="2000"></textarea></label><button id="reg-confirm" class="primary">Xác nhận</button>');
 $('reg-confirm').onclick=async()=>{const reason=$('reg-reason').value.trim();if(reason.length<3)return toast('Nhập lý do ít nhất 3 ký tự.',true);$('reg-confirm').disabled=true;try{await api(rollback?'/api/learning/rollback':'/api/learning/'+version+'/promote',{expected_active:active,reason});$('modal').close();await loadRegistry()}catch(e){toast(e.message,true);$('reg-confirm').disabled=false}};
 });
}

async function downloadReconciliation(kind){
 try{
 const sid=state.id;const r=await api('/api/evaluation/'+sid);
 if(state.id!==sid)throw Error('Ca đã thay đổi; mở lại đối soát của ca cần tải.');
 let text,mime;
 if(kind==='json'){text=JSON.stringify({exported_at:new Date().toISOString(),...r},null,2);mime='application/json;charset=utf-8';}
 else{
 const quote=v=>'"'+String(v??'').replace(/"/g,'""')+'"';
 const header=['session_id','date','revision','status','model_version','state_sha256','sku','prepared_units','sold_reported_units','sold_ledger_units','ending_stock_units','revenue_reported_vnd','revenue_ledger_vnd','passed','manager_confirmed','confirmed_by'];
 const rows=r.rows.map(x=>[r.session_id,r.day,r.revision,r.status,r.model_version,r.state_sha256,x.sku,x.prepared,x.sold,x.ledger_sold,x.ending_stock,x.reported_revenue,x.ledger_revenue,x.passed,r.receipt_current,r.receipt_current?r.receipt?.actor?.username:'']);
 text='\ufeff'+[header,...rows].map(row=>row.map(quote).join(',')).join('\r\n');mime='text/csv;charset=utf-8';
 }
 const url=URL.createObjectURL(new Blob([text],{type:mime}));const a=document.createElement('a');a.href=url;a.download='SmartFresh_DoiSoat_'+r.day+'_'+sid.slice(0,8)+'.'+kind;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
 }catch(e){toast('Không tải được đối soát: '+e.message,true)}
}
