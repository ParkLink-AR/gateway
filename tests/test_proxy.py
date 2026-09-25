from tests.conftest import make_access_token


def test_public_route_forwards_without_auth(client):
    calls = client._mock_calls
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


def test_payment_redirect_is_public(client):
    response = client.get("/payments/redirect?status=approved")

    assert response.status_code == 200
    forwarded = client._mock_calls[0]
    assert forwarded.url.path == "/api/payments/redirect"


def test_availability_subresource_routes_to_parking_not_booking(client):
    # /parking-spots/{id}/availability belongs to parking-service -- it owns
    # the spot's published schedule and calls booking-service itself for
    # active bookings, rather than the gateway routing this to booking-service
    # directly (that's how it used to work; booking-service dropped the
    # endpoint once parking-service took over computing availability).
    response = client.get("/parking-spots/some-spot/availability")

    assert response.status_code == 200
    forwarded = client._mock_calls[0]
    assert forwarded.url.host == "parking-service.test"
    assert forwarded.url.path == "/parking-spots/some-spot/availability"


def test_parking_spot_detail_still_routes_to_parking(client):
    response = client.get("/parking-spots/some-spot")

    assert response.status_code == 200
    forwarded = client._mock_calls[0]
    assert forwarded.url.host == "parking-service.test"
    assert forwarded.url.path == "/parking-spots/some-spot"


def test_parking_spots_batch_route_forwards_without_auth(client):
    calls = client._mock_calls
    response = client.get("/parking-spots?ids=11111111-1111-1111-1111-111111111111,22222222-2222-2222-2222-222222222222")

    assert response.status_code == 200
    assert len(calls) == 1
    forwarded = calls[0]
    assert forwarded.url.host == "parking-service.test"
    assert forwarded.url.path == "/parking-spots"
    assert dict(forwarded.url.params) == {
        "ids": "11111111-1111-1111-1111-111111111111,22222222-2222-2222-2222-222222222222"
    }
    assert "x-user-id" not in forwarded.headers


