"""
SMS Templates for ARTAgent
==========================

Reusable SMS message templates that can be used by any tool.
Provides consistent messaging and formatting for different use cases.
"""

from typing import Any


class SmsTemplates:
    """Collection of reusable SMS templates."""

    @staticmethod
    def create_claim_confirmation_sms(
        claim_id: str, caller_name: str, claim_data: dict[str, Any] | None = None
    ) -> str:
        """
        Create claim confirmation SMS message.

        Args:
            claim_id: The claim ID
            caller_name: Name of the caller
            claim_data: Optional claim data for additional details

        Returns:
            SMS message text
        """
        return f"""🛡️ ARTVoice Insurance - Claim Confirmation

Hi {caller_name},

Your claim has been successfully filed!

📋 Claim ID: {claim_id}

A claims adjuster will contact you within 24-48 hours. Please save this claim number for future reference.

Need help? Call our 24/7 claims hotline.

Thank you for choosing ARTVoice Insurance."""

    @staticmethod
    def create_appointment_reminder_sms(
        customer_name: str,
        appointment_date: str,
        appointment_time: str,
        appointment_type: str,
        contact_info: str | None = None,
    ) -> str:
        """
        Create appointment reminder SMS message.

        Args:
            customer_name: Name of the customer
            appointment_date: Date of the appointment
            appointment_time: Time of the appointment
            appointment_type: Type of appointment
            contact_info: Optional contact information

        Returns:
            SMS message text
        """
        message = f"""📅 ARTVoice Insurance - Appointment Reminder

Hi {customer_name},

This is a reminder for your {appointment_type} appointment:

📅 Date: {appointment_date}
🕐 Time: {appointment_time}

Please arrive 10 minutes early."""

        if contact_info:
            message += f"\n\nQuestions? Contact us: {contact_info}"

        message += "\n\nReply STOP to opt out."

        return message

    @staticmethod
    def create_policy_notification_sms(
        customer_name: str,
        policy_id: str,
        notification_type: str,
        key_details: str | None = None,
    ) -> str:
        """
        Create policy notification SMS message.

        Args:
            customer_name: Name of the customer
            policy_id: Policy ID
            notification_type: Type of notification
            key_details: Optional key details

        Returns:
            SMS message text
        """
        message = f"""📋 ARTVoice Insurance - Policy {notification_type.title()}

Hi {customer_name},

Your policy {policy_id} requires attention:

{notification_type.title()}: {key_details or 'Please contact us for details'}

Call us or visit our website for more information."""

        message += "\n\nReply STOP to opt out."

        return message

    @staticmethod
    def create_payment_reminder_sms(
        customer_name: str, policy_id: str, amount_due: str, due_date: str
    ) -> str:
        """
        Create payment reminder SMS message.

        Args:
            customer_name: Name of the customer
            policy_id: Policy ID
            amount_due: Amount due
            due_date: Payment due date

        Returns:
            SMS message text
        """
        return f"""💳 ARTVoice Insurance - Payment Reminder

Hi {customer_name},

Policy {policy_id} payment reminder:

💰 Amount Due: ${amount_due}
📅 Due Date: {due_date}

Pay online, by phone, or mobile app to avoid late fees.

Reply STOP to opt out."""

    @staticmethod
    def create_emergency_notification_sms(
        customer_name: str, message_content: str, action_required: str | None = None
    ) -> str:
        """
        Create emergency notification SMS message.

        Args:
            customer_name: Name of the customer
            message_content: Main message content
            action_required: Optional action required

        Returns:
            SMS message text
        """
        message = f"""🚨 ARTVoice Insurance - Emergency Alert

Hi {customer_name},

{message_content}"""

        if action_required:
            message += f"\n\nACTION REQUIRED: {action_required}"

        message += "\n\nCall our emergency hotline for immediate assistance."

        return message

    @staticmethod
    def create_service_update_sms(
        customer_name: str,
        service_type: str,
        update_message: str,
        estimated_resolution: str | None = None,
    ) -> str:
        """
        Create service update SMS message.

        Args:
            customer_name: Name of the customer
            service_type: Type of service affected
            update_message: Update message
            estimated_resolution: Optional estimated resolution time

        Returns:
            SMS message text
        """
        message = f"""🔧 ARTVoice Insurance - Service Update

Hi {customer_name},

{service_type} Update: {update_message}"""

        if estimated_resolution:
            message += f"\n\nExpected resolution: {estimated_resolution}"

        message += "\n\nWe apologize for any inconvenience. Thank you for your patience."

        return message

    @staticmethod
    def create_custom_sms(
        customer_name: str,
        message_content: str,
        include_branding: bool = True,
        include_opt_out: bool = True,
    ) -> str:
        """
        Create custom SMS message with optional branding.

        Args:
            customer_name: Name of the customer
            message_content: Main message content
            include_branding: Whether to include ARTVoice branding
            include_opt_out: Whether to include opt-out message

        Returns:
            SMS message text
        """
        if include_branding:
            message = f"ARTVoice Insurance\n\nHi {customer_name},\n\n{message_content}"
        else:
            message = f"Hi {customer_name},\n\n{message_content}"

        if include_opt_out:
            message += "\n\nReply STOP to opt out."

        return message

    @staticmethod
    def create_mfa_code_sms(otp_code: str, client_name: str, transaction_amount: float = 0) -> str:
        """
        Create MFA verification code SMS for financial services.

        Args:
            otp_code: 6-digit verification code
            client_name: Name of the client
            transaction_amount: Transaction amount if applicable

        Returns:
            SMS message text
        """
        if transaction_amount > 0:
            message = f"""🏛️ Financial Services

Hi {client_name},

Verification code: {otp_code}

Amount: ${transaction_amount:,.2f}
Expires: 5 minutes

If you didn't request this, contact us immediately.

Reply STOP to opt out."""
        else:
            message = f"""🏛️ Financial Services

Hi {client_name},

Your verification code: {otp_code}

This code expires in 5 minutes.

If you didn't request this, contact us immediately.

Reply STOP to opt out."""

        return message
