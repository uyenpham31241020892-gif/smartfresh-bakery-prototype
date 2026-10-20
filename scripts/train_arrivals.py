import json
from services.arrivals import train
if __name__=='__main__':
    print(json.dumps(train(),ensure_ascii=False,indent=2))
