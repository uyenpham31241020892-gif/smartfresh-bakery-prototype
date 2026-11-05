function renderLiveSales(){
 if(typeof state==='undefined'||!state)return;
 document.querySelectorAll('[data-simulator-report]').forEach(b=>b.textContent='Nguồn mô phỏng');
 let panel=document.getElementById('v4-live');
 if(!panel){const anchor=document.querySelector('.simulation-strip');if(!anchor)return;panel=document.createElement('section');panel.id='v4-live';panel.className='panel';panel.style.margin='14px 0';anchor.insertAdjacentElement('afterend',panel);}
 const rows=state.live_products||Object.entries(state.products).map(([sku,p])=>({sku,...p,transactions:state.ledger.filter(t=>t.sku===sku).length}));
 panel.innerHTML='<div class="panel-head"><div><h2>Bán hàng trực tiếp theo từng sản phẩm</h2><p>Đồng hồ '+hour(state.minute)+' · revision '+state.revision+' · '+state.ledger.length+' dòng giao dịch. Số bán lũy kế khác số bán trong 30/60 phút gần nhất.</p></div></div>'+
 '<div class="table-scroll"><table><thead><tr><th>Sản phẩm</th><th>Đã chuẩn bị</th><th>Đã bán từ mở cửa</th><th>Tồn hiện tại</th><th>Bán 30 phút</th><th>Bán 60 phút</th><th>Doanh thu</th></tr></thead><tbody>'+
 rows.map(r=>'<tr data-live-sku="'+esc(r.sku)+'"><td>'+esc(r.name)+'<small style="display:block">'+esc(r.sku)+'</small></td><td>'+r.prepared+'</td><td data-live-sold>'+r.sold+'</td><td data-live-stock>'+r.stock+'</td><td>'+String(r.sales30??'—')+'</td><td>'+String(r.sales60??'—')+'</td><td>'+money(r.revenue)+'</td></tr>').join('')+
 '</tbody></table></div>'+(rows.length?'':'<p class="notice">Chưa xác nhận đã chuẩn bị; chưa có hàng thực tế để ghi nhận bán.</p>');
}
setInterval(renderLiveSales,1000);
