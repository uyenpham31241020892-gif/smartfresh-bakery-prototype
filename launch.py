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
 # A local listener is not assumed to belong to this app. Never kill processes automatically.
 import socket
 with socket.socket() as sock:
  if sock.connect_ex(('127.0.0.1',8000))==0:raise RuntimeError('Port 8000 dang duoc su dung. Dong cua so SmartFresh cu hoac dung port khac bang uvicorn.')
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
  proc=subprocess.Popen([str(py),'-m','uvicorn','app:app','--host','127.0.0.1','--port','8000','--workers','1'],stdout=log,stderr=log)
  print('Dang khoi dong server, xem runtime/server.log neu co loi...',flush=True)
  for _ in range(120):
   if proc.poll() is not None:raise RuntimeError('Server dung. Xem runtime/server.log')
   try:
    with urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=1) as r:
     if json.load(r).get('ok'):break
   except Exception:time.sleep(.5)
  else:
   proc.terminate();raise RuntimeError('Health check khong dat. Xem runtime/server.log')
  print('SmartFresh V4: http://127.0.0.1:8000 - dong cua so/Ctrl+C de dung.',flush=True);webbrowser.open('http://127.0.0.1:8000')
  try:proc.wait()
  except KeyboardInterrupt:proc.terminate();proc.wait()
except Exception as e:print('LOI:',e);sys.exit(1)
