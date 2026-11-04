import importlib.metadata as m,sys
assert sys.version_info[0]==3, "Use Python 3"
assert m.version("scikit-learn")=="1.9.1", "scikit-learn 1.9.1 required"
import pandas,scipy,httpx,uvicorn,openpyxl,multipart,numpy,joblib
print("V4 runtime OK")
