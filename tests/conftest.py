import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from services.engine import Engine
from services.simulator import Simulator
from services.store import Store
from services.workflow import Workflow

@pytest.fixture(autouse=True)
def isolate_provider_selection(monkeypatch):
    # Unit tests must not select a real provider from the user's local .env.
    monkeypatch.setenv('AI_PROVIDER', 'OpenAI')

@pytest.fixture(scope='session')
def engine():
    return Engine()

@pytest.fixture(scope='session')
def simulator(engine):
    return Simulator(engine)

@pytest.fixture
def flow(engine, simulator, tmp_path):
    return Workflow(engine, simulator, Store(tmp_path / 'test.sqlite3'))
