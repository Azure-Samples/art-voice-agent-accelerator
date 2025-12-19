"""
SMS Service for ARTAgent
========================

Reusable SMS service that can be used by any tool to send text messages via Azure Communication Services SMS.
Supports delivery reports and custom tagging for message tracking.
"""

from __future__ import annotations

import asyncio
import os
import threading
from typing import Any

from utils.ml_logging import get_logger

# SMS service imports
try:
    from azure.communication.sms import SmsClient

    AZURE_SMS_AVAILABLE = True
except ImportError:
    AZURE_SMS_AVAILABLE = False

logger = get_logger("sms_service")


class SmsService:
    """Reusable SMS service for ARTAgent tools."""

    def __init__(self):
        """Initialize the SMS service with Azure configuration."""
        self.connection_string = os.getenv("AZURE_COMMUNICATION_SMS_CONNECTION_STRING")
        self.from_phone_number = os.getenv("AZURE_SMS_FROM_PHONE_NUMBER")

    def is_configured(self) -> bool:
        """Check if SMS service is properly configured."""
        return AZURE_SMS_AVAILABLE and bool(self.connection_string) and bool(self.from_phone_number)

    async def send_sms(
        self,
        to_phone_numbers: str | list[str],
        message: str,
        enable_delivery_report: bool = True,
        tag: str | None = None,
    ) -> dict[str, Any]:
        """
        Send SMS using Azure Communication Services SMS.

        Args:
            to_phone_numbers: Recipient phone number(s) - can be single string or list
            message: SMS message content
            enable_delivery_report: Whether to enable delivery reports
            tag: Optional tag for message tracking

        Returns:
            Dict containing success status, message IDs, and error details if any
        """
        try:
            if not self.is_configured():
                return {
                    "success": False,
                    "error": "Azure SMS service not configured or not available",
                    "sent_messages": [],
                }

            # Ensure phone numbers is a list
            if isinstance(to_phone_numbers, str):
                to_phone_numbers = [to_phone_numbers]

            # Create SMS client
            sms_client = SmsClient.from_connection_string(self.connection_string)

            # Send SMS
            sms_responses = sms_client.send(
                from_=self.from_phone_number,
                to=to_phone_numbers,
                message=message,
                enable_delivery_report=enable_delivery_report,
                tag=tag or "ARTAgent SMS",
            )

            # Process responses
            sent_messages = []
            failed_messages = []

            for response in sms_responses:
                message_data = {
                    "to": response.to,
                    "message_id": response.message_id,
                    "http_status_code": response.http_status_code,
                    "successful": response.successful,
                    "error_message": (
                        response.error_message if hasattr(response, "error_message") else None
                    ),
                }

                if response.successful:
                    sent_messages.append(message_data)
                    logger.info(
                        "📱 SMS sent successfully to %s, message ID: %s",
                        response.to,
                        response.message_id,
                    )
                else:
                    failed_messages.append(message_data)
                    logger.error(
                        "📱 SMS failed to %s: %s",
                        response.to,
                        (
                            response.error_message
                            if hasattr(response, "error_message")
                            else "Unknown error"
                        ),
                    )

            return {
                "success": len(failed_messages) == 0,
                "sent_count": len(sent_messages),
                "failed_count": len(failed_messages),
                "sent_messages": sent_messages,
                "failed_messages": failed_messages,
                "service": "Azure Communication Services SMS",
                "tag": tag or "ARTAgent SMS",
            }

        except Exception as exc:
            logger.error("SMS sending failed: %s", exc)
            return {
                "success": False,
                "error": f"Azure SMS error: {str(exc)}",
                "sent_messages": [],
                "failed_messages": [],
            }

    def send_sms_background(
        self,
        to_phone_numbers: str | list[str],
        message: str,
        enable_delivery_report: bool = True,
        tag: str | None = None,
        callback: callable | None = None,
    ) -> None:
        """
        Send SMS in background thread without blocking the main response.

        Args:
            to_phone_numbers: Recipient phone number(s) - can be single string or list
            message: SMS message content
            enable_delivery_report: Whether to enable delivery reports
            tag: Optional tag for message tracking
            callback: Optional callback function to handle the result
        """

        def _send_sms_background_task():
            try:
                # Create new event loop for background task
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                # Send the SMS
                result = loop.run_until_complete(
                    self.send_sms(to_phone_numbers, message, enable_delivery_report, tag)
                )

                # Log result
                if result.get("success"):
                    logger.info(
                        "📱 Background SMS sent successfully: %d messages",
                        result.get("sent_count", 0),
                    )
                else:
                    logger.warning("📱 Background SMS failed: %s", result.get("error"))

                # Call callback if provided
                if callback:
                    callback(result)

            except Exception as exc:
                logger.error("Background SMS task failed: %s", exc, exc_info=True)
            finally:
                loop.close()

        try:
            sms_thread = threading.Thread(target=_send_sms_background_task, daemon=True)
            sms_thread.start()
            logger.info("📱 SMS sending started in background thread")
        except Exception as exc:
            logger.error("Failed to start background SMS thread: %s", exc)


# Global SMS service instance
sms_service = SmsService()


# Convenience functions for easy import
async def send_sms(
    to_phone_numbers: str | list[str],
    message: str,
    enable_delivery_report: bool = True,
    tag: str | None = None,
) -> dict[str, Any]:
    """Convenience function to send SMS."""
    return await sms_service.send_sms(to_phone_numbers, message, enable_delivery_report, tag)


def send_sms_background(
    to_phone_numbers: str | list[str],
    message: str,
    enable_delivery_report: bool = True,
    tag: str | None = None,
    callback: callable | None = None,
) -> None:
    """Convenience function to send SMS in background."""
    sms_service.send_sms_background(
        to_phone_numbers, message, enable_delivery_report, tag, callback
    )


def is_sms_configured() -> bool:
    """Check if SMS service is configured."""
    return sms_service.is_configured()
