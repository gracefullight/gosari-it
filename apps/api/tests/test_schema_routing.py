"""Built-in API schema remains reachable when the SPA is installed."""

from litestar.testing import TestClient

from gosari.app import SPAStaticMiddleware, create_app


def test_schema_bypasses_spa_without_claiming_similar_paths(tmp_path, monkeypatch):
    index = '<html><div id="root">fixture</div></html>'
    (tmp_path / "index.html").write_text(index)
    monkeypatch.setattr("gosari.app.open_pool", lambda settings: None)
    monkeypatch.setattr("gosari.app.close_pool", lambda: None)
    app = create_app()
    app.asgi_handler = SPAStaticMiddleware(app.asgi_handler, tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        schema = client.get("/schema/openapi.json")
        assert schema.status_code == 200
        assert schema.headers["content-type"].split(";")[0] in (
            "application/json",
            "application/vnd.oai.openapi+json",
        )
        assert "/api/v1/analysis/chat" in schema.json()["paths"]
        assert "text/html" in client.get("/schema").headers["content-type"]
        assert client.get("/notebook").text == index
        assert client.get("/schema-unrelated").text == index
