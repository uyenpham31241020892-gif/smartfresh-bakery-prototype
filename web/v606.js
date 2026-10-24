// Existing prototype UI, with backend POS and explicit scenario comparison.
document.addEventListener('click',async e=>{
 const button=e.target.closest('[data-simulator-report]');if(!button)return;
 e.preventDefault();e.stopImmediatePropagation();
 try{
  const r=await api('/api/simulation-comparison?day='+state.day+'&seed='+state.seed);
  modal('Hiệu quả model V6.06 · mô phỏng đông khách',
   '<p>Ngày '+esc(r.day)+' · seed '+r.seed+' · '+r.potential_purchases+' lượt yêu cầu mua. Cả bốn nhánh nhận cùng một luồng khách.</p>'+
   '<div class="notice">Kịch bản thử tải: lượng mua 4× trung bình lịch sử quan sát trước test. Đây là giả định, chưa phải kết quả chạy thị trường private gốc hay đo đạc AEON. Không retrain model. Tự duyệt đề xuất hợp lệ theo cùng quy trình trong phép so sánh này.</div>'+
   '<table><thead><tr><th>Nhánh</th><th>Chuẩn bị</th><th>Bán</th><th>Doanh thu</th><th>Chênh baseline</th><th>Không phục vụ</th></tr></thead><tbody>'+
   r.branches.map(b=>'<tr><td>'+esc(b.branch)+'</td><td>'+b.prepared+'</td><td>'+b.sold+'</td><td>'+fmt(b.revenue)+'đ</td><td>'+fmt(b.delta_revenue)+'đ ('+b.delta_percent.toFixed(2)+'%)</td><td>'+b.lost+'</td></tr>').join('')+
   '</tbody></table><p>M1 học bắt chước hành động đã ghi nhận, không chứng minh uplift giảm giá. Khách đông có thể làm hết hàng sớm: lượt mua tiềm năng không đồng nghĩa đã bán. Không tự tăng công suất hoặc lượng model dự báo để tạo kết quả tốt. Chi phí chưa có nên không báo lợi nhuận. Không tính SHAP trong tích hợp này.</p>');
 }catch(err){toast(err.message,true)}
},true);

function renderLiveSales(){
 if(typeof state==='undefined'||!state)return;
 document.querySelectorAll('[data-simulator-report]').forEach(b=>b.textContent='Model V6.06: baseline vs AI');
 let panel=document.getElementById('v606-live');
 if(!panel){const anchor=document.querySelector('.simulation-strip');if(!anchor)return;panel=document.createElement('section');panel.id='v606-live';panel.className='panel';panel.style.margin='14px 0';anchor.insertAdjacentElement('afterend',panel);}
 const rows=state.live_products||Object.entries(state.products).map(([sku,p])=>({sku,...p,transactions:state.ledger.filter(t=>t.sku===sku).length}));
 const oldPolicy=typeof meta!=='undefined'&&meta&&state.model_version!==meta.model;
 panel.innerHTML=(oldPolicy?'<div class="notice pink"><b>Ca này dùng kế hoạch cũ trước bản sửa giữ hàng đến 21:30.</b> Giao dịch cũ được giữ nguyên để đối chiếu. <button data-new>Tạo ca mới với kế hoạch đã sửa</button></div>':'')+'<div class="panel-head"><div><h2>Bán hàng trực tiếp theo từng sản phẩm</h2><p>Đồng hồ '+hour(state.minute)+' · revision '+state.revision+' · '+state.ledger.length+' dòng giao dịch. Số bán lũy kế khác số bán trong 30/60 phút gần nhất.</p></div></div>'+
 '<div class="table-scroll"><table><thead><tr><th>Sản phẩm</th><th>Đã chuẩn bị</th><th>Đã bán từ mở cửa</th><th>Tồn hiện tại</th><th>Bán 30 phút</th><th>Bán 60 phút</th><th>Doanh thu</th></tr></thead><tbody>'+
 rows.map(r=>'<tr data-live-sku="'+esc(r.sku)+'"><td>'+esc(r.name)+'<small style="display:block">'+esc(r.sku)+'</small></td><td>'+r.prepared+'</td><td data-live-sold>'+r.sold+'</td><td data-live-stock>'+r.stock+'</td><td>'+String(r.sales30??'—')+'</td><td>'+String(r.sales60??'—')+'</td><td>'+money(r.revenue)+'</td></tr>').join('')+
 '</tbody></table></div>'+(rows.length?'':'<p class="notice">Chưa xác nhận đã chuẩn bị; chưa có hàng thực tế để ghi nhận bán.</p>');
}
setInterval(renderLiveSales,1000);
