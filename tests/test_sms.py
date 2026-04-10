"""Tests for SMS adapter via Twilio."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from clanker.remote.sms import SMSAdapter


def _make_adapter() -> SMSAdapter:
    return SMSAdapter(
        account_sid="AC_test",
        auth_token="token_test",
        from_number="+15551234567",
        to_numbers=["+15559876543"],
    )


async def test_send_sms() -> None:
    adapter = _make_adapter()
    adapter._client.post = AsyncMock(
        return_value=MagicMock(status_code=201)
    )
    ok = await adapter.send("Hello from Clanker!")
    assert ok is True
    adapter._client.post.assert_awaited_once()

    # Verify Twilio API call
    call_args = adapter._client.post.call_args
    assert "Messages.json" in call_args[0][0]
    data = call_args[1]["data"]
    assert data["From"] == "+15551234567"
    assert data["To"] == "+15559876543"
    assert data["Body"] == "Hello from Clanker!"


async def test_send_to_specific_number() -> None:
    adapter = _make_adapter()
    adapter._client.post = AsyncMock(
        return_value=MagicMock(status_code=201)
    )
    await adapter.send("Alert!", to="+15550000000")
    data = adapter._client.post.call_args[1]["data"]
    assert data["To"] == "+15550000000"


async def test_send_with_image_url() -> None:
    adapter = _make_adapter()
    adapter._client.post = AsyncMock(
        return_value=MagicMock(status_code=201)
    )
    await adapter.send("Person at door", image_url="https://example.com/snap.jpg")
    data = adapter._client.post.call_args[1]["data"]
    assert data["MediaUrl"] == "https://example.com/snap.jpg"


async def test_send_fails() -> None:
    adapter = _make_adapter()
    adapter._client.post = AsyncMock(
        return_value=MagicMock(status_code=400, text="Bad request")
    )
    ok = await adapter.send("test")
    assert ok is False


async def test_send_truncates_long_messages() -> None:
    adapter = _make_adapter()
    adapter._client.post = AsyncMock(
        return_value=MagicMock(status_code=201)
    )
    long_msg = "x" * 2000
    await adapter.send(long_msg)
    data = adapter._client.post.call_args[1]["data"]
    assert len(data["Body"]) == 1600


# ------------------------------------------------------------------
# Webhook (inbound)
# ------------------------------------------------------------------


async def test_webhook_routes_to_agent() -> None:
    adapter = _make_adapter()
    agent = AsyncMock()
    agent.process = AsyncMock(
        return_value={"speech": "Lights off!", "conversation_id": "sms:+15559876543"}
    )
    adapter._agent = agent

    twiml = await adapter.handle_webhook({
        "From": "+15559876543",
        "Body": "Turn off the lights",
    })

    agent.process.assert_awaited_once()
    assert "Lights off!" in twiml
    assert "<Message>" in twiml


async def test_webhook_unauthorized_silently_dropped() -> None:
    adapter = _make_adapter()
    twiml = await adapter.handle_webhook({
        "From": "+15550000000",  # not in to_numbers
        "Body": "Hack!",
    })
    # Silent drop — empty TwiML response, no info leaked
    assert "<Message>" not in twiml


async def test_webhook_empty_body() -> None:
    adapter = _make_adapter()
    twiml = await adapter.handle_webhook({"From": "+15559876543", "Body": ""})
    assert "<Response></Response>" in twiml


# ------------------------------------------------------------------
# TwiML
# ------------------------------------------------------------------


def test_twiml_escapes_xml() -> None:
    result = SMSAdapter._twiml("Test <script> & stuff")
    assert "&lt;script&gt;" in result
    assert "&amp;" in result
