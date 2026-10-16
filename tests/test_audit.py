"""What the gateway records about admin actions (see app/audit.py)."""
import asyncio

from app import audit


def test_summary_keeps_only_the_interesting_fields():
    body = b'{"reason": "Fotos falsas", "amount": 250000, "password": "secreto", "photo": "..."}'
    assert audit.summarize(body) == "reason: Fotos falsas \xb7 amount: 250000"


def test_summary_keeps_when_support_says_the_vehicle_left():
    assert audit.summarize(b'{"exited_at": "2026-10-12T20:30:00-03:00"}') == "exited_at: 2026-10-12T20:30:00-03:00"


def test_summary_of_a_body_that_is_not_json_is_empty():
    assert audit.summarize(b"--multipart--") is None
    assert audit.summarize(b"") is None


def test_only_successful_writes_are_recorded(monkeypatch):
    sent = []

    async def fake_send(_client, entry):
        sent.append(entry)

    monkeypatch.setattr(audit, "_send", fake_send)

    async def scenario():
        common = {"admin_id": "a1", "admin_username": "ana", "path": "/admin/x", "body": b'{"note": "ok"}'}
        audit.record_admin_action(None, method="GET", status_code=200, **common)
        audit.record_admin_action(None, method="POST", status_code=409, **common)
        audit.record_admin_action(None, method="POST", status_code=200, **common)
        await asyncio.sleep(0)

    asyncio.run(scenario())
    assert [(e["method"], e["status_code"], e["summary"]) for e in sent] == [("POST", 200, "note: ok")]
