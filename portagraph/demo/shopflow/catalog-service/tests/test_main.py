from fastapi.testclient import TestClient

from app.main import app


def test_products_list():
    client = TestClient(app)
    assert client.get("/api/v1/products").status_code == 200
