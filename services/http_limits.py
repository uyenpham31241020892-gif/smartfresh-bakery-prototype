"""Bound buffered unsafe request bodies, including chunked requests."""
from starlette.responses import JSONResponse
MAX_REQUEST_BYTES=25*1024*1024
class BodySizeLimit:
    def __init__(self,app,max_bytes=MAX_REQUEST_BYTES):self.app,self.max_bytes=app,max_bytes
    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or scope['method'] in ['GET','HEAD','OPTIONS']:
            return await self.app(scope,receive,send)
        headers=dict(scope.get('headers',[]));length=headers.get(b'content-length')
        try:declared=int(length) if length else 0
        except ValueError:declared=self.max_bytes+1
        if declared>self.max_bytes or declared<0:
            return await JSONResponse({'error':'Yêu cầu vượt giới hạn dung lượng.','code':'PAYLOAD_TOO_LARGE'},status_code=413)(scope,receive,send)
        chunks=[];size=0
        while True:
            msg=await receive()
            if msg['type']=='http.disconnect':return
            size+=len(msg.get('body',b''))
            if size>self.max_bytes:
                return await JSONResponse({'error':'Yêu cầu vượt giới hạn dung lượng.','code':'PAYLOAD_TOO_LARGE'},status_code=413)(scope,receive,send)
            chunks.append(msg)
            if not msg.get('more_body',False):break
        index=0
        async def replay():
            nonlocal index
            if index<len(chunks):value=chunks[index];index+=1;return value
            return await receive()
        await self.app(scope,replay,send)
