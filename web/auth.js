let authUser=null;
async function ensureLogin(){
  const status=await fetch('/api/auth/status').then(r=>r.json());
  if(status.user){authUser=status.user;showIdentity();return true;}
  const box=document.createElement('div');box.id='auth-overlay';box.className='auth-overlay';
  box.innerHTML='<form id="auth-form" class="auth-card"><div class="eyebrow">SMARTFRESH</div><h2>Đăng nhập</h2><label class="field">Tài khoản<input name="username" autocomplete="username" minlength="3" maxlength="40" required></label><label class="field">Mật khẩu<input name="password" type="password" autocomplete="current-password" minlength="8" maxlength="128" required></label><p id="auth-error" role="alert"></p><button class="primary" type="submit">Đăng nhập</button><button type="button" id="staff-register" class="ghost">Đăng ký nhân viên</button></form>';
  let registerStaff=false;
  box.querySelector('#staff-register').onclick=()=>{registerStaff=!registerStaff;box.querySelector('h2').textContent=registerStaff?'Đăng ký nhân viên':'Đăng nhập';box.querySelector('[type="submit"]').textContent=registerStaff?'Tạo tài khoản nhân viên':'Đăng nhập';};
  document.body.appendChild(box);
  return await new Promise(resolve=>{
    box.querySelector('form').onsubmit=async e=>{
      e.preventDefault();const form=e.target,b=form.querySelector('button');b.disabled=true;
      try{
        const r=await fetch('/api/auth/'+(registerStaff?'setup':'login'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:form.elements.namedItem('username').value.trim(),password:form.elements.namedItem('password').value})});
        const result=await r.json();if(!r.ok)throw Error(result.error||'Không đăng nhập được.');
        authUser=result.user;box.remove();showIdentity();resolve(true);
      }catch(err){box.querySelector('#auth-error').textContent=err.message;}finally{b.disabled=false;}
    };
  });
}
function showIdentity(){
 const el=document.querySelector('.sidebar-bottom .user');
 if(el&&authUser){el.querySelector('strong').textContent=authUser.username;el.querySelector('small').textContent={manager:'Manager · có quyền duyệt',staff:'Staff · vận hành',viewer:'Viewer · chỉ xem'}[authUser.role];el.title='Nhấn để đăng xuất';el.style.cursor='pointer';el.onclick=async()=>{if(confirm('Đăng xuất tài khoản '+authUser.username+'?')){await fetch('/api/auth/logout',{method:'POST'});location.reload();}};}
}
function applyPermissions(){
 if(!authUser)return;
 if(authUser.role!=='manager')document.querySelectorAll('[data-approve],[data-reject],[data-qty],[data-discount],[data-safety-post],[data-incident],[data-user-create],#learning-upload,#learning-train,#learning-demo,[data-promote],[data-rollback-model],#settings-form input,#settings-form select,#settings-form button').forEach(b=>{b.disabled=true;b.title='Cần đăng nhập tài khoản Manager';});
 if(authUser.role!=='manager'&&currentView==='learning')document.querySelectorAll('#view form input,#view form select,#view form button').forEach(b=>b.disabled=true);
 if(authUser.role==='viewer')document.querySelectorAll('#new-session,#upload-shortcut,#file-input,[data-act],[data-advance],[data-play],[data-confirm-import],[data-quality-verify],[data-confirm-zero],[data-fork-simulation],[data-next-day]').forEach(b=>{b.disabled=true;b.title='Viewer chỉ được xem';});
}
