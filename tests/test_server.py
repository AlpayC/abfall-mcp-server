from starlette.testclient import TestClient

from abfall_mcp_server import __version__, server


def test_healthcheck() -> None:
    app = server.mcp.streamable_http_app(stateless_http=True, host="0.0.0.0")

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    # Gegen __version__ pruefen, nicht gegen eine feste Zahl: der Test soll
    # die Form der Antwort sichern und nicht bei jedem Release brechen.
    assert response.json() == {"status": "ok", "version": __version__}


def test_landingpages_and_assets(monkeypatch, tmp_path) -> None:
    (tmp_path / "en").mkdir()
    (tmp_path / "_next" / "static").mkdir(parents=True)
    (tmp_path / "index.html").write_text("<h1>Abfall MCP</h1>", encoding="utf-8")
    (tmp_path / "en" / "index.html").write_text("<h1>Waste MCP</h1>", encoding="utf-8")
    (tmp_path / "_next" / "static" / "app.css").write_text("body{}", encoding="utf-8")
    monkeypatch.setenv("ABFALL_MCP_WEB_DIR", str(tmp_path))
    app = server.mcp.streamable_http_app(stateless_http=True, host="0.0.0.0")

    with TestClient(app) as client:
        deutsch = client.get("/")
        englisch = client.get("/en/")
        asset = client.get("/_next/static/app.css")
        fehlt = client.get("/_next/static/fehlt.css")

    assert deutsch.status_code == 200
    assert "Abfall MCP" in deutsch.text
    assert englisch.status_code == 200
    assert "Waste MCP" in englisch.text
    assert asset.status_code == 200
    assert asset.text == "body{}"
    assert fehlt.status_code == 404


def test_http_start_uses_stateless_transport(monkeypatch) -> None:
    aufruf = {}
    monkeypatch.setattr(server.registry, "load", list)
    monkeypatch.setattr(
        server.mcp,
        "run",
        lambda transport, **kwargs: aufruf.update(transport=transport, **kwargs),
    )

    assert server.main(["--http", "--host", "0.0.0.0", "--port", "8123"]) == 0
    assert aufruf == {
        "transport": "streamable-http",
        "host": "0.0.0.0",
        "port": 8123,
        "json_response": True,
        "stateless_http": True,
    }
