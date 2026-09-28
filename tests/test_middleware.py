from starlette.requests import Request

from app.middleware import RateLimitMiddleware


def _make_request(headers: dict[str, str]) -> Request:
    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)


def _middleware() -> RateLimitMiddleware:
    # _get_client_ip doesn't touch self.app, so a dummy callable is enough here --
    # no need to spin up the real ASGI app just to unit-test header parsing.
    return RateLimitMiddleware(app=lambda *args, **kwargs: None)


def test_get_client_ip_prefers_cf_connecting_ip():
    # Set only by Cloudflare's own edge (used locally via `cloudflared tunnel`) -- checked
    # first so every real device behind the same tunnel gets its own rate-limit bucket
    # instead of all colliding on the tunnel's one apparent X-Forwarded-For last hop.
    request = _make_request({"cf-connecting-ip": "9.9.9.9", "x-forwarded-for": "5.5.5.5, 6.6.6.6"})

    assert _middleware()._get_client_ip(request) == "9.9.9.9"


def test_get_client_ip_falls_back_to_last_forwarded_for_entry_without_cloudflare():
    # Render (production) appends its own resolved address as the LAST entry -- the client
    # can forge everything before it, so only the last entry is trusted.
    request = _make_request({"x-forwarded-for": "5.5.5.5, 6.6.6.6"})

    assert _middleware()._get_client_ip(request) == "6.6.6.6"


def test_get_client_ip_falls_back_to_socket_address_without_any_header():
    request = _make_request({})

    assert _middleware()._get_client_ip(request) == "127.0.0.1"
