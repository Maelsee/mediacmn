from fastapi.testclient import TestClient
from main import create_app


def _client():
    app = create_app()
    return TestClient(app)


def test_openapi_json_has_info_and_security():
    client = _client()
    resp = client.get("/api/openapi.json")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    assert data.get("info", {}).get("title")
    comp = data.get("components", {})
    sec = comp.get("securitySchemes", {})
    assert "BearerAuth" in sec
    assert data.get("security") == [{"BearerAuth": []}]


def test_swagger_ui_docs_available():
    client = _client()
    resp = client.get("/api/docs")
    assert resp.status_code == 200
    ctype = resp.headers.get("content-type", "")
    assert "text/html" in ctype


def test_redoc_available():
    client = _client()
    resp = client.get("/api/redoc")
    assert resp.status_code == 200
    ctype = resp.headers.get("content-type", "")
    assert "text/html" in ctype
