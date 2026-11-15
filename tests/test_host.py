from trustrag.webapp import resolve_host


def test_local_runs_stay_on_localhost(monkeypatch):
    monkeypatch.delenv("HOST", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    assert resolve_host() == "127.0.0.1"


def test_hosting_platform_port_binds_publicly(monkeypatch):
    """Render/Heroku set PORT but not HOST: binding to localhost there means 'no open ports detected'."""
    monkeypatch.delenv("HOST", raising=False)
    monkeypatch.setenv("PORT", "10000")
    assert resolve_host() == "0.0.0.0"


def test_explicit_host_always_wins(monkeypatch):
    monkeypatch.setenv("PORT", "10000")
    monkeypatch.setenv("HOST", "127.0.0.1")
    assert resolve_host() == "127.0.0.1"
