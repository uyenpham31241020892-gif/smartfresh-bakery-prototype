"""Windows launcher; stdlib only, own environment, wait for health before browser."""
from pathlib import Path
import sys,subprocess,hashlib,time,urllib.request,webbrowser,os,json
if sys.version_info[0] < 3:raise SystemExit('Can Python 3. Dung Start.cmd / Start-Gemini.cmd.')
R=Path(__file__).resolve().parent;os.chdir(R);runtime=R/'runtime';runtime.mkdir(exist_ok=True)
check_sys=subprocess.run([sys.executable,str(R/'scripts/check_runtime.py')],capture_output=True)
if check_sys.returncode==0:
 py=sys.executable
else:
 py=R/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python');stamp=R/'.venv/requirements.sha256';digest=hashlib.sha256((R/'requirements.txt').read_bytes()).hexdigest()
 try:
  if not Path(py).exists():subprocess.run([sys.executable,'-m','venv',str(R/'.venv')],check=True)
  check=subprocess.run([str(py),str(R/'scripts/check_runtime.py')],capture_output=True)
  if check.returncode or not stamp.exists() or stamp.read_text()!=digest:
   subprocess.run([str(py),'-m','pip','install','-r','requirements.txt'],check=True);stamp.write_text(digest)
 except Exception as e:print('Loi tao venv:',e);sys.exit(1)
try:
 # Determine an available port automatically — never crash because port 8000 is busy.
 import socket
 def _find_free_port(start=int(os.environ.get('SMARTFRESH_PORT','8000')),end=8010):
  # Check if port is already used by an old SmartFresh uvicorn process and terminate it cleanly
  if os.name=='nt':
   try:
    chk=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    if chk.connect_ex(('127.0.0.1',start))==0:
     chk.close()
     out=subprocess.check_output(f'powershell -NoProfile -Command "(Get-NetTCPConnection -LocalPort {start} -ErrorAction SilentlyContinue).OwningProcess"',shell=True,text=True).strip()
     if out and out.isdigit():
      pid=int(out)
      cmdline=subprocess.check_output(f'powershell -NoProfile -Command "(Get-CimInstance Win32_Process -Filter \\"ProcessId = {pid}\\").CommandLine"',shell=True,text=True)
      if 'uvicorn' in cmdline.lower() and 'app:app' in cmdline.lower():
       print(f'Phat hien tien trinh SmartFresh cu (PID {pid}) tren port {start}, dang giai phong...')
       subprocess.run(f'taskkill /F /PID {pid}',shell=True,capture_output=True)
       time.sleep(1)
    else:chk.close()
   except Exception:pass
  for p in range(start,end+1):
   with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as s:
    if s.connect_ex(('127.0.0.1',p))!=0:return p
  raise RuntimeError(f'Khong tim duoc port trong khoang {start}-{end}')
 PORT=_find_free_port()
 # Reuse an existing optional Ollama installation only when that provider is selected.
 provider=os.environ.get('AI_PROVIDER','')
 if not provider and (R/'.env').exists():
  for line in (R/'.env').read_text(encoding='utf-8-sig').splitlines():
   if line.strip().startswith('AI_PROVIDER='):provider=line.split('=',1)[1].strip().strip('"').strip("'")
 local_exe=R/'.tools/ollama/ollama.exe'
 if os.name=='nt' and provider=='Ollama' and local_exe.is_file():
  with socket.socket() as sock:local_running=sock.connect_ex(('127.0.0.1',11434))==0
  if not local_running:
   ollama_env=os.environ.copy();ollama_env.update(OLLAMA_HOST='127.0.0.1:11434',OLLAMA_MODELS=str(runtime/'ollama-models'),OLLAMA_NO_CLOUD='1')
   with open(runtime/'ollama.log','a',encoding='utf-8') as ollama_log:
    subprocess.Popen([str(local_exe),'serve'],env=ollama_env,stdout=ollama_log,stderr=ollama_log,creationflags=subprocess.CREATE_NO_WINDOW)
 with open(runtime/'server.log','w',encoding='utf8') as log:
  proc=subprocess.Popen([str(py),'-m','uvicorn','app:app','--host','127.0.0.1','--port',str(PORT),'--workers','1'],stdout=log,stderr=log)
  print(f'Dang khoi dong server tren port {PORT}, xem runtime/server.log neu co loi...',flush=True)
  for _ in range(120):
   if proc.poll() is not None:raise RuntimeError('Server dung. Xem runtime/server.log')
   try:
    with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/api/health',timeout=1) as r:
     if json.load(r).get('ok'):break
   except Exception:time.sleep(.5)
  else:
   proc.terminate();raise RuntimeError('Health check khong dat. Xem runtime/server.log')
  print(f'SmartFresh V4: http://127.0.0.1:{PORT} - dong cua so/Ctrl+C de dung.',flush=True);webbrowser.open(f'http://127.0.0.1:{PORT}')
  try:proc.wait()
  except KeyboardInterrupt:proc.terminate();proc.wait()
except Exception as e:print('LOI:',e);sys.exit(1)
