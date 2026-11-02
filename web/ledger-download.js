// Fetch authenticated CSV explicitly and trigger a real file download.
document.addEventListener('click',async event=>{
 const link=event.target.closest('a[href^="/api/export/"]');if(!link)return;
 event.preventDefault();event.stopImmediatePropagation();
 if(link.dataset.downloading==='1')return;
 link.dataset.downloading='1';link.setAttribute('aria-busy','true');
 try{
 const response=await fetch(link.getAttribute('href'),{credentials:'same-origin',headers:{Accept:'text/csv'}});
 if(!response.ok){const error=await response.json().catch(()=>({}));throw Error(error.error||'Không tải được sổ giao dịch (HTTP '+response.status+').');}
 if(!(response.headers.get('content-type')||'').includes('text/csv'))throw Error('Máy chủ chưa trả file CSV. Vui lòng đăng nhập lại.');
 const blob=await response.blob();const disposition=response.headers.get('content-disposition')||'';
 const match=disposition.match(/filename="?([^";]+)"?/i);
 const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=match?match[1]:'SmartFresh_So_Giao_Dich.csv';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1500);
 toast('Đã gửi file CSV tới trình duyệt. Kiểm tra mục Tải xuống.');
 }catch(error){toast(error.message,true)}finally{delete link.dataset.downloading;link.removeAttribute('aria-busy');}
},true);
