"""Persist only non-secret local defaults after a successful live connection."""
from pathlib import Path
import re
import httpx

root = Path(__file__).resolve().parents[1]
status = httpx.get('http://127.0.0.1:8000/api/health').json()['ai']
if status['provider'] != 'Ollama' or not status['verified']:
    raise RuntimeError('Verify Ollama before selecting the local default.')
p = root / '.env'
text = p.read_text(encoding='utf-8-sig') if p.exists() else ''
for key, value in [('AI_PROVIDER', 'Ollama'), ('OLLAMA_MODEL', 'qwen3.5:4b')]:
    pattern = r'(?m)^' + key + r'=.*$'
    line = key + '=' + value
    text = re.sub(pattern, line, text) if re.search(pattern, text) else text.rstrip() + '\n' + line + '\n'
p.write_text(text.lstrip('\n'), encoding='utf-8')
print('Local default saved; no API credentials were written.')
