"""Persist the verified local provider/model, never password or API credentials."""
from pathlib import Path
import getpass,re,httpx

def main():
    root=Path(__file__).resolve().parents[1]
    username=input('Tai khoan SmartFresh: ').strip();password=getpass.getpass('Mat khau (khong luu): ')
    with httpx.Client(base_url='http://127.0.0.1:8000',timeout=10) as client:
        r=client.post('/api/auth/login',json={'username':username,'password':password});r.raise_for_status()
        status=client.get('/api/metadata').json()['ai'];client.post('/api/auth/logout')
    if status['provider']!='Ollama' or not status['verified']:raise ValueError('Kiem tra ket noi Ollama trong Cai dat AI truoc.')
    p=root/'.env';text=p.read_text(encoding='utf-8-sig') if p.exists() else ''
    for key,value in [('AI_PROVIDER','Ollama'),('OLLAMA_MODEL',status['model'])]:
        pattern=r'(?m)^'+key+r'=.*$';line=key+'='+value
        text=re.sub(pattern,line,text) if re.search(pattern,text) else text.rstrip()+'\n'+line+'\n'
    p.write_text(text.lstrip('\n'),encoding='utf-8');print('Da luu provider/model local; khong luu thong tin dang nhap.')
if __name__=='__main__':main()
