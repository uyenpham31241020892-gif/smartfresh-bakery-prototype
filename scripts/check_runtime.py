import importlib.metadata as m,sys
assert sys.version_info[:2]==(3,12), "Use Python 3.12"
for k,v in {"scikit-learn":"1.9.1","joblib":"1.6.0","fastapi":"0.116.1","numpy":"2.3.5"}.items():
 assert m.version(k)==v,k+" version mismatch"
import pandas,scipy,httpx,uvicorn,openpyxl,multipart
print("V4 runtime OK")
