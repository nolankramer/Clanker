"""SMS adapter via Twilio — send alerts and receive commands via text.

Supports:
- Outbound: text alerts, MMS with camera snapshots
- Inbound: user texts Clanker, routed through conversation agent
- Bidirectional via Twilio webhooks on the conversation HTTP server

Setup: Twilio account → get account_sid, auth_token, buy a phone number.
More complex than Telegram but works with any phone — no app needed.

Uses Twilio's REST API directly via httpx (no twilio SDK dependency).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import structlog

if TYPE_CHECKING:
    from clanker.conversation.agent import ConversationAgent

logger = structlog.get_logger(__name__)

_TWILIO_API = "https://api.twilio.com/2010-04-01"


class SMSAdapter:
    """SMS notification and chat adapter via Twilio.

    Outbound messages are sent via Twilio's REST API. Inbound messages
    arrive as webhooks — the conversation HTTP server needs to forward
    ``/api/sms/webhook`` POST requests to :meth:`handle_webhook`.
    """

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        from_number: str,
        to_numbers: list[str],
        *,
        agent: ConversationAgent | None = None,
    ) -> None:
        self._sid = account_sid
        self._token = auth_token
        self._from = from_number
        self._to_numbers = to_numbers
        self._agent = agent
        self._client = httpx.AsyncClient(
            auth=(account_sid, auth_token),
            timeout=30.0,
        )

    async def send(
        self,
        message: str,
        *,
        to: str | None = None,
        image_url: str | None = None,
    ) -> bool:
        """Send an SMS (or MMS with image) via Twilio.

        Args:
            message: Text message body (max ~1600 chars for SMS).
            to: Specific phone number, or None to send to all configured.
            image_url: Public URL for MMS image attachment.

        Returns:
            True if at least one message was sent.
        """
        targets = [to] if to else self._to_numbers
        ok = False

        for number in targets:
            data: dict[str, str] = {
                "From": self._from,
                "To": number,
                "Body": message[:1600],
            }
            if image_url:
                data["MediaUrl"] = image_url

            try:
                resp = await self._client.post(
                    f"{_TWILIO_API}/Accounts/{self._sid}/Messages.json",
                    data=data,
                )
                if resp.status_code in (200, 201):
                    ok = True
                    logger.info("sms.sent", to=number)
                else:
                    logger.warning(
                        "sms.send_failed",
                        to=number,
                        status=resp.status_code,
                        body=resp.text[:200],
                    )
            except Exception:
                logger.exception("sms.send_error", to=number)

        return ok

    async def send_with_image(
        self,
        message: str,
        image: bytes,
        *,
        to: str | None = None,
    ) -> bool:
        """Send an MMS by uploading image to a temp URL.

        Since Twilio needs a public URL for MMS, this method base64-encodes
        the image into a data URI. Note: Twilio requires a publicly
        accessible URL — for true MMS, host the image and pass the URL
        to :meth:`send` instead.

        For most alert use cases, text-only SMS is sufficient. Use
        Telegram for image-rich notifications.
        """
        # Twilio doesn't support data URIs for MMS — send text-only
        logger.info("sms.image_not_supported_falling_back_to_text")
        return await self.send(message, to=to)

    async def handle_webhook(self, body: dict[str, Any]) -> str:
        """Process an inbound SMS webhook from Twilio.

        Twilio POSTs form-encoded data to our webhook URL. The
        conversation server should parse it and call this method.

        Args:
            body: Parsed form data from Twilio webhook.

        Returns:
            TwiML response string.
        """
        raw_from = body.get("From", "")
        from_number = raw_from[0] if isinstance(raw_from, list) else raw_from
        raw_body = body.get("Body", "")
        text = raw_body[0] if isinstance(raw_body, list) else raw_body

        if not text:
            return self._twiml("")

        logger.info("sms.received", from_number=from_number, text=text[:80])

        # Security: only process from known numbers
        if from_number not in self._to_numbers:
            logger.warning("sms.unauthorized", from_number=from_number)
            return self._twiml("Unauthorized number.")

        # Route through conversation agent
        if self._agent:
            try:
                result = await self._agent.process(
                    text,
                    conversation_id=f"sms:{from_number}",
                )
                return self._twiml(result["speech"])
            except Exception:
                logger.exception("sms.agent_error")
                return self._twiml("Sorry, something went wrong.")

        return self._twiml("Clanker brain is not connected.")

    async def close(self) -> None:
        """Release HTTP client."""
        await self._client.aclose()

    @staticmethod
    def _twiml(message: str) -> str:
        """Build a minimal TwiML response."""
        if not message:
            return '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
        # Escape XML
        safe = (
            message.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f"<Response><Message>{safe}</Message></Response>"
        )


def test_twilio_credentials(
    account_sid: str, auth_token: str
) -> dict[str, Any]:
    """Verify Twilio credentials by fetching account info."""
    try:
        with httpx.Client(
            auth=(account_sid, auth_token), timeout=10.0
        ) as client:
            resp = client.get(
                f"{_TWILIO_API}/Accounts/{account_sid}.json"
            )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "ok": True,
                    "name": data.get("friendly_name", ""),
                    "status": data.get("status", ""),
                }
            if resp.status_code == 401:
                return {"ok": False, "message": "Invalid credentials"}
            return {
                "ok": False,
                "message": f"Twilio API returned {resp.status_code}",
            }
    except httpx.ConnectError:
        return {"ok": False, "message": "Cannot reach Twilio API"}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}
