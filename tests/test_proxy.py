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


def test_removed_payment_routes_are_not_proxied(client):
    # /payments/redirect never had a handler; the transaction lookups are staff-only on
    # payment-service and unused by the app; /bookings/{id}/confirm is payment-service-only.
    for method, path in [
        ("GET", "/payments/redirect?status=approved"),
        ("GET", "/payments/123"),
        ("GET", "/payments/external-reference/ref-1"),
        ("POST", "/bookings/11111111-1111-1111-1111-111111111111/confirm"),
    ]:
        response = client.request(method, path)
        assert response.status_code in (404, 405), path
    assert client._mock_calls == []


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


def test_admin_owner_settlement_draft_route_with_non_admin_token_is_forbidden(client):
    token = make_access_token(user_id="66666666-6666-6666-6666-666666666666")

    response = client.post(
        "/admin/owners/some-owner-id/settlements",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert client._mock_calls == []


def test_admin_settlement_confirm_route_with_admin_token_hits_unconfigured_booking_service(client):
    token = make_access_token(user_id="admin-1", role="admin")

    response = client.post(
        "/admin/settlements/some-settlement-id/confirm",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 503
    assert client._mock_calls == []


def test_owner_settlement_detail_route_without_token_is_rejected(client):
    response = client.get("/settlements/some-settlement-id")

    assert response.status_code == 401
    assert client._mock_calls == []


def test_owner_settlement_detail_route_with_valid_token_hits_unconfigured_booking_service(client):
    # booking-service has no mock host in this suite (see conftest.py), so the strongest
    # assertion is that a valid token gets *past* auth (503, not 401).
    token = make_access_token()

    response = client.get(
        "/settlements/some-settlement-id",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 503
    assert client._mock_calls == []


def test_users_tickets_route_without_token_is_rejected(client):
    response = client.get("/users/11111111-1111-1111-1111-111111111111/tickets")

    assert response.status_code == 401
    assert client._mock_calls == []


def test_users_tickets_route_with_valid_token_hits_unconfigured_booking_service(client):
    token = make_access_token()

    response = client.get(
        "/users/11111111-1111-1111-1111-111111111111/tickets",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 503
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


def test_get_admin_account_route_without_token_is_rejected(client):
    response = client.get("/admin/accounts/some-admin-id")

    assert response.status_code == 401
    assert client._mock_calls == []


def test_get_admin_account_route_with_admin_token_forwards(client):
    token = make_access_token(user_id="admin-1", role="admin")

    response = client.get("/admin/accounts/some-admin-id", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    forwarded = client._mock_calls[0]
    assert forwarded.url.host == "auth-service.test"
    assert forwarded.url.path == "/admin/accounts/some-admin-id"


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


def test_admin_route_forwards_admin_role_header_when_present(client):
    # Lets a service that doesn't own admin_accounts (e.g. booking-service's commission
    # settings) gate a SUPERADMIN-only action without calling back into auth-service.
    token = make_access_token(user_id="admin-1", role="admin", admin_role="SUPERADMIN")

    response = client.get("/admin/accounts", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    forwarded = client._mock_calls[0]
    assert forwarded.headers["x-admin-role"] == "SUPERADMIN"


def test_admin_route_omits_admin_role_header_when_token_lacks_it(client):
    token = make_access_token(user_id="admin-1", role="admin")

    response = client.get("/admin/accounts", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    forwarded = client._mock_calls[0]
    assert "x-admin-role" not in forwarded.headers


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


def test_admin_parking_spots_review_queue_requires_admin(client):
    assert client.get("/admin/parking-spots").status_code == 401

    token = make_access_token(user_id="66666666-6666-6666-6666-666666666666")
    response = client.get("/admin/parking-spots", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    assert client._mock_calls == []


def test_admin_parking_spots_review_routes_forward_to_parking_with_admin_token(client):
    token = make_access_token(user_id="admin-1", role="admin")
    headers = {"Authorization": f"Bearer {token}"}

    client.get("/admin/parking-spots", headers=headers)
    client.get("/admin/parking-spots/spot-1", headers=headers)
    client.patch("/admin/parking-spots/spot-1/review", headers=headers, json={"decision": "approved"})

    calls = [(c.method, c.url.host, c.url.path) for c in client._mock_calls]
    # The approval/rejection (a write) is also recorded in the admin audit log.
    assert ("POST", "auth-service.test", "/internal/admin-audit") in calls
    forwarded = [call for call in calls if call[2] != "/internal/admin-audit"]
    assert forwarded == [
        ("GET", "parking-service.test", "/admin/parking-spots"),
        ("GET", "parking-service.test", "/admin/parking-spots/spot-1"),
        ("PATCH", "parking-service.test", "/admin/parking-spots/spot-1/review"),
    ]


def test_spot_verification_photos_upload_requires_auth_and_forwards_to_parking(client):
    assert client.post("/parking-spots/spot-1/verification-photos").status_code == 401

    response = client.post(
        "/parking-spots/spot-1/verification-photos",
        headers={"Authorization": f"Bearer {make_access_token()}"},
    )

    assert response.status_code == 200
    forwarded = client._mock_calls[0]
    assert forwarded.url.host == "parking-service.test"
    assert forwarded.url.path == "/parking-spots/spot-1/verification-photos"


def test_admin_refunds_route_with_non_admin_token_is_forbidden(client):
    token = make_access_token(user_id="66666666-6666-6666-6666-666666666666")

    response = client.get("/admin/refunds", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    assert client._mock_calls == []


def test_admin_refunds_routes_with_admin_token_forward_to_payment_service_as_is(client):
    token = make_access_token(user_id="admin-1", role="admin")
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/admin/refunds", headers=headers).status_code == 200
    assert client.get("/admin/refunds/count", headers=headers).status_code == 200
    assert client.post("/admin/refunds/182168894549/retry", headers=headers).status_code == 200
    assert client.post(
        "/admin/refunds/182168894549/resolve", headers=headers, json={"resolution": "discarded", "note": "prueba"}
    ).status_code == 200

    forwarded = [
        (call.method, call.url.host, call.url.path) for call in client._mock_calls
        if call.url.path != "/internal/admin-audit"  # admin writes are also logged (app/audit.py)
    ]
    assert forwarded == [
        ("GET", "payment-service.test", "/admin/refunds"),
        ("GET", "payment-service.test", "/admin/refunds/count"),
        ("POST", "payment-service.test", "/admin/refunds/182168894549/retry"),
        ("POST", "payment-service.test", "/admin/refunds/182168894549/resolve"),
    ]
    # payment-service re-checks the admin role from the token itself.
    assert all(
        call.headers["authorization"] == f"Bearer {token}"
        for call in client._mock_calls
        if call.url.path != "/internal/admin-audit"  # the audit call carries the gateway secret instead
    )


def test_vehicle_type_update_route_forwards_to_auth_service(client):
    token = make_access_token(user_id="11111111-1111-1111-1111-111111111111")

    response = client.patch(
        "/users/11111111-1111-1111-1111-111111111111/vehicles/22222222-2222-2222-2222-222222222222",
        headers={"Authorization": f"Bearer {token}"},
        json={"type": "car"},
    )

    assert response.status_code == 200
    forwarded = client._mock_calls[0]
    assert forwarded.url.host == "auth-service.test"
    assert forwarded.method == "PATCH"