def test_bookings_verify_code_requires_auth_then_hits_unconfigured_booking_service(client):
    # booking-service has no mock host in this suite (BOOKING_SERVICE_URL is left
    # unconfigured on purpose, see conftest.py and test_unconfigured_service_returns_503_
    # without_calling_out above) -- so the strongest assertion available here is that a
    # valid token gets *past* auth for this route (503, not 401) with no upstream call
    # made, same as every other booking-service route in this suite.
    token = make_access_token(user_id="55555555-5555-5555-5555-555555555555")

    response = client.post(
        "/bookings/some-booking-id/verify-code",
        json={"code": "9542"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 503
    assert client._mock_calls == []


def test_bookings_verify_code_without_token_is_rejected(client):
    response = client.post("/bookings/some-booking-id/verify-code", json={"code": "9542"})

    assert response.status_code == 401
    assert client._mock_calls == []


def test_notifications_token_register_requires_auth_and_forwards(client):
    token = make_access_token(user_id="33333333-3333-3333-3333-333333333333")
    response = client.put(
        "/notifications/tokens",
        json={"token": "fcm-abc", "platform": "android"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    forwarded = client._mock_calls[0]
    assert forwarded.url.host == "notifications-service.test"
    assert forwarded.url.path == "/notifications/tokens"
    assert forwarded.headers["x-user-id"] == "33333333-3333-3333-3333-333333333333"


def test_notifications_token_register_without_token_is_rejected(client):
    response = client.put(
        "/notifications/tokens", json={"token": "fcm-abc", "platform": "android"}
    )

    assert response.status_code == 401
    assert client._mock_calls == []


def test_admin_tickets_route_without_token_is_rejected(client):
    response = client.get("/admin/tickets")

    assert response.status_code == 401
    assert client._mock_calls == []


def test_admin_tickets_route_with_non_admin_token_is_forbidden(client):
    token = make_access_token(user_id="66666666-6666-6666-6666-666666666666")

    response = client.get("/admin/tickets", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    assert client._mock_calls == []


def test_admin_tickets_route_with_admin_token_hits_unconfigured_booking_service(client):
    # Same reasoning as test_bookings_verify_code_requires_auth_then_hits_unconfigured_
    # booking_service above: booking-service has no mock host in this suite, so the
    # strongest assertion is that an admin token gets *past* auth (503, not 401/403).
    token = make_access_token(user_id="admin-1", role="admin")

    response = client.get("/admin/tickets", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 503
    assert client._mock_calls == []


def test_notifications_token_delete_routes_with_path_param(client):
    response = client.delete(
        "/notifications/tokens/fcm-abc",
        headers={"Authorization": f"Bearer {make_access_token()}"},
    )

    assert response.status_code == 200
    forwarded = client._mock_calls[0]
    assert forwarded.url.host == "notifications-service.test"
    assert forwarded.url.path == "/notifications/tokens/fcm-abc"


def test_payout_info_route_without_token_is_rejected(client):
    response = client.get("/users/11111111-1111-1111-1111-111111111111/payout-info")

    assert response.status_code == 401
    assert client._mock_calls == []


def test_payout_info_route_with_valid_token_forwards_and_injects_user_id(client):
    user_id = "22222222-2222-2222-2222-222222222222"
    token = make_access_token(user_id=user_id)

    response = client.get(
        f"/users/{user_id}/payout-info",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    forwarded = client._mock_calls[0]
    assert forwarded.url.host == "auth-service.test"
    assert forwarded.url.path == f"/users/{user_id}/payout-info"
    assert forwarded.headers["x-user-id"] == user_id


def test_admin_payouts_route_without_token_is_rejected(client):
    response = client.get("/admin/payouts")

    assert response.status_code == 401
    assert client._mock_calls == []


def test_admin_payouts_route_with_non_admin_token_is_forbidden(client):
    token = make_access_token(user_id="66666666-6666-6666-6666-666666666666")

    response = client.get("/admin/payouts", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    assert client._mock_calls == []


def test_admin_payouts_route_with_admin_token_hits_unconfigured_booking_service(client):
    # Same reasoning as test_admin_tickets_route_with_admin_token_hits_unconfigured_
    # booking_service above: booking-service has no mock host in this suite, so the
    # strongest assertion is that an admin token gets *past* auth (503, not 401/403).
    token = make_access_token(user_id="admin-1", role="admin")

    response = client.get("/admin/payouts", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 503
    assert client._mock_calls == []


def test_admin_payout_mark_paid_route_with_non_admin_token_is_forbidden(client):
    token = make_access_token(user_id="66666666-6666-6666-6666-666666666666")

    response = client.post(
        "/admin/payouts/some-payout-id/mark-paid",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert client._mock_calls == []


def test_admin_users_route_without_token_is_rejected(client):
    response = client.get("/admin/users")

    assert response.status_code == 401
    assert client._mock_calls == []


def test_admin_users_route_with_non_admin_token_is_forbidden(client):
    token = make_access_token(user_id="66666666-6666-6666-6666-666666666666")

    response = client.get("/admin/users", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    assert client._mock_calls == []


def test_admin_users_route_with_admin_token_forwards(client):
    token = make_access_token(user_id="admin-1", role="admin")

    response = client.get("/admin/users", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    forwarded = client._mock_calls[0]
    assert forwarded.url.host == "auth-service.test"
    assert forwarded.url.path == "/admin/users"


def test_admin_user_detail_route_with_admin_token_forwards(client):
    token = make_access_token(user_id="admin-1", role="admin")

    response = client.get(
        "/admin/users/33333333-3333-3333-3333-333333333333",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    forwarded = client._mock_calls[0]
    assert forwarded.url.host == "auth-service.test"
    assert forwarded.url.path == "/admin/users/33333333-3333-3333-3333-333333333333"


def test_admin_auth_login_route_is_public_and_forwards(client):
    # Separate identity system from /auth/login (see auth-service's AdminAccount) --
    # still PUBLIC because you need a token before you can carry one.
    response = client.post(
        "/admin/auth/login",
        json={"username": "superadmin", "password": "whatever"},
    )

    assert response.status_code == 200
    forwarded = client._mock_calls[0]
    assert forwarded.url.host == "auth-service.test"
    assert forwarded.url.path == "/admin/auth/login"
    assert "x-user-id" not in forwarded.headers


def test_admin_accounts_route_without_token_is_rejected(client):
    response = client.get("/admin/accounts")

    assert response.status_code == 401
    assert client._mock_calls == []


def test_admin_accounts_route_with_non_admin_token_is_forbidden(client):
    token = make_access_token(user_id="66666666-6666-6666-6666-666666666666")

    response = client.get("/admin/accounts", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    assert client._mock_calls == []


def test_admin_accounts_route_with_admin_token_forwards(client):
    token = make_access_token(user_id="admin-1", role="admin")

    response = client.get("/admin/accounts", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    forwarded = client._mock_calls[0]
    assert forwarded.url.host == "auth-service.test"
    assert forwarded.url.path == "/admin/accounts"
    assert forwarded.headers["x-user-id"] == "admin-1"


def test_admin_accounts_create_route_with_non_admin_token_is_forbidden(client):
    token = make_access_token(user_id="66666666-6666-6666-6666-666666666666")

    response = client.post(
        "/admin/accounts",
        json={"username": "new-admin", "password": "x", "role": "ADMIN"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert client._mock_calls == []


def test_admin_account_patch_route_with_admin_token_forwards(client):
    token = make_access_token(user_id="admin-1", role="admin")

    response = client.patch(
        "/admin/accounts/44444444-4444-4444-4444-444444444444",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    forwarded = client._mock_calls[0]
    assert forwarded.url.host == "auth-service.test"
    assert forwarded.url.path == "/admin/accounts/44444444-4444-4444-4444-444444444444"
