from fastapi.testclient import TestClient

from backend.main import app


def test_health_returns_ok():
    with TestClient(app) as client:
        res = client.get("/health")

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["model"]
    assert "X-Process-Time" in res.headers


def test_cors_allows_vite_origin():
    with TestClient(app) as client:
        res = client.get("/health", headers={"Origin": "http://localhost:5173"})

    assert res.headers["access-control-allow-origin"] == "http://localhost:5173"
