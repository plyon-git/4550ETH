from pathlib import Path
import sys,socket
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bootstrap_engine import build
build()
@pytest.fixture(autouse=True)
def prohibit_external_network(monkeypatch):
    def fail(*args,**kwargs):raise AssertionError('unit tests must not access an exchange or network')
    monkeypatch.setattr(socket,'create_connection',fail)
