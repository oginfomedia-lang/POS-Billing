"""Health endpoint and error format tests (pass with or without the test database)."""


def test_health_reports_database_status(client):
    response = client.get("/api/v1/health")

    assert response.status_code in (200, 503)
    body = response.get_json()
    assert body["database"] in ("up", "down")
    assert body["status"] == ("ok" if body["database"] == "up" else "degraded")
    assert "server_time" in body


def test_unknown_route_returns_json_error(client):
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "NOT_FOUND"
