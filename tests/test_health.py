def test_livez(client):
    response = client.get("/livez")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_readyz(client):
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_health_reports_service_configuration(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["services_configured"] == {
        "auth": True,
        "parking": True,
        "payment": True,
        "booking": False,
    }
    # RabbitMQ isn't reachable in the test environment; the gateway must
    # still boot and answer instead of crashing on a broker outage.
    assert body["rabbitmq"] == "disconnected"
