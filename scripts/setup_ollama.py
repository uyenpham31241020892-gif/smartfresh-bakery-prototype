"""Install the official portable Ollama CLI inside this workspace and pull a model."""
from pathlib import Path
import os
import subprocess
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
import httpx

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / '.tools' / 'ollama'
MODEL = 'qwen3.5:4b'


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    exe = DEST / 'ollama.exe'
    with httpx.Client(follow_redirects=True, timeout=120) as client:
        if not (DEST / 'installed.txt').exists():
            from scripts.inspect_ollama_zip import RemoteZip
            release = client.get('https://api.github.com/repos/ollama/ollama/releases/latest')
            release.raise_for_status()
            asset = next(a for a in release.json()['assets'] if a['name'] == 'ollama-windows-amd64.zip')
            print('Downloading official Ollama', release.json()['tag_name'], flush=True)
            print('Installing CPU + Vulkan backend (NVIDIA/AMD); skipping large CUDA bundles.', flush=True)
            with zipfile.ZipFile(RemoteZip(asset['browser_download_url'])) as bundle:
                members = bundle.infolist()
            def extract(member):
                if '/cuda_' in member.filename or member.is_dir():
                    return
                if not (DEST / member.filename).resolve().is_relative_to(DEST.resolve()):
                    raise ValueError('Unsafe archive path')
                target = DEST / member.filename
                if target.exists() and target.stat().st_size == member.file_size:
                    import zlib
                    if zlib.crc32(target.read_bytes()) == member.CRC:
                        return
                print('Extracting', member.filename, flush=True)
                with zipfile.ZipFile(RemoteZip(asset['browser_download_url'])) as part:
                    part.extract(member, DEST)
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(extract, members))
            print('Portable executable extracted.', flush=True)
            (DEST / 'installed.txt').write_text(release.json()['tag_name'], encoding='utf-8')
        env = os.environ.copy()
        env.update(OLLAMA_HOST='127.0.0.1:11434', OLLAMA_MODELS=str(ROOT / 'runtime' / 'ollama-models'), OLLAMA_NO_CLOUD='1')
        try:
            client.get('http://127.0.0.1:11434/api/version').raise_for_status()
        except httpx.RequestError:
            subprocess.Popen([str(exe), 'serve'], env=env, creationflags=subprocess.CREATE_NO_WINDOW,
                             stdout=(DEST / 'server.log').open('ab'), stderr=subprocess.STDOUT)
            for _ in range(30):
                try:
                    client.get('http://127.0.0.1:11434/api/version').raise_for_status()
                    break
                except httpx.RequestError:
                    time.sleep(1)
        print('Pulling model', MODEL, flush=True)
        with client.stream('POST', 'http://127.0.0.1:11434/api/pull', json={'model': MODEL}, timeout=300) as response:
            import json
            response.raise_for_status()
            last = None
            for line in response.iter_lines():
                item = json.loads(line)
                if item.get('error'):
                    raise ValueError(item['error'])
                progress = (item.get('status'), int(100 * item.get('completed', 0) / max(item.get('total', 1), 1)) // 10)
                if progress != last:
                    print(progress, flush=True)
                    last = progress
    print('Ollama ready at 127.0.0.1:11434; select Ollama in AI settings.', flush=True)


if __name__ == '__main__':
    main()
