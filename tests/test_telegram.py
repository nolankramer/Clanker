"""Tests for Telegram bot and push notifier."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from clanker.remote.chat import TelegramBot
from clanker.remote.push import PushAction, PushNotification, PushNotifier

# ------------------------------------------------------------------
# TelegramBot
# ------------------------------------------------------------------


@pytest.fixture
def bot() -> TelegramBot:
    return TelegramBot(
        token="123:fake",
        chat_ids=[111, 222],
    )


async def test_send_message(bot: TelegramBot) -> None:
    bot._client.post = AsyncMock(
        return_value=MagicMock(json=lambda: {"ok": True})
    )
    ok = await bot.send("Hello!")
    assert ok is True
    assert bot._client.post.await_count == 2  # sent to both chat_ids


async def test_send_to_specific_chat(bot: TelegramBot) -> None:
    bot._client.post = AsyncMock(
        return_value=MagicMock(json=lambda: {"ok": True})
    )
    ok = await bot.send("Hello!", chat_id=111)
    assert ok is True
    assert bot._client.post.await_count == 1


async def test_send_with_buttons(bot: TelegramBot) -> None:
    bot._client.post = AsyncMock(
        return_value=MagicMock(json=lambda: {"ok": True})
    )
    await bot.send(
        "Choose:",
        chat_id=111,
        buttons=[[{"text": "Yes", "callback_data": "yes"}]],
    )
    call_args = bot._client.post.call_args[1]["json"]
    assert "reply_markup" in call_args


async def test_send_photo(bot: TelegramBot) -> None:
    bot._client.post = AsyncMock(
        return_value=MagicMock(json=lambda: {"ok": True})
    )
    ok = await bot.send_photo(b"\xff\xd8fake", caption="Test")
    assert ok is True


async def test_send_fails_gracefully(bot: TelegramBot) -> None:
    bot._client.post = AsyncMock(
        return_value=MagicMock(
            json=lambda: {"ok": False, "description": "error"}
        )
    )
    ok = await bot.send("Hello!", chat_id=111)
    assert ok is False


async def test_unauthorized_message(bot: TelegramBot) -> None:
    """Messages from unknown chat IDs should be rejected."""
    bot._client.post = AsyncMock(
        return_value=MagicMock(json=lambda: {"ok": True})
    )
    update = {
        "message": {
            "chat": {"id": 999},  # not in allowed list
            "text": "hack the planet",
        }
    }
    await bot._handle_update(update)
    # Should send "unauthorized" response
    assert bot._client.post.await_count == 1
    call_args = bot._client.post.call_args[1]["json"]
    assert "Unauthorized" in call_args.get("text", "")


async def test_routes_to_agent(bot: TelegramBot) -> None:
    agent = AsyncMock()
    agent.process = AsyncMock(
        return_value={"speech": "Lights off!", "conversation_id": "t:111"}
    )
    bot._agent = agent
    bot._client.post = AsyncMock(
        return_value=MagicMock(json=lambda: {"ok": True})
    )

    update = {
        "message": {
            "chat": {"id": 111},
            "text": "Turn off the lights",
        }
    }
    await bot._handle_update(update)
    agent.process.assert_awaited_once()
    assert "Turn off the lights" in agent.process.call_args[0][0]


async def test_start_command(bot: TelegramBot) -> None:
    bot._client.post = AsyncMock(
        return_value=MagicMock(json=lambda: {"ok": True})
    )
    await bot._handle_command("/start", 111)
    call_args = bot._client.post.call_args[1]["json"]
    assert "connected" in call_args["text"].lower()


# ------------------------------------------------------------------
# PushNotifier
# ------------------------------------------------------------------


async def test_push_via_telegram() -> None:
    telegram = AsyncMock()
    telegram.send = AsyncMock(return_value=True)
    notifier = PushNotifier(telegram=telegram)

    n = PushNotification(message="Alert!", title="Test")
    ok = await notifier.notify(n)
    assert ok is True
    telegram.send.assert_awaited_once()


async def test_push_via_telegram_with_image() -> None:
    telegram = AsyncMock()
    telegram.send_photo = AsyncMock(return_value=True)
    notifier = PushNotifier(telegram=telegram)

    n = PushNotification(
        message="Person at door",
        image=b"\xff\xd8",
    )
    ok = await notifier.notify(n)
    assert ok is True
    telegram.send_photo.assert_awaited_once()


async def test_push_via_ha_fallback() -> None:
    ha = AsyncMock()
    ha.notify = AsyncMock()
    notifier = PushNotifier(
        ha_services=ha, ha_targets=["notify.mobile_app_phone"]
    )

    n = PushNotification(message="Alert!", title="Test")
    ok = await notifier.notify(n)
    assert ok is True
    ha.notify.assert_awaited_once()


async def test_push_with_actions() -> None:
    telegram = AsyncMock()
    telegram.send = AsyncMock(return_value=True)
    notifier = PushNotifier(telegram=telegram)

    n = PushNotification(
        message="Doorbell!",
        actions=[
            PushAction("Talk", "TALK"),
            PushAction("Ignore", "IGNORE"),
        ],
    )
    await notifier.notify(n)
    call_args = telegram.send.call_args
    assert call_args[1].get("buttons") is not None


async def test_push_no_channels() -> None:
    notifier = PushNotifier()
    n = PushNotification(message="Hello")
    ok = await notifier.notify(n)
    assert ok is False
