"""WhatsApp and IVR adapters.

These are real, working *adapters* - they normalise inbound webhook payloads
into the shape the conversation engine consumes, and they know how to format an
outbound reply. What they are NOT is a live integration: without credentials,
`send_text` raises ProviderNotConfigured instead of pretending a message was
delivered. The inbound direction can be exercised end-to-end today by POSTing a
sample payload to /api/channels/{whatsapp,ivr}/inbound.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import httpx

from ..config import get_settings
from ..core.enums import Channel
from .base import InboundMessage, MessagingProvider, ProviderNotConfigured, ProviderStatus


class NullMessagingProvider:
    name = "none"
    channel = "none"

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            kind="messaging",
            configured=False,
            detail="No messaging channel configured. Web is the active channel.",
            is_offline_default=True,
        )

    def parse_inbound(self, payload: dict[str, Any]) -> InboundMessage:
        raise ProviderNotConfigured("No messaging provider is configured.")

    def send_text(self, recipient_ref: str, text: str, language: str = "en") -> dict[str, Any]:
        raise ProviderNotConfigured("No messaging provider is configured.")


class WhatsAppCloudProvider:
    """Adapter for the WhatsApp Business Cloud API webhook format."""

    name = "whatsapp_cloud"
    channel = Channel.WHATSAPP

    def __init__(self) -> None:
        settings = get_settings()
        self.phone_number_id = settings.whatsapp_phone_number_id
        self.access_token = settings.whatsapp_access_token
        self.verify_token = settings.whatsapp_verify_token

    @property
    def configured(self) -> bool:
        return bool(self.phone_number_id and self.access_token)

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            kind="messaging",
            configured=self.configured,
            detail=(
                "Outbound sending enabled."
                if self.configured
                else "Adapter present; inbound parsing works. Outbound sending "
                "requires WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_ACCESS_TOKEN."
            ),
        )

    def parse_inbound(self, payload: dict[str, Any]) -> InboundMessage:
        """Normalise a Cloud API webhook body into an InboundMessage."""
        try:
            change = payload["entry"][0]["changes"][0]["value"]
            message = change["messages"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("Unrecognised WhatsApp webhook payload") from exc

        sender = message.get("from", "")
        msg_type = message.get("type")
        text = None
        if msg_type == "text":
            text = message.get("text", {}).get("body")
        elif msg_type == "interactive":
            interactive = message.get("interactive", {})
            text = (
                interactive.get("button_reply", {}).get("title")
                or interactive.get("list_reply", {}).get("title")
            )
        # Audio arrives as a media id that must be downloaded separately; we
        # surface the id rather than inventing a transcript.
        metadata: dict[str, Any] = {"type": msg_type, "wa_message_id": message.get("id")}
        if msg_type == "audio":
            metadata["media_id"] = message.get("audio", {}).get("id")

        return InboundMessage(
            channel=Channel.WHATSAPP,
            sender_ref=sender,
            text=text,
            language_hint=(change.get("contacts") or [{}])[0].get("language"),
            metadata=metadata,
        )

    def send_text(self, recipient_ref: str, text: str, language: str = "en") -> dict[str, Any]:
        if not self.configured:
            raise ProviderNotConfigured(
                "WhatsApp credentials are not configured; message was not sent."
            )
        response = httpx.post(  # pragma: no cover - requires live credentials
            f"https://graph.facebook.com/v20.0/{self.phone_number_id}/messages",
            headers={"Authorization": f"Bearer {self.access_token}"},
            json={
                "messaging_product": "whatsapp",
                "to": recipient_ref,
                "type": "text",
                "text": {"body": text},
            },
            timeout=20.0,
        )
        response.raise_for_status()
        return response.json()


class IVRWebhookProvider:
    """Adapter for a generic IVR/telephony webhook (DTMF + recording URL)."""

    name = "ivr_webhook"
    channel = Channel.IVR

    def __init__(self) -> None:
        self.secret = get_settings().ivr_webhook_secret

    @property
    def configured(self) -> bool:
        return bool(self.secret)

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            kind="messaging",
            configured=self.configured,
            detail=(
                "IVR webhook adapter active."
                if self.configured
                else "Adapter present; set IVR_WEBHOOK_SECRET to accept live callbacks."
            ),
        )

    def parse_inbound(self, payload: dict[str, Any]) -> InboundMessage:
        caller = payload.get("from") or payload.get("caller") or ""
        if not caller:
            raise ValueError("IVR payload is missing the caller identifier")
        return InboundMessage(
            channel=Channel.IVR,
            sender_ref=caller,
            text=payload.get("speech_text") or payload.get("transcript"),
            language_hint=payload.get("language"),
            metadata={
                "call_id": payload.get("call_id"),
                "dtmf": payload.get("dtmf"),
                "recording_url": payload.get("recording_url"),
            },
        )

    def send_text(self, recipient_ref: str, text: str, language: str = "en") -> dict[str, Any]:
        """IVR replies are spoken; return a TTS instruction for the telephony layer."""
        if not self.configured:
            raise ProviderNotConfigured("IVR_WEBHOOK_SECRET is not configured.")
        return {"action": "say", "language": language, "text": text, "to": recipient_ref}


@lru_cache
def get_messaging_provider() -> MessagingProvider:
    settings = get_settings()
    match settings.messaging_provider:
        case "whatsapp_cloud":
            return WhatsAppCloudProvider()
        case "ivr_webhook":
            return IVRWebhookProvider()
        case _:
            return NullMessagingProvider()


def get_channel_adapter(channel: str) -> MessagingProvider:
    """Return the adapter for a channel regardless of the configured default.

    Inbound parsing must work for demonstration even when outbound credentials
    are absent.
    """
    if channel == Channel.WHATSAPP:
        return WhatsAppCloudProvider()
    if channel == Channel.IVR:
        return IVRWebhookProvider()
    return NullMessagingProvider()


def all_messaging_statuses() -> list[ProviderStatus]:
    return [WhatsAppCloudProvider().status(), IVRWebhookProvider().status()]
