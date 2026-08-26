from starlette.testclient import TestClient

from mcp_abfall import server


def test_healthcheck() -> None:
    app = server.mcp.streamable_http_app(stateless_http=True, host="0.0.0.0")

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


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
