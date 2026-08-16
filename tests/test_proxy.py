from tests.conftest import make_access_token


def test_public_route_forwards_without_auth(client):
    calls, script, _ = client._mock_calls, client._mock_script, None
    response = client.get("/parking-spots/search?lat=1&lng=2")

    assert response.status_code == 200
    assert len(calls) == 1
    forwarded = calls[0]
    assert forwarded.url.host == "parking-service.test"
    assert forwarded.url.path == "/parking-spots/search"
    assert dict(forwarded.url.params) == {"lat": "1", "lng": "2"}
    assert "x-user-id" not in forwarded.headers


def test_protected_route_without_token_is_rejected(client):
    response = client.get("/users/11111111-1111-1111-1111-111111111111")

    assert response.status_code == 401
    assert client._mock_calls == []


def test_protected_route_with_valid_token_forwards_and_injects_user_id(client):
    user_id = "22222222-2222-2222-2222-222222222222"
    token = make_access_token(user_id=user_id)

    response = client.get(
        f"/users/{user_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    forwarded = client._mock_calls[0]
    assert forwarded.headers["x-user-id"] == user_id
    assert forwarded.headers["authorization"] == f"Bearer {token}"


def test_protected_route_with_garbage_token_is_rejected(client):
    response = client.get(
        "/users/11111111-1111-1111-1111-111111111111",
        headers={"Authorization": "Bearer not-a-real-token"},
    )

    assert response.status_code == 401
    assert client._mock_calls == []


def test_unconfigured_service_returns_503_without_calling_out(client):
    response = client.get("/bookings/some-id", headers={"Authorization": f"Bearer {make_access_token()}"})

    assert response.status_code == 503
    assert client._mock_calls == []


def test_payment_route_rewrites_path_prefix(client):
    token = make_access_token()
    response = client.post(
        "/payments/create-preference",
        json={"amount": 1000},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    forwarded = client._mock_calls[0]
    assert forwarded.url.host == "payment-service.test"
    assert forwarded.url.path == "/api/payments/create-preference"


def test_payment_webhook_is_public(client):
    response = client.post("/payments/webhook", json={"type": "payment"})

    assert response.status_code == 200
    forwarded = client._mock_calls[0]
    assert forwarded.url.path == "/api/payments/webhook"


def test_booking_owned_subresource_routes_to_booking_not_parking(client):
    # /parking-spots/{id}/availability belongs to booking-service per its
    # README, even though the prefix is /parking-spots. booking-service isn't
    # configured in tests, so this must 503 rather than hit parking-service.
    response = client.get("/parking-spots/some-spot/availability")

    assert response.status_code == 503
    assert client._mock_calls == []


def test_parking_spot_detail_still_routes_to_parking(client):
    response = client.get("/parking-spots/some-spot")

    assert response.status_code == 200
    forwarded = client._mock_calls[0]
    assert forwarded.url.host == "parking-service.test"
    assert forwarded.url.path == "/parking-spots/some-spot"
