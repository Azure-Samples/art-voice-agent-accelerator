"""
Email Service for ARTAgent
=========================

Reusable email service that can be used by any tool to send emails via Azure Communication Services.
Supports both plain text and HTML email formats with professional templates.
"""

from __future__ import annotations

import asyncio
import os
import threading
from typing import Any

from utils.azure_auth import get_credential
from utils.ml_logging import get_logger

# Email service imports
try:
    from azure.communication.email import EmailClient

    AZURE_EMAIL_AVAILABLE = True
except ImportError:
    AZURE_EMAIL_AVAILABLE = False

logger = get_logger("email_service")


class EmailService:
    """Reusable email service for ARTAgent tools."""

    def __init__(self):
        """Initialize the email service with Azure configuration."""
        # Try specific email connection string first, then fall back to general ACS connection string
        self.connection_string = os.getenv(
            "AZURE_COMMUNICATION_EMAIL_CONNECTION_STRING"
        ) or os.getenv("ACS_CONNECTION_STRING")
        self.sender_address = os.getenv("AZURE_EMAIL_SENDER_ADDRESS")
        self.client: EmailClient | None = None

        # Fall back to credential-based auth if no connection string
        if not self.connection_string:
            try:
                self.credential = get_credential()
                # Need endpoint for credential-based auth
                self.endpoint = os.getenv("ACS_ENDPOINT")
                if self.endpoint and self.credential:
                    self.client = EmailClient(self.endpoint, self.credential)
                else:
                    self.client = None
            except ImportError:
                logger.warning("utils.azure_auth not available for credential-based authentication")
                self.credential = None
                self.endpoint = None
                self.client = None
        else:
            self.credential = None
            self.endpoint = None
            self.client = EmailClient.from_connection_string(self.connection_string)

    def is_configured(self) -> bool:
        """Check if email service is properly configured."""
        return AZURE_EMAIL_AVAILABLE and self.client is not None and bool(self.sender_address)

    async def send_email(
        self,
        email_address: str,
        subject: str,
        plain_text_body: str,
        html_body: str | None = None,
    ) -> dict[str, Any]:
        """
        Send email using Azure Communication Services Email.

        Args:
            email_address: Recipient email address
            subject: Email subject line
            plain_text_body: Plain text version of the email
            html_body: Optional HTML version of the email

        Returns:
            Dict containing success status, message ID, and error details if any
        """
        try:
            if not self.is_configured():
                return {
                    "success": False,
                    "error": "Azure Email service not configured or not available",
                }

            # Prepare email message
            message_content = {"subject": subject, "plainText": plain_text_body}

            # Add HTML if provided
            if html_body:
                message_content["html"] = html_body

            message = {
                "senderAddress": self.sender_address,
                "recipients": {"to": [{"address": email_address}]},
                "content": message_content,
            }

            # Send email
            poller = self.client.begin_send(message)
            result = poller.result()

            # Extract message ID
            message_id = getattr(result, "id", None) or getattr(result, "message_id", "unknown")

            logger.info(
                "📧 Email sent successfully to %s, message ID: %s", email_address, message_id
            )
            return {
                "success": True,
                "message_id": message_id,
                "service": "Azure Communication Services Email",
            }

        except Exception as exc:
            logger.error("Email sending failed: %s", exc)
            return {"success": False, "error": f"Azure Email error: {str(exc)}"}

    def send_email_background(
        self,
        email_address: str,
        subject: str,
        plain_text_body: str,
        html_body: str | None = None,
        callback: callable | None = None,
    ) -> None:
        """
        Send email in background thread without blocking the main response.

        Args:
            email_address: Recipient email address
            subject: Email subject line
            plain_text_body: Plain text version of the email
            html_body: Optional HTML version of the email
            callback: Optional callback function to handle the result
        """

        def _send_email_background_task():
            try:
                # Create new event loop for background task
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                # Send the email
                result = loop.run_until_complete(
                    self.send_email(email_address, subject, plain_text_body, html_body)
                )

                # Log result
                if result.get("success"):
                    logger.info(
                        "📧 Background email sent successfully: %s", result.get("message_id")
                    )
                else:
                    logger.warning("📧 Background email failed: %s", result.get("error"))

                # Call callback if provided
                if callback:
                    callback(result)

            except Exception as exc:
                logger.error("Background email task failed: %s", exc, exc_info=True)
            finally:
                loop.close()

        try:
            email_thread = threading.Thread(target=_send_email_background_task, daemon=True)
            email_thread.start()
            logger.info("📧 Email sending started in background thread")
        except Exception as exc:
            logger.error("Failed to start background email thread: %s", exc)


# Global email service instance
email_service = EmailService()


# Convenience functions for easy import
async def send_email(
    email_address: str, subject: str, plain_text_body: str, html_body: str | None = None
) -> dict[str, Any]:
    """Convenience function to send email."""
    return await email_service.send_email(email_address, subject, plain_text_body, html_body)


def send_email_background(
    email_address: str,
    subject: str,
    plain_text_body: str,
    html_body: str | None = None,
    callback: callable | None = None,
) -> None:
    """Convenience function to send email in background."""
    email_service.send_email_background(
        email_address, subject, plain_text_body, html_body, callback
    )


def is_email_configured() -> bool:
    """Check if email service is configured."""
    return email_service.is_configured()
