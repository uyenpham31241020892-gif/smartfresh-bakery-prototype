#!/usr/bin/env python3
from pathlib import Path
import runpy, sys
script = Path(__file__).resolve().parents[1] / 'Test_SmartFresh v9' / 'run_v9.py'
sys.path.insert(0, str(script.parent))
runpy.run_path(str(script), run_name='__main__')
