import io
import zipfile
import httpx

URL = 'https://github.com/ollama/ollama/releases/download/v0.40.6/ollama-windows-amd64.zip'


class RemoteZip(io.RawIOBase):
    def __init__(self, url=URL):
        self.client = httpx.Client(follow_redirects=True, timeout=120)
        response = self.client.head(url)
        response.raise_for_status()
        self.url = str(response.url)
        self.size = int(response.headers['content-length'])
        self.pos = 0

    def seek(self, offset, whence=0):
        self.pos = offset if whence == 0 else self.pos + offset if whence == 1 else self.size + offset
        return self.pos

    def tell(self):
        return self.pos

    def read(self, size=-1):
        end = self.size - 1 if size < 0 else min(self.pos + size, self.size) - 1
        if end < self.pos:
            return b''
        response = self.client.get(self.url, headers={'Range': f'bytes={self.pos}-{end}'})
        response.raise_for_status()
        if response.status_code != 206 or len(response.content) != end - self.pos + 1:
            raise ValueError('Unexpected range response')
        self.pos = end + 1
        return response.content


if __name__ == '__main__':
    with zipfile.ZipFile(RemoteZip()) as bundle:
        for info in bundle.infolist():
            print(info.filename, info.compress_size)
