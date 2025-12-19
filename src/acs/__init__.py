"""
Azure Communication Services Package
===================================

Provides reusable email and SMS services for ARTAgent tools.

This package includes:
- EmailService: For sending emails via Azure Communication Services
- SmsService: For sending SMS messages via Azure Communication Services
- EmailTemplates: Professional email templates
- SmsTemplates: Professional SMS templates

Example usage:

    # Email Service
    from src.acs import EmailService, EmailTemplates

    email_service = EmailService()
    subject, plain_text, html = EmailTemplates.create_claim_confirmation_email(
        claim_data, claim_id, customer_name
    )
    await email_service.send_email_async(
        to_email="customer@example.com",
        subject=subject,
        plain_text_body=plain_text,
        html_body=html
    )

    # SMS Service
    from src.acs import SmsService, SmsTemplates

    sms_service = SmsService()
    message = SmsTemplates.create_claim_confirmation_sms(claim_id)
    await sms_service.send_sms_async(
        to_phone="+1234567890",
        message=message
    )
"""

from .email_service import EmailService
from .email_templates import EmailTemplates
from .sms_service import SmsService, is_sms_configured, send_sms, send_sms_background, sms_service
from .sms_templates import SmsTemplates

__all__ = [
    "EmailService",
    "EmailTemplates",
    "send_sms",
    "send_sms_background",
    "is_sms_configured",
    "SmsService",
    "sms_service",
    "SmsTemplates",
]
