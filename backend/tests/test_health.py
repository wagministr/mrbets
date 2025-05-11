"""
Test health endpoint.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint():
    """Test that health endpoint returns correct status and version."""
    response = client.get("/health")
    assert response.status_code == 200

    json = response.json()
    assert json["status"] == "ok"
    assert json["version"] == "1.0.0"
