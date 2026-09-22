import pytest,socket
@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*a,**k):raise AssertionError('Tests may not connect to any exchange or external network')
    monkeypatch.setattr(socket,'create_connection',blocked)
