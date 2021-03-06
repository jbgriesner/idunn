from apistar import TestClient

from app import app


def test_v1_metrics_ok():
    client = TestClient(app)
    response = client.get("http://localhost/v1/metrics")

    assert response.status_code == 200

    assert b'apistar_prometheus.handlers.expose_metrics' in response.content
